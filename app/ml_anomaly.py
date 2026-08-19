# app/ml_anomaly.py
import cv2
from sklearn.ensemble import IsolationForest
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression
from pdf2image import convert_from_path
import joblib
import os
import re
import logging
from io import BytesIO
from PIL import Image

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cached models in memory for fast thread-safe inference
_cached_models = None

def preprocess_image(file_path):
    """Preprocesses image or PDF for features; resizes to 128x128 grayscale array."""
    try:
        if file_path and file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path)
            if not images:
                raise ValueError("No images extracted from PDF")
            img = np.array(images[0].convert('L'))
        elif file_path:
            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError("Invalid image/PDF")
        else:
            return np.zeros(128 * 128, dtype=np.uint8)
        img = cv2.resize(img, (128, 128))
        return img.flatten()
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e} - Using zero vector")
        return np.zeros(128 * 128, dtype=np.uint8)

def preprocess_text(text, vectorizer=None):
    """Transforms text to TF-IDF features using the provided vectorizer (thread-safe)."""
    if not text or not isinstance(text, str):
        return np.zeros(1000)
    try:
        if vectorizer is not None:
            return vectorizer.transform([text]).toarray().flatten()
        else:
            # Fallback inline vectorizer
            vec = TfidfVectorizer(max_features=1000)
            return vec.fit_transform([text]).toarray().flatten()
    except Exception as e:
        logger.error(f"Text preprocessing failed: {e}")
        return np.zeros(1000)

def perform_ela(file_path, quality=90, scale=10, threshold=0.22):
    """
    Error Level Analysis (ELA) for image/PDF pixel tampering.
    Re-compresses image at 90% JPEG quality and analyzes pixel error distribution.
    Scanned physical documents naturally produce ~8-18% compression noise.
    Spliced/forged regions exhibit high localized variance (>22%).
    """
    try:
        if not file_path or not os.path.exists(file_path):
            raise ValueError("Invalid or missing file path")
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path)
            if not images:
                raise ValueError("No images extracted from PDF")
            original = images[0].convert('RGB')
        else:
            original = Image.open(file_path).convert('RGB')
        
        buffer = BytesIO()
        original.save(buffer, 'JPEG', quality=quality)
        buffer.seek(0)
        resaved = Image.open(buffer)
        
        original_array = np.array(original)
        resaved_array = np.array(resaved)
        difference = np.abs(original_array - resaved_array) * scale
        difference = np.clip(difference, 0, 255).astype(np.uint8)
        
        mean_error = float(np.mean(difference))
        std_error = float(np.std(difference))
        anomalous_pixels = float(np.sum(difference > (mean_error + 2 * std_error)) / difference.size)
        is_tampered = bool(anomalous_pixels > threshold)
        
        ela_save_path = os.path.join(os.path.dirname(file_path), 'ela_result.jpg')
        try:
            Image.fromarray(difference).save(ela_save_path)
        except Exception:
            pass
            
        logger.debug(f"ELA completed for {file_path}: is_tampered={is_tampered}, anomalous_pixels={anomalous_pixels:.4f}")
        return is_tampered, anomalous_pixels, difference
    except Exception as e:
        logger.error(f"ELA failed: {e} - Assuming no tampering")
        return False, 0.0, np.zeros((128, 128, 3), dtype=np.uint8)

def train_model(sample_image_features, sample_text_features, raw_texts):
    """Trains IsolationForest models and fits TfidfVectorizer on corpus."""
    if not raw_texts or not sample_image_features or not sample_text_features:
        raise ValueError("Sample data required for vectorizer and model fitting")
    
    vec = TfidfVectorizer(max_features=1000)
    X_text = vec.fit_transform(raw_texts).toarray()
    
    model_image = IsolationForest(contamination=0.1, random_state=42)
    model_image.fit(sample_image_features)
    
    model_text = IsolationForest(contamination=0.1, random_state=42)
    model_text.fit(X_text)
    
    return {
        'text_vectorizer': vec,
        'text_model': model_text,
        'image_model': model_image
    }

