#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/harshitagarwal/Downloads/Match_analysis_engine_app"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python venv not found at $PYTHON"
  echo "Create it with: python3 -m venv .venv && ./.venv/bin/pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org numpy pandas scipy"
  exit 1
fi

DIR="$ROOT/harshan"
fps_default=30

echo "=== Processing: $DIR ==="

detailed_csv="$(ls "$DIR"/*_detailed.csv 2>/dev/null | head -n1 || true)"
eff_csv="$(ls "$DIR"/*_detailed_effectiveness.csv 2>/dev/null | head -n1 || true)"
narr_csv="$(ls "$DIR"/rally_narratives_enriched*.csv 2>/dev/null | head -n1 || true)"

if [[ -z "${detailed_csv}" || -z "${eff_csv}" ]]; then
  echo "Missing *_detailed.csv or *_detailed_effectiveness.csv in $DIR"; exit 1
fi

# Ensure effectiveness CSV has a Phase column for scripts that expect it
eff_aug_output=$("$PYTHON" - "$eff_csv" <<'PY'
import pandas as pd
import sys
from pathlib import Path

src = Path(sys.argv[1])
df = pd.read_csv(src)
if "Phase" in df.columns:
    print("")  # indicator: no change needed
    sys.exit(0)

if "PhaseDetail" in df.columns:
    df["Phase"] = df["PhaseDetail"].fillna("Unknown")
else:
    df["Phase"] = "Unknown"

dst = src.with_name(src.stem + "_with_phase.csv")
df.to_csv(dst, index=False)
print(str(dst))
PY
)
if [[ -n "$eff_aug_output" ]]; then
  eff_aug="$eff_aug_output"
  echo "Added fallback Phase column -> $(basename "$eff_aug")"
else
  eff_aug="$eff_csv"
fi

prefix="${detailed_csv%_detailed.csv}"
cons_out="${prefix}_consolidated_with_eff.csv"
rn_with_shots="$DIR/rally_narratives_enriched_with_shots.csv"
struct_csv="$DIR/structured_analysis.csv"
struct_summary_txt="$DIR/structured_analysis_summary.txt"
struct_summary_json="$DIR/structured_analysis_summary.json"

"$PYTHON" "$ROOT/build_tempo_analysis.py" "$detailed_csv" --fps "$fps_default" --effectiveness-csv "$eff_aug" || true
"$PYTHON" "$ROOT/build_rally_timeseries.py" "$eff_aug" --fps "$fps_default" || true

if [[ -n "$narr_csv" ]]; then
  "$PYTHON" "$ROOT/consolidated_analysis.py" \
    --input "$detailed_csv" \
    --output "$cons_out" \
    --effectiveness "$eff_aug" \
    --include-shot-timeline \
    --add-shot-variation \
    --shot-variation-by-phase \
    --rally-narratives "$narr_csv"
else
  "$PYTHON" "$ROOT/consolidated_analysis.py" \
    --input "$detailed_csv" \
    --output "$cons_out" \
    --effectiveness "$eff_aug" \
    --include-shot-timeline \
    --add-shot-variation \
    --shot-variation-by-phase
fi

if [[ -n "$narr_csv" ]]; then
  "$PYTHON" "$ROOT/generate_topic_csvs.py" --input "$cons_out" --outdir "$DIR" --rally-narratives "$narr_csv"
else
  "$PYTHON" "$ROOT/generate_topic_csvs.py" --input "$cons_out" --outdir "$DIR"
fi

"$PYTHON" "$ROOT/generate_important_insights.py" --indir "$DIR" --output "$DIR/important_insights.csv"
"$PYTHON" "$ROOT/badminton_analyzer_refined.py" --input "$eff_aug" --output "$DIR/refined_outputs"

if [[ -n "$narr_csv" ]]; then
  if [[ ! -f "$rn_with_shots" ]]; then
    "$PYTHON" "$ROOT/rally_dynamics_with_shots.py" "$eff_aug" "$narr_csv" "$rn_with_shots"
  fi
  "$PYTHON" "$ROOT/build_structured_analysis.py" "$rn_with_shots" "$eff_csv" "$struct_csv"
  if [[ -f "$struct_summary_txt" ]]; then
    "$PYTHON" "$ROOT/convert_structured_to_json.py" "$struct_csv" "$struct_summary_txt" "$struct_summary_json"
  else
    echo "Note: $struct_summary_txt not found; skipping structured_analysis_summary.json"
  fi
else
  echo "Note: No rally_narratives_enriched*.csv in $DIR; skipping structured analysis."
fi

echo "✓ Completed: $DIR"
echo "All done."

