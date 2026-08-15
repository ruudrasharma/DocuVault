import os
import glob
import shutil
import logging
from io import BytesIO
import numpy as np
import cv2
from PIL import Image
from pdf2image import convert_from_path
import pytesseract
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import IsolationForest

import torch
from app.federated_learning import DocumentAutoencoder, train_autoencoder, preprocess_image_tensor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(__file__))
models_dir = os.path.join(base_dir, 'app', 'models')
data_dir = os.path.join(base_dir, 'data')
os.makedirs(models_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True)


def extract_features_from_file(file_path: str):
    """Extracts raw text and 128x128 image feature vector from a file."""
    raw_text = ""
    img_feature = None
    try:
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path)
            if images:
                for img in images:
                    try:
                        raw_text += pytesseract.image_to_string(img) + "\n"
                    except Exception:
                        pass
                gray_img = np.array(images[0].convert('L'))
                img_resized = cv2.resize(gray_img, (128, 128))
                img_feature = img_resized.flatten()
        else:
            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                try:
                    raw_text = pytesseract.image_to_string(img)
                except Exception:
                    raw_text = ""
                img_resized = cv2.resize(img, (128, 128))
                img_feature = img_resized.flatten()
    except Exception as e:
        logger.warning(f"Error processing {file_path} for training: {e}")

    return raw_text.strip(), img_feature


def build_and_evaluate_pipeline():
    logger.info("Starting historical document corpus scan in data/...")

    all_files = glob.glob(os.path.join(data_dir, '*.*'))
    valid_files = [f for f in all_files if not os.path.basename(f).startswith('.') and not f.endswith('.jpg_ela') and not f.endswith('.tmp')]

    logger.info(f"Found {len(valid_files)} historical documents in data/")

    texts = []
    image_features = []

    for fp in valid_files:
        text, img_feat = extract_features_from_file(fp)
        if text:
            texts.append(text)
        if img_feat is not None:
            image_features.append(img_feat)

    # Ensure minimum corpus baseline if empty
    if len(texts) < 3:
        logger.info("Augmenting corpus with standard educational certificate text patterns...")
        texts.extend([
            "Central Board of Secondary Education All India Senior School Certificate Examination CBSE Grade A Honours",
            "Indian Institute of Technology Bachelor of Technology Degree in Computer Science and Engineering",
            "Birla Institute of Technology and Science Master of Science Degree Certificate of Distinction",
            "National Institute of Technology Degree Certificate Examination Board Passed First Division"
        ])

    if len(image_features) < 3:
        for _ in range(5):
            syn_img = np.random.normal(128, 15, 128 * 128).clip(0, 255).astype(np.uint8)
            image_features.append(syn_img)

    logger.info(f"Training TF-IDF Vectorizer on {len(texts)} text samples...")
    vectorizer = TfidfVectorizer(max_features=1000)
    X_text = vectorizer.fit_transform(texts).toarray()

    logger.info(f"Training IsolationForest text model...")
    model_text = IsolationForest(contamination=0.1, random_state=42)
    model_text.fit(X_text)

    logger.info(f"Training IsolationForest image model on {len(image_features)} image vectors...")
    model_image = IsolationForest(contamination=0.1, random_state=42)
    model_image.fit(image_features)

    # Train PyTorch Autoencoder on image tensors
    logger.info("Training PyTorch DocumentAutoencoder on document image tensors...")
    autoencoder = DocumentAutoencoder()
    tensor_list = []
    for fp in valid_files:
        t = preprocess_image_tensor(fp)
        if t is not None:
            tensor_list.append(t)

    if not tensor_list:
        for _ in range(10):
            tensor_list.append(torch.rand(1, 1, 64, 64) * 0.8 + 0.1)

    all_tensors = torch.cat(tensor_list, dim=0)
    from torch.utils.data import TensorDataset, DataLoader
    dataset = TensorDataset(all_tensors)
    loader = DataLoader(dataset, batch_size=4, shuffle=True)
    train_autoencoder(autoencoder, loader, epochs=3)

    # Evaluate model against benchmark test set
    logger.info("Running evaluation against benchmark test set...")
    eval_texts = [
        "Central Board of Secondary Education All India Senior School Certificate Examination CBSE Grade A", # Clean
        "Fake Invalid Examination Marksheet Fake Data Tampered Grade 999%",                                   # Tampered text
    ]
    eval_text_vecs = vectorizer.transform(eval_texts).toarray()
    preds = model_text.predict(eval_text_vecs)
    clean_correct = preds[0] == 1
    tampered_correct = preds[1] == -1
    logger.info(f"Evaluation benchmark result: Clean text identified={clean_correct}, Tampered text caught={tampered_correct}")

    models = {
        'text_vectorizer': vectorizer,
        'text_model': model_text,
        'image_model': model_image,
        'autoencoder': autoencoder
    }

    # Atomic Save & Rollback Backup
    models_file = os.path.join(models_dir, 'anomaly_models.pkl')
    backup_file = os.path.join(models_dir, 'anomaly_models.pkl.bak')
    tmp_file = os.path.join(models_dir, 'anomaly_models.pkl.tmp')

    if os.path.exists(models_file):
        shutil.copy2(models_file, backup_file)
        logger.info(f"Created backup of previous models at {backup_file}")

    joblib.dump(models, tmp_file)
    shutil.move(tmp_file, models_file)
    logger.info(f"Atomically saved new models to {models_file}")

    return models


if __name__ == '__main__':
    build_and_evaluate_pipeline()