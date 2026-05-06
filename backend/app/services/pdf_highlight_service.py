import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from app.services.privacy_masking import (
    mask_name,
    mask_phone_number,
    mask_resident_registration_number,
    mask_sensitive_data,
)
from app.services.rag_contract_rules import RAG_CONDITION_FIELD_PATHS, normalize_review_level


@dataclass
class WordBox:
    rect: fitz.Rect
    text: str
    block_no: int
    line_no: int
    word_no: int


@dataclass
class TextLine:
    rect: fitz.Rect
    text: str
    compact_text: str
    words: list[WordBox]
    block_no: int
    line_no: int


@dataclass
class TextBlock:
    rect: fitz.Rect
    text: str
    compact_text: str
    index: int
    words: list[WordBox]


@dataclass(frozen=True)
class StaticFieldSpec:
    field_path: str
    anchor: str
    y_range: tuple[float, float] | None
    value_keys: tuple[str, ...] = ()
    literal_value: str | None = None
    locator: str = "block"
    source: str = "text_layer:block"


STATIC_FIELD_SPECS = [
    StaticFieldSpec("document_title", "부동산임대차계약서", None, literal_value="부동산임대차계약서"),
    StaticFieldSpec("property.address", "소재지", (120.0, 145.0), ("property", "address", "raw_text")),
    StaticFieldSpec("property.land.category", "토지", (150.0, 170.0), ("property", "land", "category", "raw_text")),
    StaticFieldSpec("property.land.area_m2", "토지", (150.0, 170.0), ("property", "land", "area_m2", "raw_text")),
    StaticFieldSpec("property.building.structure_usage", "건물", (165.0, 182.0), ("property", "building", "structure_usage", "value")),
    StaticFieldSpec("property.building.area_m2", "건물", (165.0, 182.0), ("property", "building", "area_m2", "raw_text")),
    StaticFieldSpec("property.leased_part.raw_text", "임대할부분", (180.0, 198.0), ("property", "leased_part", "raw_text")),
    StaticFieldSpec("payment.deposit", "보증금", (220.0, 237.0), ("payment", "deposit", "raw_text")),
    StaticFieldSpec("payment.contract_money", "계약금", (238.0, 252.0), ("payment", "contract_money", "raw_text")),
    StaticFieldSpec("payment.contract_money_received_by", "계약금", (238.0, 252.0), ("payment", "contract_money_received_by", "raw_text")),
    StaticFieldSpec("payment.intermediate_money", "중도금", (252.0, 279.0), ("payment", "intermediate_money", "raw_text")),
    StaticFieldSpec("payment.intermediate_money_payment_date", "중도금", (252.0, 266.0), ("payment", "intermediate_money_payment_date", "raw_text")),
    StaticFieldSpec("payment.balance", "잔금", (252.0, 279.0), ("payment", "balance", "raw_text")),
    StaticFieldSpec("payment.balance_payment_date", "잔금", (252.0, 279.0), ("payment", "balance_payment_date", "raw_text")),
    StaticFieldSpec("payment.monthly_rent", "차임", (282.0, 296.0), ("payment", "monthly_rent", "raw_text")),
    StaticFieldSpec("payment.rent_payment_type", "차임", (282.0, 296.0), ("payment", "rent_payment_type", "raw_text")),
    StaticFieldSpec("payment.monthly_due_day", "차임", (282.0, 296.0), ("payment", "monthly_due_day", "raw_text")),
]


def safe_get(obj: Any, *keys, default=None):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def compact_text(text: str | None) -> str:
    if not text:
        return ""
    value = str(text).replace("\uf000", "")
    value = re.sub(r"\s+", "", value)
    return value.strip()


def union_rects(rects: list[fitz.Rect]) -> fitz.Rect | None:
    valid_rects = [rect for rect in rects if rect is not None and not rect.is_empty]
    if not valid_rects:
        return None

    result = fitz.Rect(valid_rects[0])
    for rect in valid_rects[1:]:
        result |= rect
    return result


def rect_to_bbox_0_999(page: fitz.Page, rect: fitz.Rect) -> list[int]:
    page_rect = page.rect
    width = page_rect.width or 1.0
    height = page_rect.height or 1.0

    def clamp_0_999(value: float) -> int:
        return max(0, min(999, int(round(value))))

    return [
        clamp_0_999(rect.x0 / width * 999.0),
        clamp_0_999(rect.y0 / height * 999.0),
        clamp_0_999(rect.x1 / width * 999.0),
        clamp_0_999(rect.y1 / height * 999.0),
    ]


