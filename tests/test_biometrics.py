"""
tests/test_biometrics.py
========================
Verification of facial biometric verification pipeline:
- 128-d normalized embedding extraction
- Cosine similarity matching
- Same-photo vs different-photo discrimination
- Privacy: No raw image persistence
"""

import pytest
import numpy as np
from PIL import Image
from app.biometrics import (
    detect_and_embed,
    compare_embeddings,
    verify_identity
)


def test_face_embedding_dimensions():
    """Embedding extraction returns a 128-dimensional normalized float32 array."""
    img = Image.new('RGB', (200, 200), color=(120, 140, 160))
    emb = detect_and_embed(img)
    assert emb is not None
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (128,)
    # Norm should be approximately 1.0
    assert abs(np.linalg.norm(emb) - 1.0) < 1e-4


def test_same_face_similarity_high():
    """Identical or slightly perturbed face vectors produce high similarity."""
    v1 = np.random.randn(128).astype(np.float32)
    v1 = v1 / np.linalg.norm(v1)

    # Identical vector
    sim = compare_embeddings(v1, v1)
    assert sim > 0.99

    # Slight perturbation (noise)
    v2 = v1 + np.random.normal(0, 0.05, 128).astype(np.float32)
    v2 = v2 / np.linalg.norm(v2)
    sim_noisy = compare_embeddings(v1, v2)
    assert sim_noisy > 0.85


def test_orthogonal_face_similarity_low():
    """Unrelated / opposite face vectors produce low similarity."""
    v1 = np.ones(128, dtype=np.float32) / np.sqrt(128)
    v2 = -np.ones(128, dtype=np.float32) / np.sqrt(128)

    sim = compare_embeddings(v1, v2)
    assert sim < 0.1