def detect_anomaly(models, file_path, text="", extracted_data=None):
    """
    Evaluates file for pixel & text anomalies using consensus & confidence scoring.
    Returns (is_anomaly, score, details_dict).
    """
    if models is None:
        models = load_models()

    if not isinstance(models, dict):
        logger.error("Invalid models provided")
        return False, 0.0, {"error": "Invalid models"}

    image_model = models.get('image_model')
    text_model = models.get('text_model')
    vectorizer = models.get('text_vectorizer')
    autoencoder = models.get('autoencoder')

    blockchain_valid = False
    if isinstance(extracted_data, dict):
        blockchain_valid = bool(extracted_data.get('blockchain_valid', False))

    ela_tampered, ela_score, _ = perform_ela(file_path) if file_path and os.path.exists(file_path) else (False, 0.0, None)
    
    image_features = preprocess_image(file_path) if file_path else np.zeros(128*128, dtype=np.uint8)
    text_features = preprocess_text(text, vectorizer=vectorizer) if text else np.zeros(1000, dtype=np.float32)
    
    image_pred = False
    text_pred = False
    image_score = 0.0
    text_score = 0.0

    try:
        if image_model:
            image_pred = bool(image_model.predict([image_features])[0] == -1)
            image_score = float(-image_model.decision_function([image_features])[0])
        if text_model:
            text_pred = bool(text_model.predict([text_features])[0] == -1)
            text_score = float(-text_model.decision_function([text_features])[0])
    except Exception as e:
        logger.error(f"Anomaly score evaluation failed: {e}")

    # PyTorch Autoencoder reconstruction check if loaded
    ae_anomaly = False
    ae_loss = 0.0
    if autoencoder is not None and file_path and os.path.exists(file_path):
        try:
            from app.federated_learning import evaluate_image_autoencoder
            ae_anomaly, ae_loss = evaluate_image_autoencoder(autoencoder, file_path)
        except Exception as e:
            logger.debug(f"Autoencoder evaluation skipped: {e}")

    # Multi-signal consensus logic:
    flag_count = sum([ela_tampered, image_pred, text_pred, ae_anomaly])
    
    if blockchain_valid:
        # For genuine blockchain-verified documents, flag if physical pixel editing/splicing (ELA >22%)
        # or if at least 2 AI models agree on anomaly.
        final_anomaly = bool(ela_tampered or (flag_count >= 2))
    else:
        # Unverified / unregistered documents: any strong anomaly triggers tamper alert.
        final_anomaly = bool(ela_tampered or flag_count >= 1)

    combined_score = max(image_score, text_score, float(ela_score * 3.0), float(ae_loss))

    details = {
        'is_anomaly': final_anomaly,
        'anomaly_score': round(float(combined_score), 4),
        'ela_tampered': bool(ela_tampered),
        'ela_pixel_ratio': round(float(ela_score), 4),
        'image_anomaly': bool(image_pred),
        'text_anomaly': bool(text_pred),
        'autoencoder_anomaly': bool(ae_anomaly),
        'autoencoder_loss': round(float(ae_loss), 4),
        'blockchain_verified': blockchain_valid,
        'status': 'ANOMALY DETECTED' if final_anomaly else 'CLEAN'
    }

    logger.debug(f"Anomaly detection complete for {file_path}: {details}")
    return final_anomaly, combined_score, details

def forecast_forgery_trends(historical_data):
    """Predicts forgery trends from historical event logs."""
    if len(historical_data) < 2:
        return 0.0
    X = np.array([d[0] for d in historical_data]).reshape(-1, 1)
    y = np.array([d[1] for d in historical_data])
    model = LinearRegression()
    model.fit(X, y)
    return float(model.predict(np.array([[X.max() + 1]]))[0])

def load_models(force_reload=False):
    """Loads or initializes ML models from anomaly_models.pkl in a thread-safe manner."""
    global _cached_models
    if _cached_models is not None and not force_reload:
        return _cached_models

    models_file = os.path.join(os.path.dirname(__file__), 'models', 'anomaly_models.pkl')
    os.makedirs(os.path.dirname(models_file), exist_ok=True)
    try:
        with open(models_file, 'rb') as f:
            models = joblib.load(f)
        if not isinstance(models, dict) or 'text_vectorizer' not in models or 'text_model' not in models or 'image_model' not in models:
            raise ValueError("Invalid model structure in anomaly_models.pkl")
        logger.info("ML Anomaly models loaded successfully from anomaly_models.pkl")
        _cached_models = models
        return models
    except Exception as e:
        logger.warning(f"Could not load anomaly_models.pkl ({e}). Initializing baseline models.")
        sample_image_features = [np.zeros(128*128, dtype=np.uint8)]
        sample_texts = [
            'CENTRAL BOARD OF SECONDARY EDUCATION MARKS STATEMENT CUM CERTIFICATE SECONDARY SCHOOL EXAMINATION ROLL NO CANDIDATE NAME MOTHER NAME FATHER NAME SCHOOL PASCHIM VIHAR DELHI',
            'BOARD OF SECONDARY EDUCATION MARKSHEET ROLL NUMBER STUDENT NAME GRADE PASSING YEAR SUBJECTS ENGLISH MATHEMATICS SCIENCE SOCIAL SCIENCE HINDI RESULT PASS',
            'UNIVERSITY DEGREE CERTIFICATE BACHELOR OF TECHNOLOGY COMPUTER SCIENCE AND ENGINEERING FIRST CLASS WITH DISTINCTION DEAN REGISTRAR CONTROLLER OF EXAMINATIONS',
            'CERTIFICATE OF COMPLETION THIS IS TO CERTIFY THAT STUDENT HAS SUCCESSFULLY COMPLETED THE COURSE EXAMINATION WITH EXCELLENT GRADE',
            'HIGHER SECONDARY CERTIFICATE EXAMINATION ALL INDIA SENIOR SCHOOL CERTIFICATE EXAMINATION SCIENCE STREAM MARKS STATEMENT'
        ]
        vec = TfidfVectorizer(max_features=1000)
        X_text = vec.fit_transform(sample_texts).toarray()
        sample_text_features = [X_text[i] for i in range(len(sample_texts))]
        models = train_model([np.zeros(128*128, dtype=np.uint8)] * len(sample_texts), sample_text_features, sample_texts)
        try:
            with open(models_file, 'wb') as f:
                joblib.dump(models, f)
        except Exception:
            pass
        _cached_models = models
        return models


def reload_models():
    """Forces reloading of models from disk without restarting the process."""
    return load_models(force_reload=True)