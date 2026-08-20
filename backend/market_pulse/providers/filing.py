"""SEC filing provider stub — Phase 2 integration point."""

from __future__ import annotations

from market_pulse.providers.base import FilingProvider


class StubFilingProvider(FilingProvider):
    async def fetch_recent_filings(self, symbol: str, limit: int = 10) -> list[dict]:
        return []
