# main.py
"""FastAPI app that receives Tally webhook and sends extracted Excel via SendGrid."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from typing import List

import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from utils import (
    download_file_bytes,
    extract_invoice_fields_from_bytes,
    send_sendgrid_email_with_attachment,
    verify_tally_signature,
    PDFInfoNotInstalledError,
)

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="Tally Invoice Processor - Cleaned")


def find_urls(obj) -> List[str]:
    """Recursively find file URLs in a payload."""
    urls: List[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            urls.extend(find_urls(v))
    elif isinstance(obj, list):
        for it in obj:
            urls.extend(find_urls(it))
    elif isinstance(obj, str):
        if obj.startswith("http") and any(
            ext in obj.lower() for ext in (".pdf", ".jpg", ".jpeg", ".png")
        ):
            urls.append(obj)
    return urls


@app.post("/tally-webhook")
async def tally_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    signature = request.headers.get("Tally-Signature", "")
    if not verify_tally_signature(raw_body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        logger.exception("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    email = payload.get("email") or payload.get("response", {}).get("email")
    name = (
        payload.get("name")
        or payload.get("company")
        or payload.get("response", {}).get("name")
    )
    consent = payload.get("consent", True)

    file_urls: List[str] = []
    if "files" in payload:
        files = payload["files"]
        if isinstance(files, list):
            file_urls.extend(files)
        elif isinstance(files, str):
            file_urls.append(files)

    file_urls.extend(find_urls(payload))
    file_urls = list(dict.fromkeys(file_urls))

    if not consent:
        return JSONResponse({"status": "no_consent"}, status_code=200)
    if not email or not file_urls:
        logger.warning("Missing email or files in payload")
        raise HTTPException(status_code=400, detail="Missing email or files")

    extracted_rows: List[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for idx, url in enumerate(file_urls):
        try:
            file_bytes = download_file_bytes(url)
        except requests.exceptions.RequestException:
            logger.exception("Failed to download %s", url)
            continue

        # extract_invoice_fields_from_bytes is robust and returns a list (even on OCR faults)
        try:
            parsed_list = extract_invoice_fields_from_bytes(
                file_bytes, filename=f"file_{idx}"
            )
        except PDFInfoNotInstalledError:
            # poppler missing: treat as configuration error
            logger.exception("Server misconfiguration: poppler/pdftoppm not installed")
            raise HTTPException(
                status_code=500,
                detail="Server missing pdftoppm/poppler for PDF processing",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            # handle expected runtime errors specifically
            logger.exception("Extraction error for %s: %s", url, exc)
            parsed_list = []

        for parsed in parsed_list:
            row = {
                "Timestamp": timestamp,
                "Nom": name or parsed.get("Nom", ""),
                "NomFournisseur": parsed.get("NomFournisseur", ""),
                "DateFacture": parsed.get("DateFacture", ""),
                "NumFacture": parsed.get("NumFacture", ""),
                "TotalHT": parsed.get("TotalHT", ""),
                "TotalTTC": parsed.get("TotalTTC", ""),
                "TVA": parsed.get("TVA", ""),
            }
            extracted_rows.append(row)

    if not extracted_rows:
        logger.warning("No invoice data extracted")
        return JSONResponse({"status": "no_data_extracted"}, status_code=200)

    # Create Excel in a temporary file to avoid static type checker BytesIO warnings
    df = pd.DataFrame(
        extracted_rows,
        columns=[
            "Timestamp",
            "Nom",
            "NomFournisseur",
            "DateFacture",
            "NumFacture",
            "TotalHT",
            "TotalTTC",
            "TVA",
        ],
    )

    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
            df.to_excel(tmp.name, index=False)
            tmp.flush()
            tmp.seek(0)
            excel_bytes = tmp.read()
    except (OSError, ValueError) as exc:
        logger.exception("Failed to generate Excel: %s", exc)
        raise HTTPException(status_code=500, detail="Excel generation failed")

    filename = (
        f"tally_invoices_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.xlsx"
    )
    subject = "Analyse de vos factures : résultat disponible"
    html_content = (
        "<p>Bonjour,</p>"
        "<p>L'analyse de votre/vos factures a été exécutée avec succès. Le fichier Excel est en pièce jointe.</p>"
    )

    try:
        send_sendgrid_email_with_attachment(
            email, subject, html_content, filename, excel_bytes
        )
    except RuntimeError:
        logger.exception("SendGrid sending failed")
        return JSONResponse({"status": "email_failed"}, status_code=200)

    return JSONResponse({"status": "ok", "filename": filename}, status_code=200)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "_main_":
    import uvicorn
    import os

    uvicorn.run(
        "main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=True
    )
