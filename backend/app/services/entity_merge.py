import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, EntityMerge


class EntityMergeCycleError(Exception):
    """Raised when an entity merge redirect cycle is detected."""


def resolve_canonical_entity_id(
    db: Session,
    entity_id: uuid.UUID,
) -> uuid.UUID:
    """
    Follow EntityMerge redirects and return the canonical entity ID.

    Examples:
        A -> B       returns B
        A -> B -> C  returns C
        no redirect  returns A

    A redirect cycle raises EntityMergeCycleError.
    """

    current_id = entity_id
    visited: set[uuid.UUID] = set()

    while True:
        if current_id in visited:
            raise EntityMergeCycleError(
                f"Entity merge cycle detected at {current_id}"
            )

        visited.add(current_id)

        target_id = db.scalar(
            select(EntityMerge.target_entity_id).where(
                EntityMerge.source_entity_id == current_id
            )
        )

        if target_id is None:
            return current_id

        current_id = target_id


def validate_entity_merge(
    db: Session,
    source_entity_id: uuid.UUID,
    target_entity_id: uuid.UUID,
) -> uuid.UUID:
    """
    Validate a proposed entity merge.

    Returns the final canonical target entity ID.

    Prevents:
        A -> A
        nonexistent entities
        different entity types
        A -> B when A already redirects
        redirect cycles
    """

    if source_entity_id == target_entity_id:
        raise ValueError(
            "Source and target entity cannot be the same"
        )

    source_entity = db.get(Entity, source_entity_id)
    target_entity = db.get(Entity, target_entity_id)

    if source_entity is None:
        raise ValueError(
            f"Source entity does not exist: {source_entity_id}"
        )

    if target_entity is None:
        raise ValueError(
            f"Target entity does not exist: {target_entity_id}"
        )

    if source_entity.entity_type != target_entity.entity_type:
        raise ValueError(
            "Source and target entity types must match: "
            f"{source_entity.entity_type} != {target_entity.entity_type}"
        )

    existing_target = db.scalar(
        select(EntityMerge.target_entity_id).where(
            EntityMerge.source_entity_id == source_entity_id
        )
    )

    if existing_target is not None:
        raise ValueError(
            f"Source entity already redirects to {existing_target}"
        )

    canonical_target_id = resolve_canonical_entity_id(
        db,
        target_entity_id,
    )

    if canonical_target_id == source_entity_id:
        raise EntityMergeCycleError(
            "Proposed entity merge would create a redirect cycle"
        )

    return canonical_target_id


def create_entity_merge(
    db: Session,
    source_entity_id: uuid.UUID,
    target_entity_id: uuid.UUID,
    *,
    origin: str = "manual",
    reason: str | None = None,
    merge_method: str | None = None,
    confidence: float | None = None,
    reviewed_by: str | None = None,
) -> EntityMerge:
    """
    Create a validated EntityMerge redirect.

    The target is always stored as the final canonical entity.
    """

    canonical_target_id = validate_entity_merge(
        db,
        source_entity_id,
        target_entity_id,
    )

    merge = EntityMerge(
        source_entity_id=source_entity_id,
        target_entity_id=canonical_target_id,
        origin=origin,
        reason=reason,
        merge_method=merge_method,
        confidence=confidence,
        reviewed_by=reviewed_by,
    )

    db.add(merge)
    db.flush()

    return merge