"""Seed the multi-volume encyclopaedia fixture.

Shares the helpers with `seed_diverse_catalog`, including the session: a copy is
written to the tenant plane, so this has to sign in the same way.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python seed_encyclopedia.py \\
        --email katalog@kku.edu.tr --password '...'"

Both may come from SEED_EMAIL and SEED_PASSWORD instead.
"""

import argparse
import os

from seed_diverse_catalog import (
    add_identifier,
    add_subject,
    add_work_agent,
    configure,
    create_collective_agent,
    create_concept,
    create_expression,
    create_item,
    create_manifestation,
)


def main(email, password):
    configure(email, password)

    print("\nOluşturuluyor: İslâm Ansiklopedisi")

    work_id = "8d7e7a2a-c6ad-4086-95bb-9f2e0098e604"

    institution_id = create_collective_agent(
        "Türkiye Diyanet Vakfı İslâm Araştırmaları Merkezi"
    )

    # The publisher is the Work's creator. The copy belongs to whoever is signed
    # in: custody is the tenant now, so there is no holding institution to name
    # and no relation row to write.
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
        description=(
            "İslâm Ansiklopedisi Türkçe yazılı anlatımı."
        ),
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

    print("\nAnsiklopedi kaydı tamamlandı.")
    print(f"  Work          : {work_id}")
    print(f"  Institution   : {institution_id}")
    print(f"  Concept       : {concept_id}")
    print(f"  Expression    : {expression_id}")
    print(f"  Manifestation : {manifestation_id}")
    print(f"  Item          : {item_id}")


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
