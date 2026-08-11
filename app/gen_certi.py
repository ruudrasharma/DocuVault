from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os

data_dir = '/Users/rudra/Documents/SIH_Prototype/data'
os.makedirs(data_dir, exist_ok=True)

def generate_certificate(filename, name, roll, score, features_data, is_complex=False, is_fake=False):
    c = canvas.Canvas(os.path.join(data_dir, filename), pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2.0, height - inch, "Sample Academic Certificate")

    # Certification Statement
    c.setFont("Helvetica", 12)
    c.drawString(inch, height - 2 * inch, f"This is to certify that {name}, Roll Number: {roll}, has successfully completed the")
    c.drawString(inch, height - 2.25 * inch, f"examination with a score of {score}%. Issued on September 14, 2025.")

    # Features List
    c.setFont("Helvetica-Bold", 12)
    c.drawString(inch, height - 2.75 * inch, "Features Included for Testing Purposes:")
    c.setFont("Helvetica", 10)
    y = height - 3 * inch
    for i in range(1, 49):
        data = "Fake Data" if is_fake else "Sample Data"
        c.drawString(inch, y, f"Feature {i}: {data}")
        y -= 0.2 * inch
        if y < inch:
            c.showPage()
            y = height - inch

    # Complex elements
    if is_complex:
        # Border
        c.rect(0.5 * inch, 0.5 * inch, width - inch, height - inch)
        # Logo description
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(inch, 0.75 * inch, "Logo: [University Logo]")
        # Signature
        c.setFont("Helvetica", 12)
        c.drawString(width - 3 * inch, inch, "Signature: _____________________")

    c.save()

# Generate 2 originals
generate_certificate('simple_original.pdf', 'Rudra Sharma', '2025CSE001', '85', "Sample Data")
generate_certificate('complex_original.pdf', 'Rudra Sharma', '2025CSE001', '85', "Sample Data", is_complex=True)

# Generate 2 fakes
generate_certificate('simple_fake.pdf', 'Rudra Sharma', '2025CSE001', '150', "Fake Data", is_fake=True)
generate_certificate('complex_fake.pdf', 'Fake User', '999999', '200', "Fake Data", is_complex=True, is_fake=True)

print("4 certificates generated in data directory: simple_original.pdf, complex_original.pdf, simple_fake.pdf, complex_fake.pdf")