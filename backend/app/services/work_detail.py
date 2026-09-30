from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Work
from .entity_merge import resolve_canonical_entity_id


# Copies whose owning institution was never recorded still have to be counted.
# Dropping them would understate a library's holdings, which is worse than
# showing an explicit "institution not recorded" bucket.
UNATTRIBUTED_INSTITUTION = {
    "entity_id": None,
    "name": None,
}


def build_work_detail(
    work_entity_id: UUID,
    db: Session,
):
    canonical_work_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=work_entity_id,
    )

    work_entity_id = canonical_work_entity_id

    work = db.get(Work, work_entity_id)

    if work is None:
        return None


    # Authors
    author_query = """
    SELECT
        p.entity_id,
        p.canonical_name,
        war.role
    FROM work_agent_relation war
    JOIN persons p
      ON p.entity_id = war.agent_entity_id
    WHERE war.work_entity_id = :work_id
    ORDER BY p.canonical_name
    """

    authors = db.execute(
        text(author_query),
        {"work_id": str(work_entity_id)},
    ).mappings().all()

    # Subjects
    subject_query = """
    SELECT
        c.entity_id,
        c.preferred_label
    FROM entity_relation er
    JOIN concepts c
      ON c.entity_id = er.object_entity_id
    WHERE er.subject_entity_id = :work_id
      AND er.predicate = 'has_subject'
    ORDER BY c.preferred_label
    """

    subjects = db.execute(
        text(subject_query),
        {"work_id": str(work_entity_id)},
    ).mappings().all()

    # Expressions
    expression_query = """
    SELECT
        e.entity_id,
        e.language,
        e.expression_form,
        e.description
    FROM work_expression we
    JOIN expressions e
      ON e.entity_id = we.expression_entity_id
    WHERE we.work_entity_id = :work_id
    ORDER BY e.language
    """

    expressions = db.execute(
        text(expression_query),
        {"work_id": str(work_entity_id)},
    ).mappings().all()

    # Expression agents
    expression_agent_query = """
    SELECT
        ear.expression_entity_id,
        p.entity_id,
        p.canonical_name,
        ear.role
    FROM expression_agent_relation ear
    JOIN persons p
      ON p.entity_id = ear.agent_entity_id
    WHERE ear.expression_entity_id IN (
        SELECT expression_entity_id
        FROM work_expression
        WHERE work_entity_id = :work_id
    )
    ORDER BY p.canonical_name
    """

    expression_agents = db.execute(
        text(expression_agent_query),
        {"work_id": str(work_entity_id)},
    ).mappings().all()

    # Manifestations
    manifestation_query = """
    SELECT
        em.expression_entity_id,
        m.entity_id,
        m.publication_statement,
        m.publication_date,
        m.edition_statement,
        m.carrier_type,
        m.extent,
        m.notes
    FROM expression_manifestation em
    JOIN manifestations m
      ON m.entity_id = em.manifestation_entity_id
    JOIN work_expression we
      ON we.expression_entity_id = em.expression_entity_id
    WHERE we.work_entity_id = :work_id
    ORDER BY m.publication_date, m.edition_statement
    """

    manifestations = db.execute(
        text(manifestation_query),
        {"work_id": str(work_entity_id)},
    ).mappings().all()

    manifestation_ids = [
        str(row["entity_id"])
        for row in manifestations
    ]

    # Publishers
    publisher_query = """
    SELECT
        ma.manifestation_entity_id,
        ca.entity_id,
        ca.canonical_name,
        ma.role
    FROM manifestation_agent_relation ma
    JOIN collective_agents ca
      ON ca.entity_id = ma.agent_entity_id
    WHERE ma.manifestation_entity_id = ANY(:manifestation_ids)
      AND ma.role = 'publisher'
    ORDER BY ca.canonical_name
    """

    publishers = db.execute(
        text(publisher_query),
        {"manifestation_ids": manifestation_ids},
    ).mappings().all()

    # Items
    #
    # Read through public.items_compat, not the legacy tables. Items now live in
    # the Tenant Data Plane (tenant.items joined to tenant.holdings) and the
    # compatibility view reproduces the exact legacy shape while rows created
    # through the still-legacy write path remain visible. The column list and
    # the ordering are unchanged, so the response is byte-for-byte what it was.
    # See docs/architecture-v2.md §0.9.
    item_query = """
    SELECT
        v.manifestation_entity_id,
        v.entity_id,
        v.barcode,
        v.shelfmark,
        v.condition,
        v.availability_status,
        v.notes
    FROM public.items_compat v
    WHERE v.manifestation_entity_id = ANY(:manifestation_ids)
    ORDER BY v.shelfmark, v.barcode
    """

    items = db.execute(
        text(item_query),
        {"manifestation_ids": manifestation_ids},
    ).mappings().all()

    item_ids = [
        str(row["entity_id"])
        for row in items
    ]

    holding_institutions = []

    if item_ids:
        # The holding institution is structural now: it comes from the
        # organization that owns the item's tenant, not from a free-text role
        # on a relation row. The view exposes it as
        # holding_institution_entity_id and the role literal keeps the response
        # shape identical.
        holding_query = """
        SELECT
            v.entity_id AS item_entity_id,
            ca.entity_id,
            ca.canonical_name,
            'holding_institution' AS role
        FROM public.items_compat v
        JOIN collective_agents ca
          ON ca.entity_id = v.holding_institution_entity_id
        WHERE v.entity_id = ANY(:item_ids)
        ORDER BY ca.canonical_name
        """

        holding_institutions = db.execute(
            text(holding_query),
            {"item_ids": item_ids},
        ).mappings().all()

    # All identifiers for entities in this Work tree
    all_entity_ids = {str(work.entity_id)}

    all_entity_ids.update(
        str(row["entity_id"])
        for row in authors
    )

    all_entity_ids.update(
        str(row["entity_id"])
        for row in subjects
    )

    all_entity_ids.update(
        str(row["entity_id"])
        for row in expressions
    )

    all_entity_ids.update(
        str(row["entity_id"])
        for row in expression_agents
    )

    all_entity_ids.update(
        str(row["entity_id"])
        for row in manifestations
    )

    all_entity_ids.update(
        str(row["entity_id"])
        for row in publishers
    )

    identifier_query = """
    SELECT
        entity_id,
        id,
        scheme,
        value,
        qualifier,
        preferred
    FROM identifiers
    WHERE entity_id = ANY(:entity_ids)
    ORDER BY entity_id, preferred DESC, scheme, value
    """

    all_identifiers = db.execute(
        text(identifier_query),
        {"entity_ids": list(all_entity_ids)},
    ).mappings().all()

    identifiers_by_entity = {}

    for row in all_identifiers:
        entity_id = str(row["entity_id"])

        identifiers_by_entity.setdefault(
            entity_id, []
        ).append({
            "id": str(row["id"]),
            "scheme": row["scheme"],
            "value": row["value"],
            "qualifier": row["qualifier"],
            "preferred": row["preferred"],
        })

    # All nomens for entities in this Work tree
    nomen_query = """
    SELECT
        entity_id,
        id,
        value,
        language,
        script,
        nomen_type,
        preferred
    FROM nomens
    WHERE entity_id = ANY(:entity_ids)
    ORDER BY entity_id, preferred DESC, language, value
    """

    all_nomens = db.execute(
        text(nomen_query),
        {"entity_ids": list(all_entity_ids)},
    ).mappings().all()

    nomens_by_entity = {}

    for row in all_nomens:
        entity_id = str(row["entity_id"])

        nomens_by_entity.setdefault(
            entity_id, []
        ).append({
            "id": str(row["id"]),
            "value": row["value"],
            "language": row["language"],
            "script": row["script"],
            "nomen_type": row["nomen_type"],
            "preferred": row["preferred"],
        })

    # Build hierarchical WEMI response
    expression_agents_by_expression = {}

    for row in expression_agents:
        expression_id = str(row["expression_entity_id"])
        agent_id = str(row["entity_id"])

        expression_agents_by_expression.setdefault(
            expression_id, []
        ).append({
            "entity_id": agent_id,
            "name": row["canonical_name"],
            "role": row["role"],
            "identifiers": identifiers_by_entity.get(
                agent_id, []
            ),
            "nomens": nomens_by_entity.get(
                agent_id, []
            ),
        })

    publishers_by_manifestation = {}

    for row in publishers:
        manifestation_id = str(row["manifestation_entity_id"])
        publisher_id = str(row["entity_id"])

        publishers_by_manifestation.setdefault(
            manifestation_id, []
        ).append({
            "entity_id": publisher_id,
            "name": row["canonical_name"],
            "role": row["role"],
            "identifiers": identifiers_by_entity.get(
                publisher_id, []
            ),
            "nomens": nomens_by_entity.get(
                publisher_id, []
            ),
        })

    holdings_by_item = {}

    for row in holding_institutions:
        holdings_by_item.setdefault(
            str(row["item_entity_id"]), []
        ).append({
            "entity_id": str(row["entity_id"]),
            "name": row["canonical_name"],
        })

    # What the global route is allowed to say about copies.
    #
    # `/works/{id}/detail` is the *global* view: it answers "what is this work
    # and who holds it", for anyone. An individual copy is operational data of
    # the institution that owns it -- a barcode and a shelfmark describe where
    # one physical object sits on one shelf -- so this route aggregates per
    # institution instead of listing copies.
    #
    # It used to return every tenant's copies. With the scale fixtures that
    # meant a single work page listing ninety institutions' barcodes, which is
    # both an unbounded response and a cross-tenant leak once authentication
    # exists (docs/architecture-v2.md §0.12). Per-copy detail belongs to the
    # tenant-scoped view that arrives with authentication in Aşama 5.
    holdings_by_manifestation = {}
    holdings_by_institution = {}

    for row in items:
        manifestation_id = str(row["manifestation_entity_id"])
        item_id = str(row["entity_id"])
        status = row["availability_status"] or "unknown"

        institutions = holdings_by_item.get(item_id) or [
            UNATTRIBUTED_INSTITUTION
        ]

        for institution in institutions:
            key = (manifestation_id, institution["entity_id"])
            entry = holdings_by_institution.get(key)

            if entry is None:
                entry = {
                    "entity_id": institution["entity_id"],
                    "name": institution["name"],
                    "item_count": 0,
                    "availability": {},
                }
                holdings_by_institution[key] = entry
                holdings_by_manifestation.setdefault(
                    manifestation_id, []
                ).append(entry)

            entry["item_count"] += 1
            entry["availability"][status] = (
                entry["availability"].get(status, 0) + 1
            )

    manifestations_by_expression = {}

    for row in manifestations:
        expression_id = str(row["expression_entity_id"])
        manifestation_id = str(row["entity_id"])

        manifestations_by_expression.setdefault(
            expression_id, []
        ).append({
            "entity_id": manifestation_id,
            "publication_statement": row["publication_statement"],
            "publication_date": row["publication_date"],
            "edition_statement": row["edition_statement"],
            "carrier_type": row["carrier_type"],
            "extent": row["extent"],
            "notes": row["notes"],
            "identifiers": identifiers_by_entity.get(
                manifestation_id, []
            ),
            "nomens": nomens_by_entity.get(
                manifestation_id, []
            ),
            "publishers": publishers_by_manifestation.get(
                manifestation_id, []
            ),
            # Aggregated, not per copy. See the note where this is built.
            "holdings": sorted(
                holdings_by_manifestation.get(manifestation_id, []),
                key=lambda holding: (holding["name"] is None, holding["name"] or ""),
            ),
        })

    expression_tree = []

    for row in expressions:
        expression_id = str(row["entity_id"])

        expression_tree.append({
            "entity_id": expression_id,
            "language": row["language"],
            "expression_form": row["expression_form"],
            "description": row["description"],
            "identifiers": identifiers_by_entity.get(
                expression_id, []
            ),
            "nomens": nomens_by_entity.get(
                expression_id, []
            ),
            "agents": expression_agents_by_expression.get(
                expression_id, []
            ),
            "manifestations": manifestations_by_expression.get(
                expression_id, []
            ),
        })

    return {
        "entity_id": str(work.entity_id),
        "identifiers": identifiers_by_entity.get(
            str(work.entity_id), []
        ),
        "nomens": nomens_by_entity.get(
            str(work.entity_id), []
        ),
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
        "description": work.description,
        "authors": [
            {
                "entity_id": str(row["entity_id"]),
                "name": row["canonical_name"],
                "role": row["role"],
                "identifiers": identifiers_by_entity.get(
                    str(row["entity_id"]), []
                ),
                "nomens": nomens_by_entity.get(
                    str(row["entity_id"]), []
                ),
            }
            for row in authors
        ],
        "subjects": [
            {
                "entity_id": str(row["entity_id"]),
                "label": row["preferred_label"],
                "identifiers": identifiers_by_entity.get(
                    str(row["entity_id"]), []
                ),
                "nomens": nomens_by_entity.get(
                    str(row["entity_id"]), []
                ),
            }
            for row in subjects
        ],
        "expressions": expression_tree,
    }