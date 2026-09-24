from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime

from .routers import health, relations, persons, works, work_agents
from .db import get_db
from .services.work_detail import build_work_detail

from .models import (
    Entity,
    Work,
    Expression,
    Manifestation,
    Item,
    CollectiveAgent,
    Identifier,
    WorkAgentRelation,
    ItemAgentRelation,
    Concept,
    EntityRelation,
    VocabularyScheme,
    VocabularySchemeEdition,
    ClassificationNode,
    WorkClassification,
    ClassificationMapping,
)



app = FastAPI(
    title="LibraryHub API",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(relations.router)
app.include_router(persons.router)
app.include_router(works.router)
app.include_router(work_agents.router)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)




    
class CollectiveAgentCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    agent_type: str | None = Field(default=None, max_length=100)
    description: str | None = None


class ConceptCreate(BaseModel):
    preferred_label: str = Field(min_length=1, max_length=500)
    definition: str | None = None
    scheme: str | None = Field(default=None, max_length=200)
    
class VocabularySchemeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    scheme_type: str = Field(min_length=1, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    uri: str | None = Field(default=None, max_length=1000)
    description: str | None = None

class VocabularySchemeEditionCreate(BaseModel):
    edition: str = Field(min_length=1, max_length=100)
    release_date: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    uri: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default="active", max_length=100)
    description: str | None = None

class ClassificationCreate(BaseModel):
    scheme_id: UUID
    scheme_edition_id: UUID | None = None

    notation: str = Field(min_length=1, max_length=200)
    notation_end: str | None = Field(
        default=None,
        max_length=200,
    )
    caption: str | None = Field(default=None, max_length=1000)
    parent_entity_id: UUID | None = None
    uri: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default="active", max_length=100)


class WorkClassificationCreate(BaseModel):
    classification_entity_id: UUID
    is_primary: bool = False
    assigned_by: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=500)
    
class ClassificationMappingCreate(BaseModel):
    source_classification_entity_id: UUID
    target_classification_entity_id: UUID

    mapping_type: str = Field(
        pattern="^(exact_match|close_match|broad_match|narrow_match|related_match)$"
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    mapping_method: str | None = Field(
        default=None,
        max_length=100,
    )

    source: str | None = Field(
        default=None,
        max_length=500,
    )

    source_uri: str | None = Field(
        default=None,
        max_length=1000,
    )

    source_scheme_version: str | None = Field(
        default=None,
        max_length=100,
    )

    target_scheme_version: str | None = Field(
        default=None,
        max_length=100,
    )

    review_status: str | None = Field(
        default=None,
        max_length=50,
    )

    reviewed_by: str | None = Field(
        default=None,
        max_length=200,
    )
    
class ClassificationMappingCreate(BaseModel):
    source_classification_entity_id: UUID
    target_classification_entity_id: UUID

    mapping_type: str = Field(
        pattern="^(exact_match|close_match|broad_match|narrow_match|related_match)$"
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    mapping_method: str | None = Field(
        default=None,
        max_length=100,
    )

    source: str | None = Field(
        default=None,
        max_length=500,
    )

    source_uri: str | None = Field(
        default=None,
        max_length=1000,
    )

    source_scheme_version: str | None = Field(
        default=None,
        max_length=100,
    )

    target_scheme_version: str | None = Field(
        default=None,
        max_length=100,
    )

    review_status: str | None = Field(
        default=None,
        max_length=50,
    )

    reviewed_by: str | None = Field(
        default=None,
        max_length=200,
    )

class ExpressionCreate(BaseModel):
    work_entity_id: UUID
    language: str | None = Field(default=None, max_length=100)
    expression_form: str | None = Field(default=None, max_length=100)
    description: str | None = None


class ManifestationCreate(BaseModel):
    expression_entity_id: UUID
    publication_statement: str | None = Field(default=None, max_length=1000)
    publication_date: str | None = Field(default=None, max_length=100)
    edition_statement: str | None = Field(default=None, max_length=500)
    carrier_type: str | None = Field(default=None, max_length=100)
    extent: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class ItemCreate(BaseModel):
    manifestation_entity_id: UUID
    barcode: str | None = Field(default=None, max_length=200)
    shelfmark: str | None = Field(default=None, max_length=300)
    condition: str | None = Field(default=None, max_length=200)
    availability_status: str | None = Field(default=None, max_length=100)
    notes: str | None = None



    
class IdentifierCreate(BaseModel):
    scheme: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)
    qualifier: str | None = Field(default=None, max_length=500)
    preferred: bool = False

class AgentRelationCreate(BaseModel):
    agent_entity_id: UUID
    role: str = Field(min_length=1, max_length=100)

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("app/static/index.html")



@app.post("/collective-agents", status_code=201)
def create_collective_agent(
    payload: CollectiveAgentCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="ORGANIZATION",
    )

    agent = CollectiveAgent(
        entity_id=entity_id,
        canonical_name=payload.canonical_name,
        agent_type=payload.agent_type,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.flush()

        db.add(agent)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "ORGANIZATION",
        "canonical_name": agent.canonical_name,
        "agent_type": agent.agent_type,
    }

@app.post("/concepts", status_code=201)
def create_concept(
    payload: ConceptCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="CONCEPT",
    )

    concept = Concept(
        entity_id=entity_id,
        preferred_label=payload.preferred_label,
        definition=payload.definition,
        scheme=payload.scheme,
    )

    try:
        db.add(entity)
        db.flush()
        
        db.add(concept)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "CONCEPT",
        "preferred_label": concept.preferred_label,
        "scheme": concept.scheme,
    }
    
