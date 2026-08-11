import pytesseract
from PIL import Image
import os
from pdf2image import convert_from_path
from app.ml_anomaly import detect_anomaly, load_models
from app.auth_checker import validate_data
from app import blockchain
import json
import re
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_legacy_upload(file_path, role='verifier'):
    logger.debug(f"Processing legacy upload: {file_path}, role: {role}")
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False, None, "File not found"
        
        extracted_data, extracted_text = extract_legacy_data(file_path)
        if not extracted_data:
            logger.error(f"Failed to extract data from {file_path}")
            return False, None, "Failed to extract data from document"
        
        logger.debug(f"Extracted data: {extracted_data}")
        models = load_models()
        if not models:
            logger.error("Failed to load anomaly detection models")
            return False, None, "Failed to load anomaly detection models"
        
        try:
            is_anomaly, anomaly_score = detect_anomaly(models, file_path, extracted_text, extracted_data)
            logger.debug(f"Anomaly detection result: is_anomaly={is_anomaly}, score={anomaly_score}")
            if is_anomaly:
                logger.warning(f"Anomaly detected: Score {anomaly_score}")
                return False, None, f"Anomaly detected: Score {anomaly_score}"
        except Exception as e:
            logger.error(f"Anomaly detection failed: {str(e)}")
            return False, None, f"Anomaly detection failed: {str(e)}"
        
        is_valid = validate_data(extracted_data, blockchain, file_path, is_legacy=True)
        logger.debug(f"Validation result: {is_valid}")
        
        return is_valid, None, None
    except Exception as e:
        logger.error(f"Processing failed for {file_path}: {str(e)}")
        return False, None, f"Processing failed: {str(e)}"

def extract_legacy_data(file_path, lang='eng'):
    logger.debug(f"Extracting data from {file_path}")
    try:
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return None, ""
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=300, first_page=1, last_page=1)
            if not images:
                logger.error(f"No images extracted from PDF: {file_path}")
                return None, ""
            text = pytesseract.image_to_string(images[0], lang=lang)
        else:
            text = pytesseract.image_to_string(Image.open(file_path), lang=lang)
        
        logger.debug(f"Extracted raw text: {text[:100]}...")
        name_match = re.search(r'(?:This is to certify that|Name:\s*)([\w\s]+?)(?:,|\n)', text, re.IGNORECASE)
        roll_match = re.search(r'Roll\s*(?:Number|No\.?):\s*(\d+[A-Za-z0-9]*)', text, re.IGNORECASE)
        grade_match = re.search(r'score of\s*([\d.]+)%', text, re.IGNORECASE) or re.search(r'Grade:\s*([\d.]+)', text, re.IGNORECASE)
        institution_match = re.search(r'Institution:\s*([\w\s]+)|Authorized\s*Signatory\s*([\w\s]+)', text, re.IGNORECASE)
        uid_match = re.search(r'UID:\s*(\w+)', text, re.IGNORECASE)

        extracted_data = {
            'name': name_match.group(1).strip() if name_match else 'Unknown',
            'roll': roll_match.group(1) if roll_match else 'Unknown',
            'grade': grade_match.group(1) if grade_match else 'Unknown',
            'id': 'LEGACY_CERT',
            'institution': (institution_match.group(1) or institution_match.group(2) or '').strip() or 'Sample University' if 'Authorized Signatory' in text else 'Unknown',
            'uid': uid_match.group(1) if uid_match else 'Unknown'
        }
        logger.debug(f"Extracted metadata: {extracted_data}")
        return extracted_data, text
    except Exception as e:
        logger.error(f"Extraction failed for {file_path}: {str(e)}")
        return None, ""