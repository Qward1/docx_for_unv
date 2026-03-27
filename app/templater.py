from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import LetterData


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}

ET.register_namespace("w", W_NS)
ET.register_namespace("xml", XML_NS)

DOCUMENT_XML_PATH = "word/document.xml"
BODY_PLACEHOLDER_START = "{{BODY_START}}"
BODY_PLACEHOLDER_END = "{{BODY_END}}"


def render_docx(template_path: Path, data: LetterData) -> bytes:
    with zipfile.ZipFile(template_path, "r") as source:
        archive_map = {name: source.read(name) for name in source.namelist()}

    root = ET.fromstring(archive_map[DOCUMENT_XML_PATH])

    replace_special_paragraphs(root, data)
    replace_paragraph_texts(
        root,
        {
            "Т.С. Митюков": data.signer_name,
            "Исп. Шишкин Е.Н.": f"Исп. {data.executor_name}",
            "8 (495) 870-29-21 доб. 18569": data.executor_phone,
        },
    )
    replace_signature_department(root, data)
    replace_body_paragraphs(root, data.body_paragraphs)
    tighten_trailing_layout(root, data)
    turn_red_text_black(root)

    archive_map[DOCUMENT_XML_PATH] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as destination:
        for name, payload in archive_map.items():
            destination.writestr(name, payload)
    return output.getvalue()


def replace_paragraph_texts(root: ET.Element, replacements: dict[str, str]) -> None:
    for paragraph in root.findall(".//w:p", NS):
        current = paragraph_text(paragraph)
        if current in replacements:
            rewrite_paragraph(paragraph, replacements[current])


def replace_special_paragraphs(root: ET.Element, data: LetterData) -> None:
    for paragraph in root.findall(".//w:p", NS):
        current = paragraph_text(paragraph)
        if current == "{{RECIPIENT_BLOCK}}":
            rewrite_recipient_paragraph(paragraph, data.recipient_block)
        elif current == "{{SUBJECT_TITLE}}":
            rewrite_subject_title_paragraph(paragraph, data.subject_title)
        elif current == "{{REFERENCE_CAPTION}}":
            rewrite_reference_caption_paragraph(paragraph, data.reference_caption)
        elif current == "{{SALUTATION}}":
            rewrite_paragraph(paragraph, data.salutation)
        elif "{{BODY_ECP}}" in current:
            rewrite_paragraph(paragraph, "")
        elif current == "{{BODY_EXEC}}":
            rewrite_paragraph(paragraph, "")


def replace_body_paragraphs(root: ET.Element, paragraphs: list[str]) -> None:
    body = root.find(".//w:body", NS)
    if body is None:
        raise ValueError("В шаблоне не найден body")

    body_children = list(body)
    start_index = None
    end_index = None
    template_start = None
    template_end = None

    for index, child in enumerate(body_children):
        if child.tag != w_tag("p"):
            continue
        text = paragraph_text(child)
        if start_index is None and text.startswith(BODY_PLACEHOLDER_START):
            start_index = index
            template_start = child
            continue
        if start_index is not None and text.startswith(BODY_PLACEHOLDER_END):
            end_index = index
            template_end = child
            break

    if start_index is None or end_index is None or template_start is None or template_end is None:
        raise ValueError("В шаблоне не найдены абзацы для тела письма")

    for index in range(end_index, start_index - 1, -1):
        body.remove(body_children[index])

    insert_index = start_index
    for position, paragraph in enumerate(paragraphs):
        template = template_start if position == 0 else template_end
        body.insert(insert_index + position, build_paragraph(template, paragraph))


def build_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = copy.deepcopy(template)
    rewrite_paragraph(paragraph, text)
    return paragraph


def rewrite_paragraph(paragraph: ET.Element, text: str) -> None:
    run_props, preserved_children = prepare_paragraph(paragraph)
    clear_paragraph(paragraph)
    for child in preserved_children:
        paragraph.append(child)

    wrote_content = False
    for line_index, line in enumerate(text.split("\n")):
        if line_index > 0:
            paragraph.append(build_control_run(run_props, "br"))
            wrote_content = True

        segments = line.split("\t")
        for segment_index, segment in enumerate(segments):
            if segment:
                paragraph.append(build_text_run(run_props, segment))
                wrote_content = True
            if segment_index < len(segments) - 1:
                paragraph.append(build_control_run(run_props, "tab"))
                wrote_content = True

    if not wrote_content:
        paragraph.append(build_text_run(run_props, ""))