@app.post("/expressions", status_code=201)
def create_expression(
    payload: ExpressionCreate,
    db: Session = Depends(get_db),
):
    work = db.get(Work, payload.work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="EXPRESSION",
    )

    expression = Expression(
        entity_id=entity_id,
        language=payload.language,
        expression_form=payload.expression_form,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.add(expression)
        db.flush()

        db.execute(
            text("""
                INSERT INTO work_expression (
                    work_entity_id,
                    expression_entity_id
                )
                VALUES (
                    :work_entity_id,
                    :expression_entity_id
                )
            """),
            {
                "work_entity_id": payload.work_entity_id,
                "expression_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "EXPRESSION",
        "work_entity_id": str(payload.work_entity_id),
        "language": expression.language,
        "expression_form": expression.expression_form,
    }

@app.post("/manifestations", status_code=201)
def create_manifestation(
    payload: ManifestationCreate,
    db: Session = Depends(get_db),
):
    expression = db.get(
        Expression,
        payload.expression_entity_id,
    )

    if expression is None:
        raise HTTPException(
            status_code=404,
            detail="Expression not found",
        )

    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="MANIFESTATION",
    )

    manifestation = Manifestation(
        entity_id=entity_id,
        publication_statement=payload.publication_statement,
        publication_date=payload.publication_date,
        edition_statement=payload.edition_statement,
        carrier_type=payload.carrier_type,
        extent=payload.extent,
        notes=payload.notes,
    )

    try:
        db.add(entity)
        db.add(manifestation)
        db.flush()

        db.execute(
            text("""
                INSERT INTO expression_manifestation (
                    expression_entity_id,
                    manifestation_entity_id
                )
                VALUES (
                    :expression_entity_id,
                    :manifestation_entity_id
                )
            """),
            {
                "expression_entity_id": payload.expression_entity_id,
                "manifestation_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "MANIFESTATION",
        "expression_entity_id": str(payload.expression_entity_id),
        "publication_statement": manifestation.publication_statement,
        "publication_date": manifestation.publication_date,
    }

@app.post("/items", status_code=201)
def create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
):
    manifestation = db.get(
        Manifestation,
        payload.manifestation_entity_id,
    )

    if manifestation is None:
        raise HTTPException(
            status_code=404,
            detail="Manifestation not found",
        )

    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="ITEM",
    )

    item = Item(
        entity_id=entity_id,
        barcode=payload.barcode,
        shelfmark=payload.shelfmark,
        condition=payload.condition,
        availability_status=payload.availability_status,
        notes=payload.notes,
    )

    try:
        db.add(entity)
        db.add(item)
        db.flush()

        db.execute(
            text("""
                INSERT INTO manifestation_item (
                    manifestation_entity_id,
                    item_entity_id
                )
                VALUES (
                    :manifestation_entity_id,
                    :item_entity_id
                )
            """),
            {
                "manifestation_entity_id": payload.manifestation_entity_id,
                "item_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "ITEM",
        "manifestation_entity_id": str(
            payload.manifestation_entity_id
        ),
        "barcode": item.barcode,
        "shelfmark": item.shelfmark,
        "availability_status": item.availability_status,
    }


@app.get("/entities/{entity_id}/identifiers")
def get_entity_identifiers(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    entity = db.get(Entity, entity_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    identifiers = db.execute(
        select(Identifier)
        .where(Identifier.entity_id == entity_id)
        .order_by(
            Identifier.preferred.desc(),
            Identifier.scheme,
            Identifier.value,
        )
    ).scalars().all()

    return {
        "entity_id": str(entity.id),
        "entity_type": entity.entity_type,
        "identifiers": [
            {
                "id": str(identifier.id),
                "scheme": identifier.scheme,
                "value": identifier.value,
                "qualifier": identifier.qualifier,
                "preferred": identifier.preferred,
            }
            for identifier in identifiers
        ],
    }


@app.post("/entities/{entity_id}/identifiers", status_code=201)
def create_entity_identifier(
    entity_id: UUID,
    payload: IdentifierCreate,
    db: Session = Depends(get_db),
):
    entity = db.get(Entity, entity_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    identifier = Identifier(
        entity_id=entity_id,
        scheme=payload.scheme.strip().lower(),
        value=payload.value.strip(),
        qualifier=payload.qualifier.strip() if payload.qualifier else None,
        preferred=payload.preferred,
    )

    db.add(identifier)

    try:
        db.commit()
        db.refresh(identifier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This identifier already exists for this entity",
        )

    return {
        "id": str(identifier.id),
        "entity_id": str(identifier.entity_id),
        "scheme": identifier.scheme,
        "value": identifier.value,
        "qualifier": identifier.qualifier,
        "preferred": identifier.preferred,
    }


@app.post("/items/{item_entity_id}/agents", status_code=201)
def add_item_agent(
    item_entity_id: UUID,
    payload: AgentRelationCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_entity_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    agent = db.get(Entity, payload.agent_entity_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agent entity not found",
        )

    if agent.entity_type not in {"PERSON", "ORGANIZATION"}:
        raise HTTPException(
            status_code=400,
            detail="Entity is not an Agent",
        )

    relation = ItemAgentRelation(
        item_entity_id=item_entity_id,
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
            detail="This Item-Agent relation already exists",
        )

    return {
        "item_entity_id": str(item_entity_id),
        "agent_entity_id": str(payload.agent_entity_id),
        "role": payload.role,
    }


@app.get("/items/{item_entity_id}/agents")
def list_item_agents(
    item_entity_id: UUID,
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_entity_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    relations = db.scalars(
        select(ItemAgentRelation)
        .where(
            ItemAgentRelation.item_entity_id == item_entity_id
        )
        .order_by(ItemAgentRelation.role)
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

        elif agent.entity_type == "ORGANIZATION":
            organization = db.get(
                CollectiveAgent,
                relation.agent_entity_id,
            )

            result.append(
                {
                    "entity_id": str(agent.id),
                    "entity_type": "ORGANIZATION",
                    "name": (
                        organization.canonical_name
                        if organization is not None
                        else None
                    ),
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
    
    -- Work tanımlayıcıları
    LEFT JOIN identifiers work_identifier
      ON work_identifier.entity_id = w.entity_id

    -- Work yazarları / yaratıcıları
    LEFT JOIN work_agent_relation war
      ON war.work_entity_id = w.entity_id
    LEFT JOIN persons work_person
      ON work_person.entity_id = war.agent_entity_id
    -- Work kişilerinin Nomen kayıtları
    LEFT JOIN nomens work_person_nomen
      ON work_person_nomen.entity_id = work_person.entity_id
    -- Work kişilerinin tanımlayıcıları
    LEFT JOIN identifiers work_person_identifier
      ON work_person_identifier.entity_id = work_person.entity_id

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
      
    -- Expression tanımlayıcıları
    LEFT JOIN identifiers expression_identifier
      ON expression_identifier.entity_id = expression.entity_id

    -- Expression kişileri (örn. çevirmen)
    LEFT JOIN expression_agent_relation ear
      ON ear.expression_entity_id = expression.entity_id
    LEFT JOIN persons expression_person
      ON expression_person.entity_id = ear.agent_entity_id
    -- Expression kişilerinin Nomen kayıtları
    LEFT JOIN nomens expression_person_nomen
      ON expression_person_nomen.entity_id = expression_person.entity_id
    -- Expression kişilerinin tanımlayıcıları
    LEFT JOIN identifiers expression_person_identifier
      ON expression_person_identifier.entity_id = expression_person.entity_id

    -- Expression -> Manifestation
    LEFT JOIN expression_manifestation em
      ON em.expression_entity_id = expression.entity_id

    LEFT JOIN manifestations manifestation
      ON manifestation.entity_id = em.manifestation_entity_id
      
    -- Manifestation tanımlayıcıları (ISBN vb.)
    LEFT JOIN identifiers manifestation_identifier
      ON manifestation_identifier.entity_id = manifestation.entity_id

    -- Manifestation ajanları (örn. yayıncı)
    LEFT JOIN manifestation_agent_relation mar
      ON mar.manifestation_entity_id = manifestation.entity_id
    LEFT JOIN collective_agents manifestation_agent
      ON manifestation_agent.entity_id = mar.agent_entity_id
    -- Manifestation ajanının tanımlayıcıları
    LEFT JOIN identifiers manifestation_agent_identifier
      ON manifestation_agent_identifier.entity_id = manifestation_agent.entity_id

    -- Manifestation -> Item
    LEFT JOIN manifestation_item mi
      ON mi.manifestation_entity_id = manifestation.entity_id
    LEFT JOIN items item
      ON item.entity_id = mi.item_entity_id
    -- Item tanımlayıcıları
    LEFT JOIN identifiers item_identifier
      ON item_identifier.entity_id = item.entity_id

    WHERE
        w.canonical_title ILIKE :search_term
        OR w.original_title ILIKE :search_term
        OR work_identifier.value ILIKE :search_term
        OR work_person.canonical_name ILIKE :search_term
        OR work_person_nomen.value ILIKE :search_term
        OR work_person_identifier.value ILIKE :search_term
        OR concept.preferred_label ILIKE :search_term
        OR expression.language ILIKE :search_term
        OR expression_identifier.value ILIKE :search_term
        OR expression_person.canonical_name ILIKE :search_term
        OR expression_person_nomen.value ILIKE :search_term
        OR expression_person_identifier.value ILIKE :search_term
        OR manifestation.publication_statement ILIKE :search_term
        OR manifestation.publication_date ILIKE :search_term
        OR manifestation.edition_statement ILIKE :search_term
        OR manifestation_identifier.value ILIKE :search_term
        OR manifestation_agent.canonical_name ILIKE :search_term
        OR manifestation_agent_identifier.value ILIKE :search_term
        OR item.barcode ILIKE :search_term
        OR item.shelfmark ILIKE :search_term
        OR item_identifier.value ILIKE :search_term

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
@app.get("/collective-agents/{entity_id}/works")
def get_collective_agent_works(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    agent = db.get(CollectiveAgent, entity_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Collective agent not found",
        )

    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                related.entity_id,
                related.role,
                related.relation_level
            FROM (
                -- Collective Agent -> Manifestation -> Expression -> Work
                SELECT
                    w.entity_id AS entity_id,
                    mar.role AS role,
                    'manifestation' AS relation_level
                FROM manifestation_agent_relation mar
                JOIN expression_manifestation em
                  ON em.manifestation_entity_id = mar.manifestation_entity_id
                JOIN work_expression we
                  ON we.expression_entity_id = em.expression_entity_id
                JOIN works w
                  ON w.entity_id = we.work_entity_id
                WHERE mar.agent_entity_id = :entity_id

                UNION

                -- Collective Agent -> Item -> Manifestation -> Expression -> Work
                SELECT
                    w.entity_id AS entity_id,
                    iar.role AS role,
                    'item' AS relation_level
                FROM item_agent_relation iar
                JOIN manifestation_item mi
                  ON mi.item_entity_id = iar.item_entity_id
                JOIN expression_manifestation em
                  ON em.manifestation_entity_id = mi.manifestation_entity_id
                JOIN work_expression we
                  ON we.expression_entity_id = em.expression_entity_id
                JOIN works w
                  ON w.entity_id = we.work_entity_id
                WHERE iar.agent_entity_id = :entity_id
            ) AS related
            ORDER BY
                related.entity_id,
                related.role
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
                    "relation_level": row["relation_level"],
                    "work": detail,
                }
            )

    return {
        "entity_id": str(agent.entity_id),
        "canonical_name": agent.canonical_name,
        "agent_type": agent.agent_type,
        "description": agent.description,
        "works": works,
    }

# ============================================================
# Vocabulary Schemes / Classification
# ============================================================


@app.post("/vocabulary-schemes")
def create_vocabulary_scheme(
    payload: VocabularySchemeCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(VocabularyScheme).where(
            VocabularyScheme.code == payload.code
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Vocabulary scheme with this code already exists",
        )

    scheme = VocabularyScheme(
        code=payload.code,
        name=payload.name,
        scheme_type=payload.scheme_type,
        version=payload.version,
        uri=payload.uri,
        description=payload.description,
    )

    db.add(scheme)

    try:
        db.commit()
        db.refresh(scheme)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Vocabulary scheme could not be created",
        )

    return {
        "id": scheme.id,
        "code": scheme.code,
        "name": scheme.name,
        "scheme_type": scheme.scheme_type,
        "version": scheme.version,
        "uri": scheme.uri,
        "description": scheme.description,
    }


@app.get("/vocabulary-schemes")
def list_vocabulary_schemes(
    db: Session = Depends(get_db),
):
    schemes = db.scalars(
        select(VocabularyScheme).order_by(VocabularyScheme.code)
    ).all()

    return [
        {
            "id": scheme.id,
            "code": scheme.code,
            "name": scheme.name,
            "scheme_type": scheme.scheme_type,
            "version": scheme.version,
            "uri": scheme.uri,
            "description": scheme.description,
        }
        for scheme in schemes
    ]

@app.post("/vocabulary-schemes/{scheme_id}/editions")
def create_vocabulary_scheme_edition(
    scheme_id: UUID,
    payload: VocabularySchemeEditionCreate,
    db: Session = Depends(get_db),
):
    scheme = db.get(VocabularyScheme, scheme_id)

    if not scheme:
        raise HTTPException(
            status_code=404,
            detail="Vocabulary scheme not found",
        )

    if (
        payload.valid_from is not None
        and payload.valid_to is not None
        and payload.valid_to < payload.valid_from
    ):
        raise HTTPException(
            status_code=400,
            detail="valid_to cannot be earlier than valid_from",
        )

    existing = db.scalar(
        select(VocabularySchemeEdition).where(
            VocabularySchemeEdition.scheme_id == scheme_id,
            VocabularySchemeEdition.edition == payload.edition,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This edition already exists for the vocabulary scheme",
        )

    edition = VocabularySchemeEdition(
        scheme_id=scheme_id,
        edition=payload.edition,
        release_date=payload.release_date,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        uri=payload.uri,
        status=payload.status,
        description=payload.description,
    )

    db.add(edition)

    try:
        db.commit()
        db.refresh(edition)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Vocabulary scheme edition could not be created",
        )

    return {
        "id": edition.id,
        "scheme_id": edition.scheme_id,
        "scheme_code": scheme.code,
        "scheme_name": scheme.name,
        "edition": edition.edition,
        "release_date": edition.release_date,
        "valid_from": edition.valid_from,
        "valid_to": edition.valid_to,
        "uri": edition.uri,
        "status": edition.status,
        "description": edition.description,
    }


@app.get("/vocabulary-schemes/{scheme_id}/editions")
def get_vocabulary_scheme_editions(
    scheme_id: UUID,
    db: Session = Depends(get_db),
):
    scheme = db.get(VocabularyScheme, scheme_id)

    if not scheme:
        raise HTTPException(
            status_code=404,
            detail="Vocabulary scheme not found",
        )

    editions = db.scalars(
        select(VocabularySchemeEdition)
        .where(
            VocabularySchemeEdition.scheme_id == scheme_id
        )
        .order_by(
            VocabularySchemeEdition.edition
        )
    ).all()

    return {
        "scheme_id": scheme.id,
        "scheme_code": scheme.code,
        "scheme_name": scheme.name,
        "editions": [
            {
                "id": edition.id,
                "edition": edition.edition,
                "release_date": edition.release_date,
                "valid_from": edition.valid_from,
                "valid_to": edition.valid_to,
                "uri": edition.uri,
                "status": edition.status,
                "description": edition.description,
            }
            for edition in editions
        ],
    }

@app.post("/classifications")
def create_classification(
    payload: ClassificationCreate,
    db: Session = Depends(get_db),
):
    scheme = db.get(VocabularyScheme, payload.scheme_id)

    if not scheme:
        raise HTTPException(
            status_code=404,
            detail="Vocabulary scheme not found",
        )

    # Edition verilmişse edition'ın varlığını ve
    # seçilen scheme'e ait olup olmadığını kontrol et.
    scheme_edition = None

    if payload.scheme_edition_id is not None:
        scheme_edition = db.get(
            VocabularySchemeEdition,
            payload.scheme_edition_id,
        )

        if not scheme_edition:
            raise HTTPException(
                status_code=404,
                detail="Vocabulary scheme edition not found",
            )

        if scheme_edition.scheme_id != payload.scheme_id:
            raise HTTPException(
                status_code=400,
                detail="Vocabulary scheme edition does not belong to the selected scheme",
            )

    if payload.parent_entity_id:
        parent = db.get(
            ClassificationNode,
            payload.parent_entity_id,
        )

        if not parent:
            raise HTTPException(
                status_code=404,
                detail="Parent classification not found",
            )

        if parent.scheme_id != payload.scheme_id:
            raise HTTPException(
                status_code=400,
                detail="Parent classification must belong to the same scheme",
            )

    existing = db.scalar(
        select(ClassificationNode).where(
            ClassificationNode.scheme_id == payload.scheme_id,
            ClassificationNode.notation == payload.notation,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Classification notation already exists in this scheme",
        )

    entity = Entity(
        entity_type="CLASSIFICATION",
    )

    db.add(entity)

    # PostgreSQL subtype trigger requires the Entity row
    # to exist before ClassificationNode is inserted.
    db.flush()

    classification = ClassificationNode(
        entity_id=entity.id,
        scheme_id=payload.scheme_id,
        scheme_edition_id=payload.scheme_edition_id,
        notation=payload.notation,
        notation_end=payload.notation_end,
        caption=payload.caption,
        parent_entity_id=payload.parent_entity_id,
        uri=payload.uri,
        status=payload.status,
    )

    db.add(classification)

    try:
        db.commit()
        db.refresh(classification)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Classification could not be created",
        )

    return {
        "entity_id": classification.entity_id,
        "scheme_id": classification.scheme_id,
        "scheme_edition_id": classification.scheme_edition_id,
        "scheme_code": scheme.code,
        "notation": classification.notation,
        "notation_end": classification.notation_end,
        "caption": classification.caption,
        "parent_entity_id": classification.parent_entity_id,
        "uri": classification.uri,
        "status": classification.status,
    }

@app.get("/classifications/{entity_id}")
def get_classification(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    classification = db.get(
        ClassificationNode,
        entity_id,
    )

    if not classification:
        raise HTTPException(
            status_code=404,
            detail="Classification not found",
        )

    scheme = db.get(
        VocabularyScheme,
        classification.scheme_id,
    )

    return {
        "entity_id": classification.entity_id,
        "scheme": {
            "id": scheme.id,
            "code": scheme.code,
            "name": scheme.name,
            "version": scheme.version,
        },
        "notation": classification.notation,
        "caption": classification.caption,
        "parent_entity_id": classification.parent_entity_id,
        "uri": classification.uri,
        "status": classification.status,
    }


@app.post("/works/{work_entity_id}/classifications")
def assign_work_classification(
    work_entity_id: UUID,
    payload: WorkClassificationCreate,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if not work:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    classification = db.get(
        ClassificationNode,
        payload.classification_entity_id,
    )

    if not classification:
        raise HTTPException(
            status_code=404,
            detail="Classification not found",
        )

    existing = db.scalar(
        select(WorkClassification).where(
            WorkClassification.work_entity_id == work_entity_id,
            WorkClassification.classification_entity_id
            == payload.classification_entity_id,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This classification is already assigned to the Work",
        )

    assignment = WorkClassification(
        work_entity_id=work_entity_id,
        classification_entity_id=payload.classification_entity_id,
        is_primary=payload.is_primary,
        assigned_by=payload.assigned_by,
        source=payload.source,
    )

    db.add(assignment)

    try:
        db.commit()
        db.refresh(assignment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Classification assignment could not be created",
        )

    return {
        "id": assignment.id,
        "work_entity_id": assignment.work_entity_id,
        "classification_entity_id": assignment.classification_entity_id,
        "is_primary": assignment.is_primary,
        "assigned_by": assignment.assigned_by,
        "source": assignment.source,
    }


@app.get("/works/{work_entity_id}/classifications")
def get_work_classifications(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if not work:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    rows = db.execute(
        select(
            WorkClassification,
            ClassificationNode,
            VocabularyScheme,
        )
        .join(
            ClassificationNode,
            ClassificationNode.entity_id
            == WorkClassification.classification_entity_id,
        )
        .join(
            VocabularyScheme,
            VocabularyScheme.id
            == ClassificationNode.scheme_id,
        )
        .where(
            WorkClassification.work_entity_id
            == work_entity_id
        )
        .order_by(
            VocabularyScheme.code,
            ClassificationNode.notation,
        )
    ).all()

    classifications = []

    for assignment, classification, scheme in rows:
        classifications.append(
            {
                "assignment_id": assignment.id,
                "classification_entity_id": classification.entity_id,
                "scheme": {
                    "id": scheme.id,
                    "code": scheme.code,
                    "name": scheme.name,
                    "version": scheme.version,
                },
                "notation": classification.notation,
                "notation_end": classification.notation_end,
                "caption": classification.caption,
                "parent_entity_id": classification.parent_entity_id,
                "uri": classification.uri,
                "status": classification.status,
                "is_primary": assignment.is_primary,
                "assigned_by": assignment.assigned_by,
                "source": assignment.source,
            }
        )

    return {
        "work_entity_id": work.entity_id,
        "canonical_title": work.canonical_title,
        "classifications": classifications,
    }
@app.post("/classification-mappings")
def create_classification_mapping(
    payload: ClassificationMappingCreate,
    db: Session = Depends(get_db),
):
    source_node = db.get(
        ClassificationNode,
        payload.source_classification_entity_id,
    )
    if source_node is None:
        raise HTTPException(
            status_code=404,
            detail="Source classification not found",
        )

    target_node = db.get(
        ClassificationNode,
        payload.target_classification_entity_id,
    )
    if target_node is None:
        raise HTTPException(
            status_code=404,
            detail="Target classification not found",
        )

    if (
        payload.source_classification_entity_id
        == payload.target_classification_entity_id
    ):
        raise HTTPException(
            status_code=400,
            detail="A classification cannot be mapped to itself",
        )

    if source_node.scheme_id == target_node.scheme_id:
        raise HTTPException(
            status_code=400,
            detail="Classification mappings must connect different schemes",
        )

    existing = (
        db.query(ClassificationMapping)
        .filter(
            ClassificationMapping.source_classification_entity_id
            == payload.source_classification_entity_id,
            ClassificationMapping.target_classification_entity_id
            == payload.target_classification_entity_id,
            ClassificationMapping.mapping_type
            == payload.mapping_type,
        )
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This classification mapping already exists",
        )

    mapping = ClassificationMapping(
        source_classification_entity_id=(
            payload.source_classification_entity_id
        ),
        target_classification_entity_id=(
            payload.target_classification_entity_id
        ),
        mapping_type=payload.mapping_type,
        confidence=payload.confidence,
        mapping_method=payload.mapping_method,
        source=payload.source,
        source_uri=payload.source_uri,
        source_scheme_version=payload.source_scheme_version,
        target_scheme_version=payload.target_scheme_version,
        review_status=payload.review_status,
        reviewed_by=payload.reviewed_by,
    )

    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return {
        "id": mapping.id,
        "source_classification_entity_id": (
            mapping.source_classification_entity_id
        ),
        "target_classification_entity_id": (
            mapping.target_classification_entity_id
        ),
        "mapping_type": mapping.mapping_type,
        "confidence": mapping.confidence,
        "mapping_method": mapping.mapping_method,
        "source": mapping.source,
        "source_uri": mapping.source_uri,
        "source_scheme_version": mapping.source_scheme_version,
        "target_scheme_version": mapping.target_scheme_version,
        "review_status": mapping.review_status,
        "reviewed_by": mapping.reviewed_by,
        "reviewed_at": mapping.reviewed_at,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at,
    }


@app.get("/classification-mappings/{mapping_id}")
def get_classification_mapping(
    mapping_id: UUID,
    db: Session = Depends(get_db),
):
    mapping = db.get(ClassificationMapping, mapping_id)

    if mapping is None:
        raise HTTPException(
            status_code=404,
            detail="Classification mapping not found",
        )

    return {
        "id": mapping.id,
        "source_classification_entity_id": (
            mapping.source_classification_entity_id
        ),
        "target_classification_entity_id": (
            mapping.target_classification_entity_id
        ),
        "mapping_type": mapping.mapping_type,
        "confidence": mapping.confidence,
        "mapping_method": mapping.mapping_method,
        "source": mapping.source,
        "source_uri": mapping.source_uri,
        "source_scheme_version": mapping.source_scheme_version,
        "target_scheme_version": mapping.target_scheme_version,
        "review_status": mapping.review_status,
        "reviewed_by": mapping.reviewed_by,
        "reviewed_at": mapping.reviewed_at,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at,
    }


@app.get("/classifications/{entity_id}/mappings")
def get_classification_mappings(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    node = db.get(ClassificationNode, entity_id)

    if node is None:
        raise HTTPException(
            status_code=404,
            detail="Classification not found",
        )

    mappings = (
        db.query(ClassificationMapping)
        .filter(
            (
                ClassificationMapping.source_classification_entity_id
                == entity_id
            )
            | (
                ClassificationMapping.target_classification_entity_id
                == entity_id
            )
        )
        .all()
    )

    results = []

    for mapping in mappings:
        if mapping.source_classification_entity_id == entity_id:
            direction = "outgoing"
            related_entity_id = (
                mapping.target_classification_entity_id
            )
        else:
            direction = "incoming"
            related_entity_id = (
                mapping.source_classification_entity_id
            )

        related_node = db.get(
            ClassificationNode,
            related_entity_id,
        )

        related_scheme = None

        if related_node is not None:
            related_scheme = db.get(
                VocabularyScheme,
                related_node.scheme_id,
            )

        results.append(
            {
                "id": mapping.id,
                "direction": direction,
                "mapping_type": mapping.mapping_type,
                "confidence": mapping.confidence,
                "mapping_method": mapping.mapping_method,
                "source": mapping.source,
                "source_uri": mapping.source_uri,
                "review_status": mapping.review_status,
                "related_classification": {
                    "entity_id": related_entity_id,
                    "notation": (
                        related_node.notation
                        if related_node
                        else None
                    ),
                    "notation_end": (
                        related_node.notation_end
                        if related_node
                        else None
                    ),
                    "caption": (
                        related_node.caption
                        if related_node
                        else None
                    ),
                    "scheme_code": (
                        related_scheme.code
                        if related_scheme
                        else None
                    ),
                    "scheme_name": (
                        related_scheme.name
                        if related_scheme
                        else None
                    ),
                },
            }
        )

    return {
        "classification_entity_id": entity_id,
        "mappings": results,
    }


@app.delete("/classification-mappings/{mapping_id}")
def delete_classification_mapping(
    mapping_id: UUID,
    db: Session = Depends(get_db),
):
    mapping = db.get(ClassificationMapping, mapping_id)

    if mapping is None:
        raise HTTPException(
            status_code=404,
            detail="Classification mapping not found",
        )

    db.delete(mapping)
    db.commit()

    return {
        "deleted": True,
        "mapping_id": mapping_id,
    }