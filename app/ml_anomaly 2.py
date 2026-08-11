# app/ml_anomaly.py (AI-driven anomaly detection for iONBLOCKS DocuVault)
# Scrutinizes patterns for advanced forgeries using multimodal ML; includes forecasting.

import cv2
from sklearn.ensemble import IsolationForest
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression
from pdf2image import convert_from_path  # For PDF in preprocessing
import joblib
import os
import re

# Global vectorizer for consistent text features (fit during training)
text_vectorizer = TfidfVectorizer(max_features=50)  # Fixed size for consistency

def preprocess_image(file_path):
    """Preprocesses image or PDF for features; resizes to 128x128."""
    try:
        if file_path and file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path)
            if not images:
                raise ValueError("No images extracted from PDF")
            img = np.array(images[0].convert('L'))  # First page grayscale
        elif file_path:
            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError("Invalid image/PDF")
        else:
            return np.zeros(128 * 128, dtype=np.uint8)  # Default feature array for no input
        img = cv2.resize(img, (128, 128))
        return img.flatten()
    except Exception as e:
        print(f"Preprocessing failed: {e} - Using default features")
        return np.zeros(128 * 128, dtype=np.uint8)  # Fallback to zero array

def preprocess_text(text):
    """Transforms text to TF-IDF features using global vectorizer."""
    if not text:
        raise ValueError("Empty text")
    return text_vectorizer.transform([text]).toarray().flatten()

def train_model(sample_image_features, sample_text_features, raw_texts):
    """Trains models and fits vectorizer on corpus."""
    if not raw_texts or not sample_image_features or not sample_text_features:
        raise ValueError("Sample data required for vectorizer and model fitting")
    text_vectorizer.fit(raw_texts)
    model_image = IsolationForest(contamination=0.05, random_state=42)  # Lowered contamination for stricter detection
    model_image.fit(sample_image_features)
    model_text = IsolationForest(contamination=0.05, random_state=42)  # Lowered contamination
    model_text.fit(sample_text_features)
    return {'text_vectorizer': text_vectorizer, 'text_model': model_text, 'image_model': model_image}

def detect_anomaly(models, file_path, text, extracted_data=None):
    """Multimodal anomaly detection; returns (is_anomaly, score)."""
    if models is None:
        return False, 0.0
    image_model = models.get('image_model')
    text_model = models.get('text_model')
    if not image_model or not text_model:
        return False, 0.0
    image_features = preprocess_image(file_path) if file_path else np.zeros(128*128, dtype=np.uint8)  # Default for manual entry
    try:
        text_features = preprocess_text(text)
        image_pred = image_model.predict([image_features])[0] == -1
        text_pred = text_model.predict([text_features])[0] == -1
        score = max(-image_model.decision_function([image_features])[0], -text_model.decision_function([text_features])[0])

        # Enhanced check: Flag metadata deviations as anomalies
        if text and any(k in text.lower() for k in ['name', 'grade', 'id', 'roll', 'institution', 'uid']):
            name = re.search(r'Name:\s*([\w\s]+)', text, re.IGNORECASE)
            grade = re.search(r'(?:Grade|score of)\s*([\d.]+)(?:%|)', text, re.IGNORECASE)
            if name and grade and extracted_data:
                if float(grade.group(1)) > 100 or len(name.group(1).split()) > 3:  # Strict thresholds
                    return True, score * 2.0  # Amplify score for obvious anomalies
                # Check against extracted data for consistency
                if (extracted_data.get('name') and name.group(1) != extracted_data.get('name') or
                    extracted_data.get('grade') and float(grade.group(1)) != float(extracted_data.get('grade', 0))):
                    return True, score * 1.5  # Flag subtle changes
    except ValueError:
        # Fallback if text processing fails
        image_pred = image_model.predict([image_features])[0] == -1
        text_pred = False
        score = -image_model.decision_function([image_features])[0]
    return image_pred or text_pred, score

def forecast_forgery_trends(historical_data):
    """Predicts forgery trends from logs."""
    if len(historical_data) < 2:
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
    os.makedirs(os.path.dirname(models_file), exist_ok=True)  # Ensure models directory exists
    try:
        with open(models_file, 'rb') as f:
            models = joblib.load(f)
        if not isinstance(models, dict) or 'text_vectorizer' not in models or 'text_model' not in models or 'image_model' not in models:
            raise ValueError("Invalid model structure in anomaly_models.pkl")
        # Update global text_vectorizer with loaded instance
        global text_vectorizer
        text_vectorizer = models['text_vectorizer']
        return models
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"Error loading models: {e}. Training new models with default data.")
        # Fallback: Train with minimal default data
        sample_image_features = [np.zeros(128*128, dtype=np.uint8)]  # Default image
        sample_texts = ['Sample certificate text with name and grade', 'Another valid certificate']  # Minimal corpus
        sample_text_features = [preprocess_text(text) for text in sample_texts]
        models = train_model(sample_image_features, sample_text_features, sample_texts)
        with open(models_file, 'wb') as f:
            joblib.dump(models, f)
        return models