def build_page_index(page: fitz.Page) -> tuple[list[TextLine], list[TextBlock]]:
    raw_words = page.get_text("words")
    words = [
        WordBox(
            rect=fitz.Rect(x0, y0, x1, y1),
            text=text,
            block_no=block_no,
            line_no=line_no,
            word_no=word_no,
        )
        for x0, y0, x1, y1, text, block_no, line_no, word_no in raw_words
    ]

    line_groups: dict[tuple[int, int], list[WordBox]] = {}
    for word in words:
        line_groups.setdefault((word.block_no, word.line_no), []).append(word)

    lines: list[TextLine] = []
    for (block_no, line_no), group in sorted(line_groups.items()):
        group.sort(key=lambda word: word.word_no)
        text = " ".join(word.text for word in group)
        rect = union_rects([word.rect for word in group])
        if rect is None:
            continue
        lines.append(
            TextLine(
                rect=rect,
                text=text,
                compact_text=compact_text(text),
                words=group,
                block_no=block_no,
                line_no=line_no,
            )
        )

    block_words: dict[int, list[WordBox]] = {}
    for word in words:
        block_words.setdefault(word.block_no, []).append(word)

    blocks: list[TextBlock] = []
    for index, block in enumerate(page.get_text("blocks")):
        x0, y0, x1, y1, text, *_rest = block
        group = sorted(block_words.get(index, []), key=lambda word: (word.line_no, word.word_no))
        blocks.append(
            TextBlock(
                rect=fitz.Rect(x0, y0, x1, y1),
                text=text,
                compact_text=compact_text(text),
                index=index,
                words=group,
            )
        )

    return lines, blocks


def match_target_in_words(words: list[WordBox], target: str) -> fitz.Rect | None:
    target_compact = compact_text(target)
    if not target_compact:
        return None

    filtered_words = [word for word in words if compact_text(word.text)]

    for start_index in range(len(filtered_words)):
        combined = ""
        rects: list[fitz.Rect] = []
        for next_index in range(start_index, len(filtered_words)):
            piece = compact_text(filtered_words[next_index].text)
            combined += piece
            rects.append(filtered_words[next_index].rect)
            if combined == target_compact:
                return union_rects(rects)
            if not target_compact.startswith(combined):
                break

    for word in filtered_words:
        if target_compact in compact_text(word.text):
            return word.rect

    tokens = [compact_text(part) for part in re.split(r"\s+", str(target)) if compact_text(part)]
    matched_rects: list[fitz.Rect] = []
    cursor = 0
    for token in tokens:
        found_index = None
        for index in range(cursor, len(filtered_words)):
            if token in compact_text(filtered_words[index].text):
                matched_rects.append(filtered_words[index].rect)
                found_index = index + 1
                break
        if found_index is None:
            return None
        cursor = found_index
    return union_rects(matched_rects)


def match_target_after_anchor(words: list[WordBox], anchor: str, target: str) -> fitz.Rect | None:
    anchor_compact = compact_text(anchor)
    target_compact = compact_text(target)
    if not anchor_compact or not target_compact:
        return None

    filtered_words = [word for word in words if compact_text(word.text)]

    for start_index, word in enumerate(filtered_words):
        word_compact = compact_text(word.text)
        if anchor_compact not in word_compact:
            continue

        suffix = word_compact.split(anchor_compact, 1)[1]
        rects: list[fitz.Rect] = []
        combined = suffix

        if suffix:
            rects.append(word.rect)
            if combined == target_compact or target_compact in word_compact:
                return union_rects(rects)
            if not target_compact.startswith(combined):
                combined = ""
                rects = []

        for next_index in range(start_index + 1, len(filtered_words)):
            piece = compact_text(filtered_words[next_index].text)
            combined += piece
            rects.append(filtered_words[next_index].rect)
            if combined == target_compact:
                return union_rects(rects)
            if not target_compact.startswith(combined):
                break

    return None


def find_line(lines: list[TextLine], anchor: str, y_range: tuple[float, float] | None = None) -> TextLine | None:
    anchor_compact = compact_text(anchor)
    candidates = []
    for line in lines:
        if anchor_compact not in line.compact_text:
            continue
        if y_range is not None and not (y_range[0] <= line.rect.y0 <= y_range[1]):
            continue
        candidates.append(line)
    if not candidates:
        return None
    candidates.sort(key=lambda line: line.rect.y0)
    return candidates[0]


def find_block(blocks: list[TextBlock], anchor: str, y_range: tuple[float, float] | None = None) -> TextBlock | None:
    anchor_compact = compact_text(anchor)
    candidates = []
    for block in blocks:
        if anchor_compact not in block.compact_text:
            continue
        if y_range is not None and not (y_range[0] <= block.rect.y0 <= y_range[1]):
            continue
        candidates.append(block)
    if not candidates:
        return None
    candidates.sort(key=lambda block: block.rect.y0)
    return candidates[0]


def locate_in_line(lines: list[TextLine], value: str | None, anchor: str, y_range: tuple[float, float] | None = None) -> fitz.Rect | None:
    if not value:
        return None
    line = find_line(lines, anchor, y_range)
    if line is None:
        return None
    return (
        match_target_in_words(line.words, value)
        or match_target_after_anchor(line.words, anchor, value)
        or line.rect
    )


def locate_in_block(blocks: list[TextBlock], value: str | None, anchor: str, y_range: tuple[float, float] | None = None) -> fitz.Rect | None:
    if not value:
        return None
    block = find_block(blocks, anchor, y_range)
    if block is None:
        return None
    return (
        match_target_in_words(block.words, value)
        or match_target_after_anchor(block.words, anchor, value)
        or block.rect
    )


