"""Request models for classifications."""

from __future__ import annotations

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


__all__ = ["VocabularySchemeCreate", "VocabularySchemeEditionCreate", "ClassificationCreate", "WorkClassificationCreate", "ClassificationMappingCreate", "SourceClassificationCreate", "ClassificationValidationCreate"]


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
