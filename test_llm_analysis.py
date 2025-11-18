#!/usr/bin/env python3
"""
Test script for the LLM-enhanced 12 Key Takeaways Generator

This script demonstrates the system without requiring an OpenAI API key.
It shows the data preparation and prompt structure.
"""

import os
import json
from generate_12_key_takeaways import BadmintonAnalysisGenerator

def test_without_llm():
    """Test the system without LLM calls to show data preparation."""
    print("=== Testing 12 Key Takeaways System (Data Preparation) ===")
    
    match_dir = "Akira_vs_Mithra_Semis_1"
    if not os.path.exists(match_dir):
        print(f"Match directory '{match_dir}' not found.")
        return
    
    # Create generator without API key (will show LLM error messages)
    generator = BadmintonAnalysisGenerator(match_dir)
    
    print("\n1. Testing data loading...")
    sr_summary = generator.load_csv_safely("sr_summary.csv")
    if sr_summary is not None:
        print(f"   ✓ Loaded sr_summary.csv: {len(sr_summary)} rows")
    else:
        print("   ✗ Could not load sr_summary.csv")
    
    shot_totals = generator.load_csv_safely("final_shot_totals.csv")
    if shot_totals is not None:
        print(f"   ✓ Loaded final_shot_totals.csv: {len(shot_totals)} rows")
    else:
        print("   ✗ Could not load final_shot_totals.csv")
    
    print("\n2. Testing data preparation for LLM...")
    
    # Test serve-receive data preparation
    if sr_summary is not None:
        data_summary = {
            "sr_summary": sr_summary.to_dict('records')[:5],  # Sample first 5 rows
            "sr_top_receives": []
        }
        print(f"   ✓ Prepared serve-receive data: {len(data_summary['sr_summary'])} sample rows")
    
    # Test shot totals data preparation
    if shot_totals is not None:
        data_summary = {
            "shot_totals": shot_totals.to_dict('records'),
            "shot_top3": []
        }
        print(f"   ✓ Prepared shot totals data: {len(data_summary['shot_totals'])} rows")
    
    print("\n3. Testing prompt structure...")
    
    # Show the exact prompt that would be sent to LLM
    system_prompt = generator.shared_guard_rails
    print(f"   ✓ System prompt length: {len(system_prompt)} characters")
    
    user_prompt = """Task: Summarize serve–receive patterns.

Inputs:
- sr_summary.csv with columns: Phase, Server, PatternServeShot, PatternReceiveShot, Count, PatternServeFrameExample{1..3}, PatternReceiveFrameExample{1..3}, ReceiveAvgEffectiveness.
- sr_top_receives.csv with columns: Server, PatternReceiveShot, Count, ReceiveAvgEffectiveness.

Instructions:
- Map P0→"you", P1→"opponent".
- Section title: "Serve Variation".
- Output ≤3 bullets per player (unless data strongly warrants one more).
- Cover:
  1) Server variation (per server): the serve shots that show up most; mention spread (pattern names; light on numbers).
  2) Top serve→receive pairs (overall and notable phases), highlighting most frequent and strongest/weakest receives by ReceiveAvgEffectiveness. Include frames by pairing serve/receive examples (as spans).
- Apply shared guard-rails and "no Mixed-focused observation".

Produce:
# Serve Variation
- (your bullets with frame spans)
---
- (opponent bullets with frame spans)"""
    
    print(f"   ✓ User prompt length: {len(user_prompt)} characters")
    
    print("\n4. Testing section generation (will show LLM error messages)...")
    
    # This will show the LLM error messages since no API key is provided
    print("   Generating Section 1: Serve-Receive...")
    result1 = generator.section_1_serve_receive()
    print(f"   Result preview: {result1[:100]}...")
    
    print("   Generating Section 2: Winning & Losing Shots...")
    result2 = generator.section_2_winning_losing_shots()
    print(f"   Result preview: {result2[:100]}...")
    
    print("\n=== Test Complete ===")
    print("\nTo use with actual LLM analysis:")
    print("1. Set your OpenAI API key: export OPENAI_API_KEY='your-key-here'")
    print("2. Or pass it as argument: python generate_12_key_takeaways.py --openai_api_key your-key-here")
    print("3. Run: python generate_12_key_takeaways.py --match_dir Akira_vs_Mithra_Semis_1")

if __name__ == "__main__":
    test_without_llm()

