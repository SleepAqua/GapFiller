from collections import Counter

class Rule:
    def __init__(self, cond: dict, action: dict):
        self.cond = cond
        self.action = action

    @classmethod
    def from_dict(cls, d):
        return cls(d.get('cond', {}), d.get('action', {}))

    def matches(self, state):
        # state: dict with keys: roll (1-3), dice (list), open_categories (set)
        r = self.cond
        if 'roll' in r:
            if isinstance(r['roll'], list):
                if state['roll'] not in r['roll']:
                    return False
            else:
                if state['roll'] != r['roll']:
                    return False
        if 'category_open' in r:
            cats = set(r['category_open'])
            if not (cats & state['open_categories']):
                return False
        if 'min_count_of_face' in r:
            face = r['min_count_of_face'].get('face')
            n = r['min_count_of_face'].get('count', 1)
            if state['dice'].count(face) < n:
                return False
        if 'min_most_common' in r:
            n = r['min_most_common']
            if max(Counter(state['dice']).values()) < n:
                return False
        return True

    def apply(self, state):
        # returns action dict if applied, else None
        if not self.matches(state):
            return None
        return self.action

class RuleEngine:
    def __init__(self, rules):
        # rules: list of Rule or dict
        self.rules = [r if isinstance(r, Rule) else Rule.from_dict(r) for r in rules]

    def decide_keep(self, state):
        # returns list of indices to keep (True/False mask)
        for r in self.rules:
            a = r.apply(state)
            if not a:
                continue
            if 'keep_values' in a:
                vals = set(a['keep_values'])
                return [d in vals for d in state['dice']]
            if a.get('keep_most_common'):
                from collections import Counter
                c = Counter(state['dice'])
                val, _ = c.most_common(1)[0]
                return [d == val for d in state['dice']]
        # default: keep nothing
        return [False] * len(state['dice'])

    def decide_score(self, state):
        # actions may include 'score_category'
        for r in self.rules:
            a = r.apply(state)
            if not a:
                continue
            if 'score_category' in a:
                return a['score_category']
        return None
