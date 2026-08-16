# DocuVault v2 — Rehearsed Demonstration Script
### Hackathon & Presentation Walkthrough Guide

---

## Act 1: Institution Issuance & Security
1. **Login as Institution** (`institution` / `Inst@DocuVault2026!`).
2. **Issue Document**:
   - Upload a genuine certificate (`marksheet.jpg`).
   - Highlight the **multi-layer processing**:
     - OCR extraction
     - Canonical SHA-256 hash
     - AI Anomaly check
     - BN128 Pedersen Commitment
     - Post-Quantum Cryptography (ML-KEM-768 hybrid key wrapping)
     - Ed25519 Cryptographic Block Signing onto the immutable ledger.
3. Show **W3C Verifiable Credential** JSON output and QR code.

---

## Act 2: Citizen Privacy & Smart-Contract Consent
1. **Login as Citizen** (`citizen` / `Citizen@DocuVault2026!`).
2. **Wallet Access**: View encrypted document at rest.
3. **Time-Limited Access Grant**:
   - Grant access to `verifier` for 30 minutes.
   - Show how the smart-contract access grant is recorded on the blockchain.
4. **Selective Disclosure with Zero-Knowledge Proof**:
   - Click **Generate ZKP Proof**.
   - Show the Schnorr NIZK proof token `{commitment, e, z1, z2}`.
   - Point out: **The raw hash and document contents are never revealed to the verifier!**

---

## Act 3: Verification & AI Anomaly Defense
1. **Login as Verifier** (`verifier` / `Verify@DocuVault2026!`).
2. **Verify Genuine Document**:
   - Upload `marksheet.jpg`.
   - Result: `✓ VERIFIED ON BLOCKCHAIN` + `✓ AI VERIFIED CLEAN` (Scan noise is accurately distinguished from tampering).
3. **Verify Tampered / Fake Document**:
   - Upload `marksheet1.jpg` (fake / synthetic document).
   - Result: `✗ NOT VERIFIED` + `⚠️ TAMPER RISK DETECTED` (Isolation Forest / ELA flags synthetic forgery).

---

## Act 4: Admin Governance & Federated Learning
1. **Login as Admin** (`admin` / `Admin@DocuVault2026!`).
2. **Blockchain Ledger**:
   - View signed blocks with Ed25519 signature validity checkmarks.
3. **Analytics Dashboard**:
   - Review live verification counts, anomaly rates, and document statistics.
4. **Federated Learning Retraining**:
   - Trigger **Run Federated Retraining**.
   - Show real-time FedAvg multi-client training progress without centralizing sensitive student documents.
