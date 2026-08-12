# DocuVault OCR Service

Standalone OCR microservice running on port **5002**, separate from the main DocuVault app.

## Stack
- **EasyOCR** — primary engine (deep learning, high accuracy, supports Hindi + English)
- **Tesseract** — fallback engine (classical OCR)
- **Flask** — lightweight API wrapper

## Endpoints

### `GET /health`
Returns engine status.
```json
{"status": "ok", "engines": {"easyocr": true, "tesseract": true}}
```

### `POST /ocr`
Extract raw text from a document.
```bash
curl -X POST http://localhost:5002/ocr \
  -F "file=@certificate.pdf"
```
Response:
```json
{
  "text": "This is to certify that Rudra Sharma...",
  "engine": "easyocr",
  "confidence": 0.93,
  "pages": 1,
  "chars": 512
}
```

### `POST /ocr/fields`
Extract structured fields (name, degree, date, institute, grade, roll_no).
```bash
curl -X POST http://localhost:5002/ocr/fields \
  -F "file=@degree_cert.jpg"
```
Response:
```json
{
  "text": "...",
  "fields": {
    "name": "Rudra Sharma",
    "degree": "Bachelor of Technology",
    "date": "15/05/2024",
    "institute": "IIT Bombay"
  },
  "engine": "easyocr",
  "confidence": 0.91
}
```

## Supported Formats
PDF, JPG, JPEG, PNG, BMP, TIFF, WEBP

## Integration with DocuVault (Python)
```python
import requests

def extract_from_document(file_path):
    with open(file_path, 'rb') as f:
        r = requests.post('http://localhost:5002/ocr/fields', files={'file': f})
    return r.json()  # {'text': '...', 'fields': {...}}
```

## Service Management
```bash
sudo systemctl status docuvault-ocr
sudo systemctl restart docuvault-ocr
sudo journalctl -u docuvault-ocr -f      # live logs
```
