from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SUBJECT_TITLE = "О рассмотрении обращения"
DEFAULT_SOURCE_LINE_1 = "Обращение абитуриента"
DEFAULT_SOURCE_LINE_2 = "поступившее в приемную комиссию"
DEFAULT_REFERENCE_LINE = "Реквизиты входящего обращения"
DEFAULT_REFERENCE_CAPTION = "На обращение абитуриента"
DEFAULT_SALUTATION = "Уважаемый абитуриент!"
DEFAULT_SIGNER_TITLE = "Ректор"
DEFAULT_SIGNER_NAME = "М.А. Погосян"
DEFAULT_EXECUTOR_NAME = ""
DEFAULT_EXECUTOR_PHONE = ""
DEFAULT_EXECUTOR_DEPARTMENT = (
    "Приемная комиссия"
)


@dataclass(slots=True)
class LetterOverrides:
    applicant_name: str | None = None
    recipient_block: str | None = None
    subject_title: str | None = None
    source_title: str | None = None
    source_line1: str | None = None
    source_line2: str | None = None
    reference_line: str | None = None
    reference_caption: str | None = None
    salutation: str | None = None
    body_text: str | None = None
    signer_title: str | None = None
    signer_department: str | None = None
    signer_name: str | None = None
    executor_name: str | None = None
    executor_phone: str | None = None
    executor_department: str | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "LetterOverrides":
        def pick(key: str) -> str | None:
            value = payload.get(key)
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        return cls(
            applicant_name=pick("applicant_name"),
            recipient_block=pick("recipient_block"),
            subject_title=pick("subject_title"),
            source_title=pick("source_title"),
            source_line1=pick("source_line1"),
            source_line2=pick("source_line2"),
            reference_line=pick("reference_line"),
            reference_caption=pick("reference_caption"),
            salutation=pick("salutation"),
            body_text=pick("body_text"),
            signer_title=pick("signer_title"),
            signer_department=pick("signer_department"),
            signer_name=pick("signer_name"),
            executor_name=pick("executor_name"),
            executor_phone=pick("executor_phone"),
            executor_department=pick("executor_department"),
        )


@dataclass(slots=True)
class LetterData:
    applicant_display: str
    applicant_email: str | None
    recipient_block: str
    subject_title: str
    source_line1: str
    source_line2: str
    reference_line: str
    reference_caption: str
    salutation: str
    body_paragraphs: list[str]
    signer_title: str
    signer_department: str
    signer_name: str
    executor_name: str
    executor_phone: str
    executor_department_line1: str
    executor_department_line2: str
    extracted_text: str
    topic: str | None = None
