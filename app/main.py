from __future__ import annotations

import io
import re
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .extractor import extract_text
from .models import LetterData, LetterOverrides
from .parser import parse_letter_data
from .templater import render_docx


app = FastAPI(
    title="UNV DOCX Response Generator",
    description=(
        "Микросервис принимает готовый текст ответа абитуриенту и возвращает "
        "оформленный DOCX-файл на основе шаблона приемной комиссии."
    ),
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = BASE_DIR / "shablon_unv.docx"
OUTPUT_FILENAME = "Ответ_абитуриенту.docx"
MAX_FILE_SIZE_MB = 20


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
async def extract_document_payload(request: Request):
    try:
        text, overrides = await parse_input(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        letter_data = parse_letter_data(text, overrides)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Ошибка извлечения данных: {exc}") from exc

    return {
        "text": text,
        "parsed": serialize_letter_data(letter_data),
    }


@app.post("/generate")
async def generate_document(request: Request):
    try:
        text, overrides = await parse_input(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        letter_data = parse_letter_data(text, overrides)
        document = render_docx(TEMPLATE_PATH, letter_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Ошибка генерации DOCX: {exc}") from exc

    output_filename = build_output_filename(letter_data)
    headers = {"Content-Disposition": build_content_disposition(output_filename)}
    return StreamingResponse(
        io.BytesIO(document),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


async def parse_input(request: Request) -> tuple[str, LetterOverrides]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("JSON-тело должно быть объектом")
        text = normalize_text_field(payload.get("text")) or normalize_text_field(payload.get("body_text"))
        if not text:
            raise ValueError("В JSON-запросе требуется поле text или body_text")
        return text, LetterOverrides.from_mapping(payload)

    if "multipart/form-data" in content_type:
        form = await request.form()
        overrides = LetterOverrides.from_mapping(
            {
                key: value
                for key, value in form.multi_items()
                if not hasattr(value, "filename")
            }
        )

        raw_text = normalize_text_field(form.get("text")) or normalize_text_field(form.get("body_text"))
        file_obj = form.get("file")

        if raw_text:
            return raw_text, overrides

        if file_obj is None or not hasattr(file_obj, "read"):
            raise ValueError("Нужно передать либо text, либо file")

        try:
            file_bytes = await file_obj.read()
            validate_payload_size(file_bytes)

            extracted = extract_text(
                filename=getattr(file_obj, "filename", ""),
                content_type=getattr(file_obj, "content_type", None),
                payload=file_bytes,
            )
            return extracted, overrides
        finally:
            close_method = getattr(file_obj, "close", None)
            if close_method is not None:
                await close_method()

    raw_payload = await request.body()
    validate_payload_size(raw_payload)
    extracted = extract_text(
        filename=extract_filename_from_headers(request),
        content_type=content_type,
        payload=raw_payload,
    )
    return extracted, LetterOverrides()


def normalize_text_field(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_payload_size(payload: bytes) -> None:
    if not payload:
        raise ValueError("Передан пустой файл")
    if len(payload) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Файл слишком большой. Максимум: {MAX_FILE_SIZE_MB} MB")


def extract_filename_from_headers(request: Request) -> str:
    direct = request.headers.get("x-filename")
    if direct:
        return direct

    content_disposition = request.headers.get("content-disposition", "")
    marker = "filename="
    if marker not in content_disposition:
        return ""

    filename = content_disposition.split(marker, 1)[1].strip().strip('"')
    return filename


def build_output_filename(data: LetterData) -> str:
    applicant_part = sanitize_filename_part(data.applicant_display)
    if not applicant_part:
        return OUTPUT_FILENAME
    return f"Ответ_{applicant_part}.docx"


def sanitize_filename_part(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", value or "")
    sanitized = re.sub(r"\s+", "_", sanitized).strip(" ._")
    return sanitized[:80]


def build_content_disposition(filename: str) -> str:
    ascii_fallback = "response.docx"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


def serialize_letter_data(data: LetterData) -> dict[str, object]:
    return {
        "applicant_name": data.applicant_display,
        "applicant_email": data.applicant_email,
        "recipient_block": data.recipient_block,
        "subject_title": data.subject_title,
        "source_line1": data.source_line1,
        "source_line2": data.source_line2,
        "reference_line": data.reference_line,
        "reference_caption": data.reference_caption,
        "salutation": data.salutation,
        "body_text": "\n\n".join(data.body_paragraphs),
        "body_paragraphs": data.body_paragraphs,
        "signer_title": data.signer_title,
        "signer_department": data.signer_department,
        "signer_name": data.signer_name,
        "executor_name": data.executor_name,
        "executor_phone": data.executor_phone,
        "executor_department": " ".join(
            part for part in [data.executor_department_line1, data.executor_department_line2] if part
        ),
        "topic": data.topic,
    }