def detect_party_blocks(blocks: list[TextBlock]) -> dict[str, TextBlock]:
    def sorted_blocks_with(anchor: str, y_min: float = 0.0) -> list[TextBlock]:
        anchor_compact = compact_text(anchor)
        result = [block for block in blocks if anchor_compact in block.compact_text and block.rect.y0 >= y_min]
        result.sort(key=lambda block: block.rect.y0)
        return result

    address_blocks = [
        block
        for block in sorted_blocks_with("주소", 600.0)
        if "대리인" not in block.compact_text and len(block.words) >= 5
    ]
    id_blocks = [
        block
        for block in sorted_blocks_with("주민등록번호", 600.0)
        if any(char.isdigit() for char in block.text) and ("전화" in block.compact_text or "성명" in block.compact_text)
    ]

    sections: dict[str, TextBlock] = {}
    if len(address_blocks) >= 1:
        sections["lessor_address"] = address_blocks[0]
    if len(address_blocks) >= 2:
        sections["lessee_address"] = address_blocks[1]
    if len(id_blocks) >= 1:
        sections["lessor_id"] = id_blocks[0]
    if len(id_blocks) >= 2:
        sections["lessee_id"] = id_blocks[1]

    broker_address = find_block(blocks, "사무소소재지", (700.0, 735.0))
    broker_name = find_block(blocks, "사무소명칭", (720.0, 745.0))
    broker_rep = find_block(blocks, "대표", (735.0, 760.0))
    broker_reg = find_block(blocks, "등록번호", (750.0, 775.0))

    if broker_address is not None:
        sections["broker_address"] = broker_address
    if broker_name is not None:
        sections["broker_name"] = broker_name
    if broker_rep is not None:
        sections["broker_rep"] = broker_rep
    if broker_reg is not None:
        sections["broker_reg"] = broker_reg

    return sections


def extract_special_terms_text(contract_data: dict[str, Any]) -> str | None:
    terms = contract_data.get("special_terms") or []
    contents = [term.get("content") for term in terms if isinstance(term, dict) and term.get("content")]
    if not contents:
        return None
    return " ".join(contents)


def add_field(
    page: fitz.Page,
    field_results: dict[str, dict[str, Any]],
    field_path: str,
    value: str | None,
    rect: fitz.Rect | None,
    source: str,
) -> None:
    if not value or rect is None or rect.is_empty:
        return
    field_results[field_path] = {
        "value": value,
        "page_number": page.number + 1,
        "bbox_0_999": rect_to_bbox_0_999(page, rect),
        "source": source,
    }


def value_for_static_spec(contract_data: dict[str, Any], spec: StaticFieldSpec) -> str | None:
    if spec.literal_value is not None:
        return spec.literal_value
    return safe_get(contract_data, *spec.value_keys)


def locate_static_spec(
    lines: list[TextLine],
    blocks: list[TextBlock],
    value: str | None,
    spec: StaticFieldSpec,
) -> fitz.Rect | None:
    if spec.locator == "line":
        return locate_in_line(lines, value, spec.anchor, spec.y_range)
    return locate_in_block(blocks, value, spec.anchor, spec.y_range)


