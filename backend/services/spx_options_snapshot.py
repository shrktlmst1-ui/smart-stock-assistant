"""SPX option-chain snapshot helper using the Massive/Polygon API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.polygon_client import PolygonAPIError, PolygonClient


async def get_spx_option_chain(
    client: PolygonClient,
    *,
    expiration_date: str | None = None,
    contract_type: str | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Return an SPX option-chain snapshot, trying the common SPX underlyings."""
    expiration = expiration_date or datetime.now().date().isoformat()
    params: dict[str, Any] = {
        "expiration_date": expiration,
        "limit": min(max(limit, 1), 250),
        "order": "asc",
        "sort": "ticker",
    }
    if contract_type:
        params["contract_type"] = contract_type.lower()

    last_error: PolygonAPIError | None = None
    for underlying in ("SPX", "I:SPX"):
        try:
            data = await client._request(
                f"/v3/snapshot/options/{underlying}",
                params=params,
            )
            results = data.get("results", [])
            if results:
                return results
        except PolygonAPIError as exc:
            last_error = exc
            if exc.status_code not in (400, 404):
                raise

    if last_error and last_error.status_code not in (400, 404):
        raise last_error
    return []
