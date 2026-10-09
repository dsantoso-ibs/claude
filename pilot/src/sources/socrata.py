"""Generic Socrata SODA client. Public open-data endpoints only."""
from __future__ import annotations

import os
import time
from typing import Any, Iterator

import httpx


class SocrataClient:
    def __init__(self, domain: str, *, timeout: float = 30.0, max_retries: int = 5,
                 backoff_base: float = 2.0, app_token: str | None = None):
        self.domain = domain
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        token = app_token if app_token is not None else os.environ.get("SOCRATA_APP_TOKEN")
        headers = {"Accept": "application/json", "User-Agent": "baucore-pilot/0.1"}
        if token:
            headers["X-App-Token"] = token
        self._http = httpx.Client(base_url=f"https://{domain}", headers=headers, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.get(path, params=params)
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == self.max_retries:
                        resp.raise_for_status()
                else:
                    resp.raise_for_status()
                    return resp.json()
            time.sleep(self.backoff_base * (2 ** attempt))
        raise RuntimeError("unreachable")

    def metadata(self, dataset_id: str) -> dict[str, Any]:
        return self._get(f"/api/views/{dataset_id}.json")

    def query(self, dataset_id: str, **soql: Any) -> list[dict[str, Any]]:
        """Run one SoQL query; keys are SODA params without '$' (select, where, limit...)."""
        return self._get(f"/resource/{dataset_id}.json", {f"${k}": v for k, v in soql.items()})

    def iter_rows(self, dataset_id: str, *, where: str | None = None,
                  order: str = ":id", page_size: int = 1000) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            params: dict[str, Any] = {"order": order, "limit": page_size, "offset": offset}
            if where:
                params["where"] = where
            page = self.query(dataset_id, **params)
            yield from page
            if len(page) < page_size:
                return
            offset += page_size
