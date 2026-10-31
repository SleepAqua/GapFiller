package com.example.yahtzee

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlin.random.Random

@Serializable
data class RuleCond(
    val roll: List<Int>? = null,
    val category_open: List<String>? = null,
    val min_count_of_face: Map<String, Int>? = null,
    val min_most_common: Int? = null
)

@Serializable
data class RuleAction(
    val keep_values: List<Int>? = null,
    val keep_most_common: Boolean? = null,
    val score_category: String? = null
)

@Serializable
data class Rule(val cond: RuleCond? = null, val action: RuleAction? = null)

class Strategy(val name: String, val rules: List<Rule>) {
    fun takeTurn(openCategories: MutableList<String>): Pair<Int, String> {
        var dice = List(5) { Random.nextInt(1,7) }
        for (rollNum in 1..3) {
            val stateDice = dice
            if (rollNum < 3) {
                val keepMask = decideKeep(rollNum, stateDice, openCategories)
                dice = List(5) { i -> if (keepMask[i]) stateDice[i] else Random.nextInt(1,7) }
            } else {
                val scoreChoice = decideScore(rollNum, stateDice, openCategories)
                if (scoreChoice != null && openCategories.contains(scoreChoice)) {
                    return Pair(scoreCategory(scoreChoice, stateDice), scoreChoice)
                }
                val (bestCat, bestSc) = bestCategoryScore(stateDice, openCategories)
                return Pair(bestSc, bestCat)
            }
        }
        val (bc, bs) = bestCategoryScore(dice, openCategories)
        return Pair(bs, bc)
    }

    private fun decideKeep(roll: Int, dice: List<Int>, openCategories: List<String>): List<Boolean> {
        for (r in rules) {
            val c = r.cond ?: continue
            if (c.roll != null && !c.roll.contains(roll)) continue
            if (c.category_open != null && c.category_open.none { openCategories.contains(it) }) continue
            if (c.min_count_of_face != null) {
                val face = c.min_count_of_face["face"] ?: 0
                val cnt = c.min_count_of_face["count"] ?: 0
                if (dice.count { it == face } < cnt) continue
            }
            if (c.min_most_common != null) {
                val mc = dice.groupingBy { it }.eachCount().values.maxOrNull() ?: 0
                if (mc < c.min_most_common) continue
            }
            val a = r.action ?: continue
            if (a.keep_values != null) {
                val vals = a.keep_values.toSet()
                return dice.map { vals.contains(it) }
            }
            if (a.keep_most_common == true) {
                val freq = dice.groupingBy { it }.eachCount()
                val most = freq.maxByOrNull { it.value }?.key ?: dice[0]
                return dice.map { it == most }
            }
        }
        return List(dice.size) { false }
    }

    private fun decideScore(roll: Int, dice: List<Int>, openCategories: List<String>): String? {
        for (r in rules) {
            val c = r.cond ?: continue
            if (c.roll != null && !c.roll.contains(roll)) continue
            val a = r.action ?: continue
            if (a.score_category != null) return a.score_category
        }
        return null
    }

    private fun bestCategoryScore(dice: List<Int>, open: List<String>): Pair<String, Int> {
        var bestCat = ""
        var best = -1
        for (c in open) {
            val sc = scoreCategory(c, dice)
            if (sc > best) { best = sc; bestCat = c }
        }
        return Pair(bestCat, best)
    }

    private fun scoreCategory(category: String, dice: List<Int>): Int {
        return when (category.lowercase()) {
            "ones" -> dice.filter { it==1 }.sum()
            "twos" -> dice.filter { it==2 }.sum()
            "threes" -> dice.filter { it==3 }.sum()
            "fours" -> dice.filter { it==4 }.sum()
            "fives" -> dice.filter { it==5 }.sum()
            "sixes" -> dice.filter { it==6 }.sum()
            "three_kind" -> if (dice.groupingBy { it }.eachCount().values.maxOrNull() ?: 0 >= 3) dice.sum() else 0
            "four_kind" -> if (dice.groupingBy { it }.eachCount().values.maxOrNull() ?: 0 >= 4) dice.sum() else 0
            "full_house" -> {
                val vals = dice.groupingBy { it }.eachCount().values.sorted()
                if (vals == listOf(2,3)) 25 else 0
            }
            "small_straight" -> {
                val s = dice.toSet()
                if (setOf(1,2,3,4).all { s.contains(it) } || setOf(2,3,4,5).all { s.contains(it) } || setOf(3,4,5,6).all { s.contains(it) }) 30 else 0
            }
            "large_straight" -> {
                val s = dice.toSet()
                if (s == setOf(1,2,3,4,5) || s == setOf(2,3,4,5,6)) 40 else 0
            }
            "yahtzee" -> if (dice.toSet().size == 1) 50 else 0
            "chance" -> dice.sum()
            else -> 0
        }
    }

}

fun parseStrategies(jsonText: String): List<Strategy> {
    val map = Json.decodeFromString<Map<String, List<Rule>>>(jsonText)
    return map.map { Strategy(it.key, it.value) }
}

fun validateStrategiesJson(jsonText: String): Pair<Boolean, String> {
    return try {
        val parsed = Json.decodeFromString<Map<String, List<Rule>>>(jsonText)
        if (parsed.isEmpty()) Pair(false, "No strategies found") else Pair(true, "OK")
    } catch (e: Exception) {
        Pair(false, e.message ?: "Invalid JSON")
    }
}

fun simulateStream(strategies: List<Strategy>, nGames: Int, chunk: Int = 1000): Flow<Pair<Int, Map<String, Double>>> = flow {
    val chunks = (nGames + chunk - 1) / chunk
    val cumulative = strategies.associate { it.name to 0.0 }.toMutableMap()
    val counts = strategies.associate { it.name to 0 }.toMutableMap()
    for (c in 0 until chunks) {
        val toRun = minOf(chunk, nGames - c*chunk)
        // run each strategy's chunk in parallel to utilize multiple cores
        val results = coroutineScope {
            strategies.map { s ->
                async {
                    var total = 0
                    repeat(toRun) {
                        val open = YahtzeeData.ALL_CATEGORIES.toMutableList()
                        var gameScore = 0
                        repeat(13) {
                            val (sc, cat) = s.takeTurn(open)
                            gameScore += sc
                            open.remove(cat)
                        }
                        total += gameScore
                    }
                    Pair(s.name, total)
                }
            }.awaitAll()
        }

        for ((name, total) in results) {
            cumulative[name] = cumulative[name]!! + total
            counts[name] = counts[name]!! + toRun
        }

        val snapshot = cumulative.mapValues { (k, v) -> v / counts[k]!! }
        emit(Pair(c, snapshot))
        // small delay so UI can animate
        delay(50)
    }
}

object YahtzeeData {
    val ALL_CATEGORIES = listOf("ones","twos","threes","fours","fives","sixes",
        "three_kind","four_kind","full_house","small_straight","large_straight","yahtzee","chance")
}
