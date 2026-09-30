"""Seed a small, deliberately varied catalogue.

Global records -- works, expressions, manifestations, persons, concepts -- are
still created through the open API, because that is how the global plane is
written and nothing about that changed.

Copies are not. `POST /items` used to write a global `public.items` row and
register the copy in the identity registry, which is exactly what Aşama 6 has to
remove and why this moved. A copy belongs to an institution, under a Holding, in
a branch, so the script now signs in and goes through `/tenant/holdings` and
`/tenant/items`. Custody is the tenant itself; there is no relation row to write,
because the structure already says it.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python seed_diverse_catalog.py \\
        --email katalog@kku.edu.tr --password '...'"

Both may come from SEED_EMAIL and SEED_PASSWORD instead. The tenant is whatever
the account belongs to and is never passed in.

See docs/architecture-v2.md §0.17.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


BASE_URL = os.environ.get("LIBRARYHUB_API", "http://localhost:8000")

# Filled by configure(). Module state rather than an argument threaded through
# every helper: all of them need it and none of them is about authentication.
TOKEN = None
BRANCH_ID = None


def request(method, path, data=None):
    body = None
    headers = {}

    if data is not None:
        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        headers["Content-Type"] = "application/json; charset=utf-8"

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

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


def configure(email, password):
    """Sign in, and pick the branch new holdings go into.

    There is no default to fall back on. The tenant comes from the account, so a
    script that has not signed in has no business writing anything -- which is
    the whole point of the boundary this replaces.
    """
    global TOKEN, BRANCH_ID

    session = request(
        "POST",
        "/auth/login",
        {"email": email, "password": password},
    )

    TOKEN = session["token"]

    branches = request("GET", "/tenant/branches")

    if not branches["count"]:
        raise RuntimeError(
            f"'{session['user']['tenant_name']}' için tanımlı şube yok."
        )

    # The endpoint orders the default branch first.
    BRANCH_ID = branches["branches"][0]["id"]

    print(
        f"Oturum: {session['user']['email']} @ {session['user']['tenant_name']} "
        f"(şube: {branches['branches'][0]['name']})"
    )

    return session["user"]


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
    """Create a copy in the tenant plane, under a new Holding.

    One Holding per seeded manifestation, keyed by the barcode. The copy is not
    an entity and does not need one: it is identified by its own id inside the
    tenant, and `tenant.items.legacy_entity_id` is only for rows migrated from
    the old global table.
    """
    holding = request(
        "POST",
        "/tenant/holdings",
        {
            "branch_id": BRANCH_ID,
            "manifestation_entity_id": manifestation_id,
            "local_holding_key": barcode,
            "call_number": shelfmark,
            "holding_type": "physical",
        },
    )

    item = request(
        "POST",
        "/tenant/items",
        {
            "holding_id": holding["id"],
            "barcode": barcode,
            "shelfmark": shelfmark,
            "condition": "good",
            "availability_status": "available",
            "notes": "LibraryHub örnek katalog nüshası.",
        },
    )

    return item["id"]


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


def main(email, password):
    configure(email, password)

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=os.environ.get("SEED_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("SEED_PASSWORD"))
    arguments = parser.parse_args()

    if not arguments.email or not arguments.password:
        parser.error(
            "--email ve --password gerekli (veya SEED_EMAIL / SEED_PASSWORD)"
        )

    main(arguments.email, arguments.password)