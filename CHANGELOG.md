# DocuVault Changelog

All notable changes across all 10 implementation phases are documented here.

---

## [Phase 0] — Safety Net — 2026-08-16
- Created `tests/` directory with `conftest.py` and `test_smoke.py`.
- Added `requirements-dev.txt` (pytest, pytest-flask, pytest-cov, locust, pip-audit).
- Added `Makefile` with test automation targets.
- Created `CHANGELOG.md`.

---

## [Phase 1] — Cleanup & De-duplication — 2026-08-16
- Removed dead and un-importable modules (`app/routes.py`, `app/models.py`, `app/auth_checker.py`, `app/legacy_ocr.py`, `ocr copy.py`, `ocr copy 2.py`, `ml_anomaly 2.py`).
- Consolidated `admin_cli` into `scripts/admin_cli.py`.
- Moved unintegrated Ray module to `future/ray_database.py` with `future/README.md`.
- Verified 0 broken references remain.

---

## [Phase 2] — Critical Security Hardening — 2026-08-16
- Removed hardcoded fallback password list from `database.py` (strict hash + salt verification only).
- Removed universal TOTP bypass codes (`123456`, `000000`, `888888`, `999999`) from `database.py`.
- Removed candidate password list from `consent.py` (`get_user_private_key`).
- Removed auto-account-creation backdoor from login route in `auth.py`.
- Added startup check in `app/__init__.py` to refuse booting in production with placeholder `SECRET_KEY`.
- Added `Flask-Limiter` rate limiting and `Flask-WTF` CSRF protection.
- Added magic-byte sniffing (`_validate_upload`) and image dimension bounds checking (`_check_image_dimensions`) to `/upload` and `/verify_document` in `main.py`.
- Created `scripts/reset_demo_accounts.py` and `scripts/migrate_secure_passwords.py`.
- Added `tests/test_security.py`.

---

## [Phase 3] — Real Post-Quantum Cryptography — 2026-08-16
- Replaced Fernet symmetric placeholder in `app/pqc.py` with real NIST ML-KEM-768 (Kyber768) implementation using `liboqs`.
- Implemented NIST Hybrid Migration standard combining classical secrets with ML-KEM-768 shared secrets via HKDF-SHA256 (`hybrid_combine_secrets`).
- Added `pqc_public_key` and `pqc_encrypted_private_key` columns to `WalletKey` in `app/database.py`.
- Added automatic column migration in `app/__init__.py`.
- Added `tests/test_pqc.py`.

---

## [Phase 4] — Real Zero-Knowledge Proofs — 2026-08-16
- Implemented real BN128 Pedersen commitments ($C = vG + rH$) with independent generator point $H$ in `app/zkp.py`.
- Implemented Fiat-Shamir Non-Interactive Zero-Knowledge Proofs of Knowledge (Schnorr NIZK).
- Refactored `prove_claim` in `app/routes_wallet.py` to return the NIZK proof token without revealing raw hashes to verifiers.
- Refactored `verify_claim` to evaluate Schnorr NIZK verification equation.
- Added `tests/test_zkp.py`.

---

## [Phase 5] — Signed Blockchain Blocks — 2026-08-16
- Added Ed25519 cryptographic block signing to `app/blockchain.py`.
- Updated `Block` class with `signature` and `signer_pubkey` fields.
- Implemented signature verification in `is_chain_valid()` to detect post-hoc tamper and re-signing attacks.
- Maintained seamless backward compatibility for legacy unsigned blocks.
- Added `tests/test_blockchain_signing.py`.

---

## [Phase 6] — Verifiable Credentials, QR, Watermarking & Analytics — 2026-08-16
- Implemented W3C-compliant Verifiable Credentials with Ed25519 signatures in `app/verifiable_credentials.py` (`POST /vc/issue`, `POST /vc/verify`).
- Added HMAC-authenticated QR scan-to-verify (`GET /verify_by_hash`) and OpenCV QR photo decoding (`POST /verify_by_qr_image`).
- Implemented LSB steganographic watermarking in `app/watermark.py`.
- Added `AnalyticsLog` model and `GET /admin/analytics` endpoint.
- Documented future National Registry integration contract in `docs/national_integration_interface.md`.
- Added `tests/test_vc.py`, `tests/test_watermark.py`, `tests/test_qr_verify.py`.

---

## [Phase 7] — Real Biometrics — 2026-08-16
- Replaced `matchTemplate` with a 128-dimensional directional gradient face embedding extraction pipeline in `app/biometrics.py`.
- Implemented cosine similarity comparison with strict thresholding.
- Guaranteed zero photo storage (raw images discarded immediately after embedding computation).
- Added encrypted embedding storage on `WalletKey` and routes `POST /wallet/enroll_face` and `POST /wallet/verify_face`.
- Added `tests/test_biometrics.py`.

---

## [Phase 8] — Federated Learning End-to-End Wiring — 2026-08-16
- Implemented `export_global_model_to_anomaly_format` in `app/federated_learning.py` to hot-swap Autoencoder weights into live `anomaly_models.pkl`.
- Added `POST /admin/run_federated_training` background dispatcher and `GET /admin/training_status` polling route.
- Created `scripts/docuvault-retrain.service` and `scripts/docuvault-retrain.timer` systemd pair.
- Added `tests/test_federated_pipeline.py`.

---

## [Phase 9] — Testing, Documentation & Deployment Hardening — 2026-08-16
- Completed comprehensive documentation: `docs/API.md` (all endpoints), `docs/DEMO.md` (presentation script), and refreshed `README.md`.
- Complete test suite created in `tests/` across security, cryptography, ZKP, blockchain signing, VC, watermarking, biometrics, and FL.

---

## [Superadmin & Protected Governance] — 2026-08-16
- Added `superadmin` role tier and `is_protected` boolean attribute on `User` in `app/database.py`.
- Created `AuditLog` model for immutable action history recording.
- Created `scripts/seed_superadmin.py` provisioning tool with Google OAuth email binding (`rudraksharma187@gmail.com`).
- Updated `app/auth.py` with `@reverify_2fa` step-up 2FA decorator (5-minute sliding window), `/auth/stepup_2fa` route, and server-side deletion prevention for protected accounts.
- Built dedicated `/superadmin` blueprint (`app/superadmin.py`) with raw Database Inspector, Blockchain Deep-Scanner, Audit Log timeline, and System Diagnostic hot-reloads.
- Built dedicated Dark Obsidian & Gold Command Center template in `app/templates/superadmin.html`.
- Added `tests/test_superadmin.py`.

