from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..services.classification_validation import create_automatic_validation

from ..db import get_db
from ..models import (
    Entity,
    Work,
    CollectiveAgent,
    VocabularyScheme,
    VocabularySchemeEdition,
    ClassificationNode,
    WorkClassification,
    ClassificationMapping,
    SourceClassification,
    ClassificationValidation,
)


router = APIRouter(
    tags=["classifications"],
)


# ============================================================
# Schemas
# ============================================================


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

    caption: str | None = Field(
        default=None,
        max_length=1000,
    )

    parent_entity_id: UUID | None = None

    uri: str | None = Field(
        default=None,
        max_length=1000,
    )

    status: str | None = Field(
        default="active",
        max_length=100,
    )


class WorkClassificationCreate(BaseModel):
    classification_entity_id: UUID
    is_primary: bool = False
    assigned_by: str | None = Field(
        default=None,
        max_length=200,
    )
    source: str | None = Field(
        default=None,
        max_length=500,
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
class SourceClassificationCreate(BaseModel):
    work_entity_id: UUID
    institution_entity_id: UUID
    scheme_id: UUID
    scheme_edition_id: UUID | None = None

    notation: str = Field(
        min_length=1,
        max_length=300,
    )

    source_record_id: str | None = Field(
        default=None,
        max_length=500,
    )

    source_uri: str | None = Field(
        default=None,
        max_length=1000,
    )

    notes: str | None = None
    
class ClassificationValidationCreate(BaseModel):
    source_classification_id: UUID

    status: str = Field(
        default="unresolved",
        pattern="^(valid|warning|probable_error|unresolved)$",
    )

    warning_code: str | None = Field(
        default=None,
        max_length=100,
    )

    message: str | None = None

    suggested_classification_entity_id: UUID | None = None

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    validation_method: str | None = Field(
        default=None,
        max_length=100,
    )

    reviewed_by: str | None = Field(
        default=None,
        max_length=200,
    )

# ============================================================
# Vocabulary Schemes
# ============================================================


@router.post("/vocabulary-schemes")
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


@router.get("/vocabulary-schemes")
def list_vocabulary_schemes(
    db: Session = Depends(get_db),
):
    schemes = db.scalars(
        select(VocabularyScheme).order_by(
            VocabularyScheme.code
        )
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


# ============================================================
# Vocabulary Scheme Editions
# ============================================================


@router.post("/vocabulary-schemes/{scheme_id}/editions")
def create_vocabulary_scheme_edition(
    scheme_id: UUID,
    payload: VocabularySchemeEditionCreate,
    db: Session = Depends(get_db),
):
    scheme = db.get(
        VocabularyScheme,
        scheme_id,
    )

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


@router.get("/vocabulary-schemes/{scheme_id}/editions")
def get_vocabulary_scheme_editions(
    scheme_id: UUID,
    db: Session = Depends(get_db),
):
    scheme = db.get(
        VocabularyScheme,
        scheme_id,
    )

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


# ============================================================
# Classification Nodes
# ============================================================


@router.post("/classifications")
def create_classification(
    payload: ClassificationCreate,
    db: Session = Depends(get_db),
):
    scheme = db.get(
        VocabularyScheme,
        payload.scheme_id,
    )

    if not scheme:
        raise HTTPException(
            status_code=404,
            detail="Vocabulary scheme not found",
        )

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
                detail=(
                    "Vocabulary scheme edition does not "
                    "belong to the selected scheme"
                ),
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
                detail=(
                    "Parent classification must belong "
                    "to the same scheme"
                ),
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
            detail=(
                "Classification notation already exists "
                "in this scheme"
            ),
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


@router.get("/classifications/{entity_id}")
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


# ============================================================
# Work Classification Assignments
# ============================================================


@router.post("/works/{work_entity_id}/classifications")
def assign_work_classification(
    work_entity_id: UUID,
    payload: WorkClassificationCreate,
    db: Session = Depends(get_db),
):
    work = db.get(
        Work,
        work_entity_id,
    )

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
            detail=(
                "This classification is already "
                "assigned to the Work"
            ),
        )

    assignment = WorkClassification(
        work_entity_id=work_entity_id,
        classification_entity_id=(
            payload.classification_entity_id
        ),
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
            detail=(
                "Classification assignment "
                "could not be created"
            ),
        )

    return {
        "id": assignment.id,
        "work_entity_id": assignment.work_entity_id,
        "classification_entity_id": (
            assignment.classification_entity_id
        ),
        "is_primary": assignment.is_primary,
        "assigned_by": assignment.assigned_by,
        "source": assignment.source,
    }


@router.get("/works/{work_entity_id}/classifications")
def get_work_classifications(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(
        Work,
        work_entity_id,
    )

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
                "classification_entity_id": (
                    classification.entity_id
                ),
                "scheme": {
                    "id": scheme.id,
                    "code": scheme.code,
                    "name": scheme.name,
                    "version": scheme.version,
                },
                "notation": classification.notation,
                "notation_end": classification.notation_end,
                "caption": classification.caption,
                "parent_entity_id": (
                    classification.parent_entity_id
                ),
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


# ============================================================
# Classification Mappings
# ============================================================


@router.post("/classification-mappings")
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
            detail=(
                "Classification mappings must "
                "connect different schemes"
            ),
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


@router.get("/classification-mappings/{mapping_id}")
def get_classification_mapping(
    mapping_id: UUID,
    db: Session = Depends(get_db),
):
    mapping = db.get(
        ClassificationMapping,
        mapping_id,
    )

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


@router.get("/classifications/{entity_id}/mappings")
def get_classification_mappings(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    node = db.get(
        ClassificationNode,
        entity_id,
    )

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
        if (
            mapping.source_classification_entity_id
            == entity_id
        ):
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


@router.delete("/classification-mappings/{mapping_id}")
def delete_classification_mapping(
    mapping_id: UUID,
    db: Session = Depends(get_db),
):
    mapping = db.get(
        ClassificationMapping,
        mapping_id,
    )

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
    
# ============================================================
# Source Classification Observations
# ============================================================


@router.post("/source-classifications")
def create_source_classification(
    payload: SourceClassificationCreate,
    db: Session = Depends(get_db),
):
    work = db.get(
        Work,
        payload.work_entity_id,
    )

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    institution = db.get(
        CollectiveAgent,
        payload.institution_entity_id,
    )

    if institution is None:
        raise HTTPException(
            status_code=404,
            detail="Institution not found",
        )

    scheme = db.get(
        VocabularyScheme,
        payload.scheme_id,
    )

    if scheme is None:
        raise HTTPException(
            status_code=404,
            detail="Vocabulary scheme not found",
        )

    if payload.scheme_edition_id is not None:
        scheme_edition = db.get(
            VocabularySchemeEdition,
            payload.scheme_edition_id,
        )

        if scheme_edition is None:
            raise HTTPException(
                status_code=404,
                detail="Vocabulary scheme edition not found",
            )

        if scheme_edition.scheme_id != payload.scheme_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Vocabulary scheme edition does not "
                    "belong to the selected scheme"
                ),
            )

    observation = SourceClassification(
        work_entity_id=payload.work_entity_id,
        institution_entity_id=payload.institution_entity_id,
        scheme_id=payload.scheme_id,
        scheme_edition_id=payload.scheme_edition_id,
        notation=payload.notation,
        source_record_id=payload.source_record_id,
        source_uri=payload.source_uri,
        notes=payload.notes,
    )

    db.add(observation)

    try:
        db.commit()
        db.refresh(observation)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Source classification observation already exists",
        )

    validation = create_automatic_validation(
        db,
        observation,
    )

    return {
        "id": observation.id,
        "work": {
            "entity_id": work.entity_id,
            "canonical_title": work.canonical_title,
        },
        "institution": {
            "entity_id": institution.entity_id,
            "canonical_name": institution.canonical_name,
        },
        "scheme": {
            "id": scheme.id,
            "code": scheme.code,
            "name": scheme.name,
        },
        "scheme_edition_id": observation.scheme_edition_id,
        "notation": observation.notation,
        "source_record_id": observation.source_record_id,
        "source_uri": observation.source_uri,
        "observed_at": observation.observed_at,
        "notes": observation.notes,
        "validation": {
            "id": validation.id,
            "status": validation.status,
            "warning_code": validation.warning_code,
            "message": validation.message,
            "suggested_classification_entity_id": (
                validation.suggested_classification_entity_id
            ),
            "confidence": validation.confidence,
            "validation_method": validation.validation_method,
        },
    }
    
