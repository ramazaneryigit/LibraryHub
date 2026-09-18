from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    Entity,
    Work,
    Person,
    Nomen,
    WorkAgentRelation,
    Concept,
    EntityRelation,
)


app = FastAPI(
    title="LibraryHub API",
    version="0.1.0",
)
app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


class WorkCreate(BaseModel):
    canonical_title: str = Field(min_length=1, max_length=1000)
    original_title: str | None = Field(default=None, max_length=1000)
    original_language: str | None = Field(default=None, max_length=100)
    description: str | None = None


class PersonCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    given_name: str | None = Field(default=None, max_length=250)
    family_name: str | None = Field(default=None, max_length=250)
    biography: str | None = None


class NomenCreate(BaseModel):
    value: str = Field(min_length=1, max_length=1000)
    language: str | None = Field(default=None, max_length=100)
    script: str | None = Field(default=None, max_length=100)
    nomen_type: str | None = Field(default=None, max_length=100)
    preferred: bool = False


class AgentRelationCreate(BaseModel):
    agent_entity_id: UUID
    role: str = Field(min_length=1, max_length=100)


class EntityRelationCreate(BaseModel):
    object_entity_id: UUID
    predicate: str = Field(min_length=1, max_length=100)


RELATION_DEFINITIONS = {
    "broader": {
        "inverse": "narrower",
        "symmetric": False,
    },
    "has_subject": {
        "inverse": "subject_of",
        "symmetric": False,
    },
    "related_to": {
        "inverse": "related_to",
        "symmetric": True,
    },
}

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("app/static/index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
    }
@app.get("/relations/{entity_id}")
def list_entity_relations(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    """Entity ile ilişkili tüm ilişkileri listeler (gelen ve giden)"""
    entity = db.get(Entity, entity_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    rows = db.execute(
        text("""
            SELECT
                er.subject_entity_id,
                er.predicate,
                er.object_entity_id
            FROM entity_relation er
            WHERE er.subject_entity_id = :entity_id
               OR er.object_entity_id = :entity_id
            ORDER BY er.predicate
        """),
        {"entity_id": str(entity_id)},
    ).fetchall()

    relations = []

    for row in rows:
        subject_id = row.subject_entity_id
        predicate = row.predicate
        object_id = row.object_entity_id

        definition = RELATION_DEFINITIONS.get(predicate)

        if str(subject_id) == str(entity_id):
            direction = "outgoing"
            related_entity_id = object_id

            relation = {
                "direction": direction,
                "predicate": predicate,
                "related_entity_id": str(related_entity_id),
            }

            if definition:
                relation["inverse"] = definition["inverse"]
                relation["symmetric"] = definition["symmetric"]

        else:
            direction = "incoming"
            related_entity_id = subject_id

            relation = {
                "direction": direction,
                "predicate": predicate,
                "related_entity_id": str(related_entity_id),
            }

            if definition:
                relation["inverse"] = definition["inverse"]
                relation["symmetric"] = definition["symmetric"]

        relations.append(relation)

    return {
        "entity_id": str(entity_id),
        "relations": relations,
    }

    
@app.post("/relations/{entity_id}", status_code=201)
def create_entity_relation(
    entity_id: UUID,
    payload: EntityRelationCreate,
    db: Session = Depends(get_db),
):
    """Entity arasında yeni bir ilişki oluşturur ve tüm ilişkileri döner"""
    subject = db.get(Entity, entity_id)

    if subject is None:
        raise HTTPException(
            status_code=404,
            detail="Subject entity not found",
        )

    object_entity = db.get(Entity, payload.object_entity_id)

    if object_entity is None:
        raise HTTPException(
            status_code=404,
            detail="Object entity not found",
        )

    relation = EntityRelation(
        subject_entity_id=entity_id,
        predicate=payload.predicate.strip(),
        object_entity_id=payload.object_entity_id,
    )

    try:
        db.add(relation)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This entity relation already exists",
        )

    # Yeni ilişki oluşturulduktan sonra, entity'nin tüm ilişkilerini listele
    rows = db.execute(
        text("""
            SELECT
                er.subject_entity_id,
                er.predicate,
                er.object_entity_id
            FROM entity_relation er
            WHERE er.subject_entity_id = :entity_id
               OR er.object_entity_id = :entity_id
            ORDER BY er.predicate
        """),
        {"entity_id": str(entity_id)},
    ).fetchall()

    relations = []

    for row in rows:
        subject_id = row.subject_entity_id
        predicate = row.predicate
        object_id = row.object_entity_id

        definition = RELATION_DEFINITIONS.get(predicate)

        if str(subject_id) == str(entity_id):
            direction = "outgoing"
            related_entity_id = object_id

            relation_item = {
                "direction": direction,
                "predicate": predicate,
                "related_entity_id": str(related_entity_id),
            }

            if definition:
                relation_item["inverse"] = definition["inverse"]
                relation_item["symmetric"] = definition["symmetric"]

        else:
            direction = "incoming"
            related_entity_id = subject_id

            relation_item = {
                "direction": direction,
                "predicate": predicate,
                "related_entity_id": str(related_entity_id),
            }

            if definition:
                relation_item["inverse"] = definition["inverse"]
                relation_item["symmetric"] = definition["symmetric"]

        relations.append(relation_item)

    return {
        "entity_id": str(entity_id),
        "relations": relations,
    }
@app.get("/works")
def list_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count()).select_from(Work)
    )

    offset = (page - 1) * page_size

    works = db.scalars(
        select(Work)
        .order_by(Work.canonical_title, Work.entity_id)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "entity_id": str(work.entity_id),
                "canonical_title": work.canonical_title,
                "original_title": work.original_title,
                "original_language": work.original_language,
            }
            for work in works
        ],
    }


