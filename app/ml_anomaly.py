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
from PIL import Image  # Added import

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global vectorizer (updated by load_models)
text_vectorizer = TfidfVectorizer(max_features=1000)

def preprocess_image(file_path):
    """Preprocesses image or PDF for features; resizes to 128x128."""
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
        logger.error(f"Preprocessing failed: {e} - Using default features")
        return np.zeros(128 * 128, dtype=np.uint8)

def preprocess_text(text):
    """Transforms text to TF-IDF features using global vectorizer."""
    if not text or not isinstance(text, str):
        logger.warning("Empty or invalid text provided; using default features")
        return np.zeros(1000)
    try:
        return text_vectorizer.transform([text]).toarray().flatten()
    except ValueError as e:
        logger.error(f"Text preprocessing failed: {e} - Vectorizer not fitted")
        return np.zeros(1000)

def perform_ela(file_path, quality=90, scale=10, threshold=0.05):
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
        
        mean_error = np.mean(difference)
        std_error = np.std(difference)
        anomalous_pixels = np.sum(difference > (mean_error + 2 * std_error)) / difference.size
        is_tampered = anomalous_pixels > threshold
        
        Image.fromarray(difference).save(os.path.join(os.path.dirname(file_path), 'ela_result.jpg'))
        logger.debug(f"ELA completed for {file_path}: is_tampered={is_tampered}, anomalous_pixels={anomalous_pixels}")
        return is_tampered, difference
    except Exception as e:
        logger.error(f"ELA failed: {e} - Assuming no tampering")
        return False, np.zeros((128, 128, 3), dtype=np.uint8)

def train_model(sample_image_features, sample_text_features, raw_texts):
    """Trains models and fits vectorizer on corpus."""
    global text_vectorizer
    if not raw_texts or not sample_image_features or not sample_text_features:
        raise ValueError("Sample data required for vectorizer and model fitting")
    text_vectorizer.fit(raw_texts)
    model_image = IsolationForest(contamination=0.1, random_state=42)
    model_image.fit(sample_image_features)
    model_text = IsolationForest(contamination=0.1, random_state=42)
    model_text.fit(sample_text_features)
    return {'text_vectorizer': text_vectorizer, 'text_model': model_text, 'image_model': model_image}

def detect_anomaly(models, file_path, text, extracted_data=None):
    if models is None or not isinstance(models, dict):
        logger.error("Invalid models provided")
        return False, 0.0
    image_model = models.get('image_model')
    text_model = models.get('text_model')
    if not image_model or not text_model:
        logger.error("Missing image or text model")
        return False, 0.0
    
    is_tampered, ela_image = perform_ela(file_path) if file_path and os.path.exists(file_path) else (False, np.zeros((128, 128, 3), dtype=np.uint8))
    
    image_features = preprocess_image(file_path) if file_path else np.zeros(128*128, dtype=np.uint8)
    text_features = preprocess_text(text) if text else np.zeros(1000, dtype=np.float32)
    
    try:
        image_pred = image_model.predict([image_features])[0] == -1
        text_pred = text_model.predict([text_features])[0] == -1
        score = max(-image_model.decision_function([image_features])[0], -text_model.decision_function([text_features])[0])
    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        return False, 0.0

    final_pred = is_tampered or image_pred or text_pred
    logger.debug(f"Anomaly detection result: is_anomaly={final_pred}, score={score}")
    return final_pred, score

def forecast_forgery_trends(historical_data):
    """Predicts forgery trends from logs."""
    if len(historical_data) < 2:
        logger.warning("Insufficient historical data for trend forecasting")
        return 0.0
    X = np.array([d[0] for d in historical_data]).reshape(-1, 1)
    y = np.array([d[1] for d in historical_data])
    model = LinearRegression()
    model.fit(X, y)
    return model.predict(np.array([[X.max() + 1]]))[0]

def refine_models_with_federated():
    """Simulates federated learning for model improvement."""
    from app.federated_learning import simulate_federated_learning
    simulate_federated_learning(mock_mode=True)

def load_models():
    """Loads or initializes ML models from file or trains if not available."""
    models_file = os.path.join(os.path.dirname(__file__), 'models', 'anomaly_models.pkl')
    os.makedirs(os.path.dirname(models_file), exist_ok=True)
    try:
        with open(models_file, 'rb') as f:
            models = joblib.load(f)
        if not isinstance(models, dict) or 'text_vectorizer' not in models or 'text_model' not in models or 'image_model' not in models:
            raise ValueError("Invalid model structure in anomaly_models.pkl")
        global text_vectorizer
        text_vectorizer = models['text_vectorizer']
        logger.debug("Models loaded successfully from anomaly_models.pkl")
        return models
    except (FileNotFoundError, ValueError, KeyError) as e:
        logger.warning(f"Error loading models: {e}. Training new models with default data.")
        sample_image_features = [np.zeros(128*128, dtype=np.uint8)]
        sample_texts = ['Sample certificate text with name and grade', 'Another valid certificate']
        sample_text_features = [preprocess_text(text) for text in sample_texts]
        models = train_model(sample_image_features, sample_text_features, sample_texts)
        with open(models_file, 'wb') as f:
            joblib.dump(models, f)
        logger.debug("New models trained and saved to anomaly_models.pkl")
        return models