# ============================================================
# Classification Validations
# ============================================================


@router.post("/classification-validations")
def create_classification_validation(
    payload: ClassificationValidationCreate,
    db: Session = Depends(get_db),
):
    source_classification = db.get(
        SourceClassification,
        payload.source_classification_id,
    )

    if source_classification is None:
        raise HTTPException(
            status_code=404,
            detail="Source classification not found",
        )

    if payload.suggested_classification_entity_id is not None:
        suggested_classification = db.get(
            ClassificationNode,
            payload.suggested_classification_entity_id,
        )

        if suggested_classification is None:
            raise HTTPException(
                status_code=404,
                detail="Suggested classification not found",
            )

        if suggested_classification.scheme_id != source_classification.scheme_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Suggested classification must belong "
                    "to the same vocabulary scheme"
                ),
            )

    existing = db.scalar(
        select(ClassificationValidation).where(
            ClassificationValidation.source_classification_id
            == payload.source_classification_id
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Classification validation already exists",
        )

    validation = ClassificationValidation(
        source_classification_id=payload.source_classification_id,
        status=payload.status,
        warning_code=payload.warning_code,
        message=payload.message,
        suggested_classification_entity_id=(
            payload.suggested_classification_entity_id
        ),
        confidence=payload.confidence,
        validation_method=payload.validation_method,
        reviewed_by=payload.reviewed_by,
    )

    db.add(validation)

    try:
        db.commit()
        db.refresh(validation)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Classification validation already exists",
        )

    return {
        "id": validation.id,
        "source_classification_id": validation.source_classification_id,
        "status": validation.status,
        "warning_code": validation.warning_code,
        "message": validation.message,
        "suggested_classification_entity_id": (
            validation.suggested_classification_entity_id
        ),
        "confidence": validation.confidence,
        "validation_method": validation.validation_method,
        "reviewed_by": validation.reviewed_by,
        "reviewed_at": validation.reviewed_at,
        "created_at": validation.created_at,
        "updated_at": validation.updated_at,
    }
    
