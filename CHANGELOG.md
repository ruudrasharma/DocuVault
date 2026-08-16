# DocuVault Changelog

All notable changes are documented here, one entry per phase.

---

## [Phase 0] — Safety Net — 2026-08-16

- Created `tests/` directory with `conftest.py` and `test_smoke.py`
- Added `requirements-dev.txt` (pytest, pytest-flask, pytest-cov, locust, pip-audit)
- Added `Makefile` with `make test` and `make lint` targets
- Added `CHANGELOG.md`
- Verified 5-test smoke suite passes against unmodified app

---

## [Phase 1] — Cleanup & De-duplication — 2026-08-16

- Removed dead modules: `app/routes.py`, `app/models.py`, `app/auth_checker.py`, `app/legacy_ocr.py`, duplicates (`ocr copy.py`, `ocr copy 2.py`, `ml_anomaly 2.py`).
- Consolidated `app/admin_cli.py` & `app/admin_cli_new.py` into `scripts/admin_cli.py`.
- Moved unintegrated Ray module to `future/ray_database.py` with explanatory `future/README.md`.
- Verified 0 dead module imports remain across `app/`.

---

## [Phase 2] — Critical Security Hardening — 2026-08-16

- Removed hardcoded fallback password list from `database.py` (strict hash + salt verification only).
- Removed universal TOTP bypass codes (`123456`, `000000`, `888888`, `999999`) from `database.py`.
- Removed candidate password list from `consent.py` (`get_user_private_key`).
- Removed auto-account-creation backdoor from login route in `auth.py`.
- Added startup check in `app/__init__.py` to refuse booting in production with placeholder `SECRET_KEY`.
- Added `Flask-Limiter` and `Flask-WTF` CSRF configurations.
- Added magic-byte sniffing (`_validate_upload`) and image dimension bounds checking (`_check_image_dimensions`) to `/upload` and `/verify_document` in `main.py`.
- Created `scripts/reset_demo_accounts.py` and `scripts/migrate_secure_passwords.py`.
- Added `tests/test_security.py`.

---
