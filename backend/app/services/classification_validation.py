import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ClassificationNode,
    SourceClassification,
    VocabularyScheme,
    WorkClassification,
)


def is_valid_ddc_notation(notation: str) -> bool:
    """
    Validate the basic syntactic form of a DDC notation.

    Examples accepted:
    020
    641
    641.5
    641.594

    This checks notation syntax only.
    It does not prove that the number exists in a specific DDC edition.
    """

    value = notation.strip()

    return bool(
        re.fullmatch(
            r"\d{3}(?:\.\d+)?",
            value,
        )
    )


def is_valid_lcc_notation(notation: str) -> bool:
    """
    Validate the basic syntactic form of an LCC notation.

    Examples accepted:
    Z
    Z665
    Z665.2
    QA76
    QA76.73

    This checks notation syntax only.
    It does not prove that the number exists in the LCC schedules.
    """

    value = notation.strip().upper()

    return bool(
        re.fullmatch(
            r"[A-Z]{1,3}(?:\d+(?:\.\d+)?)?",
            value,
        )
    )


def evaluate_source_classification(
    db: Session,
    source_classification: SourceClassification,
) -> dict:
    """
    Compare a source classification observation with LibraryHub's
    normalized classifications for the same Work and vocabulary scheme.

    This function only evaluates.
    It does not create or update database records.
    """

    scheme = db.get(
        VocabularyScheme,
        source_classification.scheme_id,
    )

    # DDC syntax validation
    if (
        scheme is not None
        and scheme.code.upper() == "DDC"
        and not is_valid_ddc_notation(source_classification.notation)
    ):
        return {
            "status": "warning",
            "warning_code": "INVALID_NOTATION",
            "message": (
                "Kaynak sınıflama değeri temel DDC "
                "notasyon biçimine uymuyor."
            ),
            "confidence": 1.0,
            "validation_method": "ddc_syntax_validation",
            "suggested_classification_entity_id": None,
        }

    # LCC syntax validation
    if (
        scheme is not None
        and scheme.code.upper() == "LCC"
        and not is_valid_lcc_notation(source_classification.notation)
    ):
        return {
            "status": "warning",
            "warning_code": "INVALID_NOTATION",
            "message": (
                "Kaynak sınıflama değeri temel LCC "
                "notasyon biçimine uymuyor."
            ),
            "confidence": 1.0,
            "validation_method": "lcc_syntax_validation",
            "suggested_classification_entity_id": None,
        }

    # LibraryHub normalized classifications for the same Work
    # and vocabulary scheme.
    normalized_rows = db.execute(
        select(
            WorkClassification,
            ClassificationNode,
        )
        .join(
            ClassificationNode,
            ClassificationNode.entity_id
            == WorkClassification.classification_entity_id,
        )
        .where(
            WorkClassification.work_entity_id
            == source_classification.work_entity_id,
            ClassificationNode.scheme_id
            == source_classification.scheme_id,
        )
    ).all()

    # No normalized classification exists yet.
    if not normalized_rows:
        return {
            "status": "unresolved",
            "warning_code": "NO_NORMALIZED_CLASSIFICATION",
            "message": (
                "Bu eser için aynı sınıflama şemasında "
                "LibraryHub normalleştirilmiş sınıflaması bulunamadı."
            ),
            "confidence": None,
            "validation_method": "normalized_comparison",
            "suggested_classification_entity_id": None,
        }

    source_notation = source_classification.notation.strip()

    # Exact match with a normalized classification.
    for work_classification, node in normalized_rows:
        if source_notation == node.notation.strip():
            return {
                "status": "valid",
                "warning_code": None,
                "message": (
                    "Kaynak sınıflama LibraryHub normalleştirilmiş "
                    "sınıflaması ile tam eşleşiyor."
                ),
                "confidence": 1.0,
                "validation_method": "exact_normalized_match",
                "suggested_classification_entity_id": None,
            }

    # Prefer the primary normalized classification as suggestion.
    primary_candidates = [
        node
        for work_classification, node in normalized_rows
        if work_classification.is_primary
    ]

    suggested_node = (
        primary_candidates[0]
        if primary_candidates
        else normalized_rows[0][1]
    )

    return {
        "status": "warning",
        "warning_code": "NORMALIZED_MISMATCH",
        "message": (
            "Kaynak sınıflama, aynı şemadaki LibraryHub "
            "normalleştirilmiş sınıflamasıyla tam eşleşmiyor."
        ),
        "confidence": None,
        "validation_method": "normalized_comparison",
        "suggested_classification_entity_id": suggested_node.entity_id,
    }


def create_automatic_validation(
    db: Session,
    source_classification: SourceClassification,
):
    from ..models import ClassificationValidation

    existing = db.scalar(
        select(ClassificationValidation).where(
            ClassificationValidation.source_classification_id
            == source_classification.id
        )
    )

    if existing is not None:
        return existing

    result = evaluate_source_classification(
        db,
        source_classification,
    )

    validation = ClassificationValidation(
        source_classification_id=source_classification.id,
        status=result["status"],
        origin="automatic",
        warning_code=result["warning_code"],
        message=result["message"],
        suggested_classification_entity_id=(
            result["suggested_classification_entity_id"]
        ),
        confidence=result["confidence"],
        validation_method=result["validation_method"],
    )

    db.add(validation)
    db.commit()
    db.refresh(validation)

    return validation


def revalidate_classification(
    db: Session,
    source_classification: SourceClassification,
):
    from ..models import ClassificationValidation

    validation = db.scalar(
        select(ClassificationValidation).where(
            ClassificationValidation.source_classification_id
            == source_classification.id
        )
    )

    # No validation exists yet:
    # create a new automatic validation.
    if validation is None:
        return create_automatic_validation(
            db,
            source_classification,
        )

    # Manual decisions must never be overwritten automatically.
    if validation.origin != "automatic":
        return validation

    # Re-evaluate automatic validation using current rules.
    result = evaluate_source_classification(
        db,
        source_classification,
    )

    validation.status = result["status"]
    validation.warning_code = result["warning_code"]
    validation.message = result["message"]
    validation.suggested_classification_entity_id = (
        result["suggested_classification_entity_id"]
    )
    validation.confidence = result["confidence"]
    validation.validation_method = result["validation_method"]

    db.commit()
    db.refresh(validation)

    return validation