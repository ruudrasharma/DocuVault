from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import IsolationForest
import joblib
import os
from pdf2image import convert_from_path
import pytesseract
import re
import cv2
import numpy as np
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define paths
base_dir = os.path.dirname(os.path.dirname(__file__))  # /Users/rudra/Documents/SIH_Prototype
models_dir = os.path.join(base_dir, 'app', 'models')
data_dir = os.path.join(base_dir, 'data')
os.makedirs(models_dir, exist_ok=True)

# Certificates for training (originals and fakes)
certificates = [
    'certificate_original.pdf',  # User's original (85%)
    'simple_original.pdf',       # Generated original (85%)
    'complex_original.pdf',      # Generated complex original (85%)
    'simple_fake.pdf',           # Generated fake (150%)
    'complex_fake.pdf'           # Generated fake (200%)
]

texts = []
sample_image_features = []
for cert_file in certificates:
    cert_path = os.path.join(data_dir, cert_file)
    if os.path.exists(cert_path):
        try:
            images = convert_from_path(cert_path)
            if images:
                text = ""
                for image in images:
                    text += pytesseract.image_to_string(image) + "\n"  # Concatenate all pages
                logger.debug(f"Extracted full text from {cert_file}: {text[:200]}...")
                texts.append(text)  # Original text
                if 'original' in cert_file or 'certificate_original' in cert_file:
                    for _ in range(5):  # Add 5 duplicates for originals
                        texts.append(text)
                elif 'fake' in cert_file:
                    texts.append(text.replace("Fake Data", "Invalid Data"))  # Variation for fakes
            else:
                logger.warning(f"No images extracted from {cert_file}")
        except Exception as e:
            logger.error(f"Failed to process {cert_path}: {e}")
    else:
        logger.warning(f"{cert_path} not found")

# Add additional forged samples with high scores
texts.extend([
    "Fake Certificate This is to certify that Test User, Roll Number: 999999, has successfully completed the examination with a score of 200%. Features included for testing purposes: " + " ".join([f"Feature {i}: Invalid Data" for i in range(1, 49)]),
    "Fake Certificate This is to certify that Invalid User, Roll Number: 123456, has successfully completed the examination with a score of 150%. Features included for testing purposes: " + " ".join([f"Feature {i}: Fake Data" for i in range(1, 49)]),
])

# Add variations for originals with valid scores
C = "CSE"
for i in range(5):  # Add 5 more valid samples
    texts.append(f"Sample Certificate This is to certify that User{i}, Roll Number: 202{i+1}{C}00{i}, has successfully completed the examination with a score of {80+i}%. Features included for testing purposes: " + " ".join([f"Feature {j}: Sample Data" for j in range(1, 49)]))

logger.debug(f"Training with {len(texts)} text samples")
vectorizer = TfidfVectorizer(max_features=1000)
X_text = vectorizer.fit_transform(texts).toarray()
model_text = IsolationForest(contamination=0.1, random_state=42).fit(X_text)

# Generate sample image features
for cert_file in certificates:
    cert_path = os.path.join(data_dir, cert_file)
    if os.path.exists(cert_path):
        images = convert_from_path(cert_path)
        if images:
            sample_image = np.array(images[0].convert('L'))
            sample_image = cv2.resize(sample_image, (128, 128))
            sample_image_features.append(sample_image.flatten())
            if 'original' in cert_file or 'certificate_original' in cert_file:
                for _ in range(3):  # Add 3 duplicates for originals
                    sample_image_features.append(sample_image.flatten())

# Add synthetic image features
sample_image_features.extend([
    np.random.normal(128, 10, 128*128).astype(np.uint8),  # Valid
    np.random.normal(100, 20, 128*128).astype(np.uint8)   # Tampered
])

model_image = IsolationForest(contamination=0.1, random_state=42).fit(sample_image_features)

# Save models
models_file = os.path.join(models_dir, 'anomaly_models.pkl')
models = {
    'text_vectorizer': vectorizer,
    'text_model': model_text,
    'image_model': model_image
}
try:
    joblib.dump(models, models_file)
    logger.debug("Models saved to anomaly_models.pkl")
except Exception as e:
    logger.error(f"Failed to save models: {e}")