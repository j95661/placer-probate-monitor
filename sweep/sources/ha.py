"""Home Assistant listings + DE-111 client (read-only)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

log = logging.getLogger(__name__)

DEFAULT_HA_URL = "http://192.168.0.60:8123"
LISTINGS_PATH = "/api/placer_probate_monitor/listings"
# TODO(v2): move FUB API key / Gmail app password / Sacramento portal password
# from the integration's plain-text options into HA secrets.


def _redact(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Does not override existing env."""
    candidates = []
    if path:
        candidates.append(path)
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parents[2] / ".env")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
        break


def ha_config() -> tuple[str, str]:
    load_dotenv()
    base = (os.environ.get("HA_URL") or DEFAULT_HA_URL).rstrip("/")
    token = os.environ.get("HA_TOKEN") or os.environ.get("HASSIO_TOKEN") or ""
    return base, token


class HAClient:
    """Read-only client for placer_probate_monitor listings + DE-111 PDFs."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 60.0,
    ) -> None:
        cfg_url, cfg_token = ha_config()
        self.base_url = (base_url or cfg_url).rstrip("/")
        self.token = token if token is not None else cfg_token
        self.timeout = timeout
        self.session = session or requests.Session()
        self._auth_header = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "placer-affidavit-sweep/0.1",
            **self._auth_header,
        }

    def fetch_listings(self, source: str = "Placer County") -> list[dict[str, Any]]:
        if not self.token:
            raise RuntimeError(
                "HA_TOKEN is not set. Export HA_TOKEN or put it in .env "
                "(never commit the token)."
            )
        url = f"{self.base_url}{LISTINGS_PATH}"
        log.info("GET %s", url)
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise RuntimeError(_redact(str(exc), self.token)) from exc
        if resp.status_code >= 400:
            raise RuntimeError(
                f"HA listings HTTP {resp.status_code}: "
                f"{_redact(resp.text[:200], self.token)}"
            )
        payload = resp.json()
        listings = payload.get("listings") if isinstance(payload, dict) else payload
        if not isinstance(listings, list):
            return []
        if source:
            listings = [
                row
                for row in listings
                if isinstance(row, dict)
                and str(row.get("source") or "") == source
            ]
        else:
            listings = [row for row in listings if isinstance(row, dict)]
        log.info("loaded %d listings (source filter=%r)", len(listings), source)
        return listings

    def download_de111(
        self,
        listing: dict[str, Any],
        dest: Path,
        *,
        refresh: bool = False,
    ) -> Path | None:
        """Download DE-111 PDF to dest. Returns path or None if unavailable."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0 and not refresh:
            return dest
        rel = str(listing.get("de111_url") or "").strip()
        if not rel:
            return None
        if not self.token:
            raise RuntimeError("HA_TOKEN is not set")
        url = urljoin(self.base_url + "/", rel.lstrip("/"))
        # Prefer absolute when HA already returns one.
        if re.match(r"^https?://", rel, re.I):
            url = rel
        log.info("GET de111 %s → %s", listing.get("case_number"), dest.name)
        resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            log.warning(
                "DE-111 download failed for %s: HTTP %s",
                listing.get("case_number"),
                resp.status_code,
            )
            return None
        dest.write_bytes(resp.content)
        return dest


def load_listings_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    listings = payload.get("listings") if isinstance(payload, dict) else payload
    if not isinstance(listings, list):
        return []
    return [row for row in listings if isinstance(row, dict)]
