import random
from collections import Counter

FACE_RANGE = range(1, 7)

def roll(n=5):
    return [random.randint(1, 6) for _ in range(n)]

def score_upper(dice, face):
    return sum(d for d in dice if d == face)

def three_of_a_kind(dice):
    c = Counter(dice)
    if max(c.values()) >= 3:
        return sum(dice)
    return 0

def four_of_a_kind(dice):
    c = Counter(dice)
    if max(c.values()) >= 4:
        return sum(dice)
    return 0

def full_house(dice):
    c = Counter(dice)
    vals = sorted(c.values())
    return 25 if vals == [2, 3] else 0

def small_straight(dice):
    s = set(dice)
    straights = [set([1,2,3,4]), set([2,3,4,5]), set([3,4,5,6])]
    for st in straights:
        if st.issubset(s):
            return 30
    return 0

def large_straight(dice):
    s = set(dice)
    if s == set([1,2,3,4,5]) or s == set([2,3,4,5,6]):
        return 40
    return 0

def yahtzee(dice):
    return 50 if len(set(dice)) == 1 else 0

def chance(dice):
    return sum(dice)

def score_category(category, dice):
    cat = category.lower()
    if cat in ['ones','twos','threes','fours','fives','sixes']:
        face = ['ones','twos','threes','fours','fives','sixes'].index(cat) + 1
        return score_upper(dice, face)
    if cat == 'three_kind':
        return three_of_a_kind(dice)
    if cat == 'four_kind':
        return four_of_a_kind(dice)
    if cat == 'full_house':
        return full_house(dice)
    if cat == 'small_straight':
        return small_straight(dice)
    if cat == 'large_straight':
        return large_straight(dice)
    if cat == 'yahtzee':
        return yahtzee(dice)
    if cat == 'chance':
        return chance(dice)
    raise ValueError(f'Unknown category: {category}')

ALL_CATEGORIES = ['ones','twos','threes','fours','fives','sixes',
                  'three_kind','four_kind','full_house',
                  'small_straight','large_straight','yahtzee','chance']

def best_category_score(dice, open_categories):
    best_cat = None
    best_score = -1
    for c in open_categories:
        sc = score_category(c, dice)
        if sc > best_score:
            best_score = sc
            best_cat = c
    return best_cat, best_score
