"""OCR layer.

Strategy:
- If MISTRAL_API_KEY is set → Mistral OCR API (best on French scanned docs).
- Else → Tesseract local (lang=fra), via pdf2image + pytesseract.
- Always returns: list[{"page": int, "text": str}].
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import httpx
from pypdf import PdfReader

from app.config import settings


@dataclass
class OcrPage:
    page: int
    text: str


@dataclass
class OcrResult:
    pages: list[OcrPage]
    full_text: str


def _is_pdf(mime: str) -> bool:
    return "pdf" in (mime or "").lower()


def _is_image(mime: str) -> bool:
    return (mime or "").startswith("image/")


async def ocr_document(data: bytes, mime_type: str) -> OcrResult:
    if settings.mistral_api_key:
        try:
            return await _ocr_mistral(data, mime_type)
        except Exception:  # noqa: BLE001
            # fallback gracefully
            pass
    return _ocr_local(data, mime_type)


async def _ocr_mistral(data: bytes, mime_type: str) -> OcrResult:
    """Calls Mistral OCR via REST.

    Mistral's OCR endpoint accepts a document URL or base64; we use base64
    via files API or document_url (depending on availability). Here we POST
    to https://api.mistral.ai/v1/ocr with a base64 document.
    """
    import base64

    b64 = base64.b64encode(data).decode("ascii")
    payload = {
        "model": settings.mistral_ocr_model,
        "document": {
            "type": "document_base64" if _is_pdf(mime_type) else "image_base64",
            "data": b64,
            "mime_type": mime_type,
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.mistral_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            "https://api.mistral.ai/v1/ocr", json=payload, headers=headers
        )
        resp.raise_for_status()
        body = resp.json()
    pages = []
    for i, p in enumerate(body.get("pages", []), start=1):
        text = p.get("markdown") or p.get("text") or ""
        pages.append(OcrPage(page=i, text=text))
    if not pages and "text" in body:
        pages = [OcrPage(page=1, text=body["text"])]
    full = "\n\n".join(p.text for p in pages)
    return OcrResult(pages=pages, full_text=full)


def _ocr_local(data: bytes, mime_type: str) -> OcrResult:
    if _is_pdf(mime_type):
        # 1) try text layer with pypdf (fast path)
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, p in enumerate(reader.pages, start=1):
                text = p.extract_text() or ""
                pages.append(OcrPage(page=i, text=text))
            joined = "\n\n".join(p.text for p in pages).strip()
            if len(joined) > 200:  # has a usable text layer
                return OcrResult(pages=pages, full_text=joined)
        except Exception:  # noqa: BLE001
            pass
        # 2) fallback: rasterize then tesseract
        return _ocr_pdf_tesseract(data)
    if _is_image(mime_type):
        return _ocr_image_tesseract(data)
    # text/plain etc.
    text = data.decode("utf-8", errors="replace")
    return OcrResult(pages=[OcrPage(page=1, text=text)], full_text=text)


def _ocr_pdf_tesseract(data: bytes) -> OcrResult:
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(data, dpi=200)
    pages: list[OcrPage] = []
    for i, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img, lang="fra")
        pages.append(OcrPage(page=i, text=text))
    return OcrResult(pages=pages, full_text="\n\n".join(p.text for p in pages))


def _ocr_image_tesseract(data: bytes) -> OcrResult:
    from PIL import Image
    import pytesseract

    img = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(img, lang="fra")
    return OcrResult(pages=[OcrPage(page=1, text=text)], full_text=text)
