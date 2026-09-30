from seed_diverse_catalog import (
    create_work,
    create_collective_agent,
    create_concept,
    create_expression,
    create_manifestation,
    create_item,
    add_work_agent,
    add_subject,
    add_identifier,
)


def main():
    print("\nOluşturuluyor: İslâm Ansiklopedisi")

    work_id = "8d7e7a2a-c6ad-4086-95bb-9f2e0098e604"

    institution_id = create_collective_agent(
        "Türkiye Diyanet Vakfı İslâm Araştırmaları Merkezi"
    )

    # The publisher is the Work's creator; the KKU-* copy is held by Kırıkkale.
    # These are different roles and the item needs its own recorded custody.
    holding_institution_id = create_collective_agent(
        "Kırıkkale Üniversitesi",
        agent_type="university",
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
        holding_institution_id=holding_institution_id,
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
    main()