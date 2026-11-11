"""Stage 3: free Placer GIS APN resolution (Public_Parcels FeatureServer)."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

PARCELS_URL = (
    "https://services6.arcgis.com/PArfeTGcwA9RGNzN/ArcGIS/rest/services/"
    "Public_Parcels/FeatureServer/0/query"
)
THROTTLE_S = 0.5

SUFFIX_MAP = {
    "COURT": "CT",
    "DRIVE": "DR",
    "STREET": "ST",
    "LANE": "LN",
    "ROAD": "RD",
    "AVENUE": "AV",
    "AVE": "AV",
    "WAY": "WY",
    "BOULEVARD": "BLVD",
    "CIRCLE": "CIR",
    "PLACE": "PL",
    "TRAIL": "TRL",
    "TERRACE": "TER",
}
DIRECTIONALS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "NORTH", "SOUTH", "EAST", "WEST"}
CITY_OF_RE = re.compile(
    r"\bCity\s+of\s+([A-Za-z .'-]+?)(?:\s*,\s*|\s+)(?:County\s+of\s+)?Placer\b",
    re.I,
)
STREET_NUM_RE = re.compile(r"^\s*(\d{1,6})\b")


@dataclass
class ParcelHit:
    apn: str
    situs: str
    land_value: str = ""
    structure_value: str = ""
    jurisdiction: str = ""
    apn_source: str = ""  # de111 | decedent_address | petitioner_address
    confidence: str = "medium"  # high | medium | weak
    query: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_address(raw: str) -> dict[str, str]:
    """Strip suffix words, directionals, and City-of-X / County-of-Placer chrome."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    city = ""
    m_city = CITY_OF_RE.search(text)
    if m_city:
        city = m_city.group(1).strip().upper()
        text = CITY_OF_RE.sub(" ", text)

    text = re.sub(r",?\s*County\s+of\s+Placer\b", " ", text, flags=re.I)
    text = re.sub(r",?\s*Placer\s+County\b", " ", text, flags=re.I)
    text = re.sub(r"\bCalifornia\b|\bCA\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{5}(?:-\d{4})?\b", " ", text)
    text = re.sub(r"[#].*$", " ", text)
    text = re.sub(r"[,.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().upper()

    # Pull city if still comma-separated in original.
    if not city and "," in (raw or ""):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) >= 2:
            maybe = parts[1].upper()
            maybe = re.sub(r"\b(CA|CALIFORNIA|PLACER|COUNTY)\b", "", maybe).strip()
            if maybe and not maybe[0].isdigit():
                city = maybe

    tokens = text.split()
    num = ""
    if tokens and tokens[0].isdigit():
        num = tokens[0]
        tokens = tokens[1:]

    # Drop leading directional.
    if tokens and tokens[0] in DIRECTIONALS:
        tokens = tokens[1:]
    # Drop trailing directional / unit noise.
    while tokens and tokens[-1] in DIRECTIONALS:
        tokens = tokens[:-1]

    # If city was parsed from the original line, strip it from street tokens
    # (comma removal can leave "PALM AVENUE AUBURN").
    if city:
        city_toks = city.split()
        if len(tokens) >= len(city_toks) and tokens[-len(city_toks) :] == city_toks:
            tokens = tokens[: -len(city_toks)]
        elif tokens and tokens[-1] == city_toks[0]:
            tokens = tokens[:-1]

    if tokens:
        last = tokens[-1]
        mapped = SUFFIX_MAP.get(last, last)
        # Strip suffix for the LIKE token search (StreetName is often without type).
        street_tokens = tokens[:-1] if last in SUFFIX_MAP or last in SUFFIX_MAP.values() else tokens
        street_name = " ".join(street_tokens)
        suffix = mapped if last in SUFFIX_MAP or last in set(SUFFIX_MAP.values()) else ""
    else:
        street_name = ""
        suffix = ""

    first_token = street_name.split()[0] if street_name else ""
    return {
        "street_num": num,
        "street_name": street_name,
        "first_token": first_token,
        "suffix": suffix,
        "city": city,
        "normalized": " ".join(p for p in (num, street_name, suffix) if p),
    }


def _cache_key(norm: dict[str, str]) -> str:
    return f"{norm.get('street_num')}_{norm.get('first_token')}_{norm.get('city')}".lower()


