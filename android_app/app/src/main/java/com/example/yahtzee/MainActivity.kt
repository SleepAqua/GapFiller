package com.example.yahtzee

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.Button
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Surface
import androidx.compose.material.Text
import androidx.compose.material.TextField
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    SimulatorUI()
                }
            }
        }
    }
}

@Composable
fun SimulatorUI() {
    var jsonText by remember { mutableStateOf(defaultStrategiesJson()) }
    var running by remember { mutableStateOf(false) }
    var snapshot by remember { mutableStateOf<Map<String, Double>>(emptyMap()) }
    val scope = rememberCoroutineScope()
    var simJob by remember { mutableStateOf<Job?>(null) }
    var filename by remember { mutableStateOf("my_strategy.json") }
    var validationMsg by remember { mutableStateOf<String?>(null) }

    Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
        Text("Strategies (JSON):")
        TextField(value = jsonText, onValueChange = { jsonText = it }, modifier = Modifier.height(160.dp).fillMaxWidth())
        Row(modifier = Modifier.padding(top = 8.dp)) {
            Button(onClick = {
                if (!running) {
                    // validate first
                    val (ok, msg) = validateStrategiesJson(jsonText)
                    validationMsg = msg
                    if (!ok) return@Button
                    running = true
                    val strategies = try { parseStrategies(jsonText) } catch (e: Exception) { emptyList<Strategy>() }
                    simJob = scope.launch(Dispatchers.Default) {
                        simulateStream(strategies, nGames = 200000, chunk = 5000).collect { (_, snap) ->
                            snapshot = snap
                        }
                        running = false
                    }
                } else {
                    simJob?.cancel(); running = false
                }
            }) { Text(if (!running) "Start" else "Stop") }
            Spacer(Modifier.width(8.dp))
            Button(onClick = { jsonText = defaultStrategiesJson() }) { Text("Load Presets") }
                Spacer(Modifier.width(8.dp))
                Button(onClick = {
                    // save to internal file
                    try {
                        val file = androidx.compose.ui.platform.LocalContext.current.filesDir
                        val out = java.io.File(file, filename)
                        out.writeText(jsonText)
                        validationMsg = "Saved to ${out.absolutePath}"
                    } catch (e: Exception) { validationMsg = "Save failed: ${e.message}" }
                }) { Text("Save") }
                Spacer(Modifier.width(8.dp))
                Button(onClick = {
                    try {
                        val file = androidx.compose.ui.platform.LocalContext.current.filesDir
                        val inFile = java.io.File(file, filename)
                        if (inFile.exists()) {
                            jsonText = inFile.readText()
                            validationMsg = "Loaded ${inFile.absolutePath}"
                        } else validationMsg = "File not found"
                    } catch (e: Exception) { validationMsg = "Load failed: ${e.message}" }
                }) { Text("Load") }
        }

            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Filename:")
                Spacer(Modifier.width(8.dp))
                TextField(value = filename, onValueChange = { filename = it }, modifier = Modifier.width(220.dp))
            }
            validationMsg?.let { Text(it, color = Color.Red) }

        Spacer(Modifier.height(12.dp))
        LiveBarChart(snapshot)
    }
}

@Composable
fun LiveBarChart(snapshot: Map<String, Double>) {
    val sorted = snapshot.toList().sortedByDescending { it.second }
    Column(modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
        for ((name, value) in sorted) {
            BarRow(name, value)
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
fun BarRow(name: String, value: Double) {
    val animated = animateFloatAsState(targetValue = (value/600f).toFloat())
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(name, modifier = Modifier.width(120.dp))
        Box(modifier = Modifier
            .height(24.dp)
            .fillMaxWidth()
            .background(Color.LightGray)) {
            Box(modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(animated.value)
                .background(Color(0xFF4CAF50)))
        }
        Spacer(Modifier.width(8.dp))
        Text(String.format("%.1f", value))
    }
}

fun defaultStrategiesJson(): String = """
{
  "random": [
    { "cond": { "roll": [1,2,3] }, "action": { "keep_values": [] } },
    { "cond": { "roll": 3 }, "action": { "score_category": "chance" } }
  ],
  "chase_yahtzee": [
    { "cond": { "roll": [1,2] , "min_most_common": 2 }, "action": { "keep_most_common": true } },
    { "cond": { "roll": 3 }, "action": { "score_category": "yahtzee" } }
  ],
  "heuristic_benchmark": [
    { "cond": { "roll": [1,2], "min_most_common": 3 }, "action": { "keep_most_common": true } },
    { "cond": { "roll": [1,2], "min_most_common": 2 }, "action": { "keep_most_common": true } },
    { "cond": { "roll": 3 }, "action": { "score_category": "full_house" } }
  ]
}
"""
