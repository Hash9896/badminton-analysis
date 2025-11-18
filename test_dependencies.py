#!/usr/bin/env python3
"""Test if all dependencies are installed correctly."""

def test_imports():
    try:
        import tkinter as tk
        print("✅ tkinter: OK (built-in)")
    except ImportError as e:
        print(f"❌ tkinter: FAILED - {e}")
    
    try:
        import cv2
        print(f"✅ opencv-python: OK (version {cv2.__version__})")
    except ImportError as e:
        print(f"❌ opencv-python: FAILED - {e}")
    
    try:
        import pandas as pd
        print(f"✅ pandas: OK (version {pd.__version__})")
    except ImportError as e:
        print(f"❌ pandas: FAILED - {e}")
    
    try:
        import numpy as np
        print(f"✅ numpy: OK (version {np.__version__})")
    except ImportError as e:
        print(f"❌ numpy: FAILED - {e}")
    
    try:
        import matplotlib.pyplot as plt
        print(f"✅ matplotlib: OK")
    except ImportError as e:
        print(f"❌ matplotlib: FAILED - {e}")
    
    try:
        from PIL import Image
        print(f"✅ pillow: OK")
    except ImportError as e:
        print(f"❌ pillow: FAILED - {e}")

if __name__ == "__main__":
    print("🧪 Testing Badminton Video Analyzer Dependencies...")
    print("=" * 50)
    test_imports()
    print("=" * 50)
    print("If all show ✅, you're ready to run the app!")