# utils.py
"""Utilities: download files, convert PDF/image -> OCR text, extract fields, send email (SendGrid)."""

from __future__ import annotations

import base64
import io
import logging
import re
import hmac
import hashlib
from datetime import datetime, timezone
from typing import List, Optional

import requests
from PIL import Image, UnidentifiedImageError
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
)
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "no-reply@example.com")
TALLY_SECRET = os.getenv("TALLY_SECRET", "")
POPPLER_PATH = os.getenv("POPPLER_PATH")  # optional for Windows
OCR_LANGS = os.getenv("OCR_LANGS", "fra+eng")

# ---- Regex patterns (clean, raw strings) ----

RE_DATE = re.compile(r"\b(?:\d{2}[/\-.]\d{2}[/\-.]\d{4}|\d{4}[/\-.]\d{2}[/\-.]\d{2})\b")
RE_TVA = re.compile(r"TVA[:\s]*([0-9.,]{1,20}%?)", re.IGNORECASE)
RE_TOTAL = re.compile(r"Total\s*(?:TTC|HT)?[:\s]*([0-9.,\s€]{1,30})", re.IGNORECASE)
RE_NUMFACT = re.compile(
    r"(?:Facture\s*(?:n[o°]?)?[:\s\-]|N[°o]\s[:#\s-]*)([A-Za-z0-9\-/_.]+)",
    re.IGNORECASE,
)
RE_SUPPLIER = re.compile(
    r"(?:Fournisseur|Soci[eé]t[eé]|Vendeur|Émetteur)[:\s]*([A-Za-z0-9 \-.,&]+)",
    re.IGNORECASE,
)


# ---- Utilities ----
def verify_tally_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify HMAC signature if TALLY_SECRET is configured."""
    if not TALLY_SECRET:
        return True
    try:
        mac = hmac.new(TALLY_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, signature_header)
    except Exception:  # L100: except Exception: (Garde large pour robustesse du wrapper)
        logger.exception("Signature verification error")
        return False


def download_file_bytes(url: str, timeout: int = 30) -> bytes:
    """Download a file and return its bytes. Raises requests.exceptions.RequestException on error."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


# ---- PDF / image -> OCR text pipeline (robust) ----
def images_from_pdf_bytes(file_bytes: bytes, poppler_path: Optional[str] = None) -> List[Image.Image]:
    """
    Convert PDF bytes to a list of PIL Images.
    If conversion fails because poppler is missing, PDFInfoNotInstalledError is raised.
    If not a PDF, attempt to open with PIL.
    """
    try:
        if poppler_path:
            images = convert_from_bytes(file_bytes, poppler_path=poppler_path)
        else:
            images = convert_from_bytes(file_bytes)
        return images
    except PDFInfoNotInstalledError:
        logger.error("Poppler/pdftoppm is not installed or not found.")
        raise
    except UnidentifiedImageError:
        logger.exception("File is not a valid image")
        raise
    except Exception:
        # fallback: try to open as image
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            return [img]
        except UnidentifiedImageError:
            logger.exception("File is neither a valid PDF nor a recognizable image")
            raise


def ocr_images_to_text(images: List[Image.Image]) -> str:
    """Run Tesseract OCR on provided images and return concatenated text."""
    pages: List[str] = []
    try:
        import pytesseract  # local import so we can reference Tesseract errors if needed
    except Exception:
        logger.exception("pytesseract is not installed or not available")
        # return empty text: calling code will still produce an Excel with empty fields
        return ""

    for i, img in enumerate(images, start=1):
        try:
            txt = pytesseract.image_to_string(img, lang=OCR_LANGS)
            pages.append(f"---PAGE_{i}---\n{txt}")
        except Exception as e:
            logger.exception("OCR failed on page %d: %s", i, e)
            pages.append("")
    return "\n".join(pages)


# ---- Heuristics extraction ----
def find_first_date(text: str) -> str:
    m = RE_DATE.search(text)
    return m.group(0) if m else ""


def find_invoice_number(text: str) -> str:
    m = RE_NUMFACT.search(text)
    return m.group(1).strip() if m else ""


def find_totals_and_tva(text: str) -> tuple[str, str, str]:
    tva = ""
    total_ht = ""
    total_ttc = ""
    m_tva = RE_TVA.search(text)
    if m_tva:
        tva = m_tva.group(1).strip()
    for m in RE_TOTAL.finditer(text):
        value = m.group(1).strip()
        # L151: PEP 8: E203 whitespace before ':' corrigé
        before = text[max(0, m.start() - 15):m.start()].upper()
        if "TTC" in before:
            total_ttc = value
        elif "HT" in before:
            total_ht = value
        elif not total_ttc:
            total_ttc = value
    return total_ht, total_ttc, tva


def find_supplier_name(text: str) -> str:
    m = RE_SUPPLIER.search(text)
    if m:
        return m.group(1).strip()
    for line in text.splitlines():
        candidate = line.strip()
        if len(candidate) > 3 and not re.search(r"facture|total|tva|client", candidate, re.IGNORECASE):
            return candidate
    return ""


def find_client_name(text: str) -> str:
    m = re.search(r"(Factur(?:é|ee)\s+à|Client[:\s])\s*(.+)", text, re.IGNORECASE)
    if m:
        return m.group(2).strip().splitlines()[0]
    return ""


def extract_invoice_fields_from_bytes(file_bytes: bytes, filename: str = "file") -> List[dict]:
    """
    Robust extraction: ALWAYS returns a list with one dict (fields may be empty).
    This function logs OCR failures and returns empty fields instead of raising broad exceptions.
    """
    try:
        images = images_from_pdf_bytes(file_bytes, poppler_path=POPPLER_PATH)
        ocr_text = ocr_images_to_text(images)
    except PDFInfoNotInstalledError:
        logger.exception("Poppler not available - OCR cannot run")
        raise
    except (UnidentifiedImageError, ValueError, OSError) as exc:
        logger.exception("OCR pipeline error for %s: %s", filename, exc)
        ocr_text = ""
    except Exception as e:
        logger.exception("Unexpected OCR pipeline exception for %s: %s", filename, e)
        ocr_text = ""

    date = find_first_date(ocr_text)
    # L203: Correction Typo (numfact -> num_fact)
    num_fact = find_invoice_number(ocr_text)
    total_ht, total_ttc, tva = find_totals_and_tva(ocr_text)
    supplier = find_supplier_name(ocr_text)
    client = find_client_name(ocr_text)

    result = {
        "Timestamp": datetime.now(timezone.utc).isoformat(),
        "Nom": client or "",
        "NomFournisseur": supplier or "",
        "DateFacture": date or "",
        "NumFacture": num_fact or "",
        "TotalHT": total_ht or "",
        "TotalTTC": total_ttc or "",
        "TVA": tva or "",
    }
    return [result]


# ---- SendGrid helper (attachment) ----
def send_sendgrid_email_with_attachment(
    to_email: str, subject: str, html_content: str, filename: str, file_bytes: bytes
) -> int:
    """Send email via SendGrid with file attached (base64)."""
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured")

    encoded = base64.b64encode(file_bytes).decode()

    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    attachment.file_name = FileName(filename)
    attachment.disposition = Disposition("attachment")

    message = Mail(from_email=SENDER_EMAIL, to_emails=to_email, subject=subject, html_content=html_content)
    message.attachment = attachment

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        resp = sg.send(message)
        logger.info("SendGrid response status: %s", getattr(resp, "status_code", "unknown"))
        return getattr(resp, "status_code", 202)
    except Exception:
        logger.exception("SendGrid send failed")
        raise RuntimeError("SendGrid send failed")
