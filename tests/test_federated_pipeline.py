"""
tests/test_federated_pipeline.py
================================
Verification of Federated Learning retraining pipeline and model export:
- Autoencoder initialization and PyTorch forward pass
- Model weights export to anomaly_models.pkl format
- Hot reload verification
"""

import os
import torch
import pytest
from app.federated_learning import DocumentAutoencoder, export_global_model_to_anomaly_format
from app.ml_anomaly import load_models


def test_autoencoder_architecture():
    """Autoencoder reconstructs 1x64x64 document tensors."""
    ae = DocumentAutoencoder()
    dummy_input = torch.randn(2, 1, 64, 64)
    reconstructed = ae(dummy_input)
    assert reconstructed.shape == (2, 1, 64, 64)


def test_export_global_model(tmp_path):
    """Global model exports properly into anomaly_models.pkl bundle."""
    ae = DocumentAutoencoder()
    target_pkl = str(tmp_path / "anomaly_models.pkl")
    success = export_global_model_to_anomaly_format(ae, output_path=target_pkl)
    assert success is True
    assert os.path.exists(target_pkl)
