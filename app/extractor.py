from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import fitz
import numpy as np


SUPPORTED_FILE_EXTENSIONS = {".pdf", ".txt"}
TEXT_LENGTH_THRESHOLD = 80
MAX_PDF_PAGES_FOR_OCR = 10


def extract_text(filename: str, content_type: str | None, payload: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    normalized_content_type = (content_type or "").lower()

    if suffix == ".pdf" or normalized_content_type == "application/pdf" or is_pdf_payload(payload):
        return extract_text_from_pdf(payload)

    if suffix == ".txt" or normalized_content_type.startswith("text/") or looks_like_text_payload(payload):
        return decode_text_payload(payload)

    allowed = ", ".join(sorted(SUPPORTED_FILE_EXTENSIONS))
    raise ValueError(f"Неподдерживаемый тип файла. Ожидаются: {allowed}")


def decode_text_payload(payload: bytes) -> str:
    if not payload:
        raise ValueError("Пустой текстовый файл")

    for encoding in ("utf-8", "utf-8-sig", "cp1251", "koi8-r"):
        try:
            text = payload.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text

    text = payload.decode("latin-1").strip()
    if not text:
        raise ValueError("Не удалось прочитать текст из файла")
    return text


def extract_text_from_pdf(payload: bytes) -> str:
    if not payload:
        raise ValueError("Пустой PDF-файл")

    with fitz.open(stream=payload, filetype="pdf") as pdf:
        text_parts = [page.get_text("text").strip() for page in pdf]
        joined = normalize_extracted_text("\n".join(part for part in text_parts if part))
        if len(joined) >= TEXT_LENGTH_THRESHOLD:
            return joined

        ocr_parts = []
        for page_index, page in enumerate(pdf):
            if page_index >= MAX_PDF_PAGES_FOR_OCR:
                break
            ocr_text = ocr_page(page)
            if ocr_text:
                ocr_parts.append(ocr_text)

    ocr_joined = normalize_extracted_text("\n".join(ocr_parts))
    if ocr_joined:
        return ocr_joined

    if joined:
        return joined

    raise ValueError("Не удалось извлечь текст из PDF")


def normalize_extracted_text(text: str) -> str:
    lines = [" ".join(line.replace("\xa0", " ").split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def ocr_page(page: fitz.Page) -> str:
    engine = get_ocr_engine()
    if engine is None:
        return ""

    matrix = fitz.Matrix(2.0, 2.0)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
    if pixmap.n > 3:
        image = image[:, :, :3]

    result, _ = engine(image)
    if not result:
        return ""

    lines: list[str] = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None
    return RapidOCR()


def is_pdf_payload(payload: bytes) -> bool:
    return payload.lstrip().startswith(b"%PDF-")


def looks_like_text_payload(payload: bytes) -> bool:
    if not payload:
        return False
    if is_pdf_payload(payload):
        return False

    sample = payload[:2048]
    if b"\x00" in sample:
        return False

    text_chars = sum(1 for byte in sample if byte in b"\t\n\r" or 32 <= byte <= 126 or byte >= 128)
    return text_chars / max(1, len(sample)) > 0.9
