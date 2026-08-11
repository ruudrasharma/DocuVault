# import pytesseract
# from PIL import Image
# import re
# import cv2
# import numpy as np
# from pdf2image import convert_from_path
# import hashlib
# from app import db
# from app.database_models import CertificateRecord
# from app.ml_anomaly import detect_anomaly, load_models
# import os
# import json
# import logging

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# def extract_data(file_path, lang='eng'):
#     logger.debug(f"Extracting data from {file_path}")
#     try:
#         if file_path.lower().endswith('.pdf'):
#             images = convert_from_path(file_path, dpi=300)
#             if not images:
#                 raise ValueError("No images extracted from PDF")
#             text = ''.join(pytesseract.image_to_string(img, lang=lang) for img in images)
#         else:
#             text = pytesseract.image_to_string(Image.open(file_path), lang=lang)
#         logger.debug(f"Extracted raw text: {text[:100]}...")
#         name_match = re.search(r'(?:This is to certify that|Name:\s*)([\w\s]+?)(?:,|\n)', text, re.IGNORECASE)
#         roll_match = re.search(r'Roll\s*(?:Number|No\.?):\s*(\d+[A-Za-z0-9]*)', text, re.IGNORECASE)
#         grade_match = re.search(r'score of\s*([\d.]+)%', text, re.IGNORECASE) or re.search(r'Grade:\s*([\d.]+)', text, re.IGNORECASE)
#         institution_match = re.search(r'Institution:\s*([\w\s]+)|Authorized\s*Signatory\s*([\w\s]+)', text, re.IGNORECASE)
#         uid_match = re.search(r'UID:\s*(\w+)', text, re.IGNORECASE)

#         extracted = {
#             'name': name_match.group(1).strip() if name_match else 'Unknown',
#             'roll': roll_match.group(1) if roll_match else 'Unknown',
#             'grade': grade_match.group(1) if grade_match else 'Unknown',
#             'id': 'CERT1',
#             'institution': (institution_match.group(1) or institution_match.group(2) or '').strip() or 'Sample University' if 'Authorized Signatory' in text else 'Unknown',
#             'uid': uid_match.group(1) if uid_match else 'Unknown'
#         }
#         return extracted, text
#     except Exception as e:
#         logger.error(f"Extraction failed: {e}")
#         return {'name': 'Unknown', 'roll': 'Unknown', 'grade': 'Unknown', 'id': 'CERT1', 'institution': 'Unknown', 'uid': 'Unknown'}, ''

# def detect_seal(file_path):
#     try:
#         img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE) if file_path and not file_path.lower().endswith('.pdf') else np.array(convert_from_path(file_path)[0].convert('L'))
#         _, thresh = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
#         contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
#         return any(500 < cv2.contourArea(cnt) < 5000 and cv2.isContourConvex(cnt) for cnt in contours)
#     except Exception as e:
#         logger.error(f"Seal detection failed: {e}")
#         return False

# def check_fictitious(extracted_data):
#     fictitious = ['Fake Inst', 'Nonexistent University', 'Bogus College']
#     return extracted_data.get('institution', '') in fictitious

# def validate_data(extracted_data, blockchain, file_path, max_grade=100.0, is_legacy=False):
#     logger.debug(f"Validating data: {extracted_data}, is_legacy={is_legacy}")
#     try:
#         if not extracted_data or not isinstance(extracted_data, dict):
#             logger.error("Invalid extracted data")
#             return False
        
#         models = load_models()
#         if not models:
#             logger.error("Failed to load anomaly detection models")
#             return False
        
#         is_anomaly, anomaly_score = detect_anomaly(models, file_path, str(extracted_data), extracted_data)
#         if is_anomaly:
#             logger.warning(f"Anomaly detected in document: Score {anomaly_score}")
#             return False
        
#         if not is_legacy:
#             # Blockchain validation only for non-legacy documents
#             data_hash = hashlib.sha256(str(extracted_data).encode()).hexdigest()
#             try:
#                 if not any(block.data == data_hash for block in blockchain.chain):
#                     logger.debug(f"Adding new hash to blockchain: {data_hash}")
#                     blockchain.add_block(data_hash)
#                 elif not blockchain.verify_data(data_hash):
#                     logger.warning(f"Blockchain validation failed for hash: {data_hash}")
#                     return False
#             except AttributeError as e:
#                 logger.error(f"Blockchain error: {e}")
#                 return False
        
