import argparse
import json
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple


def normalize_text(text: str) -> str:
    """Normalize unicode and common whitespace anomalies for consistent parsing."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    # Replace non-breaking spaces and similar with regular spaces
    normalized = normalized.replace("\u00A0", " ")
    normalized = normalized.replace("\u2007", " ")
    normalized = normalized.replace("\u202F", " ")
    # Trim surrounding quotes if the whole blob is quoted
    normalized = normalized.strip()
    if len(normalized) >= 2 and ((normalized[0] == '"' and normalized[-1] == '"') or (normalized[0] == "'" and normalized[-1] == "'")):
        normalized = normalized[1:-1].strip()
    return normalized


SECTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*mandatory\s+observations\s*:?\s*$", re.IGNORECASE), "mandatory_observations"),
    (re.compile(r"^\s*things\s+that\s+worked\s*:?\s*$", re.IGNORECASE), "things_that_worked"),
    (
        re.compile(r"^\s*things\s+that\s+absolutely\s+didn[’']t\s+work\s*:?\s*$", re.IGNORECASE),
        "things_that_didnt_work",
    ),
    (re.compile(r"^\s*things\s+that\s+could\s+be\s+better\s*:?\s*$", re.IGNORECASE), "things_that_could_be_better"),
]


BULLET_RE = re.compile(r"^\s*[\*\-\u2022]\s+")


def classify_anchor(token: str) -> Dict[str, str]:
    """Classify an anchor token by type and normalize its value."""
    raw = token.strip()
    compact = re.sub(r"\s+", "", raw)

    # Frame range like 12953-12984 or 16857-17118
    if re.fullmatch(r"\d+\-\d+", compact):
        start_str, end_str = compact.split("-", 1)
        return {
            "type": "frame_range",
            "value": f"{int(start_str)}-{int(end_str)}",
            "raw": raw,
        }

    # Rally identifier like G1-R5-F14680 (case-insensitive, with optional spaces around dashes)
    if re.fullmatch(r"(?i)g\d+\-r\d+\-f\d+", compact):
        parts = compact.upper().split("-")
        return {
            "type": "rally_id",
            "game": int(parts[0][1:]),
            "rally": int(parts[1][1:]),
            "frame": int(parts[2][1:]),
            "value": f"{parts[0]}-{parts[1]}-{parts[2]}",
            "raw": raw,
        }

    return {"type": "unknown", "value": raw, "raw": raw}


def extract_anchor_groups(bullet_text: str) -> Tuple[List[Dict[str, str]], List[List[Dict[str, str]]]]:
    """Extract anchors from any parenthetical groups in the bullet.

    Returns a flat list of anchors and a list of anchor groups (split by 'vs').
    """
    anchors: List[Dict[str, str]] = []
    groups: List[List[Dict[str, str]]] = []

    # Find content inside parentheses and parse tokens
    for inner in re.findall(r"\(([^)]*)\)", bullet_text):
        # Split on 'vs' boundaries to preserve comparison groupings
        vs_splits = re.split(r"\s+vs\.??\s+", inner, flags=re.IGNORECASE)
        for segment in vs_splits:
            tokens = [t.strip() for t in segment.split(",") if t.strip()]
            classified_segment = [classify_anchor(t) for t in tokens]
            if classified_segment:
                groups.append(classified_segment)
                anchors.extend(classified_segment)

    # Deduplicate anchors by (type, value)
    seen = set()
    deduped: List[Dict[str, str]] = []
    for a in anchors:
        key = (a.get("type", ""), str(a.get("value", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)

    return deduped, groups


def parse_bullets_from_section(lines: List[str], start_idx: int) -> Tuple[List[Dict[str, object]], int]:
    """Starting at start_idx (after a heading), parse consecutive bullets into items.

    Returns (items, next_index_after_section).
    """
    items: List[Dict[str, object]] = []
    i = start_idx
    current_bullet_lines: Optional[List[str]] = None

    def flush_current():
        if not current_bullet_lines:
            return
        bullet_text = " ".join(s.strip() for s in current_bullet_lines).strip()
        anchors, anchor_groups = extract_anchor_groups(bullet_text)
        items.append({
            "statement": bullet_text,
            "anchors": anchors,
            "anchor_groups": anchor_groups,
        })

    while i < len(lines):
        line = lines[i]
        if any(pat.match(line) for pat, _ in SECTION_PATTERNS):
            # Next heading encountered, end of this section
            break
        if not line.strip():
            # Blank line ends current bullet but stays in section
            flush_current()
            current_bullet_lines = None
            i += 1
            continue
        if BULLET_RE.match(line):
            # Start a new bullet
            flush_current()
            current_bullet_lines = [BULLET_RE.sub("", line, count=1)]
        else:
            # Continuation of the current bullet if any, otherwise ignore stray text
            if current_bullet_lines is not None:
                current_bullet_lines.append(line)
        i += 1

    # Flush the last bullet in the section
    flush_current()
    return items, i


def parse_summary_to_json(text: str) -> Dict[str, object]:
    """Parse a free-form LLM summary into a structured JSON-friendly dictionary."""
    normalized = normalize_text(text)
    lines = [ln.rstrip() for ln in normalized.splitlines()]

    result: Dict[str, object] = {
        "mandatory_observations": [],
        "things_that_worked": [],
        "things_that_didnt_work": [],
        "things_that_could_be_better": [],
        "_meta": {"source_length": len(text)},
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        matched_key: Optional[str] = None
        for pat, key in SECTION_PATTERNS:
            if pat.match(line):
                matched_key = key
                i += 1
                break

        if matched_key is None:
            i += 1
            continue

        items, next_i = parse_bullets_from_section(lines, i)
        result[matched_key] = items
        i = next_i

    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert LLM match summary text into structured JSON for frontend consumption.",
    )
    parser.add_argument("--in", dest="input_file", help="Path to input text file. If omitted, read from stdin.")
    parser.add_argument("--out", dest="output_file", help="Path to output JSON file. If omitted, write to stdout.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indentation.",
    )
    args = parser.parse_args(argv)

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    parsed = parse_summary_to_json(text)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2 if args.pretty else None)
    else:
        json.dump(parsed, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
        if args.pretty:
            sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


