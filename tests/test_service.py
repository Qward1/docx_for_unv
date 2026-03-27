from __future__ import annotations

import json
import socket
import threading
import time
import unittest
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

import uvicorn
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.main import app


FONT_PATH = Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
FONT_NAME = "TimesNRTest"
if FONT_PATH.exists():
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))
else:  # pragma: no cover
    FONT_NAME = "Helvetica"


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def build_multipart_body(
    fields: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = "----docx-service-boundary"
    chunks: list[bytes] = []

    for key, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(content)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def build_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont(FONT_NAME, 12)
    y = 800
    for line in text.splitlines():
        pdf.drawString(72, y, line)
        y -= 18
    pdf.save()
    return buffer.getvalue()


def extract_document_xml(payload: bytes) -> str:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


class UvicornServer:
    def __init__(self) -> None:
        self.port = get_free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app=app, host="127.0.0.1", port=self.port, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.time() + 10.0
        while not self.server.started:
            if time.time() > deadline:
                raise TimeoutError("Uvicorn did not start in time")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10.0)


class GenerateEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.http_server = UvicornServer()
        cls.http_server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.http_server.stop()

    def test_generate_from_json_returns_docx(self) -> None:
        payload = {
            "text": (
                "Заявитель: Иванов Иван Иванович\n"
                "Тема: О предоставлении разъяснений по мерам поддержки малого бизнеса.\n"
                "Просим рассмотреть обращение и дать письменный ответ."
            ),
            "reference_line": "от 9 января 2025 г. № П48-5533-1",
            "body_text": "Первый абзац ответа.\n\nВторой абзац ответа.",
        }
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.http_server.port}/generate",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            content_disposition = response.headers.get("Content-Disposition", "")
            document = response.read()

        self.assertEqual(
            content_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("filename*=UTF-8''", content_disposition)
        self.assertIn("%D0%9E%D1%82%D0%B2%D0%B5%D1%82_%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2_%D0%98.%D0%98.docx", content_disposition)
        xml = extract_document_xml(document)
        self.assertIn("Иванов И.И.", xml)
        self.assertIn("Уважаемый Иван Иванович!", xml)
        self.assertIn("Первый абзац ответа.", xml)
        self.assertIn("Второй абзац ответа.", xml)
        self.assertIn("На обращение гражданина от 9 января 2025 г. № П48-5533-1", xml)
        self.assertIn("МИНИСТЕРСТВО ЭКОНОМИЧЕСКОГО РАЗВИТИЯ", xml)
        self.assertNotIn("FF0000", xml)

    def test_generate_splits_single_body_text_into_multiple_paragraphs(self) -> None:
        payload = {
            "text": (
                "Заявитель: Рулёв Никита Сергеевич\n"
                "Тема: О представлении информации об экономическом развитии государства.\n"
                "Просим предоставить разъяснения."
            ),
            "body_text": (
                "Минэкономразвития России рассмотрело Ваше обращение и в части своей компетенции сообщает. "
                "В соответствии с Указом Президента Российской Федерации от 7 мая 2024 г. № 309 утверждены национальные цели развития. "
                "Правительством Российской Федерации утвержден Единый план по достижению национальных целей. "
                "Учитывая изложенное, сообщаем, что работа продолжается."
            ),
        }
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.http_server.port}/generate",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            document = response.read()

        xml = extract_document_xml(document)
        self.assertIn("Минэкономразвития России рассмотрело Ваше обращение и в части своей компетенции сообщает.", xml)
        self.assertIn("В соответствии с Указом Президента Российской Федерации от 7 мая 2024 г. № 309 утверждены национальные цели развития.", xml)
        self.assertIn("Правительством Российской Федерации утвержден Единый план по достижению национальных целей.", xml)
        self.assertIn("Учитывая изложенное, сообщаем, что работа продолжается.", xml)

    def test_generate_applies_custom_signature_fields(self) -> None:
        payload = {
            "text": (
                "Заявитель: Иванов Иван Иванович\n"
                "Тема: О предоставлении информации.\n"
                "Просим дать ответ."
            ),
            "signer_title": "Заместитель директора",
            "signer_department": "Департамент бюджетного планирования, государственных программ и национальных проектов",
            "signer_name": "А.А. Петров",
        }
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.http_server.port}/generate",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            document = response.read()

        xml = extract_document_xml(document)
        self.assertIn("Заместитель директора Департамента бюджетного планирования, государственных программ", xml)
        self.assertIn("и национальных проектов", xml)
        self.assertIn("А.А. Петров", xml)

    def test_generate_from_pdf_extracts_text(self) -> None:
        pdf_text = (
            "Письмо Аппарата Правительства Российской Федерации от 9 января 2025 г. № П48-5533-1\n"
            "Заявитель: Петров Петр Петрович\n"
            "Тема: О совершенствовании механизмов поддержки экспортеров.\n"
            "В обращении изложены предложения по доработке действующих мер поддержки."
        )
        body, boundary = build_multipart_body(
            fields={},
            filename="appeal.pdf",
            content=build_pdf(pdf_text),
            content_type="application/pdf",
        )
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.http_server.port}/generate",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            document = response.read()

        xml = extract_document_xml(document)
        self.assertIn("Петров П.П.", xml)
        self.assertIn("Уважаемый Петр Петрович!", xml)
        self.assertIn("На обращение гражданина от 9 января 2025 г. № П48-5533-1", xml)
        self.assertIn("МИНИСТЕРСТВО ЭКОНОМИЧЕСКОГО РАЗВИТИЯ", xml)

    def test_extract_from_raw_pdf_returns_text_and_fields(self) -> None:
        pdf_text = (
            "Письмо Аппарата Правительства Российской Федерации от 9 января 2025 г. № П48-5533-1\n"
            "Заявитель: Сидоров Семен Семенович\n"
            "Тема: О корректировке мер поддержки региональных проектов.\n"
            "Просим рассмотреть изложенные предложения."
        )
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.http_server.port}/extract",
            data=build_pdf(pdf_text),
            method="POST",
            headers={"Content-Type": "application/pdf", "X-Filename": "appeal.pdf"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertIn("Сидоров Семен Семенович", payload["text"])
        self.assertEqual(payload["parsed"]["applicant_name"], "Сидоров С.С.")
        self.assertEqual(payload["parsed"]["reference_line"], "от 9 января 2025 г. № П48-5533-1")
        self.assertEqual(payload["parsed"]["source_line1"], "Письмо Аппарата Правительства")
        self.assertEqual(payload["parsed"]["source_line2"], "Российской Федерации")


if __name__ == "__main__":
    unittest.main()