@router.get("/works/{work_entity_id}/source-classifications")
def get_work_source_classifications(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(
        Work,
        work_entity_id,
    )

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    observations = db.scalars(
        select(SourceClassification)
        .where(
            SourceClassification.work_entity_id == work_entity_id
        )
        .order_by(SourceClassification.observed_at)
    ).all()

    results = []

    for observation in observations:
        institution = db.get(
            CollectiveAgent,
            observation.institution_entity_id,
        )

        scheme = db.get(
            VocabularyScheme,
            observation.scheme_id,
        )

        validation = db.scalar(
            select(ClassificationValidation).where(
                ClassificationValidation.source_classification_id
                == observation.id
            )
        )

        validation_data = None

        if validation is not None:
            suggested_classification = None

            if validation.suggested_classification_entity_id is not None:
                suggested_node = db.get(
                    ClassificationNode,
                    validation.suggested_classification_entity_id,
                )

                if suggested_node is not None:
                    suggested_classification = {
                        "entity_id": suggested_node.entity_id,
                        "notation": suggested_node.notation,
                        "caption": suggested_node.caption,
                    }

            validation_data = {
                "id": validation.id,
                "status": validation.status,
                "warning_code": validation.warning_code,
                "message": validation.message,
                "confidence": validation.confidence,
                "validation_method": validation.validation_method,
                "suggested_classification": suggested_classification,
                "reviewed_by": validation.reviewed_by,
                "reviewed_at": validation.reviewed_at,
                "created_at": validation.created_at,
                "updated_at": validation.updated_at,
            }

        results.append(
            {
                "id": observation.id,
                "institution": {
                    "entity_id": institution.entity_id,
                    "canonical_name": institution.canonical_name,
                },
                "scheme": {
                    "id": scheme.id,
                    "code": scheme.code,
                    "name": scheme.name,
                },
                "scheme_edition_id": observation.scheme_edition_id,
                "notation": observation.notation,
                "source_record_id": observation.source_record_id,
                "source_uri": observation.source_uri,
                "observed_at": observation.observed_at,
                "notes": observation.notes,
                "validation": validation_data,
            }
        )

    return {
        "work": {
            "entity_id": work.entity_id,
            "canonical_title": work.canonical_title,
        },
        "source_classifications": results,
    }