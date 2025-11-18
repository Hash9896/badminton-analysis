"""
Convert tempo analysis CSV to CVAT XML format (image tagging format).
Matches the structure of AKANE_YAMAGUCHI.xml sample.
"""

import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime


def format_frame_filename(frame_number: int) -> str:
    """Format frame number as filename (e.g., 7922 -> frame_007922.jpg)"""
    return f"frame_{frame_number:06d}.jpg"


def convert_tempo_csv_to_cvat_xml(
    csv_path: str,
    output_path: str,
    task_name: str = "Badminton Tempo Analysis",
    image_width: int = 1920,
    image_height: int = 1080
):
    """
    Convert tempo analysis CSV to CVAT XML format.
    
    Args:
        csv_path: Path to input CSV file
        output_path: Path to output XML file
        task_name: Name for the CVAT task
        image_width: Image width (default 1920)
        image_height: Image height (default 1080)
    """
    # Load CSV
    df = pd.read_csv(csv_path)
    
    print(f"Loaded {len(df)} rows from CSV")
    
    # Filter for rows with shot_height_category (not null/empty)
    df = df[
        df['FrameNumber'].notna() & 
        df['shot_height_category'].notna() &
        (df['shot_height_category'] != '')
    ].copy()
    print(f"After filtering: {len(df)} rows with valid FrameNumber and shot_height_category")
    
    # Get unique shot_height_categories for labels
    unique_categories = sorted(df['shot_height_category'].dropna().unique())
    print(f"Found {len(unique_categories)} unique shot height categories: {unique_categories}")
    
    # Start building XML
    annotations = ET.Element("annotations")
    
    # Add version
    version = ET.SubElement(annotations, "version")
    version.text = "1.1"
    
    # Meta section
    meta = ET.SubElement(annotations, "meta")
    task = ET.SubElement(meta, "task")
    
    ET.SubElement(task, "id").text = "1"
    ET.SubElement(task, "name").text = task_name
    ET.SubElement(task, "size").text = str(len(df))
    ET.SubElement(task, "mode").text = "annotation"  # Image tagging mode
    ET.SubElement(task, "overlap").text = "0"
    ET.SubElement(task, "bugtracker")
    
    # Created/Updated timestamps
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    ET.SubElement(task, "created").text = now
    ET.SubElement(task, "updated").text = now
    
    # Labels section
    labels = ET.SubElement(task, "labels")
    for category in unique_categories:
        label_tag = ET.SubElement(labels, "label")
        ET.SubElement(label_tag, "name").text = category
        ET.SubElement(label_tag, "attributes")
    
    # Owner section
    owner = ET.SubElement(task, "owner")
    ET.SubElement(owner, "username").text = "admin"
    ET.SubElement(owner, "email")
    
    # Dumped timestamp
    ET.SubElement(meta, "dumped").text = now
    
    # Create image elements - one per row
    # Sort by FrameNumber to ensure consistent ordering
    df_sorted = df.sort_values('FrameNumber').reset_index(drop=True)
    
    image_id = 1
    for idx, row in df_sorted.iterrows():
        frame_num = int(row['FrameNumber'])
        category = str(row['shot_height_category']).strip()
        
        if pd.isna(category) or category == '':
            continue
        
        # Create image element
        image = ET.SubElement(
            annotations,
            "image",
            id=str(image_id),
            name=format_frame_filename(frame_num),
            width=str(image_width),
            height=str(image_height)
        )
        
        # Add tag with shot_height_category label
        tag = ET.SubElement(image, "tag")
        tag.set("label", category)
        
        image_id += 1
    
    # Write XML with proper formatting
    tree = ET.ElementTree(annotations)
    ET.indent(tree, space="  ")  # Pretty print with 2-space indent
    
    tree.write(
        output_path,
        encoding='utf-8',
        xml_declaration=True
    )
    
    print(f"✅ CVAT XML saved to {output_path}")
    print(f"   Total images: {image_id - 1}")
    print(f"   Unique labels: {len(unique_categories)}")


def main():
    """Main function"""
    # Input CSV
    csv_path = "tara/devika/2/QRsUgVlibBU_tempo_analysis_new.csv"
    
    # Output XML
    output_path = "tara/devika/2/QRsUgVlibBU_tempo_analysis_cvat.xml"
    
    # Task name
    task_name = "Badminton Shot Height Category - QRsUgVlibBU"
    
    convert_tempo_csv_to_cvat_xml(
        csv_path=csv_path,
        output_path=output_path,
        task_name=task_name
    )


if __name__ == "__main__":
    main()