@app.get("/works/{entity_id}")
def get_work(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(Work, entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    return {
        "entity_id": str(work.entity_id),
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
        "description": work.description,
    }


@app.post("/works", status_code=201)
def create_work(
    payload: WorkCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="WORK",
    )

    work = Work(
        entity_id=entity_id,
        canonical_title=payload.canonical_title,
        original_title=payload.original_title,
        original_language=payload.original_language,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.add(work)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "WORK",
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
    }


@app.post("/persons", status_code=201)
def create_person(
    payload: PersonCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="PERSON",
    )

    person = Person(
        entity_id=entity_id,
        canonical_name=payload.canonical_name,
        given_name=payload.given_name,
        family_name=payload.family_name,
        biography=payload.biography,
    )

    primary_nomen = Nomen(
        id=uuid4(),
        entity_id=entity_id,
        value=payload.canonical_name,
        preferred=True,
        nomen_type="preferred_name",
    )

    try:
        db.add(entity)
        db.add(person)
        db.add(primary_nomen)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "PERSON",
        "canonical_name": person.canonical_name,
        "preferred_nomen": primary_nomen.value,
    }


@app.get("/persons")
def list_persons(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count()).select_from(Person)
    )

    offset = (page - 1) * page_size

    persons = db.scalars(
        select(Person)
        .order_by(Person.canonical_name, Person.entity_id)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "entity_id": str(person.entity_id),
                "canonical_name": person.canonical_name,
                "given_name": person.given_name,
                "family_name": person.family_name,
            }
            for person in persons
        ],
    }


