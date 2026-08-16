# DocuVault v2 API Reference
Comprehensive technical documentation for all HTTP endpoints.

---

## 1. Authentication (`/auth`)

### `POST /auth/login`
- **Auth**: Public (Rate limited: 5 / 15 min)
- **Body** (Form / JSON): `username`, `password`
- **Response**: `302 Redirect` to `/auth/verify_2fa`

### `POST /auth/verify_2fa`
- **Auth**: Session (Rate limited: 5 / 15 min)
- **Body** (Form / JSON): `totp` (6-digit TOTP code)
- **Response**: `302 Redirect` to `/dashboard/<role>`

### `GET /auth/logout`
- **Auth**: Session
- **Response**: `302 Redirect` to `/auth/login`

---

## 2. Document & Blockchain Verification (`/`)

### `POST /upload`
- **Auth**: Role `institution`, `admin`
- **Validation**: Magic-byte sniffing (`%PDF`, `JPEG`, `PNG`), Dimension cap ($\le 6000\times 6000$)
- **Form Data**: `file` (multipart binary), `holder_name`, `doc_type`, `issue_date`
- **Response** (JSON):
```json
{
  "success": true,
  "hash": "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba",
  "id": 18,
  "block_index": 22,
  "fields": { "name": "Rudra Sharma", "roll": "26144112" },
  "anomaly_analysis": { "is_anomaly": false, "status": "CLEAN" }
}
```

### `POST /verify_document`
- **Auth**: Role `verifier`, `admin`, `institution`, `citizen`
- **Form Data**: `file` (multipart binary)
- **Response** (JSON): Returns OCR fields, blockchain verification status, and multi-model AI anomaly analysis.

### `GET /verify_by_hash?h=<hash>&sig=<hmac>`
- **Auth**: Public (HMAC authenticated QR link)
- **Response**: Ledger status and metadata.

### `POST /verify_by_qr_image`
- **Auth**: Public
- **Form Data**: `file` (photo of a QR code)
- **Response**: Decoded hash and blockchain ledger status.

---

## 3. Citizen Wallet & Smart-Contract Consent (`/wallet`)

### `POST /wallet/issue`
- **Auth**: Role `institution`, `admin`
- **Form Data**: `file`, `owner_username`, `doc_type`
- **Process**: Envelope encryption with AES-GCM + RSA/PQC, records `wallet_issue` block on chain.

### `POST /wallet/grant`
- **Auth**: Document Owner
- **JSON**: `{"document_id": 1, "grantee_username": "hr_verifier", "duration_minutes": 60, "password": "..."}`
- **Process**: Records `grant` block on chain, wraps DEK for grantee.

### `POST /wallet/revoke`
- **Auth**: Document Owner
- **JSON**: `{"grant_id": 4}`
- **Process**: Records `revoke` block on chain.

### `POST /wallet/prove-claim`
- **Auth**: Document Owner
- **JSON**: `{"document_id": 1}`
- **Response**: Schnorr NIZK Zero-Knowledge Proof token `{commitment, e, z1, z2}` without exposing raw cert hash.

### `POST /wallet/verify-claim`
- **Auth**: Verifier
- **JSON**: `{"proof_data": { ... }}`
- **Response**: `{"verified": true, "zkp_valid": true}`

### `POST /wallet/enroll_face`
- **Auth**: Citizen
- **Form Data**: `selfie` (binary photo), `password`
- **Process**: Computes 128-d face embedding, stores encrypted embedding, discards raw photo.

### `POST /wallet/verify_face`
- **Auth**: Verifier
- **Form Data**: `photo`, `citizen_username`, `citizen_password`
- **Response**: `{"verified": true, "similarity_score": 0.88}`

---

## 4. Verifiable Credentials (`/vc`)

### `POST /vc/issue`
- **Auth**: Institution
- **JSON**: `{"cert_hash": "...", "holder_username": "...", "claims": { ... }}`
- **Response**: W3C-compliant Verifiable Credential JSON with Ed25519 signature.

### `POST /vc/verify`
- **Auth**: Public
- **JSON**: `{"vc": { ... }}`
- **Response**: `{"verified": true, "claims": { ... }}`

---

## 5. Administration & Federated Learning (`/admin`)

### `GET /admin/analytics`
- **Auth**: Admin
- **Response**: Aggregated counts for documents, verification queries, anomaly detection rates, and block totals.

### `POST /admin/run_federated_training`
- **Auth**: Admin
- **Response**: Launches asynchronous Federated Learning retraining job.

### `GET /admin/training_status`
- **Auth**: Admin
- **Response**: Live training status and FedAvg aggregation report.
