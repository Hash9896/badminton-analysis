import json
from typing import Dict, Optional, Tuple, Any


def _strip_cross(shot: str) -> str:
    s = (shot or "").strip().lower()
    if s.endswith("_cross"):
        return s[:-6]
    return s


def _normalize_shot(shot: str) -> str:
    s = (shot or "").strip().lower()
    # Fix known typos present in some rule sets
    if s == "forehand_netkkeep":
        s = "forehand_netkeep"
    return s


class Rules:
    def __init__(self) -> None:
        self.exact_rules: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.base_rules: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def add_rule(self, attack_shot: str, response_shot: str, rule: Dict[str, Any]) -> None:
        a = _normalize_shot(attack_shot)
        b = _normalize_shot(response_shot)
        key = (a, b)
        self.exact_rules[key] = rule
        base_key = (_strip_cross(a), _strip_cross(b))
        # Only set base rule if not already set to keep first occurrence
        if base_key not in self.base_rules:
            self.base_rules[base_key] = rule

    def lookup(self, attack_shot: str, response_shot: str) -> Optional[Dict[str, Any]]:
        a = _normalize_shot(attack_shot)
        b = _normalize_shot(response_shot)
        # Exact first
        rule = self.exact_rules.get((a, b))
        if rule:
            return rule
        # Base (strip _cross) fallback
        return self.base_rules.get((_strip_cross(a), _strip_cross(b)))


def load_rules(path: str) -> Rules:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = Rules()
    sections = data.get("response_classifications", {})
    # Iterate over each list of rules in the classifications
    for _, rules_list in sections.items():
        if not isinstance(rules_list, list):
            continue
        for entry in rules_list:
            try:
                attack = entry.get("attack_shot")
                response = entry.get("response_shot")
                if not attack or not response:
                    continue
                # Basic validation and coercion
                rule = {
                    "pressure_level": str(entry.get("pressure_level", "neutral")),
                    "quality_score": float(entry.get("quality_score", 0.5)),
                    "tactical_meaning": str(entry.get("tactical_meaning", "undefined")),
                    "notes": str(entry.get("notes", "")),
                }
                # Clamp quality_score to [0,1]
                if rule["quality_score"] < 0.0:
                    rule["quality_score"] = 0.0
                if rule["quality_score"] > 1.0:
                    rule["quality_score"] = 1.0
                rules.add_rule(attack, response, rule)
            except Exception:
                # skip malformed rule entries; could log here if needed
                continue

    return rules


# ---------- Category helpers ----------

def load_shot_categories(path: str) -> Dict[str, str]:
    """Return mapping from normalized shot name -> category.
    Uses the "shot_categories" section of the JSON.
    Also maps base names with _cross stripped to the same category.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cats = data.get("shot_categories", {})
    shot_to_cat: Dict[str, str] = {}
    for cat, shots in cats.items():
        if not isinstance(shots, list):
            continue
        for s in shots:
            norm = _normalize_shot(s)
            shot_to_cat[norm] = cat
            base = _strip_cross(norm)
            if base not in shot_to_cat:
                shot_to_cat[base] = cat
    return shot_to_cat


def load_triple_category_rules(path: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Load start->end category q_end rules.
    Returns mapping: (first_category, second_category) -> { 'q_end': float, 'notes': str }
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entry in data.get("triple_category_rules", []):
        a = str(entry.get("first_category", "")).strip()
        b = str(entry.get("second_category", "")).strip()
        if not a or not b:
            continue
        q = float(entry.get("q_end", 0.5))
        if q < 0.0:
            q = 0.0
        if q > 1.0:
            q = 1.0
        out[(a, b)] = {"q_end": q, "notes": entry.get("notes", "")}
    return out


def classify_category(shot: str, shot_to_cat: Optional[Dict[str, str]]) -> str:
    """Classify a shot into a category using provided map; fallback by keywords."""
    s = _normalize_shot(shot)
    if shot_to_cat and (s in shot_to_cat or _strip_cross(s) in shot_to_cat):
        return shot_to_cat.get(s, shot_to_cat.get(_strip_cross(s), "unknown"))

    sl = s
    # Keyword fallback heuristics (coarse)
    if "smash" in sl:
        return "attacking_shots"
    if "defense" in sl:
        return "defensive_shots"
    if "nettap" in sl:
        return "net_kill"
    if "netkeep" in sl or "dribble" in sl:
        return "net_shots"
    if "drop" in sl:
        return "placement_shots"
    if "lift" in sl or "clear" in sl:
        return "reset_shots"
    if "drive" in sl or "flat" in sl or "push" in sl:
        return "pressure_shots"
    return "unknown"