@app.get("/persons/{entity_id}")
def get_person(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    person = db.get(Person, entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    nomens = db.scalars(
        select(Nomen)
        .where(Nomen.entity_id == entity_id)
        .order_by(Nomen.preferred.desc(), Nomen.value)
    ).all()

    return {
        "entity_id": str(person.entity_id),
        "canonical_name": person.canonical_name,
        "given_name": person.given_name,
        "family_name": person.family_name,
        "biography": person.biography,
        "nomens": [
            {
                "id": str(nomen.id),
                "value": nomen.value,
                "language": nomen.language,
                "script": nomen.script,
                "nomen_type": nomen.nomen_type,
                "preferred": nomen.preferred,
            }
            for nomen in nomens
        ],
    }
@app.get("/persons/{entity_id}/works")
def get_person_works(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    person = db.get(Person, entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                w.entity_id,
                war.role
            FROM work_agent_relation war
            JOIN works w
              ON w.entity_id = war.work_entity_id
            WHERE war.agent_entity_id = :entity_id
            ORDER BY w.entity_id
            """
        ),
        {
            "entity_id": entity_id,
        },
    ).mappings().all()

    works = []

    for row in rows:
        detail = build_work_detail(
            work_entity_id=row["entity_id"],
            db=db,
        )

        if detail is not None:
            works.append(
                {
                    "role": row["role"],
                    "work": detail,
                }
            )

    return {
        "entity_id": str(person.entity_id),
        "canonical_name": person.canonical_name,
        "biography": person.biography,
        "works": works,
    }


@app.post("/persons/{entity_id}/nomens", status_code=201)
def create_nomen(
    entity_id: UUID,
    payload: NomenCreate,
    db: Session = Depends(get_db),
):
    person = db.get(Person, entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    nomen = Nomen(
        id=uuid4(),
        entity_id=entity_id,
        value=payload.value,
        language=payload.language,
        script=payload.script,
        nomen_type=payload.nomen_type,
        preferred=payload.preferred,
    )

    try:
        db.add(nomen)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "id": str(nomen.id),
        "entity_id": str(entity_id),
        "value": nomen.value,
        "preferred": nomen.preferred,
    }


@app.post("/works/{work_entity_id}/agents", status_code=201)
def add_work_agent(
    work_entity_id: UUID,
    payload: AgentRelationCreate,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    agent = db.get(Entity, payload.agent_entity_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agent entity not found",
        )

    if agent.entity_type not in {"PERSON", "COLLECTIVE_AGENT"}:
        raise HTTPException(
            status_code=400,
            detail="Entity is not an Agent",
        )

    relation = WorkAgentRelation(
        work_entity_id=work_entity_id,
        agent_entity_id=payload.agent_entity_id,
        role=payload.role,
    )

    try:
        db.add(relation)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This Work-Agent relation already exists",
        )

    return {
        "work_entity_id": str(work_entity_id),
        "agent_entity_id": str(payload.agent_entity_id),
        "role": payload.role,
    }


@app.get("/works/{work_entity_id}/agents")
def list_work_agents(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    relations = db.scalars(
        select(WorkAgentRelation)
        .where(
            WorkAgentRelation.work_entity_id == work_entity_id
        )
        .order_by(WorkAgentRelation.role)
    ).all()

    result = []

    for relation in relations:
        agent = db.get(Entity, relation.agent_entity_id)

        if agent is None:
            continue

        if agent.entity_type == "PERSON":
            person = db.get(Person, relation.agent_entity_id)

            if person is not None:
                result.append(
                    {
                        "entity_id": str(person.entity_id),
                        "entity_type": "PERSON",
                        "name": person.canonical_name,
                        "role": relation.role,
                    }
                )

        elif agent.entity_type == "COLLECTIVE_AGENT":
            result.append(
                {
                    "entity_id": str(agent.id),
                    "entity_type": "COLLECTIVE_AGENT",
                    "role": relation.role,
                }
            )

    return result


@app.get("/search/concept/{concept_entity_id}")
def search_by_concept(
    concept_entity_id: UUID,
    db: Session = Depends(get_db),
):
    concept = db.get(Concept, concept_entity_id)

    if concept is None:
        raise HTTPException(
            status_code=404,
            detail="Concept not found",
        )

    query = """
    WITH RECURSIVE concept_tree AS (
        SELECT
            c.entity_id,
            c.preferred_label,
            0 AS level
        FROM concepts c
        WHERE c.entity_id = :concept_id

        UNION ALL

        SELECT
            c.entity_id,
            c.preferred_label,
            ct.level + 1
        FROM concept_tree ct
        JOIN entity_relation er
          ON er.object_entity_id = ct.entity_id
         AND er.predicate = 'broader'
        JOIN concepts c
          ON c.entity_id = er.subject_entity_id
    )
    SELECT
        w.entity_id,
        w.canonical_title,
        ct.preferred_label AS matched_concept,
        ct.level
    FROM concept_tree ct
    JOIN entity_relation er
      ON er.object_entity_id = ct.entity_id
     AND er.predicate = 'has_subject'
    JOIN works w
      ON w.entity_id = er.subject_entity_id
    ORDER BY
        ct.level,
        w.canonical_title
    """

    rows = db.execute(
        text(query),
        {"concept_id": str(concept_entity_id)},
    ).mappings().all()

    
    results = []

    for row in rows:
        work_detail = build_work_detail(
            work_entity_id=row["entity_id"],
            db=db,
        )

        results.append({
            "work_entity_id": str(row["entity_id"]),
            "canonical_title": row["canonical_title"],
            "matched_concept": row["matched_concept"],
            "level": row["level"],
            "authors": work_detail["authors"],
            "expressions": work_detail["expressions"],
        })

    return {
        "concept": {
            "entity_id": str(concept.entity_id),
            "preferred_label": concept.preferred_label,
        },
        "results": results,
    }


def build_work_detail(
    work_entity_id: UUID,
    db: Session,
):
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

    publishers = []
    items = []

    if manifestation_ids:
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
        item_query = """
        SELECT
            mi.manifestation_entity_id,
            i.entity_id,
            i.barcode,
            i.shelfmark,
            i.condition,
            i.availability_status,
            i.notes
        FROM manifestation_item mi
        JOIN items i
          ON i.entity_id = mi.item_entity_id
        WHERE mi.manifestation_entity_id = ANY(:manifestation_ids)
        ORDER BY i.shelfmark, i.barcode
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
        holding_query = """
        SELECT
            iar.item_entity_id,
            ca.entity_id,
            ca.canonical_name,
            iar.role
        FROM item_agent_relation iar
        JOIN collective_agents ca
          ON ca.entity_id = iar.agent_entity_id
        WHERE iar.item_entity_id = ANY(:item_ids)
          AND iar.role = 'holding_institution'
        ORDER BY ca.canonical_name
        """

        holding_institutions = db.execute(
            text(holding_query),
            {"item_ids": item_ids},
        ).mappings().all()

    # Build hierarchical WEMI response

    expression_agents_by_expression = {}
    for row in expression_agents:
        expression_id = str(row["expression_entity_id"])

        expression_agents_by_expression.setdefault(
            expression_id, []
        ).append({
            "entity_id": str(row["entity_id"]),
            "name": row["canonical_name"],
            "role": row["role"],
        })

    publishers_by_manifestation = {}
    for row in publishers:
        manifestation_id = str(row["manifestation_entity_id"])

        publishers_by_manifestation.setdefault(
            manifestation_id, []
        ).append({
            "entity_id": str(row["entity_id"]),
            "name": row["canonical_name"],
            "role": row["role"],
        })

    holdings_by_item = {}
    for row in holding_institutions:
        item_id = str(row["item_entity_id"])

        holdings_by_item.setdefault(
            item_id, []
        ).append({
            "entity_id": str(row["entity_id"]),
            "name": row["canonical_name"],
            "role": row["role"],
        })

    items_by_manifestation = {}
    for row in items:
        manifestation_id = str(row["manifestation_entity_id"])
        item_id = str(row["entity_id"])

        items_by_manifestation.setdefault(
            manifestation_id, []
        ).append({
            "entity_id": item_id,
            "barcode": row["barcode"],
            "shelfmark": row["shelfmark"],
            "condition": row["condition"],
            "availability_status": row["availability_status"],
            "notes": row["notes"],
            "holding_institutions": holdings_by_item.get(
                item_id, []
            ),
        })

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
            "publishers": publishers_by_manifestation.get(
                manifestation_id, []
            ),
            "items": items_by_manifestation.get(
                manifestation_id, []
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
            "agents": expression_agents_by_expression.get(
                expression_id, []
            ),
            "manifestations": manifestations_by_expression.get(
                expression_id, []
            ),
        })

    return {
        "entity_id": str(work.entity_id),
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
        "description": work.description,

        "authors": [
            {
                "entity_id": str(row["entity_id"]),
                "name": row["canonical_name"],
                "role": row["role"],
            }
            for row in authors
        ],

        "subjects": [
            {
                "entity_id": str(row["entity_id"]),
                "label": row["preferred_label"],
            }
            for row in subjects
        ],

        "expressions": expression_tree,
    }


@app.get("/works/{work_entity_id}/detail")
def get_work_detail(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    result = build_work_detail(work_entity_id, db)
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )
    
    return result
    
@app.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    db: Session = Depends(get_db),
):
    search_term = f"%{q.strip()}%"

    query = """
    SELECT DISTINCT
        w.entity_id,
        w.canonical_title
    FROM works w

    -- Work yazarları / yaratıcıları
    LEFT JOIN work_agent_relation war
      ON war.work_entity_id = w.entity_id
    LEFT JOIN persons work_person
      ON work_person.entity_id = war.agent_entity_id

    -- Work konuları
    LEFT JOIN entity_relation subject_rel
      ON subject_rel.subject_entity_id = w.entity_id
     AND subject_rel.predicate = 'has_subject'
    LEFT JOIN concepts concept
      ON concept.entity_id = subject_rel.object_entity_id

    -- Work -> Expression
    LEFT JOIN work_expression we
      ON we.work_entity_id = w.entity_id
    LEFT JOIN expressions expression
      ON expression.entity_id = we.expression_entity_id

    -- Expression kişileri (örn. çevirmen)
    LEFT JOIN expression_agent_relation ear
      ON ear.expression_entity_id = expression.entity_id
    LEFT JOIN persons expression_person
      ON expression_person.entity_id = ear.agent_entity_id

    -- Expression -> Manifestation
    LEFT JOIN expression_manifestation em
      ON em.expression_entity_id = expression.entity_id
    LEFT JOIN manifestations manifestation
      ON manifestation.entity_id = em.manifestation_entity_id

    -- Manifestation -> Item
    LEFT JOIN manifestation_item mi
      ON mi.manifestation_entity_id = manifestation.entity_id
    LEFT JOIN items item
      ON item.entity_id = mi.item_entity_id

    WHERE
        w.canonical_title ILIKE :search_term
        OR w.original_title ILIKE :search_term
        OR work_person.canonical_name ILIKE :search_term
        OR concept.preferred_label ILIKE :search_term
        OR expression_person.canonical_name ILIKE :search_term
        OR item.barcode ILIKE :search_term
        OR item.shelfmark ILIKE :search_term

    ORDER BY w.canonical_title
    LIMIT 50
    """

    rows = db.execute(
        text(query),
        {"search_term": search_term},
    ).mappings().all()

    results = []

    for row in rows:
        work_detail = build_work_detail(
            work_entity_id=row["entity_id"],
            db=db,
        )

        if work_detail is not None:
            results.append(work_detail)

    return {
        "query": q,
        "count": len(results),
        "results": results,
    }