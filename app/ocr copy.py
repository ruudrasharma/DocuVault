import re
from PIL import Image
import io
import numpy as np
import cv2
import pytesseract
import fitz  # PyMuPDF
import logging
import sys

# Path to Tesseract (update based on your system configuration)
pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'  # Example for macOS Homebrew; adjust as necessary

# Configure logging for debugging purposes
logging.basicConfig(filename='ocr_debug.log', level=logging.INFO, format='%(message)s')

def deskew(image):
    """Deskew the image to correct skew for better OCR."""
    coords = np.column_stack(np.where(image == 0))  # Find text pixels (assuming black text on white background)
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return rotated

def image_smoothening(img):
    """Apply smoothening to enhance OCR readability."""
    ret1, th1 = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    ret2, th2 = cv2.threshold(th1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    blur = cv2.GaussianBlur(th2, (1, 1), 0)
    ret3, th3 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th3

def preprocess_image(image_path):
    """
    Applies enhanced preprocessing to handle noisy scanned documents, rendering PDFs at high resolution.
    """
    if image_path.lower().endswith('.pdf'):
        doc = fitz.open(image_path)
        page = doc[0]
        mat = fitz.Matrix(8, 8)  # High resolution (800%) for improved OCR accuracy
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("ppm")
        img = Image.open(io.BytesIO(img_data))
        doc.close()
    else:
        img = Image.open(image_path)
    
    # Convert to OpenCV format
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    
    # Grayscale conversion
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Noise reduction with bilateral filter
    filtered = cv2.bilateralFilter(gray, 11, 17, 17)
    
    # Apply Gaussian blur for additional smoothing
    filtered = cv2.GaussianBlur(filtered, (3, 3), 0)
    
    # Otsu's thresholding for binarization
    thresh = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Morphological operations: opening to remove noise, closing to connect text
    kernel = np.ones((2, 2), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # Smoothening and bitwise or
    smooth = image_smoothening(gray)
    processed = cv2.bitwise_or(closing, smooth)
    
    # Deskew the image
    processed = deskew(processed)
    
    logging.info(f"Preprocessed image shape: {processed.shape}")
    return processed

def extract_fields(file_path):
    """
    Performs OCR on a CBSE class 10 marksheet (scanned PDF or image) and extracts details into a dictionary.
    
    :param file_path: Path to the PDF or image file.
    :return: Dictionary of extracted details in the specified format.
    """
    processed_image = preprocess_image(file_path)
    
    # Test multiple OCR configurations for optimal text extraction
    configs = [
        r'--oem 3 --psm 6 -l eng',
        r'--oem 3 --psm 4 -l eng',
        r'--oem 3 --psm 3 -l eng',
        r'--oem 3 --psm 1 -l eng',
        r'--oem 1 --psm 6 -l eng'
    ]
    
    best_text = ""
    for config in configs:
        text = pytesseract.image_to_string(processed_image, config=config)
        if len(text.strip()) > len(best_text.strip()):
            best_text = text
    
    text = best_text
    print("Full Raw OCR Text:\n", repr(text))  # For debugging; can be removed in production
    logging.info(f"Full Raw OCR text: {repr(text)}")
    
    lines = [re.sub(r'\s+', ' ', line.strip()) for line in text.split('\n') if line.strip()]
    full_text = ' '.join(lines)
    
    result = {
        "regn_no": "Unknown",
        "name": "Unknown",
        "roll_no": "Unknown",
        "fathers_guardians_name": "Unknown",
        "date_of_birth": "Unknown",
        "date_of_birth_descriptive": "Unknown",
        "school": "Unknown",
        "marks": {}
    }
    
    # Extract registration number
    regn_patterns = [
        r'Regn\.?No\.?\s*[:\-—]?\s*([A-Z0-9/]+)',
        r'Registration\s*No\.?\s*[:\-—]?\s*([A-Z0-9/]+)',
        r'Regn\s*No\.?\s*[:\-—]?\s*([A-Z0-9/]+)',
        r'Ragin\.\s*[:\-—]?\s*([A-Z0-9/]+)'
    ]
    for pattern in regn_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["regn_no"] = match.group(1).strip().upper()
            break
    
    # Extract name
    name_patterns = [
        r'(?i)certify that\s+([A-Z\s]+?)(?=\s+Roll|Mother|Father|Date|School|$)',
        r'(?i)this is to certify that\s+([A-Z\s]+?)(?=\s+Roll|Mother|Father|Date|School|$)',
        r'(?i)this ts to certiry that\s+([A-Z\s]+?)(?=\s+Roll|Mother|Father|Date|School|$)'
    ]
    for pattern in name_patterns:
        match = re.search(pattern, full_text)
        if match:
            name = re.sub(r'[^A-Z\s]', '', match.group(1)).strip().upper()
            result["name"] = re.sub(r'\s+', ' ', name)
            break
    
    # Extract roll number
    roll_patterns = [
        r'Roll No\.?\s*[:\-]?\s*(\d+)',
        r'Roll\s*[:\-]?\s*(\d+)',
        r'Roll Number\s*[:\-]?\s*(\d+)',
        r'Roll-No\..\s*(\d+)',
        r'© Roll No\s*(\d+)'
    ]
    for pattern in roll_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["roll_no"] = match.group(1).strip()
            break
    
    # Extract father's/guardian's name
    father_patterns = [
        r"(?i)Father’s / Guardian’s Name\s*[:\-—]?\s*([A-Z\s]+)",
        r"(?i)Father's/Guardian's Name\s*[:\-—]?\s*([A-Z\s]+)",
        r"(?i)Father’s \( Guardtan’s Name\s*([A-Z\s]+)"
    ]
    for pattern in father_patterns:
        match = re.search(pattern, full_text)
        if match:
            father = re.sub(r'[^A-Z\s]', '', match.group(1)).strip().upper()
            result["fathers_guardians_name"] = re.sub(r'\s+', ' ', father)
            break
    
    # Extract date of birth (numeric)
    dob_patterns = [
        r'Date of Birth\s*[:\-]?\s*(\d{2}-\d{2}-\d{4})',
        r'DOB\s*[:\-]?\s*(\d{2}-\d{2}-\d{4})',
        r'Birth Date\s*[:\-]?\s*(\d{2}-\d{2}-\d{4})',
        r'© Date of Birth\s*[:\-]?\s*(\d{2}\.\d{2}-\d{4})',
        r'© Date of Birth\s*[:\-]?\s*(\d{2}-[g]\d-\d{4})',
        r'© Date of Birth\s*[:\-]?\s*(\d[g]\.\d{2}-\d{4})',
        r'© Date of Birth\s*[:\-]?\s*(\d[a-z]\.\d{2}-\d{4})'
    ]
    for pattern in dob_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            dob = match.group(1).strip()
            dob = dob.replace('.', '-').replace('g', '8')
            if dob.startswith('48') or dob.startswith('4g'):
                dob = '18' + dob[2:]
            result["date_of_birth"] = dob
            break
    
    # Extract descriptive date of birth
    dob_desc_patterns = [
        r'Date of Birth\s*[:\-]?\s*\d{2}-\d{2}-\d{4}\s*([A-Z0-9\s]+)',
        r'DOB\s*[:\-]?\s*\d{2}-\d{2}-\d{4}\s*([A-Z0-9\s]+)',
        r'© Date of Birth\s*[:\-]?\s*\d{2}\.\d{2}-\d{4}\s*([A-Z0-9\s]+)',
        r'© Date of Birth\s*[:\-]?\s*(\d{2}-[g]\d-\d{4})\s*([A-Z0-9\s]+)',
        r'© Date of Birth\s*[:\-]?\s*(\d[g]\.\d{2}-\d{4})\s*([A-Z0-9\s]+)',
        r'© Date of Birth\s*[:\-]?\s*(\d[a-z]\.\d{2}-\d{4})\s*([A-Z0-9\s]+)'
    ]
    for pattern in dob_desc_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            dob_desc = re.sub(r'[^A-Z0-9\s]', '', match.group(len(match.groups()))).strip().upper()
            result["date_of_birth_descriptive"] = re.sub(r'\s+', ' ', dob_desc)
            break
    
    # Extract school
    school_patterns = [
        r"(?i)School\s*[:\-]?\s*_?(\d+\s*-\s*[A-Z\s]+)",
        r"(?i)Institute\s*[:\-]?\s*_?(\d+\s*-\s*[A-Z\s]+)",
        r"(?i)Institution\s*[:\-]?\s*_?(\d+\s*-\s*[A-Z\s]+)",
        r'\. School\s*_?(\d+\s*-\s*[A-Z\s]+)',
        r'| School\s*(\d+\s*-\s*[A-Z\s]+)'
    ]
    for pattern in school_patterns:
        match = re.search(pattern, full_text)
        if match:
            school = re.sub(r'[^\dA-Z\s-]', '', match.group(1)).strip().upper()
            result["school"] = re.sub(r'\s+', ' ', school)
            break
    
    # Identify marks table section
    marks_start = None
    marks_end = None
    text_lines = text.split('\n')
    for i, line in enumerate(text_lines):
        if re.search(r'MARKS|OBTAINED|SUBJECT|SUB\.? CODE|CODE|POSITION|GRADE|SUB|CODE', line, re.IGNORECASE):
            marks_start = i
        elif marks_start is not None and (re.search(r'Result|TOTAL|GRAND|PASS', line, re.IGNORECASE) or i > marks_start + 15):
            marks_end = i
            break
    
    marks_text = ''
    if marks_start is not None and marks_end is not None:
        marks_section = text_lines[marks_start:marks_end]
        marks_text = '\n'.join(marks_section)
        
        # Per line extraction for marks
        for line in marks_section:
            match = re.match(r'(\d{3})\s*[ :|—-]*\s*([A-Z\s&.-]+?)\s*[\— :|]*\s*(\d{3})\s*(\d{3})\s*(\d{3})\s*([A-Z\s]+)\s*([A-D][1-9tIlL])', line, re.IGNORECASE)
            if match:
                code, subject, theory, practical, total, total_words, grade = match.groups()
                subject = re.sub(r'[^A-Z\s&.-]', '', subject.upper()).strip()
                subject = re.sub(r'\s+', ' ', subject)
                total_words = re.sub(r'[^A-Z\s]', '', total_words.upper()).strip()
                total_words = re.sub(r'\s+', ' ', total_words)
                grade = grade.replace('t', '1').replace('I', '1').replace('l', '1').replace('L', '1').upper()
                
                # Standardize subject names
                subject_mapping = {
                    'ENGLISH': 'ENGLISH LNG & LIT',
                    'HINDI': 'HINDI COURSE-B',
                    'MATHEMATICS': 'MATHEMATICS STANDARD',
                    'SCIENCE': 'SCIENCE',
                    'SOCIAL SCIENCE': 'SOCIAL SCIENCE',
                    'COMPUTER': 'COMPUTER APPLICATIONS'
                }
                for key, value in subject_mapping.items():
                    if key in subject:
                        subject = value
                        break
                
                result["marks"][subject] = {
                    "code": code,
                    "theory": int(theory),
                    "practical": int(practical),
                    "total": int(total),
                    "total_in_words": total_words,
                    "grade": grade
                }
    
    # Always run the fallback to capture any missed subjects
    marks_text = '\n'.join(text_lines[marks_start:marks_end]) if marks_start is not None else full_text
    subject_patterns = [
        (r'184.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'ENGLISH LNG & LIT'),
        (r'085.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'HINDI COURSE-B'),
        (r'041.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'MATHEMATICS STANDARD'),
        (r'086.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'SCIENCE'),
        (r'087.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'SOCIAL SCIENCE'),
        (r'165.*?(\d{2,3}).*?(\d{2,3}).*?(\d{2,3}).*?([A-Z\s]+).*?([A-D][1-9tIlL])', 'COMPUTER APPLICATIONS')
    ]
    for pattern, subject_name in subject_patterns:
        match = re.search(pattern, marks_text, re.IGNORECASE | re.DOTALL)
        if match and subject_name not in result["marks"]:
            theory, practical, total, total_words, grade = match.groups()
            total_words = re.sub(r'[^A-Z\s]', '', total_words.upper()).strip()
            total_words = re.sub(r'\s+', ' ', total_words)
            grade = grade.replace('t', '1').replace('I', '1').replace('l', '1').replace('L', '1').upper()
            result["marks"][subject_name] = {
                "code": pattern[:3],
                "theory": int(theory),
                "practical": int(practical),
                "total": int(total),
                "total_in_words": total_words,
                "grade": grade
            }
    
    # Proximity-based fallback for key fields if patterns fail
    if any(value == 'Unknown' for key, value in result.items() if key != 'marks'):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'certify that' in line.lower() or 'certiry that' in line.lower():
                name_match = re.search(r'(?i)this ts to certiry that\s+([A-Z\s]+)', line)
                if name_match and result['name'] == 'Unknown':
                    name = re.sub(r'[^A-Z\s]', '', name_match.group(1)).strip().upper()
                    result['name'] = re.sub(r'\s+', ' ', name)
                
                # Scan subsequent lines for additional fields
                for j in range(i + 1, min(i + 10, len(lines))):
                    next_line = lines[j]
                    roll_match = re.search(r'© Roll No\s*(\d+)', next_line, re.IGNORECASE)
                    if roll_match and result['roll_no'] == 'Unknown':
                        result['roll_no'] = roll_match.group(1)
                    
                    father_match = re.search(r"(?i)Father’s \( Guardtan’s Name\s*([A-Z\s]+)", next_line)
                    if father_match and result['fathers_guardians_name'] == 'Unknown':
                        father = re.sub(r'[^A-Z\s]', '', father_match.group(1)).strip().upper()
                        result['fathers_guardians_name'] = re.sub(r'\s+', ' ', father)
                    
                    dob_match = re.search(r'© Date of Birth\s*[:\-]?\s*(\d{2}\.\d{2}-\d{4})\s*([A-Z0-9\s]+)', next_line, re.IGNORECASE)
                    if not dob_match:
                        dob_match = re.search(r'© Date of Birth\s*[:\-]?\s*(\d[g]\.\d{2}-\d{4})\s*([A-Z0-9\s]+)', next_line, re.IGNORECASE)
                    if dob_match and result['date_of_birth'] == 'Unknown':
                        dob = dob_match.group(1).replace('.', '-').replace('g', '8')
                        if dob.startswith('48'):
                            dob = '18' + dob[2:]
                        result["date_of_birth"] = dob
                        dob_desc = re.sub(r'[^A-Z0-9\s]', '', dob_match.group(2)).strip().upper()
                        result["date_of_birth_descriptive"] = re.sub(r'\s+', ' ', dob_desc)
    
    logging.info(f"Extracted fields: {result}")
    return result

# Example usage
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr.py <path_to_marksheet>")
        sys.exit(1)
    file_path = sys.argv[1]
    extracted_details = extract_fields(file_path)
    import json
    print("Extracted fields:", json.dumps(extracted_details, indent=2))