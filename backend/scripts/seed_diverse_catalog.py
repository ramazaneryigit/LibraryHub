import json
import urllib.error
import urllib.request


BASE_URL = "http://localhost:8000"


def request(method, path, data=None):
    body = None
    headers = {}

    if data is not None:
        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise RuntimeError(
            f"{method} {path} -> HTTP {exc.code}\n{error_body}"
        ) from exc


def create_work(
    title,
    work_type,
    language="tr",
    description=None,
):
    result = request(
        "POST",
        "/works",
        {
            "canonical_title": title,
            "original_title": None,
            "original_language": language,
            "work_type": work_type,
            "description": description,
        },
    )

    return result["entity_id"]


def create_expression(
    work_id,
    language="tr",
    expression_form="written",
    description=None,
):
    result = request(
        "POST",
        "/expressions",
        {
            "work_entity_id": work_id,
            "language": language,
            "expression_form": expression_form,
            "description": description,
        },
    )

    return result["entity_id"]


def create_manifestation(
    expression_id,
    publication_statement,
    publication_date,
    edition_statement=None,
    carrier_type="kitap",
    extent=None,
    notes=None,
):
    result = request(
        "POST",
        "/manifestations",
        {
            "expression_entity_id": expression_id,
            "publication_statement": publication_statement,
            "publication_date": publication_date,
            "edition_statement": edition_statement,
            "carrier_type": carrier_type,
            "extent": extent,
            "notes": notes,
        },
    )

    return result["entity_id"]


def create_item(
    manifestation_id,
    barcode,
    shelfmark,
):
    result = request(
        "POST",
        "/items",
        {
            "manifestation_entity_id": manifestation_id,
            "barcode": barcode,
            "shelfmark": shelfmark,
            "condition": "good",
            "availability_status": "available",
            "notes": "LibraryHub örnek katalog nüshası.",
        },
    )

    return result["entity_id"]


def create_person(
    name,
    given_name=None,
    family_name=None,
):
    result = request(
        "POST",
        "/persons?force_create=true",
        {
            "canonical_name": name,
            "given_name": given_name,
            "family_name": family_name,
            "biography": "LibraryHub test verisi için oluşturulan örnek kişi.",
        },
    )

    return result["entity_id"]


def create_collective_agent(
    name,
    agent_type="organization",
):
    result = request(
        "POST",
        "/collective-agents",
        {
            "canonical_name": name,
            "agent_type": agent_type,
            "description": "LibraryHub test verisi için oluşturulan kurum.",
        },
    )

    return result["entity_id"]


def create_concept(label):
    result = request(
        "POST",
        "/concepts",
        {
            "preferred_label": label,
            "definition": f"{label} konusunu temsil eden örnek kavram.",
            "scheme": "LibraryHub Test Subjects",
        },
    )

    return result["entity_id"]


def add_work_agent(work_id, agent_id, role):
    return request(
        "POST",
        f"/works/{work_id}/agents",
        {
            "agent_entity_id": agent_id,
            "role": role,
        },
    )


def add_subject(work_id, concept_id):
    return request(
        "POST",
        f"/relations/{work_id}",
        {
            "object_entity_id": concept_id,
            "predicate": "has_subject",
        },
    )


def add_identifier(
    entity_id,
    scheme,
    value,
    preferred=False,
):
    return request(
        "POST",
        f"/entities/{entity_id}/identifiers",
        {
            "scheme": scheme,
            "value": value,
            "qualifier": "LibraryHub seed identifier",
            "preferred": preferred,
        },
    )


