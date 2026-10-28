"""Follow Up Boss Events API client for new probate petitioners."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
from pathlib import Path

import requests

try:
    from .petition_parse import STATE_ALT as _STATE_ALT
    from .petition_parse import clean_person_name as _clean_person_name
    from .petition_parse import is_caption_name_part as _is_caption_name_part
    from .petition_parse import is_caption_person_name as _is_caption_person_name
    from .petition_parse import is_court_or_firm_caption_name as _is_court_or_firm_caption_name
    from .petition_parse import is_junk_mailing_street as _is_junk_mailing_street
    from .petition_parse import is_placeholder_estate_real as _is_placeholder_estate_real
    from .petition_parse import stored_person_name as _stored_person_name
    from .petition_parse import strip_ocr_name_junk as _strip_ocr_name_junk
except ImportError:
    from petition_parse import STATE_ALT as _STATE_ALT
    from petition_parse import clean_person_name as _clean_person_name
    from petition_parse import is_caption_name_part as _is_caption_name_part
    from petition_parse import is_caption_person_name as _is_caption_person_name
    from petition_parse import is_court_or_firm_caption_name as _is_court_or_firm_caption_name
    from petition_parse import is_junk_mailing_street as _is_junk_mailing_street
    from petition_parse import is_placeholder_estate_real as _is_placeholder_estate_real
    from petition_parse import stored_person_name as _stored_person_name
    from petition_parse import strip_ocr_name_junk as _strip_ocr_name_junk

try:
    from .datasources import COUNTY_FUB_LEAD_SOURCES, fub_lead_source, petition_docs_dir
except ImportError:
    from datasources import COUNTY_FUB_LEAD_SOURCES, fub_lead_source, petition_docs_dir


def _progress_fub(summary: dict, action: str, key: str | None = None) -> None:
    try:
        from .job_progress import report_progress
    except ImportError:
        from job_progress import report_progress

    posted = int(summary.get("posted") or 0)
    updated = int(summary.get("updated") or 0)
    skipped = int(summary.get("skipped") or 0)
    case = key or ""
    detail = f"{action} {case}".strip() if action else "importing"
    report_progress(
        "fub",
        f"Follow Up Boss: {detail} · posted {posted}, updated {updated}, skipped {skipped}",
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
        case_number=key,
    )

COURT_SEARCH_DEFAULT = "https://webportal.placerco.org/eCourtPublic/?q=node/48"
CASE_PORTAL_TEMPLATE = "https://webportal.placerco.org/eCourtPublic/?q=node/45/{nid}"
CASE_PORTAL_RE = re.compile(r"node/45/(\d+)", re.I)
SACRAMENTO_PORTAL_BASE = (
    "https://prod-portal-sacramento-ca.journaltech.com/public-portal/"
)
SACRAMENTO_CASE_RE = re.compile(
    r"prod-portal-sacramento-ca\.journaltech\.com/public-portal/.*?node/(?:397|430)/(\d+)",
    re.I,
)
DOWNLOAD_CASE_RE = re.compile(r"downloadFile/\d+/(\d+)", re.I)
MAPPING_PATH = Path(__file__).resolve().parent / "fub_mapping.yaml"
ADDR_RE = re.compile(
    rf"^(?P<street>.+?),\s*(?P<city>[^,]+),\s*"
    rf"(?P<state>{_STATE_ALT})\b"
    rf"\s*(?P<zip>\d{{5}}(?:-\d{{4}})?)?$",
    re.I,
)
ADDR_FLEX_RE = re.compile(
    rf"^(?P<street>.+?),\s*(?P<city>[A-Za-z .'-]+?)(?:\s*,\s*|\s+)"
    rf"(?P<state>{_STATE_ALT})\b"
    rf"\s*(?P<zip>\d{{5}}(?:-\d{{4}})?)?\s*$",
    re.I,
)
COUNTY_NOISE_RE = re.compile(r",?\s*Placer(?:\s+County)?\b,?", re.I)
NOT_CITIES = {"placer", "placer county", "county", "california"}
ADDRESS_COMPONENT_KEYS = {
    "decedent_city",
    "decedent_zip",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
}
ADDRESS1_TYPE = "home"
ADDRESS2_TYPE = "mailing"


def case_portal_url(row: dict) -> str:
    """Per-case court page. Placer uses node/45. Sacramento keeps node/397."""
    candidates = [
        row.get("court_url"),
        row.get("url"),
        row.get("portal_url"),
        row.get("court_search"),
    ]
    for doc in row.get("document_files") or []:
        if isinstance(doc, dict):
            candidates.append(doc.get("url"))
    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        sac = SACRAMENTO_CASE_RE.search(text)
        if sac:
            return f"{SACRAMENTO_PORTAL_BASE}?q=node/397/{sac.group(1)}"
        if "prod-portal-sacramento-ca.journaltech.com" in text.lower():
            return text
        match = CASE_PORTAL_RE.search(text)
        if match:
            return CASE_PORTAL_TEMPLATE.format(nid=match.group(1))
        match = DOWNLOAD_CASE_RE.search(text)
        if match:
            return CASE_PORTAL_TEMPLATE.format(nid=match.group(1))
    return ""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_mapping_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("FUB_MAPPING_PATH", "").strip()
    if env:
        return Path(env)
    return MAPPING_PATH


def writable_mapping_path(path: Path | None = None) -> Path:
    target = resolve_mapping_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_mapping(data: dict) -> dict:
    mapping = dict(data or {})
    skip = mapping.get("skip_petitioner_contains") or []
    if isinstance(skip, str):
        skip = [part.strip() for part in skip.split(",") if part.strip()]
    mapping["skip_petitioner_contains"] = [str(x).strip() for x in skip if str(x).strip()]
    send = dict(mapping.get("send") or {})
    mapping["send"] = {str(k): _as_bool(v, False) for k, v in send.items()}
    fields = mapping.get("custom_fields") or {}
    mapping["custom_fields"] = {
        str(k): str(v).strip()
        for k, v in (fields.items() if isinstance(fields, dict) else [])
        if str(k).strip() and str(v).strip()
    }
    sources = mapping.get("source_mappings") or {}
    normalized_sources: dict = {}
    if isinstance(sources, dict):
        for source_id, block in sources.items():
            if not isinstance(block, dict):
                continue
            nested = block.get("custom_fields") or {}
            normalized_sources[str(source_id)] = {
                "custom_fields": {
                    str(k): str(v).strip()
                    for k, v in (nested.items() if isinstance(nested, dict) else [])
                    if str(k).strip() and str(v).strip()
                }
            }
    if "placer" not in normalized_sources and mapping["custom_fields"]:
        normalized_sources["placer"] = {"custom_fields": dict(mapping["custom_fields"])}
    mapping["source_mappings"] = normalized_sources
    mapping["custom_fields"] = _split_person_source_keys(mapping["custom_fields"])
    mapping["custom_fields"] = _rewrite_address2_keys(mapping["custom_fields"])
    for source_id, block in mapping["source_mappings"].items():
        block["custom_fields"] = _rewrite_address2_keys(
            _split_person_source_keys(block.get("custom_fields") or {})
        )
        mapping["source_mappings"][source_id] = block
    if "placer" in mapping["source_mappings"]:
        mapping["custom_fields"] = dict(
            mapping["source_mappings"]["placer"].get("custom_fields") or {}
        )
    else:
        mapping["source_mappings"]["placer"] = {
            "custom_fields": dict(mapping["custom_fields"])
        }
    return mapping


def _split_person_source_keys(fields: dict) -> dict:
    """Replace a full petitioner name mapped onto first/last with split source keys."""
    out = dict(fields or {})
    target = str(out.get("petitioner") or "").strip()
    if target in PERSON_NAME_KEYS:
        out.pop("petitioner", None)
        if target in {"firstName", "person.firstName"}:
            out.setdefault("petitioner_first", "firstName")
            out.setdefault("petitioner_last", "lastName")
        elif target in {"lastName", "person.lastName"}:
            out.setdefault("petitioner_last", "lastName")
            out.setdefault("petitioner_first", "firstName")
        else:
            out.setdefault("petitioner_first", "firstName")
            out.setdefault("petitioner_last", "lastName")
    if not out.get("petitioner_first"):
        out["petitioner_first"] = "firstName"
    if not out.get("petitioner_last"):
        out["petitioner_last"] = "lastName"
    if not out.get("petitioner_email"):
        out["petitioner_email"] = "emails"
    if not out.get("petitioner_phone"):
        out["petitioner_phone"] = "phones"
    return out


def _rewrite_address2_keys(fields: dict) -> dict:
    aliases = {
        "mailingaddress",
        "mailing",
        "addresses.mailing",
        "person.mailingaddress",
    }
    out: dict[str, str] = {}
    for key, value in (fields or {}).items():
        target = str(value or "").strip()
        low = target.lower()
        if low.startswith("person."):
            low = low.split(".", 1)[1]
        out[str(key)] = "address2" if low in aliases else target
    return out


def _read_mapping_file(target: Path) -> dict:
    text = target.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return _normalize_mapping(data)
    except Exception:
        pass
    return _normalize_mapping(_parse_simple_mapping(text))


def load_mapping(path: Path | None = None) -> dict:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    env = os.environ.get("FUB_MAPPING_PATH", "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(MAPPING_PATH)
    seen: set[str] = set()
    for target in candidates:
        key = str(target)
        if key in seen:
            continue
        seen.add(key)
        if target.exists():
            return _read_mapping_file(target)
    return {}


def _parse_simple_mapping(text: str) -> dict:
    """Minimal YAML subset so the mapping file still loads without PyYAML."""
    mapping: dict = {
        "skip_petitioner_contains": [],
        "custom_fields": {},
        "send": {},
    }
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith(" ") and ":" not in line.strip().lstrip("-"):
            value = line.strip().lstrip("- ").strip().strip('"')
            if section == "skip_petitioner_contains":
                mapping["skip_petitioner_contains"].append(value)
            continue
        if line.startswith(" ") and ":" in line:
            key, _, value = line.strip().partition(":")
            mapping.setdefault(section or "custom_fields", {})[key.strip()] = value.strip().strip('"')
            continue
        if line.endswith(":") and not line.startswith(" "):
            section = line[:-1].strip()
            if section in {"skip_petitioner_contains"}:
                mapping[section] = []
            elif section in {"custom_fields", "send"}:
                mapping[section] = {}
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            mapping[key.strip()] = value.strip().strip('"')
            section = None
    return mapping


MAPPING_HEADER = """# Follow Up Boss field mapping for Placer Probate Monitor.
# Written by the mapping UI; hand-editing this file is still supported.
# Do not map attorney_phone onto person.phones.
# Decedent is not the FUB Person name (petitioner is).
"""

PERSON_PHONE_KEYS = {"phones", "person.phones"}
PERSON_NAME_KEYS = {"firstName", "lastName", "person.firstName", "person.lastName"}

PROBATE_SOURCE_FIELDS = [
    {
        "key": "petitioner_first",
        "label": "Petitioner first name",
        "group": "petitioner",
        "source": "eCourt petitioner, all tokens except last",
        "notes": "This is the source field for FUB firstName.",
        "person": "firstName",
        "custom": True,
    },
    {
        "key": "petitioner_last",
        "label": "Petitioner last name",
        "group": "petitioner",
        "source": "eCourt petitioner, last token (plus Jr/Sr/II/III)",
        "notes": "This is the source field for FUB lastName.",
        "person": "lastName",
        "custom": True,
    },
    {
        "key": "petitioner",
        "label": "Petitioner full name",
        "group": "petitioner",
        "source": "eCourt parties, else CNPA notice",
        "notes": "Raw extracted name. Map first/last above, not this row.",
        "person": None,
        "custom": False,
        "block": ["firstName", "lastName", "phones", "emails"],
    },
    {
        "key": "mailing_address",
        "label": "Petitioner address",
        "group": "petitioner",
        "source": "DE-111 item 8 / 3h or DE-147 acknowledgment, whichever has it",
        "notes": "Map this source field to Address 1 or Address 2 in the mapping UI. Not item 1 (publication) and not the attorney caption.",
        "person": None,
        "custom": True,
    },
    {
        "key": "mailing_city",
        "label": "Petitioner city",
        "group": "petitioner",
        "source": "DE-111 or DE-147, whichever has it",
        "notes": "City for the petitioner mailing line. Map the street line, not this row, to Address 1 or 2.",
        "person": None,
        "custom": True,
    },
    {
        "key": "mailing_state",
        "label": "Petitioner state",
        "group": "petitioner",
        "source": "DE-111 or DE-147, whichever has it",
        "notes": "State for the petitioner mailing line. Map the street line, not this row, to Address 1 or 2.",
        "person": None,
        "custom": True,
    },
    {
        "key": "mailing_zip",
        "label": "Petitioner ZIP",
        "group": "petitioner",
        "source": "DE-111 or DE-147, whichever has it",
        "notes": "ZIP for the petitioner mailing line. Map the street line, not this row, to Address 1 or 2.",
        "person": None,
        "custom": True,
    },
    {
        "key": "petitioner_email",
        "label": "Petitioner email",
        "group": "petitioner",
        "source": "DE-111 or DE-147, whichever has it",
        "notes": "Never use attorney caption email.",
        "person": "emails",
        "custom": True,
    },
    {
        "key": "petitioner_phone",
        "label": "Petitioner phone",
        "group": "petitioner",
        "source": "DE-111 or DE-147, whichever has it",
        "notes": "Never map attorney_phone onto person.phones.",
        "person": "phones",
        "custom": True,
    },
    {
        "key": "decedent",
        "label": "Decedent name",
        "group": "decedent",
        "source": "CNPA notice / eCourt decedent party",
        "notes": "Never Person first/last name. Custom field only.",
        "person": None,
        "custom": True,
        "block": ["firstName", "lastName", "phones", "emails"],
    },
    {
        "key": "decedent_first",
        "label": "Decedent first name",
        "group": "decedent",
        "source": "Split from decedent name",
        "notes": "Custom field only. Do not map onto Person firstName.",
        "person": None,
        "custom": True,
        "block": ["firstName", "lastName", "phones", "emails"],
    },
    {
        "key": "decedent_last",
        "label": "Decedent last name",
        "group": "decedent",
        "source": "Split from decedent name",
        "notes": "Custom field only. Do not map onto Person lastName.",
        "person": None,
        "custom": True,
        "block": ["firstName", "lastName", "phones", "emails"],
    },
    {
        "key": "decedent_residence",
        "label": "Estate location (DE-111 3.a.(2))",
        "group": "decedent",
        "source": "DE-111 item 3.a.(2) when that box is marked; otherwise item 3c",
        "notes": "The street in 3.a.(2) (estate in the county named above). Never the 'at (place)' death location.",
        "person": None,
        "custom": True,
    },
    {
        "key": "decedent_city",
        "label": "Residence city",
        "group": "decedent",
        "source": "Petition PDF",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "decedent_zip",
        "label": "Residence ZIP",
        "group": "decedent",
        "source": "Petition PDF",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "decedent_died",
        "label": "Date of death",
        "group": "decedent",
        "source": "Petition PDF",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "death_place",
        "label": "Place of death",
        "group": "decedent",
        "source": "DE-111 item 3 'at (place)'",
        "notes": "County/state of death only. Do not map this to Address 1 or 2.",
        "person": None,
        "custom": True,
    },
    {
        "key": "case_number",
        "label": "Case number",
        "group": "other",
        "notes_label": "Casenumber",
        "source": "CNPA notice / eCourt search",
        "notes": "S-PR number used as the lead key.",
        "person": None,
        "custom": True,
    },
    {
        "key": "estate_real",
        "label": "Real property GMV",
        "group": "other",
        "source": "Petition PDF",
        "notes": "Gross fair market value from DE-111, shown as $370,000.00. $0.00 is still a value.",
        "person": None,
        "custom": True,
    },
    {
        "key": "estate_personal",
        "label": "Personal property",
        "group": "other",
        "source": "Petition PDF",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "hearing",
        "label": "Hearing",
        "group": "other",
        "source": "eCourt next event, else notice text",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "court_search",
        "label": "eCourt Public case URL",
        "group": "other",
        "source": "eCourt search hit (node/45/…)",
        "notes": "Per-case portal page. Posted to Follow Up Boss Notes.",
        "person": None,
        "custom": True,
        "notes_label": "Court",
    },
    {
        "key": "notice_url",
        "label": "Newspaper notice URL",
        "group": "other",
        "source": "CNPA",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "petition_pdf",
        "label": "Petition PDF filename",
        "group": "other",
        "source": "Downloaded DE-111",
        "notes": "Local filename only. Map DE-111 PDF URL below for the download link.",
        "person": None,
        "custom": True,
    },
    {
        "key": "de111_url",
        "label": "DE-111 PDF URL",
        "group": "other",
        "notes_label": "DE-111",
        "source": "Home Assistant API URL for the stored DE-111",
        "notes": "Signed download URL. Map to Notes to include DE-111: {url}.",
        "person": None,
        "custom": True,
    },
    {
        "key": "de147_url",
        "label": "DE-147 PDF URL",
        "group": "other",
        "notes_label": "DE-147",
        "source": "Home Assistant API URL for the stored DE-147",
        "notes": "Signed download URL. Map to Notes to include DE-147: {url}.",
        "person": None,
        "custom": True,
    },
    {
        "key": "de150_url",
        "label": "Letters of Administration PDF URL",
        "group": "other",
        "notes_label": "Letters",
        "source": "Home Assistant API URL for the stored issued letters (DE-150)",
        "notes": "Signed download URL. Included in Notes when the letters PDF is on disk.",
        "person": None,
        "custom": True,
    },
    {
        "key": "filed",
        "label": "Filed date",
        "group": "other",
        "source": "eCourt search / docket",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "caption",
        "label": "Case caption",
        "group": "other",
        "source": "eCourt",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "attorney",
        "label": "Attorney (notice)",
        "group": "other",
        "source": "CNPA notice",
        "notes": "Counsel is not the Person. Custom field only.",
        "person": None,
        "custom": True,
        "block": ["firstName", "lastName", "phones", "emails"],
    },
    {
        "key": "attorney_phone",
        "label": "Attorney phone",
        "group": "other",
        "source": "CNPA notice",
        "notes": "Never map onto person.phones.",
        "person": None,
        "custom": True,
        "block": ["phones"],
    },
    {
        "key": "newspaper",
        "label": "Newspaper",
        "group": "other",
        "source": "CNPA",
        "notes": "",
        "person": None,
        "custom": True,
    },
    {
        "key": "will_offered",
        "label": "Will offered",
        "group": "other",
        "source": "CNPA notice",
        "notes": "Yes/No.",
        "person": None,
        "custom": True,
    },
    {
        "key": "iaea_requested",
        "label": "IAEA requested",
        "group": "other",
        "source": "CNPA notice",
        "notes": "Yes/No.",
        "person": None,
        "custom": True,
    },
    {
        "key": "parties",
        "label": "Parties",
        "group": "other",
        "source": "eCourt summary",
        "notes": "Petitioner, decedent, objector, administrator.",
        "person": None,
        "custom": True,
    },
]
FUB_DESTINATIONS = [
    {
        "id": "person.firstName",
        "label": "Person firstName",
        "group": "person",
        "locked_to": "petitioner_first",
    },
    {
        "id": "person.lastName",
        "label": "Person lastName",
        "group": "person",
        "locked_to": "petitioner_last",
    },
    {
        "id": "person.addresses",
        "label": "Person Address 1",
        "group": "person",
    },
    {
        "id": "person.address2",
        "label": "Person Address 2",
        "group": "person",
    },
    {
        "id": "person.emails",
        "label": "Person emails",
        "group": "person",
        "locked_to": "petitioner_email",
    },
    {
        "id": "person.phones",
        "label": "Person phones",
        "group": "person",
        "locked_to": "petitioner_phone",
    },
    {
        "id": "person.assignedTo",
        "label": "Person assignedTo",
        "group": "person",
        "from_config": "fub_assigned_to",
    },
    {
        "id": "person.stage",
        "label": "Person stage",
        "group": "person",
        "from_config": "fub_stage",
    },
    {
        "id": "event.source",
        "label": "Event source",
        "group": "event",
        "from_config": "fub_source",
    },
    {
        "id": "event.message",
        "label": "Event message + description",
        "group": "event",
    },
    {
        "id": "event.system",
        "label": "Event system name",
        "group": "event",
    },
    {
        "id": "custom",
        "label": "Custom field (API name, e.g. customCaseNumber)",
        "group": "custom",
    },
]

FUB_BUILTIN_FIELDS = [
    {"name": "firstName", "label": "First name", "group": "Person", "type": "person"},
    {"name": "lastName", "label": "Last name", "group": "Person", "type": "person"},
    {"name": "assignedTo", "label": "Assigned to", "group": "Person", "type": "person"},
    {"name": "addresses", "label": "Address 1", "group": "Person", "type": "person"},
    {"name": "address2", "label": "Address 2", "group": "Person", "type": "person"},
    {"name": "stage", "label": "Stage", "group": "Person", "type": "person"},
    {"name": "source", "label": "Lead source", "group": "Person", "type": "person"},
    {"name": "tags", "label": "Tags", "group": "Person", "type": "person"},
    {"name": "background", "label": "Background", "group": "Person", "type": "person"},
    {"name": "notes", "label": "Notes", "group": "Person", "type": "person"},
    {"name": "emails", "label": "Email", "group": "Person", "type": "person"},
    {"name": "phones", "label": "Phone", "group": "Person", "type": "person"},
]

PERSON_BUILTIN_TARGETS = {
    "firstName",
    "lastName",
    "assignedTo",
    "addresses",
    "stage",
    "source",
    "tags",
    "background",
    "emails",
    "phones",
}

ADDRESS_SLOT_TARGETS = {
    "addresses": 0,
    "address1": 0,
    "address 1": 0,
    "person.addresses": 0,
    "address2": 1,
    "address 2": 1,
    "mailingaddress": 1,
    "mailing": 1,
    "addresses.mailing": 1,
}

NOTES_TARGETS = {"notes", "note", "background"}

SEND_TOGGLES = [
    {"key": "firstName", "label": "Send petitioner firstName", "editable": True},
    {"key": "lastName", "label": "Send petitioner lastName", "editable": True},
    {"key": "emails", "label": "Send petitioner email", "editable": True},
    {"key": "phones", "label": "Send petitioner phone", "editable": True},
    {"key": "assignedTo", "label": "Send assignedTo from config", "editable": True},
    {"key": "stage", "label": "Send person stage from config", "editable": True},
    {"key": "source", "label": "Send event source from config", "editable": True},
    {"key": "message", "label": "Send event message/description", "editable": True},
    {"key": "custom_fields", "label": "Send custom fields below", "editable": True},
    {
        "key": "de111_file",
        "label": "Post DE-111 PDF link in Follow Up Boss Notes",
        "editable": True,
    },
    {
        "key": "de147_file",
        "label": "Post DE-147 duties PDF link in Follow Up Boss Notes",
        "editable": True,
    },
    {
        "key": "court_url_note",
        "label": "Post the per-case eCourt Public URL in Follow Up Boss Notes",
        "editable": True,
    },
]

MIN_ESTATE_REAL_GMV = 200_000
NOGO_ESTATE_REAL_BELOW_MIN = "estate_real_below_minimum"
NOGO_MISSING_ESTATE_REAL = "missing_estate_real"
FUB_GO_ALWAYS_NOGO = [
    {
        "key": "estate_real",
        "label": "Real property GMV at least $200,000",
        "from": "DE-111 gross fair market value of real property",
        "when": "Always. Missing or blank GMV is NO-GO. Tiny OCR crumbs ($1/$2/$6/$9) count as missing. Under $200,000 (including $0) is NO-GO. Annual income from real property is not this gate.",
    },
    {
        "key": "professional_fiduciary",
        "label": "Not a professional fiduciary",
        "from": "CNPA / DE-111 item 2 / 2.b / item 8 / Public Administrator / CLPF / PFB",
        "when": "Always. Fiduciary listings stay on the board as NO-GO and are not created or updated in Follow Up Boss.",
    },
    {
        "key": "fub_removed",
        "label": "Follow Up Boss person was not deleted",
        "from": "Follow Up Boss GET person",
        "when": "Always. A deleted person is marked fub_removed and is not recreated.",
    },
]

GO_NO_GO = [
    "Petitioner is the FUB Person. Decedent is never firstName/lastName. Form captions (Estate Of, Case Number, Hearing Date, Dept, Petitioner, County Of, Superior Court, Decedent, Casenumber) are not person names.",
    "NO-GO unless DE-111 gross fair market value of real property is present and at least $200,000. Missing, blank, tiny OCR crumbs ($1–$9), $0, and under $200,000 all fail. Annual gross income from real property is not this gate.",
    "Go if Path A or Path B. Path A (same for Placer and Sacramento): real petitioner first, real petitioner last, and petitioner mailing street. Decedent residence is collected but not required on Path A unless checked. Path B: petitioner name (first+last or full petitioner), decedent name, decedent address (DE-111 3.a.(2)/3c / decedent_residence), and petitioner phone. Case number is never required for Go.",
    "Path B does not require mailing. Path A does not require petitioner phone or decedent address. Map petitioner mailing and decedent last residence to Address 1 or Address 2 in the mapping UI. Item 1 is publication. Attorney caption is not petitioner mailing.",
    "Never map attorney_phone onto person.phones. Attorney caption address is not petitioner mailing.",
    "Last residence is DE-111 text, not a verified APN.",
    "Notes gets the per-case eCourt Public URL, a unique DE-111 PDF link, a DE-147 duties link, and a Letters (DE-150) link when issued letters were downloaded. Petitioner phone and email come from either form when present, never from the attorney caption.",
    "Only NEW cases are created on a full run. Verify can update a person ID you enter, reuse the last test person, or create one if none exist.",
    "Follow Up Boss person and event source is probate. Tags are probate plus the county name. Person updates use mergeTags=true so other tags are kept.",
    "Skip Follow Up Boss create and update when the petitioner (or DE-111 item 2 / 2.b / item 8 petitioner row, or node/415 caption/parties) is a fiduciary: public administrator/guardian, professional or private professional fiduciary, CLPF / PFB license, licensed fiduciary bureau, Fiduciary Services, corporate trustee, or a bank/trust company named as personal representative. Family petitioners who are only a proposed administrator, attorney-caption wording, and will boilerplate such as \"bank or trust company\" are not a skip. Keep the listings row as no-go.",
]

SOURCE_GO_NO_GO = {
    "placer": {
        "required": [
            {
                "key": "petitioner_first",
                "label": "Petitioner first name (real person, not a form caption)",
                "from": "eCourt petitioner",
            },
            {
                "key": "petitioner_last",
                "label": "Petitioner last name",
                "from": "eCourt petitioner",
            },
            {
                "key": "mailing_address",
                "label": "Petitioner mailing address (street, not caption or legal description)",
                "from": "DE-111 item 8 / 3h or DE-147, whichever has it",
            },
        ],
        "optional": [
            {
                "key": "case_number",
                "label": "Case number",
                "from": "CNPA notice / eCourt",
                "when": "Not required for Go. Posted to Follow Up Boss when present.",
            },
            {
                "key": "petitioner_email",
                "label": "Petitioner email",
                "from": "DE-111 or DE-147, whichever has it",
            },
            {
                "key": "petitioner_phone",
                "label": "Petitioner phone",
                "from": "DE-111 or DE-147, whichever has it",
                "when": "Required on Path B. Not required on Path A.",
            },
            {
                "key": "decedent_residence",
                "label": "Estate location (3.a.(2))",
                "from": "DE-111 item 3.a.(2) street; never 'at (place)'",
                "when": "Collected. Required on Path B (with decedent name and petitioner phone). Not required for Path A GO unless checked on Follow Up Boss → Required for Go",
            },
            {
                "key": "court_url",
                "label": "eCourt Public case URL",
                "from": "Search hit ?q=node/45/…",
                "when": "Posted to Follow Up Boss Notes when present",
            },
        ],
        "rules": GO_NO_GO,
    },
    "sacramento": {
        "required": [
            {
                "key": "petitioner_first",
                "label": "Petitioner first name (real person, not a form caption)",
                "from": "Published notice / portal parties",
            },
            {
                "key": "petitioner_last",
                "label": "Petitioner last name",
                "from": "Published notice / portal parties",
            },
            {
                "key": "mailing_address",
                "label": "Petitioner mailing address (street, not caption or legal description)",
                "from": "DE-111 item 8 / 3h or DE-147, whichever has it",
            },
        ],
        "optional": [
            {
                "key": "case_number",
                "label": "Case number",
                "from": "CNPA notice / Sacramento portal",
                "when": "Not required for Go. Posted to Follow Up Boss when present.",
            },
            {
                "key": "petitioner_email",
                "label": "Petitioner email",
                "from": "DE-111 or DE-147, whichever has it",
            },
            {
                "key": "petitioner_phone",
                "label": "Petitioner phone",
                "from": "DE-111 or DE-147, whichever has it",
                "when": "Required on Path B. Not required on Path A.",
            },
            {
                "key": "decedent_residence",
                "label": "Estate location (3.a.(2))",
                "from": "DE-111 item 3.a.(2) street; never 'at (place)'",
                "when": "Collected. Required on Path B (with decedent name and petitioner phone). Not required for Path A GO unless checked on Follow Up Boss → Required for Go",
            },
            {
                "key": "court_url",
                "label": "Sacramento case summary URL",
                "from": "Journal Technologies node/397/{id}",
                "when": "Posted to Follow Up Boss Notes when present. Never rewritten to Placer node/45.",
            },
        ],
        "rules": GO_NO_GO + [
            "Court summaries stay on prod-portal-sacramento-ca.journaltech.com node/397. Do not rewrite them to Placer node/45.",
            "Public petition and duties PDFs are downloaded after portal login. Confidential Not Viewable documents, including DE-147S, are skipped.",
            "Follow Up Boss tags are probate plus sacramento. Person updates use mergeTags=true so other tags are kept.",
            "The same Follow Up Boss mapping and Events import path as Placer. Turning this source off does not stop Placer.",
        ],
    },
}

# Gate keys that already exist in gate_reason / SOURCE_GO_NO_GO. Do not invent new ones.
FUB_GO_GATE_FIELDS = [
    {"key": "petitioner_first", "label": "Petitioner first name (real person, not a form caption)"},
    {"key": "petitioner_last", "label": "Petitioner last name"},
    {"key": "mailing_address", "label": "Petitioner mailing address (street, not caption or legal description)"},
    {"key": "decedent_residence", "label": "Estate location (decedent residence; collected, not required for GO unless checked)"},
]
FUB_GO_GATE_FIELD_KEYS = tuple(item["key"] for item in FUB_GO_GATE_FIELDS)
DEFAULT_FUB_GO_REQUIRED_FIELDS = (
    "petitioner_first",
    "petitioner_last",
    "mailing_address",
)


def normalize_fub_go_required_fields(value) -> list[str]:
    """Keep only known Go-gate keys, in catalog order."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value if str(item).strip()]
    else:
        raw = []
    wanted = {item.lower().replace("-", "_") for item in raw}
    wanted.discard("case_number")
    return [key for key in FUB_GO_GATE_FIELD_KEYS if key in wanted]


