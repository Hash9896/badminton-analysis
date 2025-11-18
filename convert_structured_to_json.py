#!/usr/bin/env python3
"""
Convert structured_analysis.csv + LLM summary text to JSON format for frontend consumption.
Groups jump links by section/sub_section/pattern with all instances.
"""

import pandas as pd
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict


def parse_llm_summary(summary_text: str) -> Dict[str, Dict[str, str]]:
    """Parse LLM summary text into sections."""
    sections = {}
    
    # Section headers: ## 1. Opening Strategy, ## 2. Rally Dominance, etc.
    pattern = r'^##\s+(\d+)\.\s+(.+?)\s*$'
    
    lines = summary_text.split('\n')
    current_section = None
    current_text = []
    
    for line in lines:
        match = re.match(pattern, line)
        if match:
            # Save previous section
            if current_section:
                section_num = current_section['num']
                section_name = current_section['name']
                sections[section_num] = {
                    'section_id': section_num,
                    'section_name': section_name,
                    'summary': '\n'.join(current_text).strip()
                }
            
            # Start new section
            current_section = {'num': match.group(1), 'name': match.group(2)}
            current_text = []
        elif current_section:
            current_text.append(line)
    
    # Save last section
    if current_section:
        section_num = current_section['num']
        section_name = current_section['name']
        sections[section_num] = {
            'section_id': section_num,
            'section_name': section_name,
            'summary': '\n'.join(current_text).strip()
        }
    
    return sections


def to_int(value: Any) -> Optional[int]:
    """Safely convert to int, returning None if not possible."""
    if pd.isna(value) or value == '' or value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def build_jump_links(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build jump links grouped by section/sub_section/pattern."""
    # Filter out rows without start_frame
    df = df[df['start_frame'].notna()].copy()
    df = df[df['start_frame'] != ''].copy()
    
    # Group by section, sub_section, pattern
    sections_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for _, row in df.iterrows():
        section = str(row.get('section', '')).strip()
        if not section or not section[0].isdigit():
            continue
        
        section_num = section.split('.')[0]
        sub_section = str(row.get('sub_section', '')).strip() or 'General'
        
        # Use pattern_key if available, otherwise evidence_shots, otherwise sub_section
        pattern_key = str(row.get('pattern_key', '')).strip()
        if not pattern_key or pattern_key == 'nan':
            pattern_key = str(row.get('evidence_shots', '')).strip()
        if not pattern_key or pattern_key == 'nan':
            pattern_key = sub_section
        
        # Extract frame data
        start_frame = to_int(row.get('start_frame'))
        if start_frame is None:
            continue
        
        trigger_frame = to_int(row.get('trigger_frame'))
        
        # Build instance
        instance = {
            'start_frame': start_frame,
            'trigger_frame': trigger_frame,
            'rally_id': str(row.get('rally_id', '')).strip() or None,
            'actor': str(row.get('actor', '')).strip() or None,
            'evidence_shots': str(row.get('evidence_shots', '')).strip() or None,
        }
        
        sections_dict[section_num][sub_section][pattern_key].append(instance)
    
    # Convert to final structure
    result = defaultdict(list)
    
    for section_num in sorted(sections_dict.keys(), key=lambda x: int(x)):
        for sub_section in sorted(sections_dict[section_num].keys()):
            for pattern_key, instances in sections_dict[section_num][sub_section].items():
                # Create label from pattern_key
                label = pattern_key if len(pattern_key) <= 100 else pattern_key[:97] + '...'
                
                # Remove duplicates based on (start_frame, trigger_frame, rally_id)
                seen = set()
                unique_instances = []
                for inst in instances:
                    key = (inst['start_frame'], inst['trigger_frame'], inst['rally_id'])
                    if key not in seen:
                        seen.add(key)
                        unique_instances.append(inst)
                
                if unique_instances:
                    result[section_num].append({
                        'label': label,
                        'pattern_key': pattern_key,
                        'sub_section': sub_section,
                        'instances': unique_instances
                    })
    
    return dict(result)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: convert_structured_to_json.py <csv_path> <summary_text_path> [output_json_path]")
        sys.exit(1)
    
    csv_path = Path(sys.argv[1])
    summary_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else csv_path.parent / 'structured_analysis_summary.json'
    
    # Load CSV
    print(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows")
    
    # Load summary text
    print(f"Loading summary: {summary_path}")
    with open(summary_path, 'r', encoding='utf-8') as f:
        summary_text = f.read()
    
    # Parse summary
    sections_summary = parse_llm_summary(summary_text)
    print(f"Parsed {len(sections_summary)} sections from summary")
    
    # Build jump links
    print("Building jump links...")
    jump_links_by_section = build_jump_links(df)
    print(f"Built jump links for {len(jump_links_by_section)} sections")
    
    # Combine sections
    sections_list = []
    for section_num in sorted(sections_summary.keys(), key=lambda x: int(x)):
        section_data = sections_summary[section_num].copy()
        section_data['jump_links'] = jump_links_by_section.get(section_num, [])
        sections_list.append(section_data)
    
    # Build final JSON
    output_json = {
        'sections': sections_list
    }
    
    # Write output
    print(f"Writing JSON: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Complete! Wrote {len(sections_list)} sections with {sum(len(s['jump_links']) for s in sections_list)} jump link groups")


if __name__ == '__main__':
    main()