def query_parcels(
    address: str,
    *,
    session: requests.Session | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    throttle_s: float = THROTTLE_S,
) -> list[dict[str, Any]]:
    """Query Public_Parcels; cache raw JSON per normalized address."""
    norm = normalize_address(address)
    if not norm["street_num"] or not norm["first_token"]:
        log.warning("cannot parse street num/name from %r", address)
        return []

    cache_path = None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{_cache_key(norm)}.json"
        if cache_path.exists() and not refresh:
            try:
                return json.loads(cache_path.read_text(encoding="utf-8")).get("features") or []
            except json.JSONDecodeError:
                pass

    where = (
        f"StreetNum={norm['street_num']} AND "
        f"UPPER(StreetName) LIKE '%{norm['first_token'].replace(chr(39), '')}%'"
    )
    params = {
        "where": where,
        "outFields": "Apn,SitusAddressFull,LandValue,Structure,Jurisdiction",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{PARCELS_URL}?{urlencode(params)}"
    sess = session or requests.Session()
    log.info("GIS query StreetNum=%s token=%s", norm["street_num"], norm["first_token"])
    resp = sess.get(url, timeout=45)
    resp.raise_for_status()
    payload = resp.json()
    features = payload.get("features") or []
    if cache_path:
        cache_path.write_text(
            json.dumps({"query": where, "address": address, "features": features}, indent=2),
            encoding="utf-8",
        )
    if throttle_s > 0:
        time.sleep(throttle_s)
    return features


def pick_parcel(
    features: list[dict[str, Any]],
    address: str,
    *,
    apn_source: str,
) -> ParcelHit | None:
    """Disambiguate multiple hits by city in SitusAddressFull."""
    if not features:
        return None
    norm = normalize_address(address)
    city = (norm.get("city") or "").upper()

    attrs_list = []
    for feat in features:
        attrs = feat.get("attributes") if isinstance(feat, dict) else None
        if isinstance(attrs, dict):
            attrs_list.append(attrs)
        elif isinstance(feat, dict) and feat.get("Apn"):
            attrs_list.append(feat)

    if not attrs_list:
        return None

    chosen = attrs_list[0]
    confidence = "medium"
    if len(attrs_list) == 1:
        confidence = "high"
    elif city:
        city_hits = [
            a
            for a in attrs_list
            if city in str(a.get("SitusAddressFull") or "").upper()
        ]
        if len(city_hits) == 1:
            chosen = city_hits[0]
            confidence = "high"
        elif city_hits:
            chosen = city_hits[0]
            confidence = "medium"
        else:
            confidence = "weak"

    if apn_source == "petitioner_address":
        confidence = "weak"

    apn = str(chosen.get("Apn") or "").strip()
    if not apn:
        return None
    # Normalize APN to ###-###-###-### when digits-only.
    digits = re.sub(r"\D", "", apn)
    if len(digits) == 12:
        apn = f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"
    elif len(digits) == 9:
        apn = f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-000"

    return ParcelHit(
        apn=apn,
        situs=str(chosen.get("SitusAddressFull") or "").strip(),
        land_value=str(chosen.get("LandValue") or "").strip(),
        structure_value=str(chosen.get("Structure") or "").strip(),
        jurisdiction=str(chosen.get("Jurisdiction") or "").strip(),
        apn_source=apn_source,
        confidence=confidence,
        query=norm.get("normalized") or "",
    )


def resolve_apn(
    *,
    de111_property: str = "",
    decedent_address: str = "",
    petitioner_address: str = "",
    session: requests.Session | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    features_override: list[dict] | None = None,
) -> ParcelHit | None:
    """Try address sources in priority order. Never claim APN equals vesting."""
    candidates = [
        ("de111", de111_property),
        ("decedent_address", decedent_address),
        ("petitioner_address", petitioner_address),
    ]
    for source, addr in candidates:
        addr = (addr or "").strip()
        if not addr:
            continue
        if features_override is not None:
            features = features_override
        else:
            features = query_parcels(
                addr, session=session, cache_dir=cache_dir, refresh=refresh
            )
        hit = pick_parcel(features, addr, apn_source=source)
        if hit:
            return hit
    return None