def should_include_generic_text(path: str, key: str, value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if key in {"raw_text", "content", "article_no"}:
        return True
    if key == "value":
        raw_text_path = path[:-len(".value")] + ".raw_text" if path.endswith(".value") else None
        if raw_text_path:
            return False
        return len(compact_text(text)) >= 8
    return False


def collect_text_targets(data: Any, path: str = "") -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            next_path = f"{path}.{key}" if path else key
            if key in {"raw_text", "value", "content", "article_no"} and isinstance(value, str) and should_include_generic_text(next_path, key, value):
                targets.append((next_path, value))
            else:
                targets.extend(collect_text_targets(value, next_path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            targets.extend(collect_text_targets(item, f"{path}[{index}]"))
    return targets


def locate_text_anywhere(lines: list[TextLine], blocks: list[TextBlock], value: str | None) -> fitz.Rect | None:
    if not value:
        return None
    value_compact = compact_text(value)
    if len(value_compact) >= 12:
        for block in blocks:
            rect = match_target_in_words(block.words, value)
            if rect is not None:
                return rect
    for line in lines:
        rect = match_target_in_words(line.words, value)
        if rect is not None:
            return rect
    for block in blocks:
        rect = match_target_in_words(block.words, value)
        if rect is not None:
            return rect
    return None


def locate_numbered_multiline_item(
    lines: list[TextLine],
    order: int,
    value: str,
    y_range: tuple[float, float],
) -> fitz.Rect | None:
    order_anchor = f"{order}."
    next_order_anchor = f"{order + 1}."
    region_lines = [line for line in lines if y_range[0] <= line.rect.y0 <= y_range[1]]
    start_index = next((index for index, line in enumerate(region_lines) if order_anchor in line.text), None)
    if start_index is None:
        return None

    selected: list[TextLine] = []
    for line in region_lines[start_index:]:
        if selected and next_order_anchor in line.text:
            break
        if selected and ("본 계약을 증명" in line.text or "임대인" in line.text or "임차인" in line.text):
            break
        selected.append(line)

    target_compact = compact_text(value)
    combined = compact_text(" ".join(line.text for line in selected))
    if target_compact and (target_compact in combined or combined in target_compact):
        return union_rects([line.rect for line in selected])
    return None


def locate_contract_term_item(lines: list[TextLine], blocks: list[TextBlock], term: dict[str, Any], sub_value: str | None) -> fitz.Rect | None:
    if not sub_value:
        return None
    article_no = term.get("article_no")
    if article_no:
        article_line = find_line(lines, str(article_no), (300.0, 560.0))
        if article_line is not None:
            start_y = article_line.rect.y0 - 2.0
            next_article_y = None
            article_y = article_line.rect.y0
            for line in lines:
                if line.rect.y0 > article_y and compact_text(line.text).startswith("제") and "조" in line.compact_text:
                    next_article_y = line.rect.y0
                    break
            end_y = next_article_y - 1.0 if next_article_y is not None else 560.0

            candidate_blocks = [block for block in blocks if start_y <= block.rect.y0 <= end_y]
            rect = locate_text_anywhere([], candidate_blocks, sub_value)
            if rect is not None:
                return rect

            candidate_lines = [line for line in lines if start_y <= line.rect.y0 <= end_y]
            rect = locate_text_anywhere(candidate_lines, candidate_blocks, sub_value)
            if rect is not None:
                return rect

    return locate_text_anywhere(
        [line for line in lines if 300.0 <= line.rect.y0 <= 560.0],
        [block for block in blocks if 300.0 <= block.rect.y0 <= 560.0],
        sub_value,
    ) or locate_text_anywhere(lines, blocks, sub_value)


def locate_special_term_item(lines: list[TextLine], blocks: list[TextBlock], term: dict[str, Any], sub_value: str | None) -> fitz.Rect | None:
    if not sub_value:
        return None
    order = term.get("order")
    special_block = find_block(blocks, "특약사항", (500.0, 690.0))
    if special_block is not None:
        rect = match_target_in_words(special_block.words, sub_value)
        if rect is not None:
            return rect

    if order is not None:
        rect = locate_numbered_multiline_item(lines, int(order), sub_value, (500.0, 690.0))
        if rect is not None:
            return rect
        order_anchor = f"{order}."
        for line in lines:
            if 500.0 <= line.rect.y0 <= 690.0 and order_anchor in line.text:
                rect = match_target_in_words(line.words, sub_value)
                if rect is not None:
                    return rect

    return locate_text_anywhere(
        [line for line in lines if 500.0 <= line.rect.y0 <= 690.0],
        [block for block in blocks if 500.0 <= block.rect.y0 <= 690.0],
        sub_value,
    ) or locate_text_anywhere(lines, blocks, sub_value)


def locate_generic_path(
    page: fitz.Page,
    lines: list[TextLine],
    blocks: list[TextBlock],
    contract_data: dict[str, Any],
    path: str,
    value: str,
) -> fitz.Rect | None:
    if not value:
        return None

    if path.startswith("contract_terms["):
        match = re.match(r"contract_terms\[(\d+)\]", path)
        if match:
            index = int(match.group(1))
            terms = contract_data.get("contract_terms") or []
            if 0 <= index < len(terms) and isinstance(terms[index], dict):
                return locate_contract_term_item(lines, blocks, terms[index], value)

    if path.startswith("special_terms["):
        match = re.match(r"special_terms\[(\d+)\]", path)
        if match:
            index = int(match.group(1))
            terms = contract_data.get("special_terms") or []
            if 0 <= index < len(terms) and isinstance(terms[index], dict):
                return locate_special_term_item(lines, blocks, terms[index], value)

    if path.startswith("special_terms_account_numbers["):
        return locate_text_anywhere(lines, blocks, value)

    return locate_text_anywhere(lines, blocks, value)


def locate_fields(page: fitz.Page, contract_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lines, blocks = build_page_index(page)
    sections = detect_party_blocks(blocks)
    fields: dict[str, dict[str, Any]] = {}

    for spec in STATIC_FIELD_SPECS:
        value = value_for_static_spec(contract_data, spec)
        add_field(page, fields, spec.field_path, value, locate_static_spec(lines, blocks, value, spec), spec.source)

    lease_type = contract_data.get("lease_type")
    if lease_type:
        add_field(page, fields, "lease_type", str(lease_type), locate_in_line(lines, str(lease_type), str(lease_type), (65.0, 90.0)), "text_layer:line")
    else:
        lease_type_line = find_line(lines, "전세", (65.0, 90.0)) or find_line(lines, "월세", (65.0, 90.0))
        if lease_type_line is not None:
            add_field(page, fields, "lease_type", "전세/월세 체크", lease_type_line.rect, "text_layer:lease_type_placeholder")

    lessor_address_block = sections.get("lessor_address")
    lessor_id_block = sections.get("lessor_id")
    lessee_address_block = sections.get("lessee_address")
    lessee_id_block = sections.get("lessee_id")
    broker_address_block = sections.get("broker_address")
    broker_name_block = sections.get("broker_name")
    broker_rep_block = sections.get("broker_rep")
    broker_reg_block = sections.get("broker_reg")

    if lessor_address_block:
        add_field(page, fields, "lessor.address", safe_get(contract_data, "lessor", "address", "raw_text"), match_target_in_words(lessor_address_block.words, safe_get(contract_data, "lessor", "address", "raw_text")), "text_layer:lessor_address_block")
    if lessor_id_block:
        add_field(page, fields, "lessor.resident_registration_number", safe_get(contract_data, "lessor", "resident_registration_number", "raw_text"), match_target_in_words(lessor_id_block.words, safe_get(contract_data, "lessor", "resident_registration_number", "raw_text")), "text_layer:lessor_id_block")
        add_field(page, fields, "lessor.phone", safe_get(contract_data, "lessor", "phone", "raw_text"), match_target_in_words(lessor_id_block.words, safe_get(contract_data, "lessor", "phone", "raw_text")), "text_layer:lessor_id_block")
        add_field(page, fields, "lessor.name", safe_get(contract_data, "lessor", "name", "raw_text"), match_target_in_words(lessor_id_block.words, safe_get(contract_data, "lessor", "name", "raw_text")), "text_layer:lessor_id_block")

    if lessee_address_block:
        add_field(page, fields, "lessee.address", safe_get(contract_data, "lessee", "address", "raw_text"), match_target_in_words(lessee_address_block.words, safe_get(contract_data, "lessee", "address", "raw_text")), "text_layer:lessee_address_block")
    if lessee_id_block:
        add_field(page, fields, "lessee.resident_registration_number", safe_get(contract_data, "lessee", "resident_registration_number", "raw_text"), match_target_in_words(lessee_id_block.words, safe_get(contract_data, "lessee", "resident_registration_number", "raw_text")), "text_layer:lessee_id_block")
        add_field(page, fields, "lessee.phone", safe_get(contract_data, "lessee", "phone", "raw_text"), match_target_in_words(lessee_id_block.words, safe_get(contract_data, "lessee", "phone", "raw_text")), "text_layer:lessee_id_block")
        add_field(page, fields, "lessee.name", safe_get(contract_data, "lessee", "name", "raw_text"), match_target_in_words(lessee_id_block.words, safe_get(contract_data, "lessee", "name", "raw_text")), "text_layer:lessee_id_block")

    if broker_address_block:
        add_field(page, fields, "broker.office_address", safe_get(contract_data, "broker", "office_address", "raw_text"), match_target_in_words(broker_address_block.words, safe_get(contract_data, "broker", "office_address", "raw_text")), "text_layer:broker_address_block")
    if broker_name_block:
        add_field(page, fields, "broker.office_name", safe_get(contract_data, "broker", "office_name", "raw_text"), match_target_in_words(broker_name_block.words, safe_get(contract_data, "broker", "office_name", "raw_text")), "text_layer:broker_name_block")
    if broker_rep_block:
        add_field(page, fields, "broker.representative_name", safe_get(contract_data, "broker", "representative_name", "raw_text"), match_target_in_words(broker_rep_block.words, safe_get(contract_data, "broker", "representative_name", "raw_text")), "text_layer:broker_rep_block")
    if broker_reg_block:
        add_field(page, fields, "broker.registration_number", safe_get(contract_data, "broker", "registration_number", "raw_text"), match_target_in_words(broker_reg_block.words, safe_get(contract_data, "broker", "registration_number", "raw_text")), "text_layer:broker_reg_block")

    special_terms_text = extract_special_terms_text(contract_data)
    add_field(page, fields, "special_terms", special_terms_text, locate_in_block(blocks, special_terms_text, "특약사항", (500.0, 690.0)), "text_layer:block")

    generic_targets = collect_text_targets(contract_data)
    for path, value in generic_targets:
        if path in fields:
            continue
        rect = locate_generic_path(page, lines, blocks, contract_data, path, value)
        if rect is None:
            continue
        add_field(page, fields, path, value, rect, "text_layer:generic")

    return fields


def review_level_color(review_level: str) -> tuple[float, float, float]:
    if review_level == "주의":
        return (1.0, 0.48, 0.22)
    if review_level == "보통":
        return (1.0, 0.84, 0.25)
    return (0.42, 0.82, 0.42)


def review_level_priority(review_level: str | None) -> int:
    if review_level == "주의":
        return 3
    if review_level == "보통":
        return 2
    return 1


def build_highlight_specs(verification_summary: dict) -> list[dict[str, Any]]:
    analysis = verification_summary.get("analysis", {})
    findings = analysis.get("findings") or []
    specs: list[dict[str, Any]] = list(findings)

    existing_paths = {item.get("field_path") for item in specs if item.get("field_path")}

    def add_pass_spec(field_path: str, title: str, message: str) -> None:
        if field_path in existing_paths:
            return
        specs.append(
            {
                "field_path": field_path,
                "review_level": "양호",
                "title": title,
                "message": message,
            }
        )
        existing_paths.add(field_path)

    address_verification = verification_summary.get("address_verification", {})
    address_data = address_verification.get("data") or {}
    if address_data.get("road"):
        add_pass_spec("property.address", "소재지 확인", "계약서 소재지가 주소 검증에서 확인되었습니다.")
        if address_data.get("detail_match") is True:
            add_pass_spec("property.leased_part.raw_text", "임대할부분 확인", "동/호 정보가 상세주소 검증에서 확인되었습니다.")

    lessor_address_verification = verification_summary.get("lessor_address_verification", {})
    if lessor_address_verification.get("status") == "success":
        add_pass_spec("lessor.address", "임대인 주소 확인", "임대인 주소가 주소 검증에서 확인되었습니다.")

    lessee_address_verification = verification_summary.get("lessee_address_verification", {})
    if lessee_address_verification.get("status") == "success":
        add_pass_spec("lessee.address", "임차인 주소 확인", "임차인 주소가 주소 검증에서 확인되었습니다.")

    broker_verification = verification_summary.get("broker_verification", {})
    if broker_verification.get("status") == "success":
        add_pass_spec("broker.registration_number", "중개업 등록번호 확인", "중개업 등록번호 조회가 정상적으로 완료되었습니다.")
        add_pass_spec("broker.office_address", "중개업 소재지 확인", "중개업 소재지 조회가 정상적으로 완료되었습니다.")
        add_pass_spec("broker.office_name", "중개업 상호 확인", "중개업 상호 조회가 정상적으로 완료되었습니다.")
        add_pass_spec("broker.representative_name", "중개업 대표자 확인", "중개업 대표자 조회가 정상적으로 완료되었습니다.")

    return specs


def add_core_payment_highlight_specs(specs: list[dict[str, Any]], extracted: dict) -> list[dict[str, Any]]:
    payment = extracted.get("payment") or {}
    existing_paths = {item.get("field_path") for item in specs if item.get("field_path")}
    payment_fields = [
        ("payment.deposit", "보증금"),
        ("payment.contract_money", "계약금"),
        ("payment.intermediate_money", "중도금"),
        ("payment.balance", "잔금"),
        ("payment.monthly_rent", "차임"),
    ]
    for field_path, label in payment_fields:
        key = field_path.removeprefix("payment.")
        value = payment.get(key) or {}
        has_value = isinstance(value, dict) and any(value.get(name) for name in ("raw_text", "korean_text", "numeric_text", "normalized_value"))
        if field_path in existing_paths or not has_value:
            continue
        specs.append(
            {
                "field_path": field_path,
                "review_level": "양호",
                "title": f"제1조 {label} 확인",
                "message": f"계약내용의 {label} 항목이 추출되어 확인되었습니다.",
            }
        )
        existing_paths.add(field_path)
    return specs


def add_rag_highlight_specs(
    specs: list[dict[str, Any]],
    extracted: dict,
    rag_summary: dict | None,
) -> list[dict[str, Any]]:
    if not rag_summary:
        return specs

    existing_keys = {
        (item.get("field_path"), item.get("title"), item.get("message"))
        for item in specs
    }
    existing_positive_paths = {
        item.get("field_path")
        for item in specs
        if item.get("field_path") and item.get("review_level") in {"양호", "보통"}
    }

    def append_spec(field_path: str, title: str, message: str, review_level: str) -> None:
        if review_level in {"양호", "보통"} and field_path in existing_positive_paths:
            return
        key = (field_path, title, message)
        if key in existing_keys:
            return
        specs.append(
            {
                "field_path": field_path,
                "review_level": review_level,
                "title": title,
                "message": message,
            }
        )
        existing_keys.add(key)
        if review_level in {"양호", "보통"}:
            existing_positive_paths.add(field_path)

    for item in rag_summary.get("contract_conditions") or []:
        label = item.get("label") or ""
        field_path = RAG_CONDITION_FIELD_PATHS.get(label)
        if not field_path:
            continue
        review_level = normalize_review_level(item.get("review_level"), item.get("judgment"))
        if review_level != "주의":
            continue
        message = item.get("reason") or ""
        append_spec(field_path, f"RAG: {label}", message, review_level)

    special_terms = extracted.get("special_terms") or []
    for item in rag_summary.get("special_terms") or []:
        order = item.get("order")
        if not isinstance(order, int):
            continue
        index = order - 1
        if index < 0 or index >= len(special_terms):
            continue
        field_path = f"special_terms[{index}].content"
        review_level = normalize_review_level(item.get("review_level"), item.get("judgment"))
        if review_level != "주의":
            continue
        message = item.get("reason") or ""
        append_spec(field_path, f"RAG: 특약 {order}", message, review_level)

    return specs


def merge_highlight_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

    for spec in specs:
        field_path = spec.get("field_path")
        if not field_path:
            passthrough.append(spec)
            continue

        existing = merged.get(field_path)
        if existing is None:
            merged[field_path] = dict(spec)
            continue

        current_priority = review_level_priority(spec.get("review_level"))
        existing_priority = review_level_priority(existing.get("review_level"))
        if current_priority > existing_priority:
            merged[field_path] = dict(spec)
        elif current_priority == existing_priority and str(spec.get("title") or "").startswith("RAG:"):
            merged[field_path] = dict(spec)

    return passthrough + list(merged.values())


def add_annotation(page: fitz.Page, rect: fitz.Rect, review_level: str, title: str, message: str) -> None:
    annot = page.add_rect_annot(rect)
    color = review_level_color(review_level)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(0.2)
    annot.set_info(title=review_level, content=f"{title}: {message}")
    annot.update()


def render_page_png(page: fitz.Page, path: str) -> None:
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pix.save(path)


def _text_node_value(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("raw_text", "value", "normalized_value"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(node, str) and node.strip():
        return node.strip()
    return None


def collect_pdf_mask_targets(extracted: dict[str, Any]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []

    def add(value: str | None, masked: str | None) -> None:
        if value and masked and value != masked:
            targets.append((value, masked))

    for role in ("lessor", "lessee"):
        party = extracted.get(role) or {}
        add(_text_node_value(party.get("name")), mask_name(_text_node_value(party.get("name"))))
        add(
            _text_node_value(party.get("resident_registration_number")),
            mask_resident_registration_number(_text_node_value(party.get("resident_registration_number"))),
        )
        add(_text_node_value(party.get("phone")), mask_phone_number(_text_node_value(party.get("phone"))))

    broker = extracted.get("broker") or {}
    add(_text_node_value(broker.get("representative_name")), mask_name(_text_node_value(broker.get("representative_name"))))

    payment = extracted.get("payment") or {}
    add(
        _text_node_value(payment.get("contract_money_received_by")),
        mask_name(_text_node_value(payment.get("contract_money_received_by"))),
    )

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value, masked in sorted(targets, key=lambda item: len(item[0]), reverse=True):
        if value in seen:
            continue
        seen.add(value)
        deduped.append((value, masked))
    return deduped


def find_font_file() -> str | None:
    for path in (
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/gulim.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    ):
        if path.exists():
            return str(path)
    return None


def _draw_masked_text(page: fitz.Page, rect: fitz.Rect, masked_text: str, font_file: str | None) -> None:
    padded = expand_mask_rect(page, rect)
    page.draw_rect(padded, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

    fontsize = max(6.0, min(10.0, padded.height * 0.7))
    try:
        page.insert_textbox(
            padded,
            masked_text,
            fontsize=fontsize,
            fontfile=font_file,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_CENTER,
            overlay=True,
        )
    except Exception:
        page.insert_textbox(
            padded,
            "*" * max(2, len(masked_text)),
            fontsize=fontsize,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_CENTER,
            overlay=True,
        )


def expand_mask_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    padded = fitz.Rect(rect)
    padded.x0 = max(0, padded.x0 - 1.0)
    padded.y0 = max(0, padded.y0 - 1.0)
    padded.x1 = min(page.rect.width, padded.x1 + 1.0)
    padded.y1 = min(page.rect.height, padded.y1 + 1.0)
    return padded


def apply_pdf_privacy_masks(doc: fitz.Document, extracted: dict[str, Any], extraction: dict[str, Any]) -> None:
    targets = collect_pdf_mask_targets(extracted)
    if not targets:
        return

    font_file = find_font_file()
    seen_rects: set[tuple[int, int, int, int, int]] = set()
    page_mask_ops: dict[int, list[tuple[fitz.Rect, str]]] = {}

    for page in doc:
        lines, blocks = build_page_index(page)
        for original, masked in targets:
            rects = list(page.search_for(original))
            if not rects:
                located = locate_text_anywhere(lines, blocks, original)
                rects = [located] if located is not None else []
            for rect in rects:
                key = (
                    page.number,
                    round(rect.x0),
                    round(rect.y0),
                    round(rect.x1),
                    round(rect.y1),
                )
                if key in seen_rects:
                    continue
                seen_rects.add(key)
                page_mask_ops.setdefault(page.number, []).append((fitz.Rect(rect), masked))

    for page_info in extraction.get("pages", []):
        page_number = page_info.get("page_number")
        if not isinstance(page_number, int) or page_number < 1 or page_number > len(doc):
            continue
        page = doc[page_number - 1]
        for item in page_info.get("fields", {}).values():
            value = item.get("value")
            masked_value = mask_sensitive_data(value)
            bbox = item.get("bbox_0_999")
            if value == masked_value or not isinstance(bbox, list) or len(bbox) != 4:
                continue
            rect = fitz.Rect(
                page.rect.width * (bbox[0] / 999.0),
                page.rect.height * (bbox[1] / 999.0),
                page.rect.width * (bbox[2] / 999.0),
                page.rect.height * (bbox[3] / 999.0),
            )
            key = (
                page.number,
                round(rect.x0),
                round(rect.y0),
                round(rect.x1),
                round(rect.y1),
            )
            if key in seen_rects:
                continue
            seen_rects.add(key)
            page_mask_ops.setdefault(page.number, []).append((rect, str(masked_value)))

    for page_number, mask_ops in page_mask_ops.items():
        page = doc[page_number]
        for rect, _masked in mask_ops:
            page.add_redact_annot(expand_mask_rect(page, rect), fill=(1, 1, 1))
        page.apply_redactions()
        for rect, masked in mask_ops:
            _draw_masked_text(page, rect, masked, font_file)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def build_extraction_map(doc: fitz.Document, contract_data: dict[str, Any]) -> dict[str, Any]:
    extraction = {
        "document_type": contract_data.get("document_type"),
        "pages": [],
    }

    for page in doc:
        extraction["pages"].append(
            {
                "page_number": page.number + 1,
                "fields": locate_fields(page, contract_data),
            }
        )

    return extraction


def build_field_lookup(extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for page_info in extraction.get("pages", []):
        for field_path, item in page_info.get("fields", {}).items():
            lookup.setdefault(field_path, item)
            term_match = re.match(r"contract_terms\[(\d+)\]\.article_no$", field_path)
            if not term_match:
                continue
            article_no = item.get("value")
            if not article_no:
                continue
            index = term_match.group(1)
            for suffix in ("content", "article_no"):
                indexed_path = f"contract_terms[{index}].{suffix}"
                if indexed_path in page_info.get("fields", {}):
                    lookup.setdefault(f"contract_terms[article_no={article_no}].{suffix}", page_info["fields"][indexed_path])
    return lookup


def generate_finding_highlight_artifacts(
    pdf_path: str,
    extracted: dict,
    verification_summary: dict,
    rag_summary: dict | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)

    extraction = build_extraction_map(doc, extracted)
    apply_pdf_privacy_masks(doc, extracted, extraction)

    rendered_png_path = unique_path(output_root / "rendered.png")
    render_page_png(doc[0], str(rendered_png_path))

    field_lookup = build_field_lookup(extraction)
    highlight_specs = build_highlight_specs(verification_summary)
    highlight_specs = add_core_payment_highlight_specs(highlight_specs, extracted)
    highlight_specs = add_rag_highlight_specs(highlight_specs, extracted=extracted, rag_summary=rag_summary)
    highlight_specs = merge_highlight_specs(highlight_specs)
    highlight_items: list[dict[str, Any]] = []

    for finding in highlight_specs:
        field_path = finding.get("field_path")
        if not field_path:
            continue

        field_item = field_lookup.get(field_path)
        if field_item is None and not field_path.endswith(".raw_text"):
            field_item = field_lookup.get(f"{field_path}.raw_text")

        if field_item is None:
            highlight_items.append(
                {
                    "field_path": field_path,
                    "review_level": finding.get("review_level", "보통"),
                    "page_number": None,
                    "bbox_0_999": None,
                    "title": finding.get("title", ""),
                    "message": finding.get("message", ""),
                    "not_found_in_extraction": True,
                }
            )
            continue

        page_number = field_item["page_number"]
        page = doc[page_number - 1]
        bbox = field_item["bbox_0_999"]
        rect = fitz.Rect(
            page.rect.width * (bbox[0] / 999.0),
            page.rect.height * (bbox[1] / 999.0),
            page.rect.width * (bbox[2] / 999.0),
            page.rect.height * (bbox[3] / 999.0),
        )

        add_annotation(
            page=page,
            rect=rect,
            review_level=finding.get("review_level", "보통"),
            title=finding.get("title", ""),
            message=finding.get("message", ""),
        )

        highlight_items.append(
            {
                "field_path": field_path,
                "review_level": finding.get("review_level", "보통"),
                "page_number": page_number,
                "bbox_0_999": bbox,
                "text": mask_sensitive_data(field_item["value"]),
                "title": finding.get("title", ""),
                "message": finding.get("message", ""),
                "source": field_item.get("source"),
            }
        )

    extraction_path = unique_path(output_root / "extraction.json")
    with open(extraction_path, "w", encoding="utf-8") as file:
        json.dump(mask_sensitive_data(extraction), file, ensure_ascii=False, indent=2)

    highlighted_pdf_path = unique_path(output_root / "highlighted.pdf")
    doc.save(str(highlighted_pdf_path))
    doc.close()

    highlighted_doc = fitz.open(str(highlighted_pdf_path))
    highlighted_png_path = unique_path(output_root / "highlighted.png")
    render_page_png(highlighted_doc[0], str(highlighted_png_path))
    highlighted_doc.close()

    highlight_json_path = unique_path(output_root / "highlighted_findings.json")
    with open(highlight_json_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "summary": verification_summary.get("analysis", {}).get("summary", {}),
                "rag_summary": rag_summary or {},
                "highlights": mask_sensitive_data(highlight_items),
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    result = {
        "pdf_path": pdf_path,
        "output_dir": str(output_root),
        "extraction_path": str(extraction_path),
        "highlighted_pdf_path": str(highlighted_pdf_path),
        "rendered_png_path": str(rendered_png_path),
        "highlighted_png_path": str(highlighted_png_path),
        "highlight_json_path": str(highlight_json_path),
        "page_count": len(extraction["pages"]),
        "field_count": sum(len(page["fields"]) for page in extraction["pages"]),
        "highlight_count": len([item for item in highlight_items if item.get("page_number") is not None]),
        "highlights": highlight_items,
    }

    result_path = unique_path(output_root / "result.json")
    with open(result_path, "w", encoding="utf-8") as file:
        json.dump(mask_sensitive_data(result), file, ensure_ascii=False, indent=2)

    return result