def resolve_fub_go_required_fields(
    required_fields=None,
    *,
    strict_property: bool | None = None,
    settings: dict | None = None,
) -> list[str]:
    """Saved checklist is the source of truth. Missing list uses production defaults.

    Production defaults: petitioner first, petitioner last, mailing.
    Case number is never a Go requirement, even if an older saved list has it.
    Decedent residence is included only when the saved list has it, or when an
    older ``fub_strict_property`` / FUB_STRICT_PROPERTY toggle is on and no list
    has been saved yet.
    """
    if required_fields is not None:
        return normalize_fub_go_required_fields(required_fields)
    if settings is not None:
        stored = settings.get("fub_go_required_fields", None)
        if stored is not None:
            return normalize_fub_go_required_fields(stored)
        strict = bool(
            settings.get("fub_strict_property")
            if strict_property is None
            else strict_property
        )
        fields = list(DEFAULT_FUB_GO_REQUIRED_FIELDS)
        if strict and "decedent_residence" not in fields:
            fields.append("decedent_residence")
        return fields
    if "FUB_GO_REQUIRED_FIELDS" in os.environ:
        return normalize_fub_go_required_fields(os.environ.get("FUB_GO_REQUIRED_FIELDS"))
    strict = (
        _env_bool("FUB_STRICT_PROPERTY") if strict_property is None else bool(strict_property)
    )
    fields = list(DEFAULT_FUB_GO_REQUIRED_FIELDS)
    if strict and "decedent_residence" not in fields:
        fields.append("decedent_residence")
    return fields


def fub_go_required_from_settings(settings: dict | None = None) -> list[str]:
    return resolve_fub_go_required_fields(settings=settings or {})


def apply_fub_go_required_env(settings: dict | None = None) -> list[str]:
    fields = fub_go_required_from_settings(settings)
    os.environ["FUB_GO_REQUIRED_FIELDS"] = ",".join(fields)
    os.environ["FUB_STRICT_PROPERTY"] = (
        "1" if "decedent_residence" in fields else "0"
    )
    return fields


def go_no_go_for_source(source_id: str, required_fields=None) -> dict:
    key = str(source_id or "placer")
    spec = SOURCE_GO_NO_GO.get(key) or {
        "required": [],
        "optional": [],
        "rules": ["Go/no-go is not defined for this source yet."],
    }
    base_required = list(spec.get("required") or [])
    base_optional = list(spec.get("optional") or [])
    if key not in {"placer", "sacramento"}:
        return {
            "source_id": key,
            "required": base_required,
            "optional": base_optional,
            "always": list(FUB_GO_ALWAYS_NOGO),
            "rules": list(spec.get("rules") or []),
        }
    required_keys = set(resolve_fub_go_required_fields(required_fields))
    combined: list[dict] = []
    seen: set[str] = set()
    for item in base_required + base_optional:
        item_key = str(item.get("key") or "")
        if not item_key or item_key in seen:
            continue
        seen.add(item_key)
        combined.append(dict(item))
    required: list[dict] = []
    optional: list[dict] = []
    for item in combined:
        item_key = str(item.get("key") or "")
        row = dict(item)
        if item_key in FUB_GO_GATE_FIELD_KEYS:
            row.pop("when", None)
            if item_key in required_keys:
                required.append(row)
            else:
                if item_key == "decedent_residence":
                    row["when"] = (
                        "Path A: optional unless checked on Follow Up Boss → Required for Go. "
                        "Path B: required (with decedent name and petitioner phone)."
                    )
                else:
                    row["when"] = (
                        "Optional unless checked on Follow Up Boss → Required for Go"
                    )
                optional.append(row)
            continue
        if any(entry.get("key") == item_key for entry in base_required):
            required.append(row)
        else:
            optional.append(row)
    return {
        "source_id": key,
        "required": required,
        "optional": optional,
        "always": list(FUB_GO_ALWAYS_NOGO),
        "rules": list(spec.get("rules") or []),
    }


DATA_SOURCES = [
    {
        "id": "placer",
        "name": "Placer County",
        "status": "live",
        "description": "California Newspaper Public Notices plus Placer eCourt Public and DE-111 petitions.",
        "extracts": "CNPA notice, eCourt docket, petition PDF",
        "lead_source": COUNTY_FUB_LEAD_SOURCES["placer"],
    },
    {
        "id": "sacramento",
        "name": "Sacramento County",
        "status": "live",
        "description": "California Newspaper Public Notices (NOTICE OF PETITION) plus Sacramento Journal Technologies summaries and public DE-111/DE-147 PDFs after portal login.",
        "extracts": "CNPA notice, Sacramento portal summary, public petition and duties PDFs",
        "lead_source": COUNTY_FUB_LEAD_SOURCES["sacramento"],
    },
]

SOURCE_SETTING_KEYS = [
    "lookback_days",
    "lookahead_days",
    "county",
    "keywords",
    "skip_portal",
    "generate_pdf",
    "ecourt_pause_seconds",
    "max_search_pages",
]

SACRAMENTO_LOOKBACK_KEY = "sacramento_lookback_days"
SACRAMENTO_LOOKAHEAD_KEY = "sacramento_lookahead_days"
SACRAMENTO_PAUSE_KEY = "sacramento_ecourt_pause_seconds"
PUBLIC_REPORTS_LOOKBACK_KEY = "public_reports_lookback_days"
DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_LOOKAHEAD_DAYS = 21
DEFAULT_SACRAMENTO_LOOKBACK_DAYS = 60
DEFAULT_SACRAMENTO_LOOKAHEAD_DAYS = 0
# Node/415 only: 2 inclusive filing days ending today (today + yesterday) so
# one missed daily HA run is recovered. One query per calendar day → 2 POSTs
# per daily job. Raise in the panel for catch-up. Never inherit CNPA lookahead.
DEFAULT_PUBLIC_REPORTS_LOOKBACK_DAYS = 2
PUBLIC_REPORTS_LOOKAHEAD_DAYS = 0
DEFAULT_PORTAL_PAUSE = 1.2