def rewrite_recipient_paragraph(paragraph: ET.Element, recipient_block: str) -> None:
    run_props, _ = prepare_paragraph(paragraph)
    clear_paragraph(paragraph)

    lines = [line.strip() for line in recipient_block.splitlines() if line.strip()]
    if not lines:
        paragraph.append(build_text_run(run_props, ""))
        return

    paragraph.append(build_text_run(run_props, lines[0]))
    for line in lines[1:]:
        paragraph.append(build_control_run(run_props, "br"))
        paragraph.append(build_text_run(run_props, line))


def rewrite_subject_title_paragraph(paragraph: ET.Element, subject_title: str) -> None:
    run_props, _ = prepare_paragraph(paragraph)
    clear_paragraph(paragraph)

    words = subject_title.split()
    if len(words) >= 3:
        append_text_and_tab(paragraph, run_props, words[0])
        append_text_and_tab(paragraph, run_props, words[1])
        paragraph.append(build_text_run(run_props, " ".join(words[2:])))
        return

    rewrite_paragraph(paragraph, subject_title)


def rewrite_reference_caption_paragraph(paragraph: ET.Element, reference_caption: str) -> None:
    run_props, _ = prepare_paragraph(paragraph)
    clear_paragraph(paragraph)

    prefix = "На обращение гражданина "
    if reference_caption.startswith(prefix):
        tail = reference_caption[len(prefix) :].strip()
        append_text_and_tab(paragraph, run_props, "На")
        append_text_and_tab(paragraph, run_props, "обращение")
        paragraph.append(build_text_run(run_props, "гражданина "))
        if tail:
            paragraph.append(build_text_run(run_props, tail))
        return

    rewrite_paragraph(paragraph, reference_caption)


def replace_signature_department(root: ET.Element, data: LetterData) -> None:
    paragraphs = root.findall(".//w:p", NS)
    signature_line1, signature_line2 = build_signature_department_lines(
        data.signer_title,
        data.signer_department,
    )

    for index, paragraph in enumerate(paragraphs):
        text = paragraph_text(paragraph)
        if text == "Директор Департамента бюджетного планирования, государственных программ":
            rewrite_paragraph(paragraph, signature_line1)
            if index + 1 < len(paragraphs):
                next_paragraph = paragraphs[index + 1]
                next_text = paragraph_text(next_paragraph)
                if next_text == "и национальных проектовТ.С. Митюков":
                    rewrite_paragraph(next_paragraph, f"{signature_line2}\t{data.signer_name}")


def build_signature_department_lines(title: str, department: str) -> tuple[str, str]:
    normalized_title = " ".join(title.split()) or "Директор"
    normalized = " ".join(department.split())
    if not normalized:
        return normalized_title, ""

    signature_department = to_signature_department_case(normalized)
    if signature_department.endswith(" и национальных проектов"):
        first_part = signature_department[: -len(" и национальных проектов")].rstrip()
        first_part = first_part.replace(", государственных программ", ",\nгосударственных программ", 1)
        return f"{normalized_title} {first_part}", "и национальных проектов"

    return f"{normalized_title} {signature_department}", ""


def to_signature_department_case(text: str) -> str:
    replacements = (
        ("Департамент ", "Департамента "),
        ("Управление ", "Управления "),
        ("Отдел ", "Отдела "),
        ("Служба ", "Службы "),
    )
    for source, target in replacements:
        if text.startswith(source):
            return target + text[len(source) :]
    return text


