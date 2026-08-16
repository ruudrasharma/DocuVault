# National Registry Integration Interface Specification
### Standard Interface Contract for DigiLocker / NAD / National Identity Systems

## 1. Overview
This document defines the standardized request/response schema and cryptographic auth model for integrating DocuVault with external National Document Registries (e.g., DigiLocker, National Academic Depository (NAD), e-Pramaan).

---

## 2. Authentication & Trust Model
All requests between DocuVault and the National Gateway MUST be authenticated using:
1. **Mutual TLS (mTLS)**: X.509 client certificates issued by the designated National Root CA.
2. **Ed25519 Payload Signing**: All API payloads must carry an `X-National-Signature` HTTP header signed by the institution's registered Ed25519 keypair.
3. **OAuth 2.0 / OIDC Bearer Tokens**: Scoped access tokens (`scope: document:read document:verify`).

---

## 3. API Contract

### 3.1 Document Verification Query
- **Endpoint**: `POST /api/v1/national/verify`
- **Headers**:
  - `Content-Type: application/json`
  - `X-National-Signature: <hex-ed25519-sig>`
  - `X-Institution-DID: did:docuvault:issuer:<id>`

#### Request Payload:
```json
{
  "queryType": "CERTIFICATE_HASH",
  "certificateHash": "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba",
  "documentType": "DEGREE_CERTIFICATE",
  "issuerRegistryCode": "CBSE_IN",
  "zkpProof": {
    "commitment": "123456...:789012...",
    "scheme": "schnorr-nizk-bn128"
  }
}
```

#### Response Payload (200 OK):
```json
{
  "status": "VALID",
  "registryRecordId": "NAT-DOC-2026-981240",
  "issuanceTimestamp": "2026-05-14T10:00:00Z",
  "canonicalHash": "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba",
  "issuer": {
    "name": "Central Board of Secondary Education",
    "did": "did:india:gov:cbse",
    "verified": true
  },
  "revocationStatus": {
    "isRevoked": false,
    "revocationDate": null
  }
}
```

---

## 4. Error Codes

| Code | Meaning | Description |
|---|---|---|
| `REGISTRY_RECORD_NOT_FOUND` | 404 | Document hash does not exist in national ledger |
| `SIGNATURE_INVALID` | 401 | Ed25519 header signature verification failed |
| `DOC_REVOKED` | 409 | Document was explicitly revoked by issuing authority |
