def safe_get(data: dict, *keys, default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def normalize_space(text: str | None) -> str | None:
    if text is None:
        return None
    return " ".join(str(text).strip().split())


def extract_sido_sigungu(address: str | None) -> tuple[str | None, str | None]:
    address = normalize_space(address)
    if not address:
        return None, None

    parts = address.split()
    if len(parts) < 2:
        return None, None

    return parts[0], parts[1]


def normalize_registration_number(reg_no: str | None) -> str | None:
    reg_no = normalize_space(reg_no)
    if not reg_no:
        return None
    return reg_no


def normalize_person(extracted: dict, role: str) -> dict:
    return {
        "address": normalize_space(safe_get(extracted, role, "address", "value")),
        "name": normalize_space(safe_get(extracted, role, "name", "value")),
    }


def first_value(*values):
    for value in values:
        if value is not None:
            return value
    return None


def normalize_contract_for_validation(extracted: dict) -> dict:
    property_address = safe_get(extracted, "property", "address", "value")
    leased_part_raw = safe_get(extracted, "property", "leased_part", "raw_text")
    leased_area = first_value(
        safe_get(extracted, "property", "leased_part", "area_m2", "normalized_value"),
        safe_get(extracted, "property", "building", "area_m2", "normalized_value"),
    )

    broker_registration_number = safe_get(extracted, "broker", "registration_number", "value")
    broker_office_address = safe_get(extracted, "broker", "office_address", "value")
    broker_office_name = safe_get(extracted, "broker", "office_name", "value")
    broker_representative_name = safe_get(extracted, "broker", "representative_name", "value")

    sido, sigungu = extract_sido_sigungu(broker_office_address)

    return {
        "property": {
            "address": normalize_space(property_address),
            "leased_part_raw": normalize_space(leased_part_raw),
            "area_m2": leased_area,
        },
        "payment": {
            "deposit": safe_get(extracted, "payment", "deposit", "normalized_value"),
            "monthly_rent": safe_get(extracted, "payment", "monthly_rent", "normalized_value"),
        },
        "lessor": normalize_person(extracted, "lessor"),
        "lessee": normalize_person(extracted, "lessee"),
        "broker": {
            "registration_number": normalize_registration_number(broker_registration_number),
            "office_address": normalize_space(broker_office_address),
            "office_name": normalize_space(broker_office_name),
            "representative_name": normalize_space(broker_representative_name),
            "sido": sido,
            "sigungu": sigungu,
        }
    }
