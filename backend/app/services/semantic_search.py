from __future__ import annotations

import json
import math
from uuid import UUID
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = ["SemanticSearchError", "search"]


class SemanticSearchError(RuntimeError):
    """The local embedding/vector service is unavailable or returned invalid data."""


def search(query: str, limit: int = 3000) -> list[dict]:
    base_url = os.environ.get("SEMANTIC_SEARCH_URL")
    if not base_url:
        raise SemanticSearchError("SEMANTIC_SEARCH_URL is not configured")

    request = Request(
        f"{base_url.rstrip('/')}/search",
        data=json.dumps({"query": query, "limit": limit}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
    except HTTPError as error:
        raise SemanticSearchError(
            f"Local semantic service returned HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SemanticSearchError(
            f"Cannot reach local semantic service: {error}"
        ) from error

    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise SemanticSearchError("Local semantic service response has no matches list")

    validated = []
    for match in matches:
        if not isinstance(match, dict):
            raise SemanticSearchError("Local semantic service returned an invalid match")
        try:
            entity_id = str(UUID(match["entity_id"]))
            score = float(match["score"])
        except (KeyError, TypeError, ValueError) as error:
            raise SemanticSearchError("Local semantic service returned an invalid match") from error
        if not math.isfinite(score):
            raise SemanticSearchError("Local semantic service returned a non-finite score")
        validated.append({"entity_id": entity_id, "score": score})

    return validated