def tighten_trailing_layout(root: ET.Element, data: LetterData) -> None:
    body = root.find(".//w:body", NS)
    if body is None:
        return

    children = list(body)
    signature_prefix = " ".join((data.signer_title or "Директор").split())
    signature_start = find_paragraph_index(children, lambda text: text.startswith(signature_prefix))
    executor_start = find_paragraph_index(children, lambda text: text.startswith("Исп. "))
    if signature_start is None or executor_start is None:
        return

    previous_content = find_previous_nonempty_paragraph(children, signature_start)
    if previous_content is not None:
        collapse_empty_paragraphs(body, children, previous_content + 1, signature_start, keep=1)
        children = list(body)
        signature_start = find_paragraph_index(children, lambda text: text.startswith(signature_prefix))
        executor_start = find_paragraph_index(children, lambda text: text.startswith("Исп. "))
        if signature_start is None or executor_start is None:
            return

    collapse_empty_paragraphs(body, children, signature_start + 2, executor_start, keep=1)


def collapse_empty_paragraphs(
    body: ET.Element,
    children: list[ET.Element],
    start_index: int,
    end_index: int,
    keep: int,
) -> None:
    empty_indexes = [
        index
        for index in range(start_index, end_index)
        if is_plain_empty_paragraph(children[index])
    ]
    if len(empty_indexes) <= keep:
        return

    for index in reversed(empty_indexes[:-keep]):
        body.remove(children[index])


def is_plain_empty_paragraph(node: ET.Element) -> bool:
    if node.tag != w_tag("p"):
        return False
    if paragraph_text(node):
        return False
    if node.find(".//w:drawing", NS) is not None:
        return False
    return True


def find_paragraph_index(children: list[ET.Element], predicate) -> int | None:
    for index, node in enumerate(children):
        if node.tag != w_tag("p"):
            continue
        if predicate(paragraph_text(node)):
            return index
    return None


def find_previous_nonempty_paragraph(children: list[ET.Element], before_index: int) -> int | None:
    for index in range(before_index - 1, -1, -1):
        node = children[index]
        if node.tag != w_tag("p"):
            continue
        if paragraph_text(node):
            return index
    return None


def turn_red_text_black(root: ET.Element) -> None:
    for node in root.findall(".//w:color", NS):
        value = node.get(w_tag("val"))
        if value == "FF0000":
            node.set(w_tag("val"), "000000")


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()


def needs_preserve_space(text: str) -> bool:
    return text.startswith(" ") or text.endswith(" ") or "  " in text


def prepare_paragraph(paragraph: ET.Element) -> tuple[ET.Element | None, list[ET.Element]]:
    first_run = paragraph.find("w:r", NS)
    run_props = None
    if first_run is not None:
        original_rpr = first_run.find("w:rPr", NS)
        if original_rpr is not None:
            run_props = copy.deepcopy(original_rpr)

    preserved_children = []
    for child in paragraph:
        if child.tag == w_tag("pPr"):
            continue
        if child.find(".//w:drawing", NS) is not None:
            preserved_children.append(copy.deepcopy(child))
    return run_props, preserved_children


def clear_paragraph(paragraph: ET.Element) -> None:
    for child in list(paragraph):
        if child.tag != w_tag("pPr"):
            paragraph.remove(child)


def build_text_run(run_props: ET.Element | None, text: str) -> ET.Element:
    run = ET.Element(w_tag("r"))
    if run_props is not None:
        run.append(copy.deepcopy(run_props))
    text_node = ET.SubElement(run, w_tag("t"))
    if needs_preserve_space(text):
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = text
    return run


def append_text_and_tab(paragraph: ET.Element, run_props: ET.Element | None, text: str) -> None:
    paragraph.append(build_text_run(run_props, text))
    paragraph.append(build_control_run(run_props, "tab"))


def build_control_run(
    run_props: ET.Element | None,
    control: str,
    attributes: dict[str, str] | None = None,
) -> ET.Element:
    run = ET.Element(w_tag("r"))
    if run_props is not None:
        run.append(copy.deepcopy(run_props))
    node = ET.SubElement(run, w_tag(control))
    if attributes:
        for key, value in attributes.items():
            node.set(w_tag(key), value)
    return run


def w_tag(local_name: str) -> str:
    return f"{{{W_NS}}}{local_name}"
