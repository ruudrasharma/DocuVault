# DocuVault Makefile

.PHONY: test lint audit install-dev server

# Run full test suite with coverage
test:
	pytest -v --cov=app --cov-report=term-missing tests/

# Run only smoke tests (fastest sanity check)
smoke:
	pytest -v tests/test_smoke.py

# Run specific phase tests
test-security:
	pytest -v tests/test_security.py

test-pqc:
	pytest -v tests/test_pqc.py

test-zkp:
	pytest -v tests/test_zkp.py

test-blockchain:
	pytest -v tests/test_blockchain_signing.py

# Install dev dependencies
install-dev:
	pip install -r requirements-dev.txt

# Security audit of production dependencies
audit:
	pip-audit -r requirements.txt

# Run dev server (port 5001)
server:
	python run.py

# Check for backdoor strings (should return nothing in app/ except test files)
check-backdoors:
	@echo "=== Scanning for hardcoded backdoor credentials ==="
	@grep -rn "123456\|888888\|999999\|Admin@1234\|admin123\|DefaultWalletPass\|known_passwords" app/ \
		|| echo "✓ Clean — no backdoor strings found in app/"
