#!/usr/bin/env python3
"""
scripts/generate_test_dataset.py
=================================
Generates labeled benchmark dataset for evaluating document anomaly detection algorithms
(ELA pixel tampering, IsolationForest outliers, and Autoencoder reconstruction errors).
"""

import os
import cv2
import numpy as np
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

def generate_benchmark_dataset():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_dir = os.path.join(base_dir, 'data', 'benchmark_test')
    os.makedirs(test_dir, exist_ok=True)

    print(f"Generating benchmark test dataset in {test_dir}...")

    # 1. Genuine Clean Document Image
    img_clean = Image.new('RGB', (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img_clean)
    draw.rectangle([40, 40, 760, 560], outline=(37, 99, 235), width=3)
    draw.text((80, 80), "CENTRAL BOARD OF SECONDARY EDUCATION", fill=(15, 23, 42))
    draw.text((80, 140), "Name: SHIVANSH SAROHA", fill=(30, 41, 59))
    draw.text((80, 180), "Roll Number: 24CSU290", fill=(30, 41, 59))
    draw.text((80, 220), "Grade: A+ (Honours)", fill=(30, 41, 59))
    draw.ellipse([600, 420, 720, 540], outline=(5, 150, 105), width=3)
    draw.text((615, 475), "VERIFIED", fill=(5, 150, 105))
    
    clean_path = os.path.join(test_dir, 'genuine_marksheet.png')
    img_clean.save(clean_path)

    # 2. ELA Tampered Document Image
    img_tampered = img_clean.copy()
    draw_t = ImageDraw.Draw(img_tampered)
    draw_t.rectangle([75, 215, 300, 255], fill=(255, 255, 255))
    draw_t.text((80, 220), "Grade: S+ (FORGED)", fill=(220, 38, 38))
    
    patch = Image.new('RGB', (140, 140), color=(254, 242, 242))
    p_draw = ImageDraw.Draw(patch)
    p_draw.ellipse([10, 10, 130, 130], outline=(220, 38, 38), width=4)
    p_draw.text((25, 60), "FAKE STAMP", fill=(220, 38, 38))
    
    buf = cv2.imencode('.jpg', np.array(patch), [int(cv2.IMWRITE_JPEG_QUALITY), 30])[1]
    patch_degraded = Image.open(BytesIO(buf.tobytes()))
    img_tampered.paste(patch_degraded, (580, 410))
    
    tampered_path = os.path.join(test_dir, 'tampered_marksheet.png')
    img_tampered.save(tampered_path)

    # 3. Degraded Honest Scan
    buf_deg = cv2.imencode('.jpg', np.array(img_clean), [int(cv2.IMWRITE_JPEG_QUALITY), 65])[1]
    degraded_img = cv2.imdecode(buf_deg, cv2.IMREAD_COLOR)
    degraded_path = os.path.join(test_dir, 'degraded_honest_scan.jpg')
    cv2.imwrite(degraded_path, degraded_img)

    print(f"Benchmark test dataset created successfully:\n - {clean_path}\n - {tampered_path}\n - {degraded_path}")

if __name__ == '__main__':
    generate_benchmark_dataset()
