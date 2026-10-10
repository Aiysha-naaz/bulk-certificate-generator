import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUTPUT_DIR = os.getenv("CERT_OUTPUT_DIR", "./generated")


def generate_pdf(cert_id: str, name: str, event_name: str, issued_date: str,
                 course: str | None = None) -> str:
    """Render the single predefined template. Returns the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{cert_id}.pdf")
    width, height = landscape(A4)

    c = canvas.Canvas(path, pagesize=(width, height))
    c.setLineWidth(4)
    c.rect(30, 30, width - 60, height - 60)
    c.setLineWidth(1)
    c.rect(42, 42, width - 84, height - 84)

    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, height - 130, "Certificate of Completion")
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 190, "This is to certify that")
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(width / 2, height - 245, name)
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 300, "has successfully completed")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 340, course or event_name)
    if course:
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 370, f"as part of {event_name}")
    c.setFont("Helvetica", 12)
    c.drawString(80, 80, f"Date: {issued_date}")
    c.drawRightString(width - 80, 80, f"ID: {cert_id}")
    c.save()
    return path