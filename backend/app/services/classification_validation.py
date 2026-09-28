import re

from sqlalchemy import select
from sqlalchemy.orm import Session


from ..models import (
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