def _optional_int(value, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _optional_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def source_window_settings(settings: dict | None, source_id: str = "placer") -> dict:
    """Lookback, lookahead, and portal pause for one county. Independent of the other.

    Sacramento CNPA uses sacramento_lookback_days / sacramento_lookahead_days
    (default 60/0). Node/415 uses public_reports_lookback_days (default 2:
    today + yesterday) with lookahead always 0 — never CNPA's lookahead.
    """
    data = settings or {}
    key = str(source_id or "placer").strip().lower()
    if key == "sacramento":
        lookback_raw = data.get(SACRAMENTO_LOOKBACK_KEY)
        lookahead_raw = data.get(SACRAMENTO_LOOKAHEAD_KEY)
        pause_raw = data.get(SACRAMENTO_PAUSE_KEY)
        lookback_default = DEFAULT_SACRAMENTO_LOOKBACK_DAYS
        lookahead_default = DEFAULT_SACRAMENTO_LOOKAHEAD_DAYS
        pr_raw = data.get(PUBLIC_REPORTS_LOOKBACK_KEY)
    else:
        lookback_raw = data.get("lookback_days")
        lookahead_raw = data.get("lookahead_days")
        pause_raw = data.get("ecourt_pause_seconds")
        lookback_default = DEFAULT_LOOKBACK_DAYS
        lookahead_default = DEFAULT_LOOKAHEAD_DAYS
        pr_raw = None
    try:
        lookback = _optional_int(lookback_raw, lookback_default)
    except (TypeError, ValueError):
        lookback = lookback_default
    try:
        lookahead = _optional_int(lookahead_raw, lookahead_default)
    except (TypeError, ValueError):
        lookahead = lookahead_default
    try:
        pause = _optional_float(pause_raw, DEFAULT_PORTAL_PAUSE)
    except (TypeError, ValueError):
        pause = DEFAULT_PORTAL_PAUSE
    pr_lookback = DEFAULT_PUBLIC_REPORTS_LOOKBACK_DAYS
    if key == "sacramento":
        try:
            pr_lookback = _optional_int(pr_raw, DEFAULT_PUBLIC_REPORTS_LOOKBACK_DAYS)
        except (TypeError, ValueError):
            pr_lookback = DEFAULT_PUBLIC_REPORTS_LOOKBACK_DAYS
    return {
        "lookback_days": lookback,
        "lookahead_days": lookahead,
        "public_reports_lookback_days": pr_lookback,
        "public_reports_lookahead_days": PUBLIC_REPORTS_LOOKAHEAD_DAYS,
        "ecourt_pause_seconds": pause,
    }


def apply_sacramento_source_settings(settings: dict, body: dict) -> dict:
    """Copy Sacramento window fields from a sources POST onto HA options.

    Accepts the panel's lookback_days / lookahead_days / ecourt_pause_seconds
    / public_reports_lookback_days or the stored sacramento_* keys.
    Does not change Placer's window. 415 lookahead is never stored (always 0).
    """
    out = dict(settings or {})
    payload = body or {}
    if "sacramento_lookback_days" in payload or "lookback_days" in payload:
        raw = (
            payload["sacramento_lookback_days"]
            if "sacramento_lookback_days" in payload
            else payload["lookback_days"]
        )
        value = _optional_int(raw, DEFAULT_SACRAMENTO_LOOKBACK_DAYS)
        if value < 1 or value > 365:
            raise ValueError("lookback_days")
        out[SACRAMENTO_LOOKBACK_KEY] = value
    if "sacramento_lookahead_days" in payload or "lookahead_days" in payload:
        raw = (
            payload["sacramento_lookahead_days"]
            if "sacramento_lookahead_days" in payload
            else payload["lookahead_days"]
        )
        value = _optional_int(raw, DEFAULT_SACRAMENTO_LOOKAHEAD_DAYS)
        if value < 0 or value > 120:
            raise ValueError("lookahead_days")
        out[SACRAMENTO_LOOKAHEAD_KEY] = value
    if PUBLIC_REPORTS_LOOKBACK_KEY in payload:
        value = _optional_int(
            payload[PUBLIC_REPORTS_LOOKBACK_KEY],
            DEFAULT_PUBLIC_REPORTS_LOOKBACK_DAYS,
        )
        if value < 1 or value > 365:
            raise ValueError("public_reports_lookback_days")
        out[PUBLIC_REPORTS_LOOKBACK_KEY] = value
    if "sacramento_ecourt_pause_seconds" in payload or "ecourt_pause_seconds" in payload:
        raw = (
            payload["sacramento_ecourt_pause_seconds"]
            if "sacramento_ecourt_pause_seconds" in payload
            else payload["ecourt_pause_seconds"]
        )
        value = _optional_float(raw, DEFAULT_PORTAL_PAUSE)
        if value < 0.5 or value > 10:
            raise ValueError("ecourt_pause_seconds")
        out[SACRAMENTO_PAUSE_KEY] = value
    return out


def sacramento_cli_window_args(settings: dict | None) -> list[str]:
    """Argv for sacramento_probate_monitor: CNPA window plus independent 415 lookback."""
    window = source_window_settings(settings, "sacramento")
    return [
        "--lookback-days",
        str(int(window["lookback_days"])),
        "--lookahead-days",
        str(int(window["lookahead_days"])),
        "--public-reports-lookback-days",
        str(int(window["public_reports_lookback_days"])),
    ]


def source_field_catalog(source_id: str) -> list[dict]:
    key = str(source_id or "placer")
    if key == "placer":
        return PROBATE_SOURCE_FIELDS
    if key == "sacramento":
        rows = []
        for item in PROBATE_SOURCE_FIELDS:
            row = dict(item)
            if row.get("key") in {"court_search", "court_url"}:
                row["label"] = "Sacramento case summary URL"
                row["source"] = "Journal Technologies public portal node/397"
            elif row.get("key") == "case_number":
                row["source"] = "CNPA notice / Sacramento portal"
                row["notes"] = "YYPR###### case number used as the lead key."
            elif row.get("key") in {
                "mailing_address",
                "petitioner_email",
                "petitioner_phone",
                "decedent_residence",
                "decedent_died",
                "death_place",
                "estate_real",
                "estate_personal",
                "petition_pdf",
                "de111_url",
                "de147_url",
                "de150_url",
            }:
                row["source"] = "Sacramento public DE-111 / DE-147 after portal login"
            else:
                src = str(row.get("source") or "CNPA notice / Sacramento portal")
                src = (
                    src.replace("eCourt petitioner", "Sacramento portal petitioner")
                    .replace("eCourt parties", "Sacramento portal parties")
                    .replace("eCourt next event", "Sacramento portal next event")
                    .replace("eCourt search / docket", "Sacramento portal docket")
                    .replace("eCourt summary", "Sacramento portal summary")
                    .replace("eCourt", "Journal Technologies public portal")
                    .replace("node/45", "node/397")
                )
                row["source"] = src
            rows.append(row)
        return rows
    rows = []
    for item in PROBATE_SOURCE_FIELDS:
        row = dict(item)
        row["unavailable"] = True
        row["source"] = "Not extracted yet"
        rows.append(row)
    return rows


def custom_fields_for_source(mapping: dict, source_id: str) -> dict:
    source_id = str(source_id or "placer")
    sources = mapping.get("source_mappings") or {}
    block = sources.get(source_id) or {}
    fields = block.get("custom_fields") if isinstance(block, dict) else None
    if isinstance(fields, dict) and fields:
        return fields
    if source_id == "placer":
        return mapping.get("custom_fields") or {}
    if source_id == "sacramento":
        return mapping.get("custom_fields") or {}
    return {}


def mapping_for_export(mapping: dict, source_id: str | None = None) -> dict:
    source_id = str(
        source_id or os.environ.get("FUB_DATA_SOURCE") or "placer"
    ).strip().lower() or "placer"
    out = dict(mapping or {})
    fields = custom_fields_for_source(out, source_id)
    if fields:
        out["custom_fields"] = fields
    try:
        out["lead_source"] = fub_lead_source(source_id)
    except ValueError:
        out["lead_source"] = ""
    return out


def normalize_source_enabled(settings: dict | None = None) -> dict[str, bool]:
    raw = (settings or {}).get("source_enabled") or {}
    if not isinstance(raw, dict):
        raw = {}
    flags = {"placer": True, "sacramento": False}
    for key in flags:
        if key in raw:
            flags[key] = bool(raw[key])
    return flags


def source_is_enabled(settings: dict | None, source_id: str) -> bool:
    key = str(source_id or "").strip().lower()
    return bool(normalize_source_enabled(settings).get(key))


def enabled_live_sources(settings: dict | None = None) -> list[str]:
    flags = normalize_source_enabled(settings)
    return [
        item["id"]
        for item in DATA_SOURCES
        if item.get("status") == "live" and flags.get(item["id"])
    ]


def sources_payload(settings: dict | None = None) -> dict:
    placer = {}
    for key in SOURCE_SETTING_KEYS:
        placer[key] = (settings or {}).get(key)
    if not placer.get("county"):
        placer["county"] = "Placer"
    enabled = normalize_source_enabled(settings)
    sac_window = source_window_settings(settings, "sacramento")
    sources = []
    for item in DATA_SOURCES:
        row = dict(item)
        row["enabled"] = bool(enabled.get(row["id"])) if row.get("status") == "live" else False
        sources.append(row)
    return {
        "sources": sources,
        "source_enabled": enabled,
        "active": "placer",
        "placer": placer,
        "sacramento": {
            "county": "Sacramento",
            "keywords": '"NOTICE OF PETITION"',
            "lookback_days": sac_window["lookback_days"],
            "lookahead_days": sac_window["lookahead_days"],
            "public_reports_lookback_days": sac_window["public_reports_lookback_days"],
            "skip_portal": placer.get("skip_portal"),
            "generate_pdf": placer.get("generate_pdf"),
            "ecourt_pause_seconds": sac_window["ecourt_pause_seconds"],
            "max_search_pages": placer.get("max_search_pages"),
            "sacramento_portal_user": str((settings or {}).get("sacramento_portal_user") or ""),
            "sacramento_portal_password_set": bool(
                str((settings or {}).get("sacramento_portal_password") or "").strip()
            ),
        },
        "fields": source_field_catalog("placer"),
        "source_fields": {item["id"]: source_field_catalog(item["id"]) for item in DATA_SOURCES},
        "fub_go_required_fields": fub_go_required_from_settings(settings),
        "fub_go_gate_fields": list(FUB_GO_GATE_FIELDS),
        "source_go_no_go": {
            item["id"]: go_no_go_for_source(
                item["id"], fub_go_required_from_settings(settings)
            )
            for item in DATA_SOURCES
        },
    }


def mapping_catalog() -> dict:
    return {
        "data_source": "placer",
        "data_source_name": "Placer County",
        "probate_fields": PROBATE_SOURCE_FIELDS,
        "fub_destinations": FUB_DESTINATIONS,
        "send_toggles": SEND_TOGGLES,
        "go_no_go": GO_NO_GO,
        "source_go_no_go": {
            item["id"]: go_no_go_for_source(item["id"]) for item in DATA_SOURCES
        },
        "fub_go_gate_fields": list(FUB_GO_GATE_FIELDS),
        "fub_go_required_fields": resolve_fub_go_required_fields(),
        "default_custom_fields": {
            "petitioner_first": "firstName",
            "petitioner_last": "lastName",
            "petitioner_email": "emails",
            "petitioner_phone": "phones",
        },
    }


def mapping_errors(mapping: dict, *, source_id: str = "placer") -> list[str]:
    errors: list[str] = []
    send = mapping.get("send") or {}
    fields = mapping.get("custom_fields") or {}
    by_key = {item["key"]: item for item in source_field_catalog(source_id)}
    live = str(source_id or "placer") in {"placer", "sacramento"}
    for local_key, api_name in fields.items():
        api = str(api_name or "").strip()
        if not api:
            continue
        meta = by_key.get(local_key) or {}
        blocked = set(meta.get("block") or [])
        if api in PERSON_PHONE_KEYS or api in blocked and api in {"phones", "person.phones"}:
            if "phones" in blocked or local_key == "attorney_phone":
                errors.append(f"Never map {local_key} onto person.phones.")
        if api in PERSON_NAME_KEYS and local_key not in {
            "petitioner_first",
            "petitioner_last",
        }:
            errors.append(f"{local_key} cannot map onto Person first/last name.")
        if live and meta.get("unavailable"):
            errors.append(f"{local_key} is not extracted yet.")
        if api in {"phones", "emails", "person.phones", "person.emails"}:
            if local_key not in {"petitioner_phone", "petitioner_email"}:
                errors.append(f"{local_key} cannot map onto person emails/phones.")
    return errors


def _dump_simple_mapping(mapping: dict) -> str:
    lines = [
        f"system: {mapping.get('system') or 'PlacerProbateMonitor'}",
        f'court_search_url: "{mapping.get("court_search_url") or COURT_SEARCH_DEFAULT}"',
        f'subject_address_type: "{mapping.get("subject_address_type") or "subject property"}"',
        "",
        "skip_petitioner_contains:",
    ]
    skip = mapping.get("skip_petitioner_contains") or []
    if skip:
        lines.extend(f"  - {item}" for item in skip)
    else:
        lines.append("  []")
    lines.extend(["", "custom_fields:"])
    fields = mapping.get("custom_fields") or {}
    if fields:
        for key, value in fields.items():
            lines.append(f"  {key}: {value}")
    else:
        lines.append("  {}")
    lines.extend(["", "send:"])
    send = mapping.get("send") or {}
    for item in SEND_TOGGLES:
        key = item["key"]
        value = send.get(key, False if item.get("forced") is False else True)
        if item.get("forced") is False:
            value = False
        lines.append(f"  {key}: {'true' if value else 'false'}")
    return "\n".join(lines) + "\n"


def save_mapping(mapping: dict, path: Path | None = None) -> Path:
    incoming = _normalize_mapping(mapping)
    source_id = str(mapping.get("source_id") or "placer")
    existing = load_mapping(path)
    sources = dict(existing.get("source_mappings") or {})
    if existing.get("custom_fields") and "placer" not in sources:
        sources["placer"] = {"custom_fields": dict(existing.get("custom_fields") or {})}
    sources[source_id] = {"custom_fields": dict(incoming.get("custom_fields") or {})}
    send = dict(incoming.get("send") or existing.get("send") or {})
    incoming["send"] = send
    incoming["source_mappings"] = sources
    errors = mapping_errors(
        {**incoming, "custom_fields": sources[source_id]["custom_fields"]},
        source_id=source_id,
    )
    if errors:
        raise ValueError("; ".join(errors))
    incoming["custom_fields"] = dict(
        (sources.get("placer") or {}).get("custom_fields") or {}
    )
    if not incoming.get("system"):
        incoming["system"] = existing.get("system") or "PlacerProbateMonitor"
    if not incoming.get("court_search_url"):
        incoming["court_search_url"] = (
            existing.get("court_search_url") or COURT_SEARCH_DEFAULT
        )
    if not incoming.get("subject_address_type"):
        incoming["subject_address_type"] = (
            existing.get("subject_address_type") or "subject property"
        )
    incoming.pop("source_id", None)
    if "skip_petitioner_contains" not in mapping:
        incoming["skip_petitioner_contains"] = existing.get("skip_petitioner_contains") or []
    target = writable_mapping_path(path)
    try:
        import yaml  # type: ignore

        body = yaml.safe_dump(incoming, sort_keys=False, allow_unicode=True)
    except Exception:
        body = _dump_simple_mapping(incoming)
    target.write_text(MAPPING_HEADER + "\n" + body, encoding="utf-8")
    return target


def _stringify_field(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if isinstance(value, list):
        return "; ".join(str(x) for x in value if x)
    if value is None:
        return ""
    return str(value).strip()


def _gmv_plain_field(value) -> str:
    """Plain GMV for review sheets. Empty if missing; '0' if $0."""
    if value is None or value is True or value is False:
        return ""
    if isinstance(value, (int, float)):
        if value == int(value):
            return str(int(value))
        return str(value)
    raw = str(value).strip()
    if not raw:
        return ""
    cleaned = raw.replace("$", "").replace(",", "").strip()
    try:
        amount = float(cleaned)
        if amount == int(amount):
            return str(int(amount))
        return f"{amount:.2f}".rstrip("0").rstrip(".")
    except ValueError:
        return raw


def _money_field(value) -> str:
    raw = _stringify_field(value)
    if not raw:
        return ""
    cleaned = raw.replace("$", "").replace(",", "").strip()
    try:
        return f"${float(cleaned):,.2f}"
    except ValueError:
        return raw


def _row_contact(row: dict) -> dict:
    try:
        from .petition_parse import merge_petitioner_contact
    except ImportError:
        from petition_parse import merge_petitioner_contact

    return merge_petitioner_contact(
        row,
        row.get("contact_de111") or {},
        row.get("contact_de147") or {},
    )


def source_extract_rows(row: dict, mapping: dict) -> list[dict]:
    values = probate_export_values(row, mapping)
    seen: set[str] = set()
    out: list[dict] = []
    source_id = _row_source_id(row)
    extra_source = (
        "Journal Technologies public portal"
        if source_id == "sacramento"
        else "eCourt"
    )
    for field in source_field_catalog(source_id):
        key = str(field.get("key") or "")
        if not key:
            continue
        seen.add(key)
        if field.get("unavailable"):
            out.append(
                {
                    "key": key,
                    "label": field.get("label") or key,
                    "source": field.get("source") or "",
                    "value": "",
                    "empty": True,
                    "unavailable": True,
                    "notes": field.get("notes") or "",
                }
            )
            continue
        value = values.get(key) or ""
        out.append(
            {
                "key": key,
                "label": field.get("label") or key,
                "source": field.get("source") or "",
                "value": value,
                "empty": value in (None, ""),
                "unavailable": False,
                "notes": field.get("notes") or "",
            }
        )
    extra_labels = {
        "county_resident": "County resident",
        "case_type": "Case type",
        "court_status": "Court status",
    }
    for key, label in extra_labels.items():
        if key in seen:
            continue
        value = values.get(key) or ""
        if value in (None, ""):
            continue
        out.append(
            {
                "key": key,
                "label": label,
                "source": extra_source,
                "value": value,
                "empty": False,
                "unavailable": False,
                "notes": "",
            }
        )
    return out


def mapped_look_payload(row: dict, person: dict, settings: dict, mapping: dict) -> dict:
    event = build_event(row, mapping, settings, person=person)
    addresses = person.get("addresses") or []
    person_rows = [
        {"label": "firstName", "value": person.get("firstName") or ""},
        {"label": "lastName", "value": person.get("lastName") or ""},
        {"label": "assignedTo", "value": person.get("assignedTo") or ""},
        {"label": "stage", "value": person.get("stage") or ""},
        {
            "label": "Address 1",
            "value": _format_fub_address(addresses[0] if addresses else None),
        },
        {
            "label": "Address 2",
            "value": _format_fub_address(addresses[1] if len(addresses) > 1 else None),
        },
        {
            "label": "emails",
            "value": _fub_display_value(person.get("emails")),
        },
        {
            "label": "phones",
            "value": _fub_display_value(person.get("phones")),
        },
    ]
    skip = {
        "id",
        "_addr_slots",
        "firstName",
        "lastName",
        "assignedTo",
        "stage",
        "addresses",
        "background",
        "emails",
        "phones",
    }
    for key, value in person.items():
        if key in skip or value in (None, "", []):
            continue
        person_rows.append({"label": str(key), "value": str(value)})
    notes = person.get("background") or combined_notes(row, mapping)
    if notes:
        person_rows.append({"label": "notes", "value": notes})
    send = mapping.get("send") or {}
    pdf_path = _petition_pdf_path(row)
    if send.get("de111_file", True):
        person_rows.append(
            {
                "label": "Files",
                "value": (
                    f"{pdf_path.name} → FUB Files (DE-111)"
                    if pdf_path
                    else "No DE-111 PDF downloaded yet"
                ),
            }
        )
    return {
        "person": person_rows,
        "event_type": event.get("type") or settings.get("event_type") or "",
        "lead_source": (
            mapping.get("lead_source")
            or event.get("source")
            or _fub_lead_source_name(row)
            or ""
        ),
        "system": event.get("system") or "",
        "message": event.get("message") or "",
        "description": event.get("description") or "",
    }


def probate_export_values(row: dict, mapping: dict) -> dict:
    petitioner = portal_petitioner(row)
    first, last = split_person_name(petitioner)
    decedent = _row_decedent_name(row)
    dec_first, dec_last = split_person_name(decedent.split(",")[0] if decedent else "")
    case = case_key(row)
    court_note = _court_search_note(row, mapping)
    petition_name = (
        Path(str(row.get("petition_pdf") or "")).name if row.get("petition_pdf") else ""
    )
    contact = _row_contact(row)
    return {
        "petitioner": petitioner,
        "petitioner_first": first,
        "petitioner_last": last,
        "decedent": decedent,
        "decedent_first": dec_first,
        "decedent_last": dec_last,
        "case_number": court_case_number(row) or "",
        "decedent_residence": _stringify_field(row.get("decedent_residence")),
        "decedent_city": _stringify_field(row.get("decedent_city")),
        "decedent_state": _stringify_field(row.get("decedent_state")),
        "decedent_zip": _stringify_field(row.get("decedent_zip")),
        "mailing_address": _stringify_field(contact.get("mailing_address") or row.get("mailing_address")),
        "mailing_city": _stringify_field(contact.get("mailing_city") or row.get("mailing_city")),
        "mailing_state": _stringify_field(contact.get("mailing_state") or row.get("mailing_state")),
        "mailing_zip": _stringify_field(contact.get("mailing_zip") or row.get("mailing_zip")),
        "petitioner_email": _stringify_field(contact.get("petitioner_email") or row.get("petitioner_email")),
        "petitioner_phone": _stringify_field(contact.get("petitioner_phone") or row.get("petitioner_phone")),
        "decedent_died": _stringify_field(row.get("decedent_died")),
        "death_place": _stringify_field(row.get("death_place")),
        "estate_real": _money_field(row.get("estate_real")),
        "estate_personal": _money_field(row.get("estate_personal")),
        "hearing": _stringify_field(row.get("next_event") or row.get("hearing")),
        "court_search": court_note,
        "court_url": case_portal_url(row) or court_note,
        "notice_url": _stringify_field(row.get("notice_url")),
        "petition_pdf": petition_name,
        "de111_url": petition_public_uri(case) if case and _petition_pdf_path(row) else "",
        "de147_url": duties_public_uri(case) if case and _duties_pdf_path(row) else "",
        "de150_url": letters_public_uri(case) if case and _letters_pdf_path(row) else "",
        "filed": _stringify_field(row.get("filed") or row.get("filed_from_docket")),
        "caption": _stringify_field(row.get("caption")),
        "attorney": _stringify_field(row.get("attorney")),
        "attorney_phone": _stringify_field(row.get("attorney_phone")),
        "newspaper": _stringify_field(row.get("newspaper")),
        "will_offered": _stringify_field(row.get("will_offered")),
        "iaea_requested": _stringify_field(row.get("iaea_requested")),
        "parties": _stringify_field(row.get("parties")),
        "county_resident": _stringify_field(row.get("county_resident")),
        "case_type": _stringify_field(row.get("case_type")),
        "court_status": _stringify_field(row.get("court_status")),
    }


def _fub_target_name(api_name: str) -> str:
    target = str(api_name or "").strip()
    if target.lower().startswith("person."):
        return target.split(".", 1)[1]
    return target


def _is_notes_target(api_name: str) -> bool:
    return _fub_target_name(api_name).lower() in NOTES_TARGETS


def _source_mapped_to_notes(mapping: dict, key: str) -> bool:
    fields = mapping.get("custom_fields") or {}
    return _is_notes_target(str(fields.get(key) or ""))


def _notes_field_label(key: str) -> str:
    special = {
        "case_number": "Casenumber",
        "decedent": "Decedent",
        "decedent_first": "Decedent",
        "decedent_last": "Decedent",
        "petitioner": "Petitioner",
        "petitioner_first": "Petitioner",
        "petitioner_last": "Petitioner",
    }
    if key in special:
        return special[key]
    for item in PROBATE_SOURCE_FIELDS:
        if item.get("key") == key:
            return str(item.get("notes_label") or item.get("label") or key)
    return key


def combined_notes(row: dict, mapping: dict) -> str:
    values = probate_export_values(row, mapping)
    fields = mapping.get("custom_fields") or {}
    note_keys = {
        str(key)
        for key, api in fields.items()
        if _is_notes_target(str(api))
    }
    parts: list[str] = []
    seen: set[str] = set()

    def mapped(*keys: str) -> bool:
        return any(key in note_keys for key in keys)

    def name_line(label: str, first: str, last: str, full: str) -> str:
        first = str(first or "").strip()
        last = str(last or "").strip()
        if not first and not last and full:
            first, last = split_person_name(str(full))
        if first and last:
            return f"{label}: {first}, {last}"
        if first or last:
            return f"{label}: {first or last}"
        return ""

    if mapped("decedent", "decedent_first", "decedent_last"):
        line = name_line(
            "Decedent",
            values.get("decedent_first") or "",
            values.get("decedent_last") or "",
            values.get("decedent") or "",
        )
        if line:
            parts.append(line)
        seen.update({"decedent", "decedent_first", "decedent_last"})
    if mapped("petitioner", "petitioner_first", "petitioner_last"):
        line = name_line(
            "Petitioner",
            values.get("petitioner_first") or "",
            values.get("petitioner_last") or "",
            values.get("petitioner") or "",
        )
        if line:
            parts.append(line)
        seen.update({"petitioner", "petitioner_first", "petitioner_last"})
    for item in PROBATE_SOURCE_FIELDS:
        key = str(item.get("key") or "")
        if not key or key in seen or key not in note_keys:
            continue
        value = values.get(key)
        if value in (None, ""):
            continue
        parts.append(f"{_notes_field_label(key)}: {value}")
        seen.add(key)
    for key in note_keys:
        if key in seen:
            continue
        value = values.get(key)
        if value in (None, ""):
            continue
        parts.append(f"{_notes_field_label(key)}: {value}")
    portal = case_portal_url(row)
    if portal and not any(portal in part for part in parts):
        parts.append(f"Court: {portal}")
    letters = values.get("de150_url") or ""
    if letters and not any(letters in part for part in parts):
        parts.append(f"Letters: {letters}")
    return "\n".join(parts)


def list_fub_custom_fields(
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    key = (api_key or os.environ.get("FUB_API_KEY") or "").strip()
    url = api_url or os.environ.get("FUB_API_URL") or "https://api.followupboss.com/v1"
    if not key:
        return {"fields": [], "error": "No Follow Up Boss API key configured."}
    try:
        response = requests.get(
            f"{_api_root(url)}/customFields",
            auth=(key, ""),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if response.status_code >= 400:
            return {
                "fields": [],
                "error": f"FUB HTTP {response.status_code}: {response.text[:300]}",
            }
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return {"fields": [], "error": str(exc)[:300]}
    rows = payload
    if isinstance(payload, dict):
        rows = (
            payload.get("customfields")
            or payload.get("customFields")
            or payload.get("fields")
            or []
        )
    fields = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        fields.append(
            {
                "name": name,
                "label": str(item.get("label") or name),
                "type": str(item.get("type") or "text"),
                "choices": item.get("choices") or [],
            }
        )
    return {"fields": fields, "error": None}


def fub_custom_field_names() -> set[str]:
    catalog = list_fub_custom_fields()
    return {
        str(item.get("name") or "").strip()
        for item in (catalog.get("fields") or [])
        if str(item.get("name") or "").strip()
    }


def _can_send_custom_field(api_name: str, allowed: set[str] | None) -> bool:
    name = str(api_name or "").strip()
    if name.lower().startswith("person."):
        name = name.split(".", 1)[1]
    if not name:
        return False
    if (
        name in PERSON_BUILTIN_TARGETS
        or name.lower() in ADDRESS_SLOT_TARGETS
        or _is_notes_target(name)
    ):
        return True
    if allowed is None:
        return True
    if name in allowed:
        return True
    print(
        f"FUB omit {name} (not a custom field on this Follow Up Boss account)",
        flush=True,
    )
    return False


PERSON_CORE_KEYS = {
    "id",
    "created",
    "updated",
    "createdById",
    "createdBy",
    "lastActivity",
    "name",
    "firstName",
    "lastName",
    "stage",
    "source",
    "sourceUrl",
    "assignedTo",
    "assignedUserId",
    "assignedToId",
    "emails",
    "phones",
    "addresses",
    "tags",
    "background",
    "pictureId",
    "collaborators",
    "contacted",
    "price",
    "timeframe",
    "website",
    "timeZone",
}


def _fub_display_value(value) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                bits = [
                    str(item.get(key) or "")
                    for key in (
                        "value",
                        "email",
                        "number",
                        "phone",
                        "street",
                        "city",
                        "state",
                        "code",
                        "type",
                    )
                    if item.get(key)
                ]
                parts.append(" ".join(bits) if bits else json.dumps(item, default=str))
            else:
                parts.append(str(item))
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return str(value)


def inspect_fub_person(query: str) -> dict:
    key = (os.environ.get("FUB_API_KEY") or "").strip()
    url = os.environ.get("FUB_API_URL") or "https://api.followupboss.com/v1"
    text = (query or "").strip()
    if not key:
        return {"error": "No Follow Up Boss API key configured.", "person": None}
    if not text:
        return {"error": "Enter a FUB person id or a name to search.", "person": None}
    try:
        if text.isdigit():
            response = requests.get(
                f"{_api_root(url)}/people/{text}",
                auth=(key, ""),
                headers={"Accept": "application/json"},
                timeout=20,
            )
            payload = response.json() if response.content else {}
            if response.status_code >= 400:
                return {
                    "error": f"FUB HTTP {response.status_code}: {str(payload)[:300]}",
                    "person": None,
                }
            person = payload.get("person") if isinstance(payload.get("person"), dict) else payload
        else:
            response = requests.get(
                f"{_api_root(url)}/people",
                params={"query": text, "limit": 5},
                auth=(key, ""),
                headers={"Accept": "application/json"},
                timeout=20,
            )
            payload = response.json() if response.content else {}
            if response.status_code >= 400:
                return {
                    "error": f"FUB HTTP {response.status_code}: {str(payload)[:300]}",
                    "person": None,
                }
            rows = payload.get("people") if isinstance(payload, dict) else payload
            if not isinstance(rows, list) or not rows:
                return {"error": f"No people matched “{text}”.", "person": None}
            person = rows[0] if isinstance(rows[0], dict) else None
        if not isinstance(person, dict):
            return {"error": "Follow Up Boss returned no person object.", "person": None}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:300], "person": None}

    catalog = list_fub_custom_fields()
    custom_meta = {item["name"]: item for item in (catalog.get("fields") or [])}
    core = []
    for name in (
        "id",
        "firstName",
        "lastName",
        "name",
        "stage",
        "source",
        "assignedTo",
        "emails",
        "phones",
        "addresses",
        "tags",
        "created",
        "updated",
        "background",
    ):
        value = _fub_display_value(person.get(name))
        core.append({"name": name, "value": value, "populated": bool(value)})
    mailing_line = ""
    addresses = person.get("addresses") or []
    if isinstance(addresses, list) and len(addresses) > 1 and isinstance(addresses[1], dict):
        mailing_line = _fub_display_value(addresses[1])
    else:
        for item in addresses:
            if isinstance(item, dict) and str(item.get("type") or "").lower() in {
                "mailing",
                "investment",
                "decedent",
                "address 2",
                "address2",
            }:
                mailing_line = _fub_display_value(item)
                break
    core.append(
        {
            "name": "address2",
            "value": mailing_line,
            "populated": bool(mailing_line),
        }
    )
    notes_text = _fetch_person_notes(person.get("id")) or _fub_display_value(
        person.get("background")
    )
    core.append(
        {
            "name": "notes",
            "value": notes_text,
            "populated": bool(notes_text),
        }
    )
    custom = []
    for name, meta in custom_meta.items():
        value = _fub_display_value(person.get(name))
        custom.append(
            {
                "name": name,
                "label": meta.get("label") or name,
                "type": meta.get("type") or "",
                "value": value,
                "populated": bool(value),
            }
        )
    extras = []
    known = PERSON_CORE_KEYS | set(custom_meta)
    for name, raw in person.items():
        if name in known:
            continue
        value = _fub_display_value(raw)
        if not value:
            continue
        extras.append({"name": str(name), "value": value, "populated": True})
    populated_custom = sum(1 for item in custom if item["populated"])
    return {
        "error": None,
        "custom_error": catalog.get("error"),
        "person_id": person.get("id"),
        "query": text,
        "core": core,
        "custom_fields": custom,
        "extra_fields": extras,
        "custom_populated": populated_custom,
        "custom_total": len(custom),
    }


def _fetch_person_notes(person_id) -> str:
    key = (os.environ.get("FUB_API_KEY") or "").strip()
    url = os.environ.get("FUB_API_URL") or "https://api.followupboss.com/v1"
    if not key or person_id in (None, "", 0, "0"):
        return ""
    try:
        response = requests.get(
            f"{_api_root(url)}/notes",
            params={"personId": int(person_id), "limit": 10},
            auth=(key, ""),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        payload = response.json() if response.content else {}
        if response.status_code >= 400 or not isinstance(payload, dict):
            return ""
        rows = payload.get("notes")
        if not isinstance(rows, list):
            return ""
        parts = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            body = str(item.get("body") or "").strip()
            subject = str(item.get("subject") or "").strip()
            if subject and body:
                parts.append(f"{subject}: {body}")
            elif body:
                parts.append(body)
        return "\n---\n".join(parts)
    except Exception:
        return ""


def mapping_payload(
    path: Path | None = None,
    *,
    fetch_fub: bool = True,
    source_id: str = "placer",
    settings: dict | None = None,
) -> dict:
    mapping = load_mapping(path)
    live = list_fub_custom_fields() if fetch_fub else {"fields": [], "error": None}
    written = resolve_mapping_path(path)
    source_id = str(source_id or "placer")
    source_fields = {item["id"]: source_field_catalog(item["id"]) for item in DATA_SOURCES}
    required = fub_go_required_from_settings(settings) if settings is not None else resolve_fub_go_required_fields()
    return {
        "mapping": mapping,
        "path": str(written),
        "exists": written.exists(),
        "catalog": mapping_catalog(),
        "data_sources": DATA_SOURCES,
        "source_id": source_id,
        "source_fields": source_fields,
        "fub_go_required_fields": required,
        "fub_go_gate_fields": list(FUB_GO_GATE_FIELDS),
        "source_go_no_go": {
            item["id"]: go_no_go_for_source(item["id"], required) for item in DATA_SOURCES
        },
        "source_custom_fields": custom_fields_for_source(mapping, source_id),
        "fub_custom_fields": live.get("fields") or [],
        "fub_builtin_fields": FUB_BUILTIN_FIELDS,
        "fub_custom_error": live.get("error"),
    }


def split_person_name(name: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", (name or "").strip())
    text = text.replace('"', "").replace("'", "")
    text = _strip_ocr_name_junk(text)
    if not text or _is_caption_person_name(text):
        return "", ""
    if "," in text:
        last, _, rest = text.partition(",")
        first = rest.strip()
        if first and last.strip():
            first_out = _strip_ocr_name_junk(first.title())
            last_out = _strip_ocr_name_junk(last.strip().title())
            if _is_caption_name_part(first_out) or _is_caption_name_part(last_out):
                return "", ""
            return first_out, last_out
    parts = [part for part in text.split(" ") if part]
    while len(parts) >= 2 and re.fullmatch(
        r"\d+|\(\s*\d+\s*\)?", parts[-1].rstrip(".,[]")
    ):
        parts.pop()
    if parts:
        parts[-1] = re.sub(r"(?<=[A-Za-z.'-])\d{1,2}$", "", parts[-1])
        if not parts[-1]:
            parts.pop()
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "esq", "esq."}
    while parts and parts[0].rstrip(".").lower() in suffixes:
        parts.pop(0)
    if not parts:
        return "", ""
    blocked_last = {"case", "number", "dept", "department", "casenumber"}
    if len(parts) == 1:
        first, last = parts[0].title(), ""
    elif len(parts) >= 3 and parts[-1].rstrip(".").lower() in suffixes:
        first, last = " ".join(parts[:-2]).title(), " ".join(parts[-2:]).title()
    else:
        first, last = " ".join(parts[:-1]).title(), parts[-1].title()
    first = _strip_ocr_name_junk(first)
    last = _strip_ocr_name_junk(last)
    if last.rstrip(".").lower() in blocked_last:
        last = ""
    if _is_caption_name_part(first) or _is_caption_name_part(last):
        return "", ""
    return first, last


def portal_party_name(row: dict, role: str) -> str:
    want = (role or "").strip().lower()
    for party in row.get("parties") or []:
        text = str(party)
        if "—" in text:
            listed, _, name = text.partition("—")
        elif " - " in text:
            listed, _, name = text.partition(" - ")
        else:
            continue
        if listed.strip().lower() == want:
            return name.strip()
    return ""


def portal_petitioner(row: dict) -> str:
    for role in ("petitioner", "administrator", "personal representative"):
        name = _usable_person_name(portal_party_name(row, role))
        if name:
            return name
    for key in ("item2b_name", "attorney_for_name", "petitioner", "petitioner_name"):
        raw = str(row.get(key) or "")
        if key == "attorney_for_name" and _is_court_or_firm_caption_name(raw):
            continue
        name = _usable_person_name(raw)
        if name:
            return name
    return ""


def _usable_person_name(raw: str) -> str:
    name = _clean_person_name(raw)
    if not name or _is_court_or_firm_caption_name(name) or _is_caption_person_name(name):
        return ""
    first, last = split_person_name(name)
    if not first and not last:
        return ""
    return name


def _strip_county_noise(text: str) -> str:
    text = COUNTY_NOISE_RE.sub(",", text)
    text = re.sub(r"\s*,\s*,+", ",", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def _usable_city(city: str) -> str:
    try:
        from .petition_parse import _usable_city as parse_city
    except ImportError:
        from petition_parse import _usable_city as parse_city

    return parse_city(city)


def split_address(line: str) -> dict | None:
    try:
        from .petition_parse import split_de111_address, _state_code
    except ImportError:
        from petition_parse import split_de111_address, _state_code

    parsed = split_de111_address(line)
    if parsed:
        return {
            "street": parsed["street"],
            "city": parsed["city"],
            "state": parsed["state"],
            "code": parsed.get("zip") or "",
        }
    text = _strip_county_noise(re.sub(r"\s+", " ", (line or "").strip()))
    if not text:
        return None
    match = ADDR_RE.match(text) or ADDR_FLEX_RE.match(text)
    if not match:
        return {"street": text}
    return {
        "street": match.group("street").strip(" ,"),
        "city": _usable_city(match.group("city")),
        "state": _state_code(match.group("state")),
        "code": (match.group("zip") or "").strip(),
    }


def _fub_address(
    line: str,
    addr_type: str,
    *,
    city: str = "",
    state: str = "",
    code: str = "",
) -> dict | None:
    parsed = split_address(line) or {}
    street = str(parsed.get("street") or line or "").strip(" ,")
    city = _usable_city(parsed.get("city") or "") or _usable_city(city)
    state = str(parsed.get("state") or state or "").strip().upper()
    zip_code = str(parsed.get("code") or code or "").strip()
    if city and street.lower().endswith(city.lower()):
        street = street[: -len(city)].strip(" ,")
    if not street or _is_junk_mailing_street(street):
        return None
    addr = {
        "street": street,
        "type": addr_type,
        "country": "United States",
    }
    if city:
        addr["city"] = city
    if state:
        addr["state"] = state
    if zip_code:
        addr["code"] = zip_code
    return addr


def _format_fub_address(addr) -> str:
    if not isinstance(addr, dict):
        return ""
    bits = [
        f"address={addr.get('street') or ''}",
        "line2=",
        f"city={addr.get('city') or ''}",
        f"state={addr.get('state') or ''}",
        f"zip={addr.get('code') or ''}",
        f"type={addr.get('type') or ''}",
    ]
    return "; ".join(bits)


def _address_parts_from_source(local_key: str, values: dict) -> tuple[str, str, str]:
    if local_key in {
        "mailing_address",
        "mailing_city",
        "mailing_state",
        "mailing_zip",
    }:
        return (
            _usable_city(str(values.get("mailing_city") or "")),
            str(values.get("mailing_state") or "").strip(),
            str(values.get("mailing_zip") or "").strip(),
        )
    if local_key in {
        "decedent_residence",
        "decedent_city",
        "decedent_zip",
        "decedent",
    }:
        return (
            _usable_city(str(values.get("decedent_city") or "")),
            str(values.get("decedent_state") or "").strip(),
            str(values.get("decedent_zip") or "").strip(),
        )
    return "", "", ""


def _set_address_slot(
    person: dict,
    line: str,
    index: int,
    addr_type: str,
    *,
    city: str = "",
    state: str = "",
    code: str = "",
) -> None:
    addr = _fub_address(line, addr_type, city=city, state=state, code=code)
    if not addr:
        return
    slots = person.setdefault("_addr_slots", {})
    slots[max(0, int(index))] = addr
    person["addresses"] = [slots[i] for i in sorted(slots)]


def _flush_address_slots(person: dict) -> None:
    slots = person.pop("_addr_slots", None)
    if slots:
        person["addresses"] = [slots[i] for i in sorted(slots)]


def case_key(row: dict) -> str:
    return str(row.get("case_number") or row.get("advert_id") or "").strip()


PLACEHOLDER_CASE_RE = re.compile(r"(?i)^notices_\d+$")


def is_placeholder_case_id(value: str | None) -> bool:
    """True when there is no court case number (blank or Notices_* style)."""
    text = str(value or "").strip()
    if not text:
        return True
    return bool(PLACEHOLDER_CASE_RE.match(text))


def court_case_number(row: dict) -> str:
    raw = str((row or {}).get("case_number") or "").strip()
    if not raw or is_placeholder_case_id(raw):
        return ""
    return raw


def _row_decedent_name(row: dict) -> str:
    for raw in (
        str(row.get("decedent") or "").strip(),
        portal_party_name(row, "decedent"),
        str(row.get("decedent_name") or "").strip(),
    ):
        name = _stored_person_name(raw)
        if not name:
            continue
        first, last = split_person_name(name)
        if first or last:
            return name
    return ""


def _row_decedent_address(row: dict) -> str:
    return str(
        row.get("decedent_residence") or row.get("decedent_address") or ""
    ).strip()


def _row_mailing_address(row: dict) -> str:
    line = str(
        _row_contact(row).get("mailing_address")
        or row.get("mailing_address")
        or row.get("petitioner_address")
        or ""
    ).strip()
    if not line or _is_junk_mailing_street(line):
        return ""
    return line


def _row_petitioner_phone(row: dict) -> str:
    return str(
        _row_contact(row).get("petitioner_phone")
        or row.get("petitioner_phone")
        or ""
    ).strip()


def _petitioner_name_parts(row: dict) -> tuple[str, str, str]:
    petitioner = portal_petitioner(row)
    first, last = split_person_name(petitioner)
    if not first:
        extra_first, extra_last = split_person_name(str(row.get("petitioner_first") or ""))
        first = extra_first
        if extra_last and not last:
            last = extra_last
    if not last:
        extra_first, extra_last = split_person_name(str(row.get("petitioner_last") or ""))
        last = extra_last
        if extra_first and not first:
            first = extra_first
    if _is_caption_name_part(first) or _is_caption_name_part(last):
        return "", "", ""
    return petitioner, first, last


def _estate_real_amount(row: dict) -> float | None:
    try:
        from .petition_parse import parse_money_amount
    except ImportError:
        from petition_parse import parse_money_amount

    amount = parse_money_amount((row or {}).get("estate_real"))
    if _is_placeholder_estate_real(amount):
        return None
    return amount


def _path_b_eligible(row: dict) -> bool:
    return not court_case_number(row)


def _path_a_reason(row: dict, required: set[str], existing_id: int | None) -> str | None:
    _petitioner, first, last = _petitioner_name_parts(row)
    if "petitioner_first" in required or "petitioner_last" in required:
        missing_first = "petitioner_first" in required and not first
        missing_last = "petitioner_last" in required and not last
        if missing_first or missing_last:
            return "petitioner_name_incomplete"
    source = str(
        row.get("source_id") or os.environ.get("FUB_DATA_SOURCE") or "placer"
    ).strip().lower()
    if (
        "mailing_address" in required
        and source in {"placer", "sacramento"}
        and not _row_mailing_address(row)
    ):
        return "missing_petitioner_address"
    if (
        "decedent_residence" in required
        and existing_id is None
        and not _row_decedent_address(row)
    ):
        return "missing_decedent_residence"
    return None


def _path_b_reason(row: dict) -> str | None:
    petitioner, first, last = _petitioner_name_parts(row)
    if not ((first and last) or petitioner):
        return "petitioner_name_incomplete"
    if not _row_decedent_name(row):
        return "missing_decedent"
    if not _row_decedent_address(row):
        return "missing_decedent_residence"
    if not _row_petitioner_phone(row):
        return "missing_petitioner_phone"
    return None


def petition_safe_case(case: str) -> str:
    return re.sub(r"[^\w\-]+", "_", str(case or "").strip()) or "case"


def petition_file_token(
    case: str,
    secret: str | None = None,
    *,
    kind: str = "de111",
    exp: int | None = None,
) -> str:
    raw = (secret or os.environ.get("FUB_PETITION_TOKEN_SECRET") or "placer-probate")
    payload = f"{kind}:{petition_safe_case(case)}"
    if exp is not None:
        payload = f"{payload}:{int(exp)}"
    return hmac.new(
        str(raw).encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


LISTINGS_SHARE_CASE = "public"
LISTINGS_SHARE_KIND = "listings"
LISTINGS_SHARE_PATH = "/api/placer_probate_monitor/listings/public"


def listings_share_token(secret: str | None = None, *, exp: int | None = None) -> str:
    return petition_file_token(
        LISTINGS_SHARE_CASE, secret=secret, kind=LISTINGS_SHARE_KIND, exp=exp
    )


def listings_share_status(
    token: str | None,
    secret: str | None = None,
    *,
    exp: str | int | None = None,
    now: int | None = None,
) -> str | None:
    """Return None when the HMAC is valid; otherwise missing, invalid, or expired."""
    import time

    given = str(token or "").strip()
    if not given:
        return "missing"
    exp_value = None
    if exp not in (None, ""):
        try:
            exp_value = int(exp)
        except (TypeError, ValueError):
            return "invalid"
    expected = listings_share_token(secret, exp=exp_value)
    if len(given) != len(expected) or not hmac.compare_digest(given, expected):
        return "invalid"
    if exp_value is not None:
        clock = int(now if now is not None else time.time())
        if exp_value < clock:
            return "expired"
    return None


def listings_share_http_error(status: str) -> tuple[dict, int]:
    if status == "missing":
        return {"error": "unauthorized", "message": "Missing share token."}, 401
    if status == "expired":
        return {"error": "expired", "message": "Share link expired."}, 403
    return {"error": "forbidden", "message": "Invalid share token."}, 403


def listings_share_payload(base: str, secret: str | None = None) -> dict:
    token = listings_share_token(secret)
    query = f"token={token}"
    root = str(base or "").rstrip("/")
    return {
        "share_path": LISTINGS_SHARE_PATH,
        "share_token": token,
        "share_url": f"{root}{LISTINGS_SHARE_PATH}?{query}" if root else "",
    }


def form_api_uri(case: str, kind: str = "de111") -> str:
    """Relative Home Assistant API path for a stored petition PDF."""
    slug = str(kind or "de111").strip().lower() or "de111"
    if slug not in {"de111", "de147", "de150"}:
        slug = "de111"
    safe = petition_safe_case(case)
    if not safe or safe == "case":
        return ""
    return f"/api/placer_probate_monitor/{slug}/{petition_file_token(case, kind=slug)}/{safe}.pdf"


def petition_public_uri(case: str) -> str:
    return form_public_uri(case, "de111")


def duties_public_uri(case: str) -> str:
    return form_public_uri(case, "de147")


def letters_public_uri(case: str) -> str:
    return form_public_uri(case, "de150")


def form_public_uri(case: str, kind: str) -> str:
    if kind == "de147":
        base = str(os.environ.get("FUB_DUTIES_BASE_URL") or "").rstrip("/")
    elif kind == "de150":
        base = str(os.environ.get("FUB_LETTERS_BASE_URL") or "").rstrip("/")
    else:
        base = str(os.environ.get("FUB_PETITION_BASE_URL") or "").rstrip("/")
    if not base:
        return ""
    safe = petition_safe_case(case)
    return f"{base}/{petition_file_token(case, kind=kind)}/{safe}.pdf"


def _petition_docs_search_dirs(row: dict | None = None) -> list[Path]:
    source = _row_source_id(row)
    primary = petition_docs_dir(source)
    other = petition_docs_dir("placer" if source == "sacramento" else "sacramento")
    seen: list[Path] = []
    for docs in (primary, other):
        if docs not in seen:
            seen.append(docs)
    return seen


def _petition_pdf_path(row: dict) -> Path | None:
    raw = str(row.get("petition_pdf") or "").strip()
    if raw:
        path = Path(raw)
        if path.is_file() and path.stat().st_size > 4:
            return path
    case = petition_safe_case(case_key(row))
    if not case:
        return None
    for docs in _petition_docs_search_dirs(row):
        if not docs.is_dir():
            continue
        folder = docs / case
        named = folder / f"{case}_DE-111.pdf"
        if named.is_file():
            return named
        if folder.is_dir():
            for path in sorted(folder.glob("*_petition.pdf")):
                if path.is_file():
                    return path
            for path in sorted(folder.glob("*.pdf")):
                upper = path.name.upper()
                if (
                    path.is_file()
                    and "_DE-147" not in upper
                    and "_DE-150" not in upper
                    and "_DE-160" not in upper
                    and "_DE-161" not in upper
                ):
                    return path
    return None


def _duties_pdf_path(row: dict) -> Path | None:
    raw = str(row.get("duties_pdf") or "").strip()
    if raw:
        path = Path(raw)
        if path.is_file() and path.stat().st_size > 4:
            return path
    case = petition_safe_case(case_key(row))
    if not case:
        return None
    for docs in _petition_docs_search_dirs(row):
        named = docs / case / f"{case}_DE-147.pdf"
        if named.is_file():
            return named
    return None


def _letters_pdf_path(row: dict) -> Path | None:
    raw = str(row.get("letters_pdf") or "").strip()
    if raw:
        path = Path(raw)
        if path.is_file() and path.stat().st_size > 4:
            return path
    case = petition_safe_case(case_key(row))
    if not case:
        return None
    for docs in _petition_docs_search_dirs(row):
        named = docs / case / f"{case}_DE-150.pdf"
        if named.is_file():
            return named
    return None


def _parse_fub_person_id(raw) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def stored_person_id(
    state: dict, key: str | None, row: dict | None = None
) -> int | None:
    record = (state.get("cases") or {}).get(key) or {} if key else {}
    pid = _parse_fub_person_id(record.get("fub_person_id"))
    if pid is not None:
        return pid
    if row:
        return _parse_fub_person_id(row.get("fub_person_id"))
    return None


def is_fub_removed(state: dict, key: str | None, row: dict | None = None) -> bool:
    record = (state.get("cases") or {}).get(key) or {} if key else {}
    if bool(record.get("fub_removed")):
        return True
    return bool(row and row.get("fub_removed"))


def needs_fub_create(
    state: dict, key: str | None, row: dict | None = None
) -> bool:
    """True when this listing has no Follow Up Boss person id.

    CNPA/email SEEN in seen_cases*.json is not a substitute. Recreate is
    skipped only when the person was deleted in Follow Up Boss (fub_removed).
    A listings.json / row fub_person_id also counts as already created.
    """
    if is_fub_removed(state, key, row):
        return False
    return stored_person_id(state, key, row) is None


def should_skip_unchanged_person(
    *,
    existing_id: int | None,
    record: dict,
    fingerprint: str,
    verify: bool,
    update_existing: bool,
) -> bool:
    """Skip PUT when this listing already has a FUB person and fields are unchanged.

    Harvest still updates the existing person when the payload fingerprint
    changes (new address, phone, decedent residence, etc.). Force, verify, and
    FUB_UPDATE_EXISTING always PUT. Listings with no person id POST/create.
    """
    if existing_id is None:
        return False
    if verify or update_existing:
        return False
    return bool(record.get("fub_fingerprint") == fingerprint)


def _one_person_verify_run(*, verify: bool, update_existing: bool) -> bool:
    """Verify-only stops after one POST/PUT unless Force PUT is on."""
    return bool(verify) and not bool(update_existing)


def _rows_for_export(rows: list[dict], state: dict, *, verify: bool) -> list[dict]:
    if not verify:
        return list(rows)
    last = str(state.get("last_fub_verify_case") or "").strip()
    preferred: list[dict] = []
    existing: list[dict] = []
    fresh: list[dict] = []
    for row in rows:
        key = case_key(row)
        pid = stored_person_id(state, key) if key else None
        if last and key == last and pid is not None:
            preferred.append(row)
        elif pid is not None:
            existing.append(row)
        else:
            fresh.append(row)
    # Verify-only should try a create first (UI: one new go-case), not PUT an existing id.
    return preferred + fresh + existing


def _forced_verify_person_id() -> int | None:
    if not _env_bool("FUB_VERIFY_EXISTING"):
        return None
    raw = str(os.environ.get("FUB_VERIFY_PERSON_ID") or "").strip()
    if not raw.isdigit():
        return None
    pid = int(raw)
    return pid if pid > 0 else None


def is_new_row(row: dict) -> bool:
    return bool(row.get("first_seen") or str(row.get("status") or "").lower() == "new")


def _row_is_fiduciary_petitioner(row: dict) -> bool:
    """Skip GO/FUB when the petitioner (not the attached will) is a fiduciary."""
    try:
        from .petition_parse import (
            is_fiduciary_petitioner_name,
            row_indicates_professional_fiduciary,
            stamp_row_professional_fiduciary,
        )
    except ImportError:
        from petition_parse import (
            is_fiduciary_petitioner_name,
            row_indicates_professional_fiduciary,
            stamp_row_professional_fiduciary,
        )

    stamp_row_professional_fiduciary(row)
    if row_indicates_professional_fiduciary(row):
        return True
    return is_fiduciary_petitioner_name(portal_petitioner(row))


def gate_reason(
    row: dict,
    state: dict,
    mapping: dict,
    *,
    strict_property: bool,
    existing_id: int | None,
    allow_seen_without_fub: bool = True,
    required_fields=None,
) -> str | None:
    """Data-quality gate only.

    Presence in seen_cases / seen_cases_sacramento without a Follow Up Boss
    person id is not a skip. Callers must POST/create those listings.
    ``allow_seen_without_fub`` is kept for callers and always treated as true.
    Required fields come from the saved Follow Up Boss “Required for Go” list
    for Path A. Path B is always an alternate: petitioner, decedent, decedent
    address, and petitioner phone. Case number is never required.
    """
    del allow_seen_without_fub
    required = set(
        resolve_fub_go_required_fields(
            required_fields, strict_property=strict_property
        )
    )
    required.discard("case_number")
    key = case_key(row)
    if is_fub_removed(state, key, row):
        return "fub_removed"
    petitioner, _first, _last = _petitioner_name_parts(row)
    if _row_is_fiduciary_petitioner(row):
        return "professional_fiduciary"
    real_gmv = _estate_real_amount(row)
    if real_gmv is None:
        return NOGO_MISSING_ESTATE_REAL
    if real_gmv < MIN_ESTATE_REAL_GMV:
        return NOGO_ESTATE_REAL_BELOW_MIN
    skip_bits = [str(x).lower() for x in mapping.get("skip_petitioner_contains") or []]
    low = petitioner.lower()
    if any(bit in low for bit in skip_bits if bit):
        return "petitioner_skipped"
    path_a = _path_a_reason(row, required, existing_id)
    if path_a is None:
        return None
    path_b = _path_b_reason(row)
    if path_b is None:
        return None
    return path_a


GO_STATUS_GO = "GO"
GO_STATUS_NOGO = "NO-GO"


def listing_as_harvest_row(listing: dict | None) -> dict:
    """Map a listings.json record onto harvest-row keys for gate_reason."""
    rec = dict(listing or {})
    if rec.get("petitioner_address") and not rec.get("mailing_address"):
        rec["mailing_address"] = rec.get("petitioner_address")
    if rec.get("decedent_address") and not rec.get("decedent_residence"):
        rec["decedent_residence"] = rec.get("decedent_address")
    return rec


def _listings_catalog(data_dir: Path) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for name in ("listings.json", "listings_sacramento.json"):
        path = Path(data_dir) / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = payload.get("listings") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("case_number") or "").strip()
            if not key:
                continue
            prev = catalog.get(key) or {}
            merged = dict(prev)
            merged.update({k: v for k, v in item.items() if v not in (None, "", [], {})})
            if prev.get("fub_removed") or item.get("fub_removed"):
                merged["fub_removed"] = True
            catalog[key] = merged
    return catalog


def _seen_fub_records(data_dir: Path) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for name in ("seen_cases.json", "seen_cases_sacramento.json"):
        path = Path(data_dir) / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        cases = payload.get("cases") if isinstance(payload, dict) else None
        if not isinstance(cases, dict):
            continue
        for key, rec in cases.items():
            case = str(key or "").strip()
            if not case or not isinstance(rec, dict):
                continue
            prev = index.get(case) or {}
            merged = dict(prev)
            merged.update({k: v for k, v in rec.items() if v not in (None, "", [], {})})
            if prev.get("fub_removed") or rec.get("fub_removed"):
                merged["fub_removed"] = True
            if prev.get("fub_person_id") and not merged.get("fub_person_id"):
                merged["fub_person_id"] = prev.get("fub_person_id")
            index[case] = merged
    return index


def persist_fub_removed_on_listings(data_dir: Path | None, cases: dict | None) -> None:
    """Keep deleted Follow Up Boss people marked on stored listings."""
    if data_dir is None:
        return
    removed = {
        str(key).strip(): rec
        for key, rec in (cases or {}).items()
        if str(key or "").strip() and isinstance(rec, dict) and rec.get("fub_removed")
    }
    if not removed:
        return
    for name in ("listings.json", "listings_sacramento.json"):
        path = Path(data_dir) / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = payload.get("listings") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        changed = False
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("case_number") or "").strip()
            rec = removed.get(key)
            if rec is None:
                continue
            if not item.get("fub_removed"):
                changed = True
            item["fub_removed"] = True
            item["go_status"] = "NO-GO"
            item["nogo_reason"] = "fub_removed"
            pid = rec.get("fub_person_id")
            if pid not in (None, "", 0, "0") and not item.get("fub_person_id"):
                item["fub_person_id"] = pid
                changed = True
        if not changed:
            continue
        if isinstance(payload, dict):
            payload["listings"] = items
            text = json.dumps(payload, indent=2, default=str)
        else:
            text = json.dumps(items, indent=2, default=str)
        path.write_text(text, encoding="utf-8")


def stored_rows_for_fub_one(
    data_dir: Path,
    source_id: str | None = None,
    person_id: int | str | None = None,
) -> list[dict]:
    """Harvest-shaped rows from stored listings.json, plus on-disk PDF paths."""
    try:
        from .datasources import local_de111_pdf, local_de147_pdf
    except ImportError:
        from datasources import local_de111_pdf, local_de147_pdf

    wanted = str(source_id or "").strip().lower()
    wanted_pid = _parse_fub_person_id(person_id)
    catalog = _listings_catalog(data_dir)
    seen = _seen_fub_records(data_dir)
    reports = Path(data_dir) / "reports"
    docs_dirs = (
        reports / "docs",
        reports / "sacramento" / "docs",
    )
    rows: list[dict] = []
    for listing in catalog.values():
        rec = listing_as_harvest_row(listing)
        case = str(rec.get("case_number") or "").strip()
        flags = seen.get(case) or {}
        if flags.get("fub_removed") or rec.get("fub_removed"):
            rec["fub_removed"] = True
        if flags.get("fub_person_id") and not rec.get("fub_person_id"):
            rec["fub_person_id"] = flags.get("fub_person_id")
        sid = str(rec.get("source_id") or "").strip().lower()
        if wanted and sid and sid != wanted:
            continue
        if wanted_pid is not None and _parse_fub_person_id(rec.get("fub_person_id")) != wanted_pid:
            continue
        for docs in docs_dirs:
            if rec.get("petition_pdf") and rec.get("duties_pdf"):
                break
            if docs.exists() and case:
                de111 = local_de111_pdf(docs, case)
                if de111 and not rec.get("petition_pdf"):
                    rec["petition_pdf"] = str(de111)
                de147 = local_de147_pdf(docs, case)
                if de147 and not rec.get("duties_pdf"):
                    rec["duties_pdf"] = str(de147)
        rows.append(rec)
    if wanted_pid is not None and not rows:
        for name, default_source in (
            ("seen_cases.json", "placer"),
            ("seen_cases_sacramento.json", "sacramento"),
        ):
            path = Path(data_dir) / name
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            cases = payload.get("cases") if isinstance(payload, dict) else None
            if not isinstance(cases, dict):
                continue
            for case, record in cases.items():
                if not isinstance(record, dict):
                    continue
                if _parse_fub_person_id(record.get("fub_person_id")) != wanted_pid:
                    continue
                listing = catalog.get(str(case)) or {
                    "case_number": case,
                    "source_id": default_source,
                    "fub_person_id": wanted_pid,
                }
                rec = listing_as_harvest_row(listing)
                rec["fub_person_id"] = wanted_pid
                rec.setdefault("source_id", default_source)
                rows.append(rec)
    rows.sort(
        key=lambda row: str(
            row.get("last_collected") or row.get("added_at") or row.get("date") or ""
        ),
        reverse=True,
    )
    return rows


def listing_go_fields(
    row: dict | None,
    *,
    state: dict | None = None,
    mapping: dict | None = None,
    required_fields=None,
    strict_property: bool | None = None,
) -> tuple[str, str]:
    """Return (go_status, nogo_reason) for a harvest or listing row.

    GO rows use nogo_reason path_a / path_b. NO-GO rows use the gate reason.
    Does not call Follow Up Boss.
    """
    harvest = listing_as_harvest_row(row)
    source_id = _row_source_id(harvest)
    if mapping is None:
        mapping = mapping_for_export(load_mapping(), source_id)
    else:
        mapping = mapping_for_export(mapping, source_id)
    key = case_key(harvest)
    gate_state = {"cases": {}}
    if state and isinstance(state.get("cases"), dict):
        gate_state = state
    elif harvest.get("fub_removed") and key:
        gate_state = {"cases": {key: {"fub_removed": True}}}
    if strict_property is None:
        strict_property = _env_bool("FUB_STRICT_PROPERTY")
    required = set(
        resolve_fub_go_required_fields(
            required_fields, strict_property=strict_property
        )
    )
    required.discard("case_number")
    existing_id = stored_person_id(gate_state, key, harvest)
    reason = gate_reason(
        harvest,
        gate_state,
        mapping,
        strict_property=strict_property,
        existing_id=existing_id,
        required_fields=required_fields,
    )
    if reason:
        return GO_STATUS_NOGO, reason
    path_a = _path_a_reason(harvest, required, existing_id)
    if path_a is None:
        return GO_STATUS_GO, "path_a"
    return GO_STATUS_GO, "path_b"


def apply_listing_go(
    row: dict,
    *,
    state: dict | None = None,
    mapping: dict | None = None,
    required_fields=None,
    strict_property: bool | None = None,
) -> dict:
    status, reason = listing_go_fields(
        row,
        state=state,
        mapping=mapping,
        required_fields=required_fields,
        strict_property=strict_property,
    )
    row["go_status"] = status
    row["nogo_reason"] = reason
    return row


def listing_go_reason_label(reason: str | None) -> str:
    raw = str(reason or "").strip()
    if raw == "path_a":
        return "Path A"
    if raw == "path_b":
        return "Path B"
    if raw == NOGO_MISSING_ESTATE_REAL:
        return "Real property GMV missing"
    if raw == NOGO_ESTATE_REAL_BELOW_MIN:
        return "Real property GMV under $200,000"
    return raw


def preview_one_record(
    rows: list[dict],
    *,
    mapping_path: Path | None = None,
    person_id: int | str | None = None,
) -> dict:
    wanted = _parse_fub_person_id(person_id)
    work = [listing_as_harvest_row(item) for item in rows]
    if wanted is not None:
        work = [
            row
            for row in work
            if _parse_fub_person_id(row.get("fub_person_id")) == wanted
        ]
        if not work:
            note = f"No stored listing has Follow Up Boss person {wanted}."
            print(f"FUB preview: {note}", flush=True)
            return {
                "ok": False,
                "verify_record": None,
                "verify_note": note,
                "skips": [],
            }
        row = work[0]
        source_id = _row_source_id(row)
        mapping = mapping_for_export(load_mapping(mapping_path), source_id)
        settings = {
            "source": mapping.get("lead_source") or os.environ.get("FUB_SOURCE", "probate"),
            "assigned_to": os.environ.get("FUB_ASSIGNED_TO", "Blake Hammond"),
            "stage": (os.environ.get("FUB_STAGE") or "").strip(),
            "event_type": os.environ.get("FUB_EVENT_TYPE", "Seller Inquiry"),
        }
        strict = _env_bool("FUB_STRICT_PROPERTY")
        reason = gate_reason(
            row,
            {"cases": {}},
            mapping,
            strict_property=strict,
            existing_id=wanted,
        )
        person = build_person(
            row,
            mapping,
            settings,
            person_id=wanted,
            allowed_custom=fub_custom_field_names(),
        )
        record = verify_record_payload(row, person, wanted, settings, mapping)
        record["view_only"] = True
        record["posted"] = False
        record["gate"] = "no-go" if reason else "go"
        if reason:
            record["gate_reason"] = reason
        print(
            f"FUB preview: {case_key(row)} person_id={wanted} "
            f"(view only, not posted)",
            flush=True,
        )
        return {
            "ok": True,
            "verify_record": record,
            "verify_note": None,
            "skips": [{"case": case_key(row), "reason": reason}] if reason else [],
        }
    source_id = _row_source_id(work[0] if work else None)
    mapping = mapping_for_export(load_mapping(mapping_path), source_id)
    settings = {
        "source": mapping.get("lead_source") or os.environ.get("FUB_SOURCE", "probate"),
        "assigned_to": os.environ.get("FUB_ASSIGNED_TO", "Blake Hammond"),
        "stage": (os.environ.get("FUB_STAGE") or "").strip(),
        "event_type": os.environ.get("FUB_EVENT_TYPE", "Seller Inquiry"),
    }
    strict = _env_bool("FUB_STRICT_PROPERTY")
    skips: list[dict] = []
    blank_state: dict = {"cases": {}}
    first_skip_record = None
    for row in work:
        key = case_key(row)
        reason = gate_reason(
            row,
            blank_state,
            mapping,
            strict_property=strict,
            existing_id=None,
        )
        if reason:
            print(
                f"FUB skip {key}: {reason} "
                f"mailing={row.get('mailing_address') or '(empty)'} "
                f"residence={row.get('decedent_residence') or '(empty)'} "
                f"pdf={Path(str(row.get('petition_pdf') or '')).name or 'none'}",
                flush=True,
            )
            skips.append({"case": key, "reason": reason})
            if first_skip_record is None:
                person = build_person(
                    row,
                    mapping,
                    settings,
                    person_id=None,
                    allowed_custom=fub_custom_field_names(),
                )
                record = verify_record_payload(row, person, None, settings, mapping)
                record["view_only"] = True
                record["posted"] = False
                record["gate"] = "no-go"
                record["gate_reason"] = reason
                record["skips"] = skips
                first_skip_record = record
            continue
        person = build_person(
            row,
            mapping,
            settings,
            person_id=None,
            allowed_custom=fub_custom_field_names(),
        )
        record = verify_record_payload(row, person, None, settings, mapping)
        record["view_only"] = True
        record["posted"] = False
        record["gate"] = "go"
        record["skips"] = skips
        print(f"FUB preview: {key} (view only, not posted)", flush=True)
        return {
            "ok": True,
            "verify_record": record,
            "verify_note": None,
            "skips": skips,
        }
    note = "No go-case in this window"
    if skips:
        sample = ", ".join(
            f"{item.get('case') or '?'}={item.get('reason')}" for item in skips[:5]
        )
        note = f"{note}. Skips: {sample}"
    print(f"FUB preview: {note}", flush=True)
    return {
        "ok": False,
        "verify_record": first_skip_record,
        "verify_note": note,
        "skips": skips,
    }


def score_stored_rows(
    rows: list[dict],
    *,
    mapping_path: Path | None = None,
) -> dict:
    """Apply the current Go checklist to already-parsed local rows. No FUB POST."""
    mapping = mapping_for_export(
        load_mapping(mapping_path),
        _row_source_id(rows[0] if rows else None),
    )
    strict = _env_bool("FUB_STRICT_PROPERTY")
    blank_state: dict = {"cases": {}}
    cases: list[dict] = []
    skips: list[dict] = []
    go = 0
    nogo = 0
    for row in rows:
        key = case_key(row)
        reason = gate_reason(
            row,
            blank_state,
            mapping,
            strict_property=strict,
            existing_id=None,
        )
        if reason:
            nogo += 1
            skips.append({"case": key, "reason": reason})
            gate = "no-go"
        else:
            go += 1
            gate = "go"
        cases.append(
            {
                "case": key,
                "gate": gate,
                "reason": reason or "",
                "petitioner": portal_petitioner(row) or row.get("petitioner") or "",
                "decedent": row.get("decedent") or "",
                "mailing_address": row.get("mailing_address") or "",
                "decedent_residence": row.get("decedent_residence") or "",
                "petition_pdf": Path(str(row.get("petition_pdf") or "")).name,
                "duties_pdf": Path(str(row.get("duties_pdf") or "")).name,
            }
        )
        print(
            f"Stored test {key}: {gate}"
            + (f" ({reason})" if reason else ""),
            flush=True,
        )
    note = (
        f"Stored test: {go} GO / {nogo} no-go using the current Required for Go list. "
        "Follow Up Boss was not updated. Seen-cases were not updated. No CNPA or court."
    )
    return {
        "ok": True,
        "posted": 0,
        "updated": 0,
        "skipped": nogo,
        "error": None,
        "stored_test": True,
        "preview": False,
        "go_count": go,
        "nogo_count": nogo,
        "cases": cases,
        "skips": skips,
        "verify_note": note,
        "verify_record": None,
    }


def _row_source_id(row: dict | None = None) -> str:
    return (
        str(
            (row or {}).get("source_id")
            or os.environ.get("FUB_DATA_SOURCE")
            or "placer"
        )
        .strip()
        .lower()
        or "placer"
    )


def _fub_lead_source_name(row: dict | None = None, source_id: str | None = None) -> str:
    key = str(source_id or "").strip().lower() or _row_source_id(row)
    try:
        return fub_lead_source(key)
    except ValueError:
        return str((row or {}).get("lead_source") or "").strip()


def _court_search_note(row: dict, mapping: dict) -> str:
    portal = case_portal_url(row)
    if portal:
        return portal
    url = mapping.get("court_search_url") or COURT_SEARCH_DEFAULT
    case = case_key(row)
    return f"{url} (paste {case} if the case page is missing)"


def build_person(
    row: dict,
    mapping: dict,
    settings: dict,
    *,
    person_id: int | None = None,
    allowed_custom: set[str] | None = None,
) -> dict:
    send = mapping.get("send") or {}
    petitioner = portal_petitioner(row)
    first, last = split_person_name(petitioner)
    person: dict = {}
    if person_id is not None:
        person["id"] = int(person_id)
    if send.get("firstName", True) and first:
        person["firstName"] = first
    if send.get("lastName", True) and last:
        person["lastName"] = last
    if send.get("assignedTo", True) and settings.get("assigned_to"):
        person["assignedTo"] = settings["assigned_to"]
    if send.get("stage", True) and settings.get("stage"):
        person["stage"] = str(settings["stage"]).strip()
    values = probate_export_values(row, mapping)
    if send.get("emails", True):
        email = str(values.get("petitioner_email") or "").strip()
        if email:
            person["emails"] = [{"value": email, "type": "home"}]
    if send.get("phones", True):
        phone = str(values.get("petitioner_phone") or "").strip()
        if phone:
            person["phones"] = [{"value": phone, "type": "home"}]
    if send.get("custom_fields", True):
        fields = mapping.get("custom_fields") or {}
        for local_key, api_name in fields.items():
            value = values.get(local_key)
            if not api_name or value in (None, ""):
                continue
            target = str(api_name).strip()
            if target.startswith("person."):
                target = target.split(".", 1)[1]
            if target in {"emails", "person.emails"}:
                if local_key == "attorney_phone":
                    continue
                person["emails"] = [{"value": str(value), "type": "home"}]
                continue
            if target in {"phones", "person.phones"}:
                if local_key == "attorney_phone":
                    continue
                person["phones"] = [{"value": str(value), "type": "home"}]
                continue
            if _is_notes_target(target):
                continue
            if local_key in ADDRESS_COMPONENT_KEYS and (
                target.lower() in ADDRESS_SLOT_TARGETS
            ):
                continue
            city, state, code = _address_parts_from_source(local_key, values)
            if target.lower() in ADDRESS_SLOT_TARGETS:
                slot = ADDRESS_SLOT_TARGETS[target.lower()]
                _set_address_slot(
                    person,
                    str(value),
                    slot,
                    ADDRESS2_TYPE if slot >= 1 else ADDRESS1_TYPE,
                    city=city,
                    state=state,
                    code=code,
                )
                continue
            if target == "tags":
                person["tags"] = [str(value)]
                continue
            if target in PERSON_BUILTIN_TARGETS:
                person[target] = str(value)
                continue
            if not _can_send_custom_field(api_name, allowed_custom):
                continue
            person[str(api_name)] = str(value)
    notes = combined_notes(row, mapping)
    if notes:
        person["background"] = notes
    _flush_address_slots(person)
    county_tags = row.get("tags")
    if not county_tags:
        source = _row_source_id(row)
        try:
            from .datasources import fub_tags
        except ImportError:
            from datasources import fub_tags

        try:
            county_tags = fub_tags(source)
        except ValueError:
            county_tags = ["probate"]
    if county_tags:
        person["tags"] = list(county_tags)
    lead_source = _fub_lead_source_name(row)
    if lead_source:
        person["source"] = lead_source
    return person


def person_fingerprint(person: dict) -> str:
    payload = {k: v for k, v in person.items() if k not in {"id", "_addr_slots"}}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def verify_record_payload(
    row: dict,
    person: dict,
    pid: int | None,
    settings: dict,
    mapping: dict,
) -> dict:
    values = probate_export_values(row, mapping)
    custom = []
    for local_key, api_name in (mapping.get("custom_fields") or {}).items():
        value = values.get(local_key)
        if api_name and value not in (None, ""):
            custom.append(
                {
                    "probate_field": local_key,
                    "fub_field": str(api_name),
                    "value": str(value),
                }
            )
    addr = {}
    addr2 = {}
    if person.get("addresses"):
        addr = person["addresses"][0] if isinstance(person["addresses"][0], dict) else {}
        if len(person["addresses"]) > 1 and isinstance(person["addresses"][1], dict):
            addr2 = person["addresses"][1]
    source_id = _row_source_id(row)
    return {
        "data_source": source_id,
        "source_id": source_id,
        "data_source_name": (
            "Sacramento County" if source_id == "sacramento" else "Placer County"
        ),
        "gate": "go",
        "case_number": case_key(row),
        "fub_person_id": int(pid) if pid else None,
        "petitioner": portal_petitioner(row),
        "firstName": person.get("firstName"),
        "lastName": person.get("lastName"),
        "assignedTo": person.get("assignedTo"),
        "stage": person.get("stage"),
        "lead_source": person.get("source")
        or mapping.get("lead_source")
        or _fub_lead_source_name(row)
        or settings.get("source"),
        "event_type": settings.get("event_type"),
        "decedent": row.get("decedent"),
        "decedent_residence": row.get("decedent_residence"),
        "address": addr,
        "address2": addr2,
        "hearing": values.get("hearing"),
        "notice_url": values.get("notice_url"),
        "court_search": values.get("court_search"),
        "court_url": values.get("court_url") or values.get("court_search"),
        "de111_url": values.get("de111_url") or "",
        "de147_url": values.get("de147_url") or "",
        "de150_url": values.get("de150_url") or "",
        "de111_file": (
            str(_petition_pdf_path(row) or "")
            if (mapping.get("send") or {}).get("de111_file", True)
            else ""
        ),
        "custom_fields": custom,
        "source_extract": source_extract_rows(row, mapping),
        "mapped": mapped_look_payload(row, person, settings, mapping),
    }


def _person_api_body(person: dict) -> dict:
    return {k: v for k, v in (person or {}).items() if k not in {"id", "_addr_slots"}}


def _log_fub_person_payload(key: str, row: dict, person: dict) -> None:
    print(
        f"FUB petitioner address {key}: "
        f"{row.get('mailing_address') or '(empty)'}",
        flush=True,
    )
    print(
        f"FUB last residence {key}: "
        f"{row.get('decedent_residence') or '(empty)'}",
        flush=True,
    )
    print(
        f"FUB sending {len(person.get('addresses') or [])} "
        f"address(es) {key}: {person.get('addresses')}",
        flush=True,
    )


def build_event(
    row: dict,
    mapping: dict,
    settings: dict,
    *,
    person: dict | None = None,
    person_id: int | None = None,
    allowed_custom: set[str] | None = None,
) -> dict:
    send = mapping.get("send") or {}
    decedent = _row_decedent_name(row)
    case = case_key(row)
    court_note = _court_search_note(row, mapping)
    source_id = _row_source_id(row)
    if source_id == "sacramento":
        message = (
            f"Estate of {decedent or '(unknown)'}. Case {case}. "
            f"Journal Technologies public portal: {court_note}."
        )
        court_label = "Journal Technologies node/397"
    else:
        message = (
            f"Estate of {decedent or '(unknown)'}. Case {case}. "
            f"Search eCourt first: {court_note}."
        )
        court_label = "eCourt"
    if row.get("notice_url"):
        message += f" Notice: {row['notice_url']}"
    if person is None:
        person = build_person(
            row,
            mapping,
            settings,
            person_id=person_id,
            allowed_custom=allowed_custom,
        )
    event: dict = {
        "system": mapping.get("system") or "PlacerProbateMonitor",
        "type": settings.get("event_type") or "Seller Inquiry",
        "person": _person_api_body(person),
    }
    if person_id is None and send.get("source", True):
        event["source"] = (
            (person or {}).get("source")
            or _fub_lead_source_name(row)
            or settings.get("source")
            or "probate"
        )
    if send.get("message", True):
        event["message"] = message
        event["description"] = (
            f"Estate location (DE-111 3.a.(2), not place of death): "
            f"{row.get('decedent_residence') or '—'}. "
            f"Hearing: {row.get('next_event') or row.get('hearing') or '—'}. "
            f"{court_label}: {case_portal_url(row) or court_note}."
        )
    return event


FUB_REVIEW_GATE_COLUMNS = (
    ("would_post", "would_post"),
    ("would_put", "would_put"),
    ("would_skip", "would_skip"),
    ("skip_reason", "skip_reason"),
    ("case_number", "case_number"),
    ("county", "county"),
    ("fub_person_id", "fub_person_id"),
    ("go_status", "go_status"),
    ("nogo_reason", "nogo_reason"),
    ("gmv_real", "gmv_real"),
    ("estate_real", "estate_real"),
    ("petition_ocr", "petition_ocr"),
)
FUB_REVIEW_LEAD_COLUMNS = FUB_REVIEW_GATE_COLUMNS
FUB_REVIEW_PERSON_COLUMNS = (
    ("firstName", "firstName"),
    ("lastName", "lastName"),
    ("emails", "emails"),
    ("phones", "phones"),
    ("assignedTo", "assignedTo"),
    ("stage", "stage"),
    ("source", "source"),
    ("tags", "tags"),
    ("background", "background"),
    ("address1_street", "address1_street"),
    ("address1_city", "address1_city"),
    ("address1_state", "address1_state"),
    ("address1_code", "address1_code"),
    ("address1_type", "address1_type"),
    ("address2_street", "address2_street"),
    ("address2_city", "address2_city"),
    ("address2_state", "address2_state"),
    ("address2_code", "address2_code"),
    ("address2_type", "address2_type"),
)
FUB_REVIEW_NOTE_COLUMNS = (
    ("note_subject", "note_subject"),
    ("note_body", "note_body"),
    ("event_type", "event_type"),
    ("event_source", "event_source"),
    ("event_system", "event_system"),
    ("event_message", "event_message"),
    ("event_description", "event_description"),
    ("put_person_json", "put_person_json"),
    ("post_event_json", "post_event_json"),
)
FUB_REVIEW_EVENT_COLUMNS = FUB_REVIEW_NOTE_COLUMNS
FUB_REVIEW_PERSON_PAYLOAD_KEYS = {
    "firstName",
    "lastName",
    "emails",
    "phones",
    "assignedTo",
    "stage",
    "source",
    "tags",
    "background",
    "addresses",
}


def _review_join_contacts(items) -> str:
    if not items:
        return ""
    if isinstance(items, str):
        return items
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("value") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            parts.append(text)
    return "; ".join(parts)


def _review_addr(person: dict, index: int) -> dict:
    addrs = person.get("addresses") if isinstance(person.get("addresses"), list) else []
    item = addrs[index] if index < len(addrs) and isinstance(addrs[index], dict) else {}
    return {
        "street": str(item.get("street") or ""),
        "city": str(item.get("city") or ""),
        "state": str(item.get("state") or ""),
        "code": str(item.get("code") or item.get("postalCode") or ""),
        "type": str(item.get("type") or ""),
    }


def _review_cell(value) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def fub_review_settings() -> dict:
    return {
        "source": os.environ.get("FUB_SOURCE", "probate"),
        "assigned_to": os.environ.get("FUB_ASSIGNED_TO", "Blake Hammond"),
        "stage": (os.environ.get("FUB_STAGE") or "").strip(),
        "event_type": os.environ.get("FUB_EVENT_TYPE", "Seller Inquiry"),
    }


def _review_custom_api_names(mapping: dict | None) -> list[str]:
    """FUB custom field API names that become top-level person keys."""
    names: list[str] = []
    seen: set[str] = set()
    blocks: list[dict] = [dict((mapping or {}).get("custom_fields") or {})]
    for block in ((mapping or {}).get("source_mappings") or {}).values():
        if isinstance(block, dict):
            nested = block.get("custom_fields") or {}
            if isinstance(nested, dict):
                blocks.append(nested)
    for fields in blocks:
        for api_name in fields.values():
            raw = str(api_name or "").strip()
            if not raw:
                continue
            target = raw.split(".", 1)[1] if raw.lower().startswith("person.") else raw
            if (
                target in PERSON_BUILTIN_TARGETS
                or target.lower() in ADDRESS_SLOT_TARGETS
                or _is_notes_target(target)
            ):
                continue
            if raw not in seen:
                seen.add(raw)
                names.append(raw)
    return names


def _review_payload_json(payload: dict) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def _review_export_action(
    go_status: str,
    person_id: int | None,
    gmv: float | None,
    nogo_reason: str,
) -> tuple[str, str, str, str]:
    """Return would_post, would_put, would_skip, skip_reason. Never calls FUB."""
    is_go = str(go_status or "").strip() == GO_STATUS_GO
    gmv_ok = gmv is not None and gmv >= MIN_ESTATE_REAL_GMV
    if is_go and person_id is not None:
        return "false", "true", "false", ""
    if is_go and gmv_ok:
        return "true", "false", "false", ""
    reason = str(nogo_reason or "").strip()
    if is_go and not gmv_ok:
        reason = (
            NOGO_MISSING_ESTATE_REAL if gmv is None else NOGO_ESTATE_REAL_BELOW_MIN
        )
    elif not reason:
        reason = "not_go"
    return "false", "false", "true", reason


def fub_review_columns(mapping: dict | None = None) -> list[tuple[str, str]]:
    cols = list(
        FUB_REVIEW_GATE_COLUMNS
        + FUB_REVIEW_PERSON_COLUMNS
        + FUB_REVIEW_NOTE_COLUMNS
    )
    seen = {key for key, _header in cols}
    for api_name in _review_custom_api_names(mapping):
        if api_name not in seen:
            cols.append((api_name, api_name))
            seen.add(api_name)
    return cols


def build_fub_review_row(
    listing: dict,
    mapping: dict | None = None,
    settings: dict | None = None,
) -> dict:
    """One stored listing as the exact local POST/PUT person payload. No FUB HTTP."""
    harvest = listing_as_harvest_row(listing)
    source_id = _row_source_id(harvest)
    mapped = mapping_for_export(mapping or {}, source_id)
    cfg = settings or fub_review_settings()
    apply_listing_go(harvest, mapping=mapped)
    go_status = str(harvest.get("go_status") or "")
    nogo = str(harvest.get("nogo_reason") or "")
    raw_id = harvest.get("fub_person_id")
    if raw_id in (None, ""):
        raw_id = listing.get("fub_person_id")
    person_id = None
    if raw_id not in (None, "", 0, "0"):
        try:
            person_id = int(raw_id)
        except (TypeError, ValueError):
            person_id = None
    person = build_person(
        harvest,
        mapped,
        cfg,
        person_id=person_id,
        allowed_custom=None,
    )
    event = build_event(
        harvest,
        mapped,
        cfg,
        person=person,
        person_id=person_id,
        allowed_custom=None,
    )
    addr1 = _review_addr(person, 0)
    addr2 = _review_addr(person, 1)
    county = str(
        harvest.get("source")
        or listing.get("source")
        or ("Sacramento County" if source_id == "sacramento" else "Placer County")
    )
    gmv_raw = (
        harvest.get("estate_real")
        if harvest.get("estate_real") not in (None, "")
        else listing.get("estate_real")
    )
    gmv_plain = _gmv_plain_field(gmv_raw)
    gmv_amount = _estate_real_amount({"estate_real": gmv_raw})
    would_post, would_put, would_skip, skip_reason = _review_export_action(
        go_status, person_id, gmv_amount, nogo
    )
    note_text = combined_notes(harvest, mapped)
    row: dict[str, str] = {
        "would_post": would_post,
        "would_put": would_put,
        "would_skip": would_skip,
        "skip_reason": skip_reason,
        "case_number": case_key(harvest),
        "county": county,
        "fub_person_id": "" if person_id is None else str(person_id),
        "go_status": go_status,
        "nogo_reason": nogo,
        "gmv_real": gmv_plain,
        "estate_real": gmv_plain,
        "petition_ocr": (
            "true"
            if harvest.get("petition_ocr")
            or listing.get("petition_ocr")
            or harvest.get("duties_ocr")
            or listing.get("duties_ocr")
            or harvest.get("petition_ocr_gmv")
            or listing.get("petition_ocr_gmv")
            else ""
        ),
        "firstName": _review_cell(person.get("firstName")),
        "lastName": _review_cell(person.get("lastName")),
        "emails": _review_join_contacts(person.get("emails")),
        "phones": _review_join_contacts(person.get("phones")),
        "assignedTo": _review_cell(person.get("assignedTo")),
        "stage": _review_cell(person.get("stage")),
        "source": _review_cell(person.get("source")),
        "tags": _review_cell(person.get("tags")),
        "background": _review_cell(person.get("background")),
        "address1_street": addr1["street"],
        "address1_city": addr1["city"],
        "address1_state": addr1["state"],
        "address1_code": addr1["code"],
        "address1_type": addr1["type"],
        "address2_street": addr2["street"],
        "address2_city": addr2["city"],
        "address2_state": addr2["state"],
        "address2_code": addr2["code"],
        "address2_type": addr2["type"],
        "note_subject": probate_note_subject(harvest),
        "note_body": _with_probate_note_marker(note_text),
        "event_type": _review_cell(event.get("type")),
        "event_source": _review_cell(event.get("source")),
        "event_system": _review_cell(event.get("system")),
        "event_message": _review_cell(event.get("message")),
        "event_description": _review_cell(event.get("description")),
        "put_person_json": _review_payload_json(_person_api_body(person)),
        "post_event_json": _review_payload_json(event),
    }
    for api_name in _review_custom_api_names(mapped):
        row[api_name] = _review_cell(person.get(api_name))
    for key, value in person.items():
        if key in {"id", "_addr_slots"} or key in FUB_REVIEW_PERSON_PAYLOAD_KEYS:
            continue
        if key not in row:
            row[key] = _review_cell(value)
    return row


def build_fub_review_table(
    listings: list[dict],
    *,
    mapping: dict | None = None,
    mapping_path: Path | None = None,
    settings: dict | None = None,
) -> tuple[list[tuple[str, str]], list[dict]]:
    loaded = mapping if mapping is not None else load_mapping(mapping_path)
    cfg = settings or fub_review_settings()
    columns = fub_review_columns(loaded)
    rows = [build_fub_review_row(item, loaded, cfg) for item in listings or []]
    seen = {key for key, _header in columns}
    extras: list[tuple[str, str]] = []
    for item in rows:
        for key in item:
            if key not in seen:
                extras.append((key, key))
                seen.add(key)
    if extras:
        note_keys = {key for key, _header in FUB_REVIEW_NOTE_COLUMNS}
        insert_at = next(
            (i for i, (key, _) in enumerate(columns) if key in note_keys),
            len(columns),
        )
        columns = columns[:insert_at] + extras + columns[insert_at:]
    return columns, rows


def _api_root(api_url: str) -> str:
    base = api_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _fub_headers(system: str) -> dict:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-System": system,
    }
    key = str(os.environ.get("FUB_SYSTEM_KEY") or "").strip()
    if key:
        headers["X-System-Key"] = key
    return headers


def post_event(api_url: str, api_key: str, payload: dict, system: str) -> dict:
    url = f"{_api_root(api_url)}/events"
    response = requests.post(
        url,
        json=payload,
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"FUB HTTP {response.status_code}: {response.text[:500]}")
    try:
        return response.json()
    except ValueError:
        return {}


def _fub_payload_missing(payload) -> bool:
    if payload is None:
        return True
    if not isinstance(payload, dict):
        return False
    err = str(payload.get("error") or payload.get("message") or "").lower()
    if "not found" in err or "has been deleted" in err:
        return True
    person = payload.get("person") if isinstance(payload.get("person"), dict) else payload
    if not isinstance(person, dict):
        return False
    if person.get("deleted") or person.get("isDeleted"):
        return True
    return str(person.get("status") or "").lower() == "deleted"


def get_person(api_url: str, api_key: str, person_id: int, system: str) -> dict | None:
    url = f"{_api_root(api_url)}/people/{int(person_id)}"
    response = requests.get(
        url,
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code in (404, 410):
        return None
    if response.status_code >= 400:
        raise RuntimeError(f"FUB HTTP {response.status_code}: {response.text[:500]}")
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if _fub_payload_missing(payload):
        return None
    return payload if isinstance(payload, dict) else {}


def put_person(api_url: str, api_key: str, person_id: int, payload: dict, system: str) -> dict | None:
    body = _person_api_body(payload)
    url = f"{_api_root(api_url)}/people/{int(person_id)}?mergeTags=true"
    response = requests.put(
        url,
        json=body,
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code in (404, 410):
        return None
    if response.status_code >= 400:
        raise RuntimeError(f"FUB HTTP {response.status_code}: {response.text[:500]}")
    try:
        parsed = response.json()
    except ValueError:
        return {}
    if _fub_payload_missing(parsed):
        return None
    return parsed if isinstance(parsed, dict) else {}


PROBATE_NOTE_MARKER = "[PPM-NOTE]"
PROBATE_NOTE_SUBJECTS = frozenset(
    {
        "placer probate",
        "sacramento probate",
        "probate monitor",
    }
)
COURT_NOTE_SUBJECTS = {
    "de-111 petition": "de111",
    "de-147 duties": "de147",
    "ecourt public case": "court",
}


def probate_note_subject(row: dict | None = None) -> str:
    if _row_source_id(row) == "sacramento":
        return "Sacramento probate"
    return "Placer probate"


def _with_probate_note_marker(body: str) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    if PROBATE_NOTE_MARKER in text:
        return text
    return f"{PROBATE_NOTE_MARKER}\n{text}"


def _parse_fub_note_id(raw) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def is_probate_monitor_note(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    body = str(item.get("body") or "")
    if PROBATE_NOTE_MARKER in body:
        return True
    subject = str(item.get("subject") or "").strip().lower()
    return subject in PROBATE_NOTE_SUBJECTS


def note_integration_kind(item: dict | None) -> str | None:
    """Return our note type, or None for CRM/human notes we must not touch."""
    if not isinstance(item, dict):
        return None
    if is_probate_monitor_note(item):
        return "probate"
    subject = str(item.get("subject") or "").strip().lower()
    return COURT_NOTE_SUBJECTS.get(subject)


def post_note(
    api_url: str,
    api_key: str,
    person_id: int,
    body: str,
    system: str,
    *,
    subject: str = "Placer probate",
    is_html: bool = False,
) -> dict:
    text = (body or "").strip()
    if not text:
        return {}
    response = requests.post(
        f"{_api_root(api_url)}/notes",
        json={
            "personId": int(person_id),
            "subject": subject or "Placer probate",
            "body": text,
            "isHtml": bool(is_html),
        },
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"FUB notes HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError:
        return {}


def put_note(
    api_url: str,
    api_key: str,
    note_id: int,
    *,
    person_id: int,
    body: str,
    subject: str,
    system: str,
    is_html: bool = False,
) -> dict | None:
    text = (body or "").strip()
    if not text:
        return {}
    response = requests.put(
        f"{_api_root(api_url)}/notes/{int(note_id)}",
        json={
            "personId": int(person_id),
            "subject": subject or "Placer probate",
            "body": text,
            "isHtml": bool(is_html),
        },
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code in (404, 410):
        return None
    if response.status_code >= 400:
        raise RuntimeError(
            f"FUB notes HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def list_person_notes(
    api_url: str,
    api_key: str,
    person_id: int,
    system: str,
    *,
    limit: int = 100,
) -> list[dict]:
    response = requests.get(
        f"{_api_root(api_url)}/notes",
        params={"personId": int(person_id), "limit": int(limit)},
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"FUB notes HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        payload = response.json()
    except ValueError:
        return []
    rows = payload.get("notes") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def find_probate_monitor_note(
    notes: list[dict],
    *,
    preferred_id: int | None = None,
) -> dict | None:
    matches = [item for item in notes if is_probate_monitor_note(item)]
    if not matches:
        return None
    if preferred_id is not None:
        for item in matches:
            if _parse_fub_note_id(item.get("id")) == int(preferred_id):
                return item
    matches.sort(key=lambda item: _parse_fub_note_id(item.get("id")) or 10**12)
    return matches[0]


def find_note_by_kind(notes: list[dict], kind: str) -> dict | None:
    wanted = str(kind or "").strip().lower()
    matches = [
        item for item in notes if note_integration_kind(item) == wanted
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: _parse_fub_note_id(item.get("id")) or 10**12)
    return matches[0]


def _prune_extra_kind_notes(
    api_url: str,
    api_key: str,
    notes: list[dict],
    *,
    kind: str,
    keep_id: int | None,
    system: str,
) -> None:
    if keep_id is None:
        return
    wanted = str(kind or "").strip().lower()
    for item in notes:
        if note_integration_kind(item) != wanted:
            continue
        note_id = _parse_fub_note_id(item.get("id"))
        if not note_id or int(note_id) == int(keep_id):
            continue
        try:
            delete_note(api_url, api_key, int(note_id), system)
            print(
                f"FUB notes deleted extra {wanted} note_id={note_id}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"FUB notes extra {wanted} delete failed note_id={note_id}: {exc}",
                flush=True,
            )


def upsert_kind_note(
    api_url: str,
    api_key: str,
    person_id: int,
    body: str,
    system: str,
    *,
    kind: str,
    subject: str,
    is_html: bool = False,
) -> dict:
    """Edit the existing DE-111 / DE-147 / court note in place; never POST a second one."""
    text = (body or "").strip()
    title = (subject or "").strip()
    wanted = str(kind or "").strip().lower()
    if not text or not wanted:
        return {"ok": True, "action": "skipped", "id": None}
    notes = list_person_notes(api_url, api_key, person_id, system)
    existing = find_note_by_kind(notes, wanted)
    note_id = _parse_fub_note_id((existing or {}).get("id"))
    action = "created"
    saved = None
    if existing is not None and note_id:
        old_body = _normalize_note_text(existing.get("body") or "")
        old_subject = str(existing.get("subject") or "").strip()
        if old_body == _normalize_note_text(text) and old_subject == title:
            action = "unchanged"
            saved = int(note_id)
        else:
            updated = put_note(
                api_url,
                api_key,
                note_id,
                person_id=person_id,
                body=text,
                subject=title,
                system=system,
                is_html=is_html,
            )
            if updated is None:
                existing = None
                note_id = None
            else:
                saved = _parse_fub_note_id(updated.get("id")) or note_id
                action = "updated"
    if saved is None:
        created = post_note(
            api_url,
            api_key,
            person_id,
            text,
            system,
            subject=title,
            is_html=is_html,
        )
        saved = _parse_fub_note_id(created.get("id"))
        action = "created"
    if saved:
        _prune_extra_kind_notes(
            api_url,
            api_key,
            notes,
            kind=wanted,
            keep_id=int(saved),
            system=system,
        )
    return {"ok": True, "action": action, "id": saved}


def upsert_probate_note(
    api_url: str,
    api_key: str,
    person_id: int,
    body: str,
    system: str,
    *,
    subject: str | None = None,
    cases: dict | None = None,
    key: str | None = None,
    is_html: bool = False,
) -> dict:
    """Edit the existing probate monitor note in place; never POST a second one."""
    text = _with_probate_note_marker(body)
    title = (subject or "Placer probate").strip() or "Placer probate"
    if not text:
        return {"ok": True, "action": "skipped", "id": None}
    record = {}
    if cases is not None and key:
        record = cases.setdefault(key, {})
    preferred_id = _parse_fub_note_id(record.get("fub_probate_note_id"))
    notes = list_person_notes(api_url, api_key, person_id, system)
    existing = find_probate_monitor_note(notes, preferred_id=preferred_id)
    note_id = _parse_fub_note_id((existing or {}).get("id")) or preferred_id
    if existing is not None and note_id:
        old_body = str(existing.get("body") or "").strip()
        old_subject = str(existing.get("subject") or "").strip()
        if old_body == text and old_subject == title:
            record["fub_probate_note_id"] = int(note_id)
            _prune_extra_kind_notes(
                api_url,
                api_key,
                notes,
                kind="probate",
                keep_id=int(note_id),
                system=system,
            )
            return {"ok": True, "action": "unchanged", "id": int(note_id)}
        updated = put_note(
            api_url,
            api_key,
            note_id,
            person_id=person_id,
            body=text,
            subject=title,
            system=system,
            is_html=is_html,
        )
        if updated is None:
            existing = None
            note_id = None
        else:
            saved = _parse_fub_note_id(updated.get("id")) or note_id
            record["fub_probate_note_id"] = int(saved)
            print(
                f"FUB notes updated probate note {key or ''} "
                f"person_id={person_id} note_id={saved}",
                flush=True,
            )
            _prune_extra_kind_notes(
                api_url,
                api_key,
                notes,
                kind="probate",
                keep_id=int(saved),
                system=system,
            )
            return {"ok": True, "action": "updated", "id": int(saved)}
    if existing is not None:
        saved = _parse_fub_note_id(existing.get("id"))
        if saved:
            record["fub_probate_note_id"] = int(saved)
            _prune_extra_kind_notes(
                api_url,
                api_key,
                notes,
                kind="probate",
                keep_id=int(saved),
                system=system,
            )
            return {"ok": True, "action": "unchanged", "id": int(saved)}
    created = post_note(
        api_url,
        api_key,
        person_id,
        text,
        system,
        subject=title,
        is_html=is_html,
    )
    saved = _parse_fub_note_id(created.get("id"))
    if saved:
        record["fub_probate_note_id"] = int(saved)
        _prune_extra_kind_notes(
            api_url,
            api_key,
            notes,
            kind="probate",
            keep_id=int(saved),
            system=system,
        )
    print(
        f"FUB notes posted probate note {key or ''} "
        f"person_id={person_id} note_id={saved}",
        flush=True,
    )
    return {"ok": True, "action": "created", "id": saved}


def _normalize_note_text(text: str) -> str:
    return "\n".join(
        line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")
    ).strip()


def _note_body_key(text: str) -> str:
    return " ".join(_normalize_note_text(text).split()).lower()


def _note_paragraphs(text: str) -> list[str]:
    chunks = []
    for block in _normalize_note_text(text).split("\n\n"):
        piece = " ".join(block.split()).strip()
        if piece and piece != PROBATE_NOTE_MARKER:
            chunks.append(piece)
    return chunks


def merge_probate_note_bodies(notes: list[dict]) -> tuple[str, str]:
    """Keep the latest/longest probate body, appending unique extra paragraphs."""
    ranked = [
        item
        for item in notes
        if isinstance(item, dict) and _parse_fub_note_id(item.get("id"))
    ]
    ranked.sort(key=lambda item: _parse_fub_note_id(item.get("id")) or 0, reverse=True)
    if not ranked:
        return "Placer probate", ""
    subject = str(ranked[0].get("subject") or "").strip() or "Placer probate"
    bodies = [
        _with_probate_note_marker(_normalize_note_text(item.get("body") or ""))
        for item in ranked
        if _normalize_note_text(item.get("body") or "")
    ]
    if not bodies:
        return subject, ""
    latest = bodies[0]
    longest = max(bodies, key=len)
    base = longest if len(longest) > len(latest) else latest
    seen = {_note_body_key(para) for para in _note_paragraphs(base)}
    extra: list[str] = []
    for body in bodies:
        for para in _note_paragraphs(body):
            key = _note_body_key(para)
            if key and key not in seen:
                extra.append(para)
                seen.add(key)
    merged = base if not extra else f"{base}\n\n" + "\n\n".join(extra)
    return subject, _with_probate_note_marker(merged)


def plan_duplicate_note_cleanup(
    notes: list[dict],
    *,
    preferred_probate_id: int | None = None,
) -> dict:
    """Plan deletes for our duplicate notes only. Human/CRM notes are skipped."""
    rows = [item for item in notes if isinstance(item, dict)]
    skipped_ids: list[int] = []
    probate: list[dict] = []
    court_groups: dict[tuple[str, str], list[dict]] = {}
    for item in rows:
        note_id = _parse_fub_note_id(item.get("id"))
        kind = note_integration_kind(item)
        if kind is None:
            if note_id:
                skipped_ids.append(int(note_id))
            continue
        if kind == "probate":
            probate.append(item)
            continue
        body_key = _note_body_key(str(item.get("body") or ""))
        court_groups.setdefault((kind, body_key), []).append(item)

    delete_ids: list[int] = []
    keep = find_probate_monitor_note(probate, preferred_id=preferred_probate_id)
    keep_id = _parse_fub_note_id((keep or {}).get("id"))
    put_subject = None
    put_body = None
    if probate and keep_id:
        subject, merged = merge_probate_note_bodies(probate)
        old_body = _normalize_note_text((keep or {}).get("body") or "")
        old_subject = str((keep or {}).get("subject") or "").strip()
        if merged and (
            _normalize_note_text(merged) != old_body or subject != old_subject
        ):
            put_subject = subject
            put_body = merged
        for item in probate:
            note_id = _parse_fub_note_id(item.get("id"))
            if note_id and note_id != keep_id:
                delete_ids.append(int(note_id))

    court_exact_deletes: list[int] = []
    for group in court_groups.values():
        valid = [item for item in group if _parse_fub_note_id(item.get("id"))]
        if len(valid) < 2:
            continue
        valid.sort(key=lambda item: _parse_fub_note_id(item.get("id")) or 0)
        for item in valid[1:]:
            note_id = _parse_fub_note_id(item.get("id"))
            if note_id:
                court_exact_deletes.append(int(note_id))
                delete_ids.append(int(note_id))

    # Stable unique order; never delete the keeper.
    seen_del: set[int] = set()
    unique_deletes: list[int] = []
    for note_id in delete_ids:
        if keep_id and note_id == keep_id:
            continue
        if note_id in seen_del:
            continue
        seen_del.add(note_id)
        unique_deletes.append(note_id)

    return {
        "keep_id": int(keep_id) if keep_id else None,
        "probate_ids": [
            int(nid)
            for nid in (_parse_fub_note_id(item.get("id")) for item in probate)
            if nid
        ],
        "put_subject": put_subject,
        "put_body": put_body,
        "delete_ids": unique_deletes,
        "court_exact_deletes": court_exact_deletes,
        "skipped_ids": skipped_ids,
        "notes_total": len(rows),
        "probate_count": len(probate),
        "would_change": bool(unique_deletes or put_body),
    }


def delete_note(
    api_url: str,
    api_key: str,
    note_id: int,
    system: str,
) -> dict:
    response = requests.delete(
        f"{_api_root(api_url)}/notes/{int(note_id)}",
        auth=(api_key, ""),
        headers=_fub_headers(system),
        timeout=30,
    )
    if response.status_code in (404, 410):
        return {"ok": True, "action": "missing", "id": int(note_id)}
    if response.status_code >= 400:
        raise RuntimeError(
            f"FUB notes HTTP {response.status_code}: {response.text[:500]}"
        )
    return {"ok": True, "action": "deleted", "id": int(note_id)}


def listing_fub_people(listings: list[dict]) -> list[dict]:
    seen: set[int] = set()
    people: list[dict] = []
    for row in listings:
        if not isinstance(row, dict):
            continue
        if row.get("fub_removed"):
            continue
        person_id = _parse_fub_person_id(row.get("fub_person_id"))
        if not person_id or person_id in seen:
            continue
        seen.add(int(person_id))
        people.append(
            {
                "person_id": int(person_id),
                "case_number": str(row.get("case_number") or ""),
                "source_id": str(row.get("source_id") or ""),
            }
        )
    return people


def cleanup_person_duplicate_notes(
    api_url: str,
    api_key: str,
    person_id: int,
    system: str,
    *,
    dry_run: bool = True,
    preferred_probate_id: int | None = None,
    cases: dict | None = None,
    key: str | None = None,
) -> dict:
    """Keep one probate-monitor note; delete only extra notes we created."""
    notes = list_person_notes(api_url, api_key, int(person_id), system)
    plan = plan_duplicate_note_cleanup(
        notes, preferred_probate_id=preferred_probate_id
    )
    result = {
        "ok": True,
        "person_id": int(person_id),
        "dry_run": bool(dry_run),
        "notes_total": plan["notes_total"],
        "probate_count": plan["probate_count"],
        "keep_id": plan["keep_id"],
        "delete_ids": list(plan["delete_ids"]),
        "court_exact_deletes": list(plan["court_exact_deletes"]),
        "skipped_other": len(plan["skipped_ids"]),
        "put": bool(plan["put_body"]),
        "would_change": plan["would_change"],
        "deleted": [],
        "action": "dry_run" if dry_run else "unchanged",
    }
    if dry_run:
        return result
    record = {}
    if cases is not None and key:
        record = cases.setdefault(key, {})
    keep_id = plan["keep_id"]
    if plan["put_body"] and keep_id:
        updated = put_note(
            api_url,
            api_key,
            keep_id,
            person_id=int(person_id),
            body=plan["put_body"],
            subject=plan["put_subject"] or "Placer probate",
            system=system,
        )
        if updated is None:
            result["ok"] = False
            result["action"] = "keep_missing"
            return result
        keep_id = _parse_fub_note_id(updated.get("id")) or keep_id
        result["keep_id"] = int(keep_id)
        result["put"] = True
    deleted: list[int] = []
    for note_id in plan["delete_ids"]:
        delete_note(api_url, api_key, note_id, system)
        deleted.append(int(note_id))
    if keep_id:
        record["fub_probate_note_id"] = int(keep_id)
    result["deleted"] = deleted
    if deleted or result["put"]:
        result["action"] = "cleaned"
        print(
            f"FUB notes cleaned person_id={person_id} keep={keep_id} "
            f"deleted={len(deleted)}",
            flush=True,
        )
    return result


def cleanup_listing_duplicate_notes(
    listings: list[dict],
    *,
    api_url: str,
    api_key: str,
    system: str,
    dry_run: bool = True,
    person_id: int | None = None,
    skip_person_ids: list[int] | tuple[int, ...] | None = None,
    cases: dict | None = None,
) -> dict:
    """Scan listing FUB people. Live deletes require a single person_id."""
    skip = {
        int(item)
        for item in (skip_person_ids or [])
        if _parse_fub_person_id(item)
    }
    wanted = _parse_fub_person_id(person_id)
    if not dry_run and not wanted:
        raise ValueError("Live FUB note cleanup requires a single person_id.")
    people = listing_fub_people(listings)
    if wanted:
        people = [item for item in people if item["person_id"] == int(wanted)]
        if not people:
            people = [
                {
                    "person_id": int(wanted),
                    "case_number": "",
                    "source_id": "",
                }
            ]
    people = [item for item in people if item["person_id"] not in skip]
    rows: list[dict] = []
    dup_people = 0
    extra_notes = 0
    for item in people:
        pid = int(item["person_id"])
        preferred = None
        if cases is not None:
            record = cases.get(item.get("case_number") or "") or {}
            preferred = _parse_fub_note_id(record.get("fub_probate_note_id"))
        cleaned = cleanup_person_duplicate_notes(
            api_url,
            api_key,
            pid,
            system,
            dry_run=dry_run,
            preferred_probate_id=preferred,
            cases=cases,
            key=item.get("case_number") or None,
        )
        extras = max(0, int(cleaned.get("probate_count") or 0) - 1) + len(
            cleaned.get("court_exact_deletes") or []
        )
        if extras:
            dup_people += 1
            extra_notes += extras
        rows.append(
            {
                "person_id": pid,
                "case_number": item.get("case_number"),
                "probate_count": cleaned.get("probate_count"),
                "keep_id": cleaned.get("keep_id"),
                "delete_count": len(cleaned.get("delete_ids") or []),
                "skipped_other": cleaned.get("skipped_other"),
                "would_change": cleaned.get("would_change"),
                "action": cleaned.get("action"),
            }
        )
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "people": len(people),
        "people_with_duplicate_notes": dup_people,
        "extra_notes": extra_notes,
        "skipped_person_ids": sorted(skip),
        "rows": rows,
    }


def _attachment_headers(system: str) -> dict:
    headers = _fub_headers(system)
    key = str(os.environ.get("FUB_SYSTEM_KEY") or "").strip()
    if key:
        headers["X-System-Key"] = key
    return headers


def post_person_attachment(
    api_url: str,
    api_key: str,
    person_id: int,
    path: Path,
    *,
    uri: str,
    file_name: str,
    system: str,
) -> dict:
    url = f"{_api_root(api_url)}/personAttachments"
    headers = _attachment_headers(system)
    errors: list[str] = []
    if uri:
        response = requests.post(
            url,
            json={
                "personId": int(person_id),
                "uri": uri,
                "fileName": file_name,
                "fileSize": int(path.stat().st_size),
            },
            auth=(api_key, ""),
            headers=headers,
            timeout=30,
        )
        if response.status_code < 400:
            try:
                return response.json()
            except ValueError:
                return {}
        errors.append(f"uri {response.status_code}: {response.text[:300]}")
    mp_headers = {key: value for key, value in headers.items() if key.lower() != "content-type"}
    with path.open("rb") as handle:
        response = requests.post(
            url,
            data={"personId": str(int(person_id)), "fileName": file_name},
            files={"file": (file_name, handle, "application/pdf")},
            auth=(api_key, ""),
            headers=mp_headers,
            timeout=60,
        )
    if response.status_code < 400:
        try:
            return response.json()
        except ValueError:
            return {}
    errors.append(f"upload {response.status_code}: {response.text[:300]}")
    raise RuntimeError("FUB files " + " | ".join(errors))


def _de111_note_payload(case: str, file_name: str, uri: str, path: Path) -> tuple[str, bool]:
    safe_case = html.escape(case or "")
    safe_name = html.escape(file_name or "DE-111.pdf")
    if uri:
        safe_uri = html.escape(uri, quote=True)
        body = (
            f"<p>DE-111 petition for {safe_case}</p>"
            f'<p><a href="{safe_uri}">{safe_name}</a></p>'
            f"<p>{safe_uri}</p>"
        )
        return body, True
    return (
        f"DE-111 petition for {case}: {file_name}\n"
        f"Saved on Home Assistant: {path}",
        False,
    )


def attach_de111_file(
    row: dict,
    person_id: int,
    *,
    mapping: dict,
    api_url: str,
    api_key: str,
    system: str,
    cases: dict,
    key: str,
    force: bool = False,
) -> dict:
    send = mapping.get("send") or {}
    if not send.get("de111_file", True):
        print(f"FUB files skip {key}: de111_file toggle off", flush=True)
        return {"ok": False, "reason": "disabled"}
    record = cases.get(key) or {}
    path = _petition_pdf_path(row)
    if not path:
        print(f"FUB files skip {key}: no DE-111 PDF", flush=True)
        return {"ok": False, "reason": "no_pdf"}
    case = case_key(row)
    file_name = f"{petition_safe_case(case)}_DE-111.pdf"
    uri = petition_public_uri(case)
    if key not in cases:
        cases[key] = {}
    if uri:
        print(f"FUB DE-111 URL {key}: {uri}", flush=True)
    else:
        print(
            f"FUB DE-111 URL {key}: missing Home Assistant external URL; "
            f"PDF is at {path}",
            flush=True,
        )
    if _source_mapped_to_notes(mapping, "de111_url"):
        print(f"FUB DE-111 notes skip {key}: URL mapped into Notes", flush=True)
        note_result = {"ok": True, "reason": "mapped_notes", "file": file_name, "uri": uri}
    elif record.get("fub_de111_note_uri") == uri and uri and not force:
        note_result = {"ok": True, "reason": "notes_link", "file": file_name, "uri": uri}
    else:
        body, is_html = _de111_note_payload(case, file_name, uri, path)
        saved = upsert_kind_note(
            api_url,
            api_key,
            person_id,
            body,
            system,
            kind="de111",
            subject="DE-111 petition",
            is_html=is_html,
        )
        cases[key]["fub_de111_note"] = True
        cases[key]["fub_de111_note_uri"] = uri
        print(
            f"FUB notes {saved.get('action')} DE-111 link {key} "
            f"person_id={person_id} note_id={saved.get('id')}",
            flush=True,
        )
        note_result = {"ok": True, "reason": "notes_link", "file": file_name, "uri": uri}
    if not str(os.environ.get("FUB_SYSTEM_KEY") or "").strip():
        return note_result
    if record.get("fub_attachment_id"):
        note_result["id"] = record.get("fub_attachment_id")
        return note_result
    try:
        attached = post_person_attachment(
            api_url,
            api_key,
            person_id,
            path,
            uri=uri,
            file_name=file_name,
            system=system,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FUB Files API skipped for {key}: {exc}", flush=True)
        note_result["error"] = str(exc)[:200]
        return note_result
    attachment_id = attached.get("id")
    if attachment_id:
        cases[key]["fub_attachment_id"] = attachment_id
        note_result["id"] = attachment_id
        note_result["reason"] = "attached"
        print(
            f"FUB files attached DE-111 {key} person_id={person_id} "
            f"attachment_id={attachment_id}",
            flush=True,
        )
    return note_result


def _de147_note_payload(case: str, file_name: str, uri: str, court_url: str, phone: str) -> tuple[str, bool]:
    safe_case = html.escape(case or "")
    safe_name = html.escape(file_name or "DE-147.pdf")
    bits = [f"<p>DE-147 duties / acknowledgment for {safe_case}</p>"]
    if uri:
        safe_uri = html.escape(uri, quote=True)
        bits.append(f'<p><a href="{safe_uri}">{safe_name}</a></p>')
        bits.append(f"<p>{safe_uri}</p>")
    if court_url:
        safe_court = html.escape(court_url, quote=True)
        bits.append(
            f'<p>eCourt file: <a href="{safe_court}">{html.escape(court_url)}</a></p>'
        )
    if phone:
        bits.append(f"<p>Petitioner phone: {html.escape(phone)}</p>")
    if len(bits) == 1:
        return f"DE-147 duties for {case}: {file_name}", False
    return "".join(bits), True


def attach_de147_file(
    row: dict,
    person_id: int,
    *,
    mapping: dict,
    api_url: str,
    api_key: str,
    system: str,
    cases: dict,
    key: str,
    force: bool = False,
) -> dict:
    send = mapping.get("send") or {}
    if not send.get("de147_file", True):
        print(f"FUB DE-147 skip {key}: de147_file toggle off", flush=True)
        return {"ok": False, "reason": "disabled"}
    if _source_mapped_to_notes(mapping, "de147_url"):
        print(f"FUB DE-147 notes skip {key}: URL mapped into Notes", flush=True)
        return {
            "ok": True,
            "reason": "mapped_notes",
            "uri": duties_public_uri(case_key(row)),
            "file": f"{petition_safe_case(case_key(row))}_DE-147.pdf",
        }
    path = _duties_pdf_path(row)
    if not path:
        print(f"FUB DE-147 skip {key}: no DE-147 PDF", flush=True)
        return {"ok": False, "reason": "no_pdf"}
    case = case_key(row)
    file_name = f"{petition_safe_case(case)}_DE-147.pdf"
    uri = duties_public_uri(case)
    court_url = str(row.get("duties_url") or "").strip()
    phone = str(_row_contact(row).get("petitioner_phone") or row.get("petitioner_phone") or "").strip()
    record = cases.get(key) or {}
    if key not in cases:
        cases[key] = {}
    fingerprint = f"{uri}|{court_url}|{phone}"
    if record.get("fub_de147_note_fp") == fingerprint and not force:
        return {"ok": True, "reason": "already", "uri": uri or court_url, "file": file_name}
    body, is_html = _de147_note_payload(case, file_name, uri, court_url, phone)
    saved = upsert_kind_note(
        api_url,
        api_key,
        person_id,
        body,
        system,
        kind="de147",
        subject="DE-147 duties",
        is_html=is_html,
    )
    cases[key]["fub_de147_note_fp"] = fingerprint
    print(
        f"FUB notes {saved.get('action')} DE-147 {key} person_id={person_id} "
        f"note_id={saved.get('id')} {uri or court_url}",
        flush=True,
    )
    return {"ok": True, "reason": "notes_link", "uri": uri or court_url, "file": file_name}


def _court_portal_note_payload(case: str, url: str) -> str:
    safe_case = html.escape(case or "")
    safe_url = html.escape(url, quote=True)
    return (
        f"<p>Placer eCourt Public case {safe_case}</p>"
        f'<p><a href="{safe_url}">Open case in eCourt Public</a></p>'
        f"<p>{html.escape(url)}</p>"
    )


def post_court_portal_note(
    row: dict,
    person_id: int,
    *,
    mapping: dict,
    api_url: str,
    api_key: str,
    system: str,
    cases: dict,
    key: str,
    force: bool = False,
) -> dict:
    send = mapping.get("send") or {}
    if not send.get("court_url_note", True):
        print(f"FUB court URL skip {key}: court_url_note toggle off", flush=True)
        return {"ok": False, "reason": "disabled"}
    url = case_portal_url(row)
    if not url:
        print(f"FUB court URL skip {key}: no eCourt case page", flush=True)
        return {"ok": False, "reason": "no_court_url"}
    record = cases.get(key) or {}
    if key not in cases:
        cases[key] = {}
    if record.get("fub_court_note_url") == url and not force:
        print(f"FUB court URL already noted {key}: {url}", flush=True)
        return {"ok": True, "reason": "already", "uri": url}
    saved = upsert_kind_note(
        api_url,
        api_key,
        person_id,
        _court_portal_note_payload(case_key(row), url),
        system,
        kind="court",
        subject="eCourt Public case",
        is_html=True,
    )
    cases[key]["fub_court_note_url"] = url
    print(
        f"FUB notes {saved.get('action')} court URL {key} "
        f"person_id={person_id} note_id={saved.get('id')} {url}",
        flush=True,
    )
    return {"ok": True, "reason": "notes_link", "uri": url}


def person_id_from_response(body: dict) -> int | None:
    if not isinstance(body, dict):
        return None
    for key in ("personId", "person_id"):
        if body.get(key):
            return int(body[key])
    person = body.get("person")
    if isinstance(person, dict) and person.get("id"):
        return int(person["id"])
    if body.get("id") and (body.get("firstName") or body.get("lastName")):
        return int(body["id"])
    return None


def _remember_person(cases: dict, key: str, person_id: int, fingerprint: str) -> None:
    if key not in cases:
        cases[key] = {}
    cases[key]["fub_person_id"] = int(person_id)
    cases[key]["fub_fingerprint"] = fingerprint
    cases[key]["fub_skip"] = None
    cases[key].pop("fub_removed", None)


def _mark_fub_removed(cases: dict, key: str, person_id: int | None) -> None:
    if not key:
        return
    record = cases.setdefault(key, {})
    if person_id not in (None, "", 0, "0"):
        record["fub_person_id"] = int(person_id)
    record["fub_removed"] = True
    record["fub_skip"] = "fub_removed"
    print(
        f"FUB person_id={person_id} was deleted; "
        f"marking {key} as fub_removed (will not recreate)",
        flush=True,
    )


def _clear_fub_person(cases: dict, key: str) -> None:
    if not key:
        return
    record = cases.setdefault(key, {})
    for field in (
        "fub_person_id",
        "fub_fingerprint",
        "fub_attachment_id",
        "fub_de111_note",
        "fub_de111_note_uri",
        "fub_de147_note_fp",
        "fub_court_note_url",
        "fub_probate_note_id",
        "fub_skip",
        "fub_removed",
    ):
        record.pop(field, None)


def export_new_leads(
    rows: list[dict],
    state: dict,
    *,
    mapping_path: Path | None = None,
    force: bool = False,
) -> dict:
    summary = {
        "posted": 0,
        "updated": 0,
        "skipped": 0,
        "error": None,
        "skips": [],
        "verify_record": None,
        "verify_note": None,
    }
    if not _env_bool("FUB_ENABLED"):
        try:
            from .job_progress import report_progress
        except ImportError:
            from job_progress import report_progress

        report_progress(
            "fub",
            "Follow Up Boss import is off.",
            fub_posted=0,
            fub_updated=0,
            fub_skipped=0,
        )
        return summary
    api_key = os.environ.get("FUB_API_KEY", "").strip()
    if not api_key:
        summary["error"] = "FUB enabled but API key is empty"
        print(summary["error"], flush=True)
        print("FUB: posted=0 updated=0 skipped=0", flush=True)
        return summary
    source_id = _row_source_id(rows[0] if rows else None)
    mapping = mapping_for_export(load_mapping(mapping_path), source_id)
    settings = {
        "api_url": os.environ.get("FUB_API_URL", "https://api.followupboss.com/v1"),
        "source": mapping.get("lead_source") or os.environ.get("FUB_SOURCE", "probate"),
        "assigned_to": os.environ.get("FUB_ASSIGNED_TO", "Blake Hammond"),
        "stage": (os.environ.get("FUB_STAGE") or "").strip(),
        "event_type": os.environ.get("FUB_EVENT_TYPE", "Seller Inquiry"),
    }
    strict = _env_bool("FUB_STRICT_PROPERTY")
    verify = _env_bool("FUB_VERIFY_ONLY")
    update_existing = bool(force) or _env_bool("FUB_UPDATE_EXISTING")
    refresh = verify or update_existing
    forced_id = _forced_verify_person_id() if verify else None
    if verify and _env_bool("FUB_VERIFY_EXISTING") and forced_id is None:
        summary["error"] = "Use existing is on but Follow Up Boss person ID is empty"
        print(summary["error"], flush=True)
        print("FUB: posted=0 updated=0 skipped=0", flush=True)
        return summary
    system = str(mapping.get("system") or "PlacerProbateMonitor")
    allowed_custom = fub_custom_field_names()
    cases = state.setdefault("cases", {})
    posted_case = None
    posted_pid = None
    work_rows = _rows_for_export(rows, state, verify=verify)
    if forced_id:
        matched = []
        for row in rows:
            harvest = listing_as_harvest_row(row)
            stored = stored_person_id(state, case_key(harvest), harvest)
            listed = _parse_fub_person_id(harvest.get("fub_person_id"))
            if stored == forced_id or listed == forced_id:
                matched.append(harvest)
        if not matched:
            summary["error"] = (
                f"No stored listing has Follow Up Boss person {forced_id}."
            )
            summary["verify_note"] = summary["error"]
            print(summary["error"], flush=True)
            print("FUB: posted=0 updated=0 skipped=0", flush=True)
            return summary
        work_rows = matched
        print(
            f"FUB verify: stored listing {case_key(matched[0])} "
            f"person_id={forced_id}",
            flush=True,
        )
    for row in work_rows:
        key = case_key(row)
        if is_fub_removed(state, key, row):
            if key:
                record = cases.setdefault(key, {})
                record["fub_removed"] = True
                record["fub_skip"] = "fub_removed"
            summary["skipped"] += 1
            summary["skips"].append({"case": key, "reason": "fub_removed"})
            print(f"FUB skip {key or '(no case)'}: fub_removed")
            _progress_fub(summary, "fub_removed", key)
            continue
        existing_id = (
            None
            if needs_fub_create(state, key, row)
            else stored_person_id(state, key, row)
        )
        if forced_id is not None:
            existing_id = forced_id
        reason = gate_reason(
            row,
            state,
            mapping,
            strict_property=strict,
            existing_id=existing_id,
        )
        if reason:
            summary["skipped"] += 1
            summary["skips"].append({"case": key, "reason": reason})
            if key and key in cases:
                cases[key]["fub_skip"] = reason
                if reason != "fub_removed" and stored_person_id(state, key) is None:
                    cases[key].pop("fub_person_id", None)
            print(f"FUB skip {key or '(no case)'}: {reason}")
            _progress_fub(summary, "skipped", key)
            continue
        person = build_person(
            row,
            mapping,
            settings,
            person_id=existing_id,
            allowed_custom=allowed_custom,
        )
        fingerprint = person_fingerprint(person)
        record = cases.get(key) or {}
        try:
            if existing_id is not None:
                if _one_person_verify_run(
                    verify=verify, update_existing=update_existing
                ) and (summary["posted"] >= 1 or summary["updated"] >= 1):
                    summary["skipped"] += 1
                    summary["skips"].append({"case": key, "reason": "verify_only_limit"})
                    print(f"FUB skip {key}: verify_only_limit")
                    _progress_fub(summary, "verify-only skip", key)
                    continue
                live = get_person(
                    settings["api_url"], api_key, existing_id, system
                )
                if live is None:
                    _mark_fub_removed(cases, key, existing_id)
                    summary["skipped"] += 1
                    summary["skips"].append({"case": key, "reason": "fub_removed"})
                    _progress_fub(summary, "fub_removed", key)
                    continue
                if should_skip_unchanged_person(
                    existing_id=existing_id,
                    record=record,
                    fingerprint=fingerprint,
                    verify=verify,
                    update_existing=update_existing,
                ):
                    summary["skipped"] += 1
                    summary["skips"].append({"case": key, "reason": "unchanged"})
                    print(f"FUB skip {key}: unchanged person_id={existing_id}")
                    _progress_fub(summary, "unchanged", key)
                    continue
                record_view = verify_record_payload(
                    row, person, existing_id, settings, mapping
                )
                record_view["view_only"] = False
                record_view["posted"] = False
                record_view["updated"] = False
                summary["verify_record"] = record_view
                _log_fub_person_payload(key, row, person)
                body = put_person(
                    settings["api_url"], api_key, existing_id, person, system
                )
                if body is None:
                    _mark_fub_removed(cases, key, existing_id)
                    summary["skipped"] += 1
                    summary["skips"].append({"case": key, "reason": "fub_removed"})
                    _progress_fub(summary, "fub_removed", key)
                    continue
                else:
                    pid = person_id_from_response(body) or existing_id
                    _remember_person(cases, key, pid, fingerprint)
                    summary["updated"] += 1
                    posted_case = key
                    posted_pid = pid
                    record_view["posted"] = True
                    record_view["updated"] = True
                    record_view["fub_person_id"] = int(pid)
                    record_view["fub_error"] = None
                    summary["verify_record"] = record_view
                    print(f"FUB updated {key} person_id={pid}")
                    _progress_fub(summary, "updated", key)
                    if verify:
                        state["last_fub_verify_case"] = key
                    try:
                        upsert_probate_note(
                            settings["api_url"],
                            api_key,
                            pid,
                            combined_notes(row, mapping),
                            system,
                            subject=probate_note_subject(row),
                            cases=cases,
                            key=key,
                        )
                    except Exception as note_exc:  # noqa: BLE001
                        print(f"FUB notes error {key}: {note_exc}", flush=True)
                    try:
                        court_note = post_court_portal_note(
                            row,
                            pid,
                            mapping=mapping,
                            api_url=settings["api_url"],
                            api_key=api_key,
                            system=system,
                            cases=cases,
                            key=key,
                            force=refresh,
                        )
                        record_view["court_url_note"] = court_note
                    except Exception as court_exc:  # noqa: BLE001
                        record_view["court_url_note"] = {
                            "ok": False,
                            "reason": str(court_exc)[:300],
                        }
                        print(f"FUB court URL notes error {key}: {court_exc}", flush=True)
                    try:
                        attached = attach_de111_file(
                            row,
                            pid,
                            mapping=mapping,
                            api_url=settings["api_url"],
                            api_key=api_key,
                            system=system,
                            cases=cases,
                            key=key,
                            force=refresh,
                        )
                        record_view["de111_attach"] = attached
                        summary["verify_record"] = record_view
                    except Exception as file_exc:  # noqa: BLE001
                        record_view["de111_attach"] = {"ok": False, "reason": str(file_exc)[:300]}
                        summary["verify_record"] = record_view
                        print(f"FUB files error {key}: {file_exc}", flush=True)
                    try:
                        duties = attach_de147_file(
                            row,
                            pid,
                            mapping=mapping,
                            api_url=settings["api_url"],
                            api_key=api_key,
                            system=system,
                            cases=cases,
                            key=key,
                            force=refresh,
                        )
                        record_view["de147_attach"] = duties
                        summary["verify_record"] = record_view
                    except Exception as duties_exc:  # noqa: BLE001
                        record_view["de147_attach"] = {"ok": False, "reason": str(duties_exc)[:300]}
                        summary["verify_record"] = record_view
                        print(f"FUB DE-147 notes error {key}: {duties_exc}", flush=True)
                    if _one_person_verify_run(
                        verify=verify, update_existing=update_existing
                    ):
                        break
                    continue
            if _one_person_verify_run(
                verify=verify, update_existing=update_existing
            ) and (summary["posted"] >= 1 or summary["updated"] >= 1):
                summary["skipped"] += 1
                summary["skips"].append({"case": key, "reason": "verify_only_limit"})
                print(f"FUB skip {key}: verify_only_limit")
                _progress_fub(summary, "verify-only skip", key)
                continue
            record_view = verify_record_payload(row, person, existing_id, settings, mapping)
            record_view["view_only"] = False
            record_view["posted"] = False
            summary["verify_record"] = record_view
            _log_fub_person_payload(key, row, person)
            payload = build_event(
                row,
                mapping,
                settings,
                person=person,
                allowed_custom=allowed_custom,
            )
            body = post_event(settings["api_url"], api_key, payload, system)
            pid = person_id_from_response(body)
            if pid is None:
                raise RuntimeError(
                    "FUB create returned no person id; refusing to continue without a trackable ID"
                )
            _remember_person(cases, key, pid, fingerprint)
            try:
                synced = put_person(
                    settings["api_url"], api_key, pid, person, system
                )
                if synced is None:
                    print(
                        f"FUB create-sync PUT skipped {key} person_id={pid} (404)",
                        flush=True,
                    )
            except Exception as put_exc:  # noqa: BLE001
                print(f"FUB create-sync PUT error {key}: {put_exc}", flush=True)
            try:
                upsert_probate_note(
                    settings["api_url"],
                    api_key,
                    pid,
                    combined_notes(row, mapping),
                    system,
                    subject=probate_note_subject(row),
                    cases=cases,
                    key=key,
                )
            except Exception as note_exc:  # noqa: BLE001
                print(f"FUB notes error {key}: {note_exc}", flush=True)
            try:
                court_note = post_court_portal_note(
                    row,
                    pid,
                    mapping=mapping,
                    api_url=settings["api_url"],
                    api_key=api_key,
                    system=system,
                    cases=cases,
                    key=key,
                    force=refresh,
                )
                record_view["court_url_note"] = court_note
            except Exception as court_exc:  # noqa: BLE001
                record_view["court_url_note"] = {
                    "ok": False,
                    "reason": str(court_exc)[:300],
                }
                print(f"FUB court URL notes error {key}: {court_exc}", flush=True)
            try:
                attached = attach_de111_file(
                    row,
                    pid,
                    mapping=mapping,
                    api_url=settings["api_url"],
                    api_key=api_key,
                    system=system,
                    cases=cases,
                    key=key,
                    force=refresh,
                )
                record_view["de111_attach"] = attached
            except Exception as file_exc:  # noqa: BLE001
                record_view["de111_attach"] = {"ok": False, "reason": str(file_exc)[:300]}
                print(f"FUB files error {key}: {file_exc}", flush=True)
            try:
                duties = attach_de147_file(
                    row,
                    pid,
                    mapping=mapping,
                    api_url=settings["api_url"],
                    api_key=api_key,
                    system=system,
                    cases=cases,
                    key=key,
                    force=refresh,
                )
                record_view["de147_attach"] = duties
            except Exception as duties_exc:  # noqa: BLE001
                record_view["de147_attach"] = {"ok": False, "reason": str(duties_exc)[:300]}
                print(f"FUB DE-147 notes error {key}: {duties_exc}", flush=True)
            summary["posted"] += 1
            posted_case = key
            posted_pid = pid
            record_view["posted"] = True
            record_view["fub_person_id"] = int(pid)
            record_view["fub_error"] = None
            summary["verify_record"] = record_view
            print(f"FUB posted {key} person_id={pid}")
            _progress_fub(summary, "posted", key)
            if verify:
                state["last_fub_verify_case"] = key
                if _one_person_verify_run(
                    verify=verify, update_existing=update_existing
                ):
                    break
        except Exception as exc:  # noqa: BLE001
            summary["skipped"] += 1
            err = str(exc)
            summary["error"] = err[:500]
            summary["skips"].append({"case": key, "reason": "fub_http_error"})
            if key and key in cases:
                cases[key]["fub_skip"] = "post_failed"
            if summary.get("verify_record"):
                summary["verify_record"]["posted"] = False
                summary["verify_record"]["fub_error"] = err[:500]
            print(f"FUB error {key}: {err}", flush=True)
            continue
    summary["verify_case"] = posted_case
    summary["verify_person_id"] = posted_pid
    if verify:
        if posted_case:
            action = "updated" if summary.get("updated") else "posted"
            print(
                f"FUB verify: {action} {posted_case} person_id={posted_pid}",
                flush=True,
            )
        else:
            rec = summary.get("verify_record") or {}
            err = summary.get("error")
            skips = summary.get("skips") or []
            if rec.get("case_number") and err:
                note = (
                    f"Mapped {rec.get('case_number')} but Follow Up Boss rejected it: {err}"
                )
            else:
                note = "No new go-case imported"
                if skips:
                    sample = ", ".join(
                        f"{item.get('case') or '?'}={item.get('reason')}"
                        for item in skips[:5]
                    )
                    note = f"{note}. Skips: {sample}"
            summary["verify_note"] = note
            print(f"FUB verify: {note}", flush=True)
    mapping_dir = mapping_path
    if mapping_dir is None:
        raw = str(os.environ.get("FUB_MAPPING_PATH") or "").strip()
        mapping_dir = Path(raw) if raw else None
    if mapping_dir:
        persist_fub_removed_on_listings(Path(mapping_dir).resolve().parent, cases)
    print(
        f"FUB: posted={summary['posted']} updated={summary['updated']} "
        f"skipped={summary['skipped']}",
        flush=True,
    )
    return summary
