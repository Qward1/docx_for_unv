# Dify Workflow Для `docx_service_for_unv`

Новая схема:

1. `Start`
2. `HTTP Request` -> `extract_pdf`
3. `Code` -> `parse_extract_json`
4. `LLM` -> `draft_response`
5. `Code` -> `normalize_json`
6. `HTTP Request` -> `render_docx`
7. `Answer`

## 1. Start

Входы:

- `application_pdf` -> `Single File`
- `instructions` -> `Paragraph` -> optional

## 2. HTTP Request -> extract_pdf

- `Method`: `POST`
- `URL`: `http://<SERVER-IP>:8011/extract`
- `Body`: `Binary`
- `Binary variable`: `application_pdf`
- `Headers`:
  - `Content-Type: application/pdf`
  - `X-Filename: application.pdf`

## 3. Code -> parse_extract_json

Входы:

- `body` = `extract_pdf.body`
- `status_code` = `extract_pdf.status_code`

```python
def main(body: str, status_code: int) -> dict:
    import json

    if status_code != 200:
        raise Exception(f"extract failed: {status_code}, body={body}")

    data = json.loads(body)
    return {
        "text": data.get("text", ""),
        "parsed": data.get("parsed", {}) or {},
    }
```

Выходы:

- `text` -> `String`
- `parsed` -> `Object`

## 4. LLM -> draft_response

Задача LLM:

- прочитать текст заявления из PDF;
- подготовить поля для шаблона МАИ;
- сгенерировать `body_text` ответа.

Structured Output:

```json
{
  "type": "object",
  "properties": {
    "recipient_block": { "type": "string" },
    "subject_title": { "type": "string" },
    "reference_caption": { "type": "string" },
    "salutation": { "type": "string" },
    "body_text": { "type": "string" }
  },
  "required": [
    "recipient_block",
    "subject_title",
    "reference_caption",
    "salutation",
    "body_text"
  ],
  "additionalProperties": false
}
```

## 5. Code -> normalize_json

Входы:

- `llm_output`
- `parsed`
- `original_text`

```python
def main(llm_output, parsed: dict, original_text: str) -> dict:
    import json

    def as_text(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = []
            for item in value:
                text = as_text(item)
                if text:
                    parts.append(text)
            return "\n\n".join(parts)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()

    data = {}
    if isinstance(llm_output, dict):
        data = llm_output
    elif isinstance(llm_output, str):
        raw = llm_output.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        if raw:
            data = json.loads(raw)

    parsed = parsed or {}

    return {
        "text": as_text(original_text),
        "recipient_block": as_text(data.get("recipient_block") or parsed.get("recipient_block")),
        "subject_title": as_text(data.get("subject_title") or parsed.get("subject_title")) or "О рассмотрении обращения",
        "reference_caption": as_text(data.get("reference_caption") or parsed.get("reference_caption")) or "На обращение абитуриента",
        "salutation": as_text(data.get("salutation") or parsed.get("salutation")) or "Уважаемый абитуриент!",
        "body_text": as_text(data.get("body_text") or parsed.get("body_text")),
    }
```

Выходы:

- `text` -> `String`
- `recipient_block` -> `String`
- `subject_title` -> `String`
- `reference_caption` -> `String`
- `salutation` -> `String`
- `body_text` -> `String`

## 6. HTTP Request -> render_docx

- `Method`: `POST`
- `URL`: `http://<SERVER-IP>:8011/generate`
- `Body`: `JSON`
- `Headers`:
  - `Content-Type: application/json`

```json
{
  "text": "{{parse_extract_json.text}}",
  "recipient_block": "{{normalize_json.recipient_block}}",
  "subject_title": "{{normalize_json.subject_title}}",
  "reference_caption": "{{normalize_json.reference_caption}}",
  "salutation": "{{normalize_json.salutation}}",
  "body_text": "{{normalize_json.body_text}}"
}
```

## 7. Answer

- текст: `Файл подготовлен.`
- файл: `render_docx.files`

`{{BODY_ECP}}` и `{{BODY_EXEC}}` Dify заполнять не нужно: микросервис очищает их сам.
