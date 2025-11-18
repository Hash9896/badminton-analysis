import re
import sys
from typing import List, Tuple

import pandas as pd


def extract_frame_ranges(ref_str: str) -> List[Tuple[int, int]]:
    if pd.isna(ref_str) or not isinstance(ref_str, str):
        return []
    # Find all [start-end] occurrences
    ranges = re.findall(r"\[(\d+)-(\d+)\]", ref_str)
    return [(int(s), int(e)) for s, e in ranges]


def choose_longest_rally_ranges(frame_refs_csv: str) -> List[Tuple[int, int]]:
    frames_df = pd.read_csv(frame_refs_csv)
    # Filter to rows that contain rally ranges
    candidates = frames_df[frames_df['insight_category'] == '03 Rally Length']
    best_ranges: List[Tuple[int, int]] = []

    for _, row in candidates.iterrows():
        row_ranges = extract_frame_ranges(row.get('frame_references', ''))
        if len(row_ranges) > len(best_ranges):
            best_ranges = row_ranges

    # Deduplicate while preserving order
    seen = set()
    unique_ranges: List[Tuple[int, int]] = []
    for rng in best_ranges:
        if rng not in seen:
            unique_ranges.append(rng)
            seen.add(rng)
    return unique_ranges


def apply_ranges_to_rallies(rally_csv: str, ranges: List[Tuple[int, int]]) -> None:
    df = pd.read_csv(rally_csv)

    # Ensure rally order by rally_id if present; otherwise keep existing order
    if 'rally_id' in df.columns:
        df = df.sort_values('rally_id', kind='stable').reset_index(drop=True)

    n = len(df)
    start_values: List[int] = []
    end_values: List[int] = []

    for i in range(n):
        if i < len(ranges):
            s, e = ranges[i]
            start_values.append(s)
            end_values.append(e)
        else:
            start_values.append('')
            end_values.append('')

    df['StartFrame'] = start_values
    df['EndFrame'] = end_values

    # Write back in-place
    df.to_csv(rally_csv, index=False)


def main():
    if len(sys.argv) < 3:
        print('Usage: python add_frames_to_rally_csv.py <rally_csv> <frame_references_csv>')
        sys.exit(1)

    rally_csv = sys.argv[1]
    frame_refs_csv = sys.argv[2]

    ranges = choose_longest_rally_ranges(frame_refs_csv)
    if not ranges:
        print('No rally frame ranges found in frame references CSV.')
        sys.exit(2)

    apply_ranges_to_rallies(rally_csv, ranges)
    print(f'Updated {rally_csv} with StartFrame/EndFrame for {min(len(ranges), len(pd.read_csv(rally_csv)))} rallies')


if __name__ == '__main__':
    main()