#         if file_path and not detect_seal(file_path):
#             logger.warning("Seal validation failed")
#             return False
#         if check_fictitious(extracted_data):
#             logger.warning(f"Fictitious institution detected: {extracted_data['institution']}")
#             return False
#         try:
#             grade = float(extracted_data.get('grade', '0'))
#             if grade > max_grade:
#                 logger.warning(f"Grade {grade} exceeds maximum {max_grade}")
#                 return False
#         except ValueError:
#             logger.error(f"Invalid grade format: {extracted_data.get('grade')}")
#             return False
#         existing_records = CertificateRecord.query.filter_by(institution=extracted_data.get('institution', '')).all()
#         for record in existing_records:
#             original_metadata = json.loads(record.encrypted_metadata or '{}')
#             if (original_metadata.get('uid') == extracted_data.get('uid') or 
#                 original_metadata.get('id') == extracted_data.get('id')):
#                 if original_metadata != extracted_data:
#                     logger.warning(f"Tampering detected: Original {original_metadata} vs New {extracted_data}")
#                     return False
#         if not is_legacy and CertificateRecord.query.filter_by(hash_value=data_hash).count() > 0:
#             logger.warning(f"Duplicate hash detected: {data_hash}")
#             return False
#         logger.debug(f"Validation successful for data: {extracted_data}")
#         return True
#     except Exception as e:
#         logger.error(f"Validation failed: {str(e)}")
#         return False





# app/auth_checker.py
import pytesseract
from PIL import Image
import re
import cv2
import numpy as np
from pdf2image import convert_from_path
import hashlib
from app import db
from app.database_models import CertificateRecord
import os
import json
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_data(file_path, lang='eng'):
    """Extracts critical data elements using OCR."""
    try:
        if not file_path or not os.path.exists(file_path):
            return None, None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=300)
            if not images:
                raise ValueError("No images extracted from PDF")
            text = ''.join(pytesseract.image_to_string(img, lang=lang) for img in images)
        else:
            text = pytesseract.image_to_string(Image.open(file_path), lang=lang)
        logger.debug(f"Extracted raw text: {text[:100]}")
        name_match = re.search(r'(?:This is to certify that|Name:\s*)([\w\s]+?)(?:,|\n)', text, re.IGNORECASE)
        roll_match = re.search(r'Roll\s*(?:Number|No\.?):\s*(\d+[A-Za-z0-9]*)', text, re.IGNORECASE)
        grade_match = re.search(r'score of\s*([\d.]+)%', text, re.IGNORECASE) or re.search(r'Grade:\s*([\d.]+)', text, re.IGNORECASE)
        institution_match = re.search(r'Institution:\s*([\w\s]+)|Authorized\s*Signatory\s*([\w\s]+)', text, re.IGNORECASE)
        uid_match = re.search(r'UID:\s*(\w+)', text, re.IGNORECASE)

        extracted = {
            'name': name_match.group(1).strip() if name_match else 'Unknown',
            'roll': roll_match.group(1) if roll_match else 'Unknown',
            'grade': grade_match.group(1) if grade_match else 'Unknown',
            'id': 'LEGACY_CERT',
            'institution': (institution_match.group(1) or institution_match.group(2) or '').strip() or 'Sample University' if 'Authorized Signatory' in text else 'Unknown',
            'uid': uid_match.group(1) if uid_match else 'Unknown'
        }
        logger.debug(f"Extracted metadata: {extracted}")
        return extracted, text
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return None, None

def detect_seal(file_path):
    try:
        img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE) if file_path and not file_path.lower().endswith('.pdf') else np.array(convert_from_path(file_path)[0].convert('L'))
        _, thresh = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        return any(500 < cv2.contourArea(cnt) < 5000 and cv2.isContourConvex(cnt) for cnt in contours)
    except Exception as e:
        logger.error(f"Seal detection failed: {e}")
        return False

def check_fictitious(extracted_data):
    fictitious = ['Fake Inst', 'Nonexistent University', 'Bogus College']
    return extracted_data.get('institution', '') in fictitious

def validate_data(extracted_data, blockchain, file_path, max_grade=100.0, is_legacy=False):
    logger.debug(f"Validating data: {extracted_data}, is_legacy={is_legacy}")
    try:
        if not extracted_data or not isinstance(extracted_data, dict):
            logger.error("Invalid extracted data")
            return False
        
        if not is_legacy:
            data_hash = hashlib.sha256(str(extracted_data).encode()).hexdigest()
            if not any(block.data == data_hash for block in blockchain.chain):
                logger.debug(f"Adding new hash to blockchain: {data_hash}")
                blockchain.add_block(data_hash)
            elif not blockchain.verify_data(data_hash):
                logger.warning(f"Blockchain validation failed for hash: {data_hash}")
                return False
        
        if not is_legacy and file_path and not detect_seal(file_path):
            logger.warning("Seal validation failed")
            return False
        if not is_legacy and check_fictitious(extracted_data):
            logger.warning(f"Fictitious institution detected: {extracted_data['institution']}")
            return False
        try:
            grade = float(extracted_data.get('grade', '0'))
            if grade > max_grade:  # Reintroduce grade check for all cases
                logger.warning(f"Grade {grade} exceeds maximum {max_grade}")
                return False
        except ValueError:
            logger.error(f"Invalid grade format: {extracted_data.get('grade')}")
            return False
        logger.debug(f"Validation successful for data: {extracted_data}")
        return True
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return False