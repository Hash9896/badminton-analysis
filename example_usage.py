#!/usr/bin/env python3
"""
Example usage of the 12 Key Takeaways Generator

This script demonstrates how to use the BadmintonAnalysisGenerator
to create comprehensive match analysis reports.
"""

from generate_12_key_takeaways import BadmintonAnalysisGenerator
import os

def main():
    # Example 1: Generate analysis for Akira vs Mithra match
    print("=== Example 1: Akira vs Mithra Analysis ===")
    
    match_dir = "Akira_vs_Mithra_Semis_1"
    output_dir = "example_output"
    
    if os.path.exists(match_dir):
        generator = BadmintonAnalysisGenerator(match_dir)
        sections = generator.generate_all_sections()
        generator.save_sections(sections, output_dir)
        print(f"Analysis complete! Check '{output_dir}' directory for results.")
    else:
        print(f"Match directory '{match_dir}' not found.")
    
    print("\n" + "="*50)
    
    # Example 2: Generate analysis for any match directory
    print("=== Example 2: Custom Match Analysis ===")
    
    # You can replace this with any match directory
    custom_match_dir = input("Enter path to match directory (or press Enter to skip): ").strip()
    
    if custom_match_dir and os.path.exists(custom_match_dir):
        custom_output_dir = f"{custom_match_dir}_analysis"
        generator = BadmintonAnalysisGenerator(custom_match_dir)
        sections = generator.generate_all_sections()
        generator.save_sections(sections, custom_output_dir)
        print(f"Analysis complete! Check '{custom_output_dir}' directory for results.")
    else:
        print("Skipping custom analysis.")
    
    print("\n" + "="*50)
    
    # Example 3: Show available sections
    print("=== Example 3: Available Analysis Sections ===")
    print("The system generates the following sections:")
    print("1. Serve-Receive Analysis")
    print("2. Winning & Losing Shots")
    print("3. Rally Momentum & Turning Points")
    print("4. Shot Effectiveness")
    print("5. Zones Analysis")
    print("6. Top-3s + Turning Points")
    print("7. Final 12 Key Takeaways")
    print("\nEach section is saved as a separate .md file,")
    print("plus a combined report with all sections.")

if __name__ == "__main__":
    main()