def create_complete_record(
    *,
    title,
    work_type,
    author_name,
    subject,
    publication_statement,
    publication_date,
    barcode,
    shelfmark,
    identifier,
    identifier_scheme="local",
    extent=None,
    carrier_type="kitap",
):
    print(f"\nOluşturuluyor: {title}")

    work_id = create_work(
        title=title,
        work_type=work_type,
        description=f"{title} için LibraryHub örnek Work kaydı.",
    )

    person_id = create_person(author_name)

    add_work_agent(
        work_id,
        person_id,
        "creator",
    )

    concept_id = create_concept(subject)

    add_subject(
        work_id,
        concept_id,
    )

    expression_id = create_expression(
        work_id,
        language="tr",
        expression_form="written",
        description=f"{title} Türkçe yazılı anlatımı.",
    )

    manifestation_id = create_manifestation(
        expression_id,
        publication_statement,
        publication_date,
        edition_statement="1. baskı",
        carrier_type=carrier_type,
        extent=extent,
        notes="LibraryHub çeşitlendirilmiş katalog test kaydı.",
    )

    item_id = create_item(
        manifestation_id,
        barcode,
        shelfmark,
    )

    add_identifier(
        manifestation_id,
        identifier_scheme,
        identifier,
        preferred=True,
    )

    print(f"  Work          : {work_id}")
    print(f"  Expression    : {expression_id}")
    print(f"  Manifestation : {manifestation_id}")
    print(f"  Item          : {item_id}")

    return work_id


def main():
    print("LibraryHub çeşitli katalog seed işlemi başlıyor.")

    create_complete_record(
        title="Bilgi Yönetimine Giriş",
        work_type="textbook",
        author_name="Ayşe Demir",
        subject="Bilgi yönetimi",
        publication_statement="Ankara : Akademi Yayınları",
        publication_date="2025",
        barcode="KKU-AKADEMIK-0001",
        shelfmark="Z665 B55 2025",
        identifier="9780000000001",
        identifier_scheme="isbn",
        extent="320 sayfa",
    )

    create_complete_record(
        title="Gökyüzünü Merak Eden Çocuk",
        work_type="children_literature",
        author_name="Mehmet Yıldız",
        subject="Çocuklar için astronomi",
        publication_statement="İstanbul : Çocuk Dünyası Yayınları",
        publication_date="2024",
        barcode="KKU-COCUK-0001",
        shelfmark="PZ8 G65 2024",
        identifier="9780000000002",
        identifier_scheme="isbn",
        extent="96 sayfa",
    )

    create_complete_record(
        title="Üniversite Kütüphanelerinde Dijital Arşivleme Uygulamaları",
        work_type="thesis",
        author_name="Elif Kaya",
        subject="Dijital arşivleme",
        publication_statement="Ankara : Örnek Üniversitesi",
        publication_date="2026",
        barcode="KKU-TEZ-0001",
        shelfmark="Z701.3 E45 2026",
        identifier="THESIS-2026-0001",
        identifier_scheme="local",
        extent="185 yaprak",
        carrier_type="tez",
    )

    #
    # Ansiklopedi senaryosu kurumsal sorumluluk gerektirdiği için
    # ayrı oluşturuluyor.
    #
    print("\nOluşturuluyor: İslâm Ansiklopedisi")

    work_id = create_work(
        title="İslâm Ansiklopedisi",
        work_type="encyclopedia",
        description="Çok ciltli ansiklopedi yapısını sınamak için örnek Work.",
    )

    institution_id = create_collective_agent(
        "Türkiye Diyanet Vakfı İslâm Araştırmaları Merkezi"
    )

    add_work_agent(
        work_id,
        institution_id,
        "creator",
    )

    concept_id = create_concept(
        "İslâm kültürü ve medeniyeti"
    )

    add_subject(
        work_id,
        concept_id,
    )

    expression_id = create_expression(
        work_id,
        language="tr",
        expression_form="written",
        description="İslâm Ansiklopedisi Türkçe yazılı anlatımı.",
    )

    manifestation_id = create_manifestation(
        expression_id,
        "İstanbul : Türkiye Diyanet Vakfı",
        "1988-2013",
        edition_statement="1. baskı",
        carrier_type="çok ciltli kitap",
        extent="44 cilt",
        notes="Çok ciltli manifestation test kaydı.",
    )

    item_id = create_item(
        manifestation_id,
        "KKU-ANSIKLOPEDI-SET-0001",
        "DR440 I75",
    )

    add_identifier(
        manifestation_id,
        "local",
        "TDV-IA-SET-001",
        preferred=True,
    )

    print(f"  Work          : {work_id}")
    print(f"  Expression    : {expression_id}")
    print(f"  Manifestation : {manifestation_id}")
    print(f"  Item          : {item_id}")

    print("\nSeed işlemi tamamlandı.")


if __name__ == "__main__":
    main()