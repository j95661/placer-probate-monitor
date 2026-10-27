"""Pick the public Home Assistant origin used in probate document links.

Nabu Casa remote UI (``https://*.ui.nabu.casa``) wins over a LAN address.
A specific instance hostname is never hardcoded. ``hooks.nabu.casa`` cloudhooks
are not the document API; they are only a signal to read the remote UI host
from the cloud integration.
"""

from __future__ import annotations

import inspect
import ipaddress
import json
import os
import re
import ssl
from pathlib import Path
from urllib.parse import urlsplit

NABU_UI_HOST = "ui.nabu.casa"
NABU_UI_SUFFIX = ".ui.nabu.casa"
CLOUDHOOK_HOST = "hooks.nabu.casa"
DOCUMENT_API_MARK = "/api/placer_probate_monitor/"

_LOCAL_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "homeassistant",
    "homeassistant.local",
    "hassio",
    "hassio.local",
}


def _split(url: str):
    text = str(url or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text.lstrip("/")
    parts = urlsplit(text)
    if not parts.hostname:
        return None
    return parts


def hostname_of(url: str) -> str:
    parts = _split(url)
    if not parts or not parts.hostname:
        return ""
    return parts.hostname.lower().rstrip(".")


def is_nabu_casa_ui_url(url: str) -> bool:
    host = hostname_of(url)
    return bool(host) and (host == NABU_UI_HOST or host.endswith(NABU_UI_SUFFIX))


def is_nabu_casa_cloudhook_url(url: str) -> bool:
    host = hostname_of(url)
    return host == CLOUDHOOK_HOST or host.endswith("." + CLOUDHOOK_HOST)


def is_local_or_private_url(url: str) -> bool:
    host = hostname_of(url)
    if not host:
        return False
    if host in _LOCAL_HOSTS or host.endswith(".local") or host.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


def origin_of(url: str) -> str:
    parts = _split(url)
    if not parts or not parts.hostname:
        return ""
    scheme = parts.scheme or "http"
    return f"{scheme}://{parts.netloc}".rstrip("/")


def nabu_casa_origin(url: str) -> str:
    """``https://<instance>.ui.nabu.casa`` with no path."""
    if not is_nabu_casa_ui_url(url):
        return ""
    parts = _split(url)
    if not parts or not parts.hostname:
        return ""
    host = parts.hostname
    port = parts.port
    if port and port not in (80, 443):
        return f"https://{host}:{port}"
    return f"https://{host}"


_UI_HOST_RE = re.compile(r"(?:[a-z0-9-]+\.)+ui\.nabu\.casa", re.I)
_STORAGE_HOST_KEYS = (
    "remote_domain",
    "remote_ui",
    "remote_ui_url",
    "instance_domain",
)


def document_api_path(url: str) -> str:
    """Return ``/api/placer_probate_monitor/...`` or another relative path."""
    text = str(url or "").strip()
    if not text:
        return ""
    idx = text.find(DOCUMENT_API_MARK)
    if idx >= 0:
        return text[idx:].split("#", 1)[0]
    if text.startswith("/") and not text.startswith("//"):
        return text.split("#", 1)[0]
    return ""


def _document_api_base_path(url: str) -> str:
    parts = _split(url)
    if not parts:
        return ""
    path = parts.path or ""
    idx = path.find(DOCUMENT_API_MARK)
    if idx < 0:
        return ""
    segments = [seg for seg in path[idx:].split("/") if seg]
    if len(segments) >= 3:
        return "/" + "/".join(segments[:3])
    if segments:
        return "/" + "/".join(segments)
    return ""


def choose_document_base(*candidates: str, fallback: str = "") -> str:
    """Return the document base. A Nabu Casa UI URL beats every LAN address.

    Candidates may be origins or full ``/api/placer_probate_monitor/de111``
    bases. When a Nabu Casa origin is present, the API prefix from any
    candidate is kept and the LAN host is dropped.
    """
    ordered: list[str] = []
    for item in (*candidates, fallback):
        text = str(item or "").strip()
        if text:
            ordered.append(text)
    if not ordered:
        return ""

    nabu_origin = ""
    for item in ordered:
        origin = nabu_casa_origin(item)
        if origin:
            nabu_origin = origin
            break

    api_path = ""
    for item in ordered:
        path = _document_api_base_path(item)
        if path:
            api_path = path
            break

    if nabu_origin:
        return f"{nabu_origin}{api_path}".rstrip("/") if api_path else nabu_origin

    for item in ordered:
        if is_local_or_private_url(item) or is_nabu_casa_cloudhook_url(item):
            continue
        return item.rstrip("/")
    for item in ordered:
        if is_nabu_casa_cloudhook_url(item):
            continue
        return item.rstrip("/")
    return ""


def document_origin(*candidates: str, fallback: str = "") -> str:
    """Scheme and host only. Nabu Casa when configured, otherwise a fallback."""
    chosen = choose_document_base(*candidates, fallback=fallback)
    if not chosen:
        return ""
    if is_nabu_casa_ui_url(chosen):
        return nabu_casa_origin(chosen)
    return origin_of(chosen)


def rewrite_local_document_url(url: str, nabu_base: str) -> str:
    """Swap a LAN host for the Nabu Casa origin. The path stays the same."""
    return public_document_url(url, nabu_base)


def should_rewrite_document_url(url: str) -> bool:
    """True when a browser would otherwise open this document on the LAN.

    Relative ``/api/...`` hrefs resolve against whatever host opened Home
    Assistant, including a 192.168 address. A bare ``host:8123`` URL is this
    instance's local API even when the host is not a private IP.
    """
    text = str(url or "").strip()
    if not text:
        return False
    if text.startswith("/") and not text.startswith("//"):
        return True
    if "://" not in text:
        text = "http://" + text.lstrip("/")
    if is_local_or_private_url(text):
        return True
    parts = _split(text)
    if not parts or not parts.hostname:
        return False
    host = parts.hostname.lower().rstrip(".")
    if parts.port == 8123:
        return True
    if "." not in host:
        return True
    if host.endswith(".home") or host.endswith(".localdomain"):
        return True
    return False


def public_document_url(url: str, nabu_base: str) -> str:
    """Absolute ``https://<instance>.ui.nabu.casa/...`` document URL.

    Private IPs, localhost, relative paths, and ``host:8123`` are rewritten.
    A URL that is already on Nabu Casa, or a non-local URL when no remote UI
    is configured, is returned unchanged. ``hooks.nabu.casa`` is never used
    as the document host.
    """
    text = str(url or "").strip()
    if not text:
        return ""
    if not is_nabu_casa_ui_url(nabu_base):
        return text
    origin = nabu_casa_origin(nabu_base)
    if not origin or not should_rewrite_document_url(text):
        return text
    if text.startswith("/") and not text.startswith("//"):
        return f"{origin}{text}"
    parts = _split(text)
    if not parts:
        return text
    path = parts.path or ""
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return f"{origin}{path}{query}{fragment}"


def _attr(obj, name: str):
    if obj is None:
        return None
    try:
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)
    except Exception:
        return None


def _add_url(found: list[str], value) -> None:
    if value is None or isinstance(value, bool):
        return
    text = str(value).strip()
    if not text:
        return
    if "://" in text or NABU_UI_HOST in text or text.startswith("hooks."):
        if "://" not in text:
            text = "https://" + text.lstrip("/")
        if text not in found:
            found.append(text)


def _add_nabu_host(found: list[str], value) -> None:
    """Keep only ``*.ui.nabu.casa`` hosts. ``hooks.nabu.casa`` is not one."""
    if value is None or isinstance(value, bool):
        return
    text = str(value).strip()
    if not text:
        return
    if is_nabu_casa_cloudhook_url(text):
        return
    if is_nabu_casa_ui_url(text) or NABU_UI_HOST in text:
        _add_url(found, text)


def _certificate_names(cert) -> list[str]:
    names: list[str] = []
    if cert is None:
        return names
    for attr in ("common_name", "commonName"):
        value = _attr(cert, attr)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    alts = _attr(cert, "alternative_names")
    if alts is None:
        alts = _attr(cert, "alt_names")
    if isinstance(alts, (list, tuple)):
        for alt in alts:
            if isinstance(alt, str) and alt.strip():
                names.append(alt.strip())
    return names


def urls_from_cloud_remote(cloud) -> list[str]:
    """Live remote UI host on ``hass.data['cloud']``.

    Preference inside this object is ``remote_domain`` / ``remote_ui``, then
    ``instance_domain``, then the certificate common name. Cloud prefs and
    ``hooks.nabu.casa`` are not read here.
    """
    found: list[str] = []
    if cloud is None:
        return found
    remote = _attr(cloud, "remote")
    for name in ("remote_domain", "remote_ui", "remote_ui_url", "ui_url"):
        _add_nabu_host(found, _attr(remote, name))
        _add_nabu_host(found, _attr(cloud, name))
    for name in ("instance_domain", "_instance_domain"):
        _add_nabu_host(found, _attr(remote, name))
        _add_nabu_host(found, _attr(cloud, name))
    for cert in (
        _attr(remote, "certificate"),
        _attr(remote, "_acme"),
        _attr(cloud, "certificate"),
    ):
        for name in _certificate_names(cert):
            _add_nabu_host(found, name)
        _add_nabu_host(found, _attr(cert, "domain"))
    aliases = _attr(remote, "alias")
    if aliases is None:
        aliases = _attr(remote, "_alias")
    if isinstance(aliases, (list, tuple)):
        for alias in aliases:
            _add_nabu_host(found, alias)
    return found


def urls_from_cloud_prefs(cloud) -> list[str]:
    """``remote_domain`` / ``remote_ui`` on ``cloud.client.prefs``."""
    found: list[str] = []
    if cloud is None:
        return found
    client = _attr(cloud, "client")
    prefs = _attr(client, "prefs")
    sources = [prefs, _attr(prefs, "_prefs"), client, cloud]
    for source in sources:
        if source is None:
            continue
        for name in ("remote_domain", "remote_ui", "remote_ui_url"):
            _add_nabu_host(found, _attr(source, name))
    return found


def _cloudhook_values(cloud) -> list:
    hooks = []
    if cloud is None:
        return hooks
    client = _attr(cloud, "client")
    prefs = _attr(client, "prefs")
    for source in (
        _attr(prefs, "cloudhooks"),
        _attr(client, "cloudhooks"),
        _attr(cloud, "cloudhooks"),
    ):
        if isinstance(source, dict):
            values = list(source.values())
        elif isinstance(source, (list, tuple)):
            values = list(source)
        else:
            continue
        for hook in values:
            if isinstance(hook, str):
                hooks.append(hook)
            elif isinstance(hook, dict):
                hooks.append(hook.get("cloudhook_url") or hook.get("url"))
            else:
                hooks.append(_attr(hook, "cloudhook_url"))
                hooks.append(_attr(hook, "url"))
    return hooks


def urls_from_cloud_object(cloud) -> list[str]:
    """Remote UI, prefs, and cloudhook URLs stored on ``hass.data['cloud']``."""
    found: list[str] = []
    found.extend(urls_from_cloud_remote(cloud))
    found.extend(urls_from_cloud_prefs(cloud))
    for hook in _cloudhook_values(cloud):
        _add_url(found, hook)
    return found


def urls_from_cloud_storage(path) -> list[str]:
    """Remote UI host saved in ``.storage/cloud``.

    ``remote_domain`` wins, then ``remote_ui``. Any other ``*.ui.nabu.casa``
    host in the file is kept. ``hooks.nabu.casa`` webhook URLs are ignored
    so their secrets are never used as the document host.
    """
    found: list[str] = []
    try:
        raw = Path(path).read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return found
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    for key in _STORAGE_HOST_KEYS:
        _add_nabu_host(found, data.get(key))
    nested = data.get("prefs") if isinstance(data, dict) else None
    if isinstance(nested, dict):
        for key in _STORAGE_HOST_KEYS:
            _add_nabu_host(found, nested.get(key))
    for host in _UI_HOST_RE.findall(raw):
        _add_nabu_host(found, host)
    return found


def urls_from_certificate_file(path) -> list[str]:
    """Common name on ``.cloud/remote_fullchain.pem`` when it is the remote UI."""
    found: list[str] = []
    try:
        decoded = ssl._ssl._test_decode_cert(os.fspath(path))
    except Exception:
        return found
    names: list[str] = []
    for rdn in decoded.get("subject") or ():
        for item in rdn:
            if (
                isinstance(item, (list, tuple))
                and len(item) >= 2
                and item[0] == "commonName"
            ):
                names.append(str(item[1]))
    for item in decoded.get("subjectAltName") or ():
        if isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == "DNS":
            names.append(str(item[1]))
    for name in names:
        _add_nabu_host(found, name)
    return found


def _config_dir(hass) -> str:
    config = getattr(hass, "config", None)
    raw = _attr(config, "config_dir")
    if raw:
        return str(raw)
    path_fn = _attr(config, "path")
    if not callable(path_fn):
        return ""
    for args in ((), ("x",)):
        try:
            sample = path_fn(*args)
        except TypeError:
            continue
        except Exception:
            return ""
        if not sample:
            continue
        path = Path(str(sample))
        return str(path if not args else path.parent)
    return ""


def _cloud_from_hass(hass):
    data = getattr(hass, "data", None)
    if data is None:
        return None
    try:
        return data.get("cloud")
    except Exception:
        return None


def _path_candidates(hass, *relative: str) -> list[str]:
    paths: list[str] = []
    config = getattr(hass, "config", None)
    path_fn = _attr(config, "path")
    if callable(path_fn):
        try:
            paths.append(str(path_fn(*relative)))
        except TypeError:
            try:
                paths.append(str(path_fn("/".join(relative))))
            except Exception:
                pass
        except Exception:
            pass
    config_dir = _config_dir(hass)
    if config_dir:
        paths.append(str(Path(config_dir).joinpath(*relative)))
    unique: list[str] = []
    for path in paths:
        if path and path not in unique:
            unique.append(path)
    return unique


def _cloud_storage_urls(hass) -> list[str]:
    for raw_path in _path_candidates(hass, ".storage", "cloud"):
        found = urls_from_cloud_storage(raw_path)
        if found:
            return found
    return []


def _certificate_file_urls(hass, cloud) -> list[str]:
    paths: list[str] = []
    path_fn = _attr(cloud, "path")
    if callable(path_fn):
        try:
            paths.append(str(path_fn("remote_fullchain.pem")))
        except Exception:
            pass
    paths.extend(_path_candidates(hass, ".cloud", "remote_fullchain.pem"))
    seen: set[str] = set()
    for raw_path in paths:
        if not raw_path or raw_path in seen:
            continue
        seen.add(raw_path)
        found = urls_from_certificate_file(raw_path)
        if found:
            return found
    return []


def _append_remote_ui_url(candidates: list[str], hass) -> None:
    """Call ``async_remote_ui_url`` without treating a coroutine as a URL."""
    try:
        from homeassistant.components.cloud import async_remote_ui_url
    except Exception:
        return
    try:
        found = async_remote_ui_url(hass)
    except Exception:
        return
    if inspect.iscoroutine(found):
        found.close()
        return
    if found:
        candidates.append(str(found))


def _get_url_candidates(hass) -> list[str]:
    found: list[str] = []
    try:
        from homeassistant.helpers.network import get_url
    except Exception:
        return found
    for kwargs in (
        {"prefer_external": True, "prefer_cloud": True},
        {"prefer_external": True, "require_cloud": True},
        {"prefer_external": True},
    ):
        try:
            url = get_url(hass, **kwargs)
        except TypeError:
            try:
                url = get_url(hass)
            except Exception:
                continue
        except Exception:
            continue
        if url:
            found.append(str(url))
    return found


def _configured_url(hass, name: str) -> str:
    config = getattr(hass, "config", None)
    value = _attr(config, name)
    return str(value).strip() if value else ""


def collect_url_candidates(hass) -> list[str]:
    """Nabu Casa remote UI first. A private ``get_url`` result does not win.

    Order when a host is present:

    1. Cloud ``remote_domain`` / ``remote_ui`` / certificate common name
    2. ``external_url`` only when it is ``*.ui.nabu.casa``
    3. ``.storage/cloud``
    4. ``cloud.client`` prefs
    5. The remote UI certificate file, then ``async_remote_ui_url`` / ``get_url``
       when those themselves return ``*.ui.nabu.casa``

    LAN addresses, localhost, and ``host:8123`` stay at the end and are used
    only when no Nabu Casa remote UI host exists. ``hooks.nabu.casa`` is never
    a document host.
    """
    cloud = _cloud_from_hass(hass)
    external = _configured_url(hass, "external_url")
    internal = _configured_url(hass, "internal_url")
    live: list[str] = []
    _append_remote_ui_url(live, hass)
    live.extend(_get_url_candidates(hass))
    nabu_live = [item for item in live if is_nabu_casa_ui_url(item)]
    other_live = [item for item in live if not is_nabu_casa_ui_url(item)]
    hook_ui = [
        str(item)
        for item in _cloudhook_values(cloud)
        if item and is_nabu_casa_ui_url(str(item)) and not is_nabu_casa_cloudhook_url(str(item))
    ]
    ordered = [
        *urls_from_cloud_remote(cloud),
        *([external] if external and is_nabu_casa_ui_url(external) else []),
        *_cloud_storage_urls(hass),
        *urls_from_cloud_prefs(cloud),
        *_certificate_file_urls(hass, cloud),
        *hook_ui,
        *nabu_live,
        *([external] if external and not is_nabu_casa_ui_url(external) else []),
        *([internal] if internal else []),
        *other_live,
    ]
    unique: list[str] = []
    for item in ordered:
        text = str(item or "").strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def _storage_probe_note(hass) -> str:
    if hass is None:
        return ""
    paths = _path_candidates(hass, ".storage", "cloud")
    existing = next((path for path in paths if Path(path).is_file()), "")
    if not existing:
        return ".storage/cloud was not found."
    try:
        payload = json.loads(Path(existing).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ".storage/cloud could not be read."
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return ".storage/cloud has no data object."
    hosts = [
        str(data.get(key) or "").strip()
        for key in ("remote_domain", "remote_ui", "remote_ui_url")
    ]
    if any(is_nabu_casa_ui_url(host) for host in hosts):
        return ""
    if any(hosts):
        return ".storage/cloud remote_domain/remote_ui is not a *.ui.nabu.casa host."
    if "google_enabled" in data or "remote_enabled" in data:
        return (
            ".storage/cloud is present (google_enabled/remote_enabled) but "
            "remote_domain and remote_ui are empty."
        )
    return ".storage/cloud has no remote_domain or remote_ui."


def explain_missing_nabu_origin(hass, candidates: list[str] | None = None) -> str:
    """Why the listings payload refused a private document host."""
    local: list[str] = []
    saw_hook = False
    for item in candidates or []:
        if is_nabu_casa_cloudhook_url(item):
            saw_hook = True
            continue
        if is_nabu_casa_ui_url(item):
            continue
        if (
            is_local_or_private_url(item)
            or should_rewrite_document_url(item)
        ):
            host = hostname_of(item) or "local"
            if host not in local:
                local.append(host)
    parts = [
        "No Nabu Casa remote UI host found.",
        "Checked cloud remote_domain/remote_ui/certificate, external_url "
        "when it is *.ui.nabu.casa, .storage/cloud, and cloud.client prefs.",
    ]
    if local:
        parts.append(
            "Ignored private or local hosts from internal_url, external_url, "
            "or get_url (" + ", ".join(local) + ")."
        )
    else:
        parts.append("internal_url and get_url did not return *.ui.nabu.casa.")
    note = _storage_probe_note(hass)
    if note:
        parts.append(note)
    if saw_hook:
        parts.append("hooks.nabu.casa was not used as the document host.")
    parts.append("Private document links were left out of the listings payload.")
    return " ".join(parts)


def discover_nabu_origin(hass, *extra) -> tuple[str, str]:
    """``(https://<instance>.ui.nabu.casa, "")`` or ``("", reason)``.

    A private IP, localhost, or ``host:8123`` is never returned, including
    when that is what ``get_url`` or the page request host reports.
    """
    candidates: list[str] = []
    if hass is not None:
        candidates.extend(collect_url_candidates(hass))
    # A Nabu Casa request host is only a fallback. Cloud remote_domain /
    # remote_ui already in ``candidates`` stays ahead of it. A LAN request
    # host is ignored so opening the page on 192.168.x.x:8123 cannot win.
    for item in extra:
        text = str(item or "").strip()
        if text and is_nabu_casa_ui_url(text) and text not in candidates:
            candidates.append(text)
    hinted = [item for item in candidates if is_nabu_casa_ui_url(item)]
    origin = document_origin(*candidates)
    if is_nabu_casa_ui_url(origin):
        return nabu_casa_origin(origin), ""
    if hass is None and not hinted:
        return "", "Home Assistant is not available to read the Nabu Casa remote UI host."
    return "", explain_missing_nabu_origin(hass, candidates)


def peek_nabu_casa_origin(hass, request_url: str = "") -> str:
    """Nabu Casa remote origin, or ``""`` when it is not configured.

    Meant to run on the Home Assistant event loop, where
    ``async_remote_ui_url`` can see the live cloud object. A LAN request URL
    is not returned.
    """
    origin, _error = discover_nabu_origin(
        hass,
        request_url if is_nabu_casa_ui_url(request_url) else "",
    )
    return origin


def apply_document_base(hass, *extra) -> str:
    """Point DE-111 and DE-147 links at Nabu Casa when that remote URL exists.

    Returns the origin that was selected. An empty string means nothing was
    configured; callers leave any previous base alone only when ``hass`` is
    missing. When ``hass`` is present and no URL can be resolved, the caller
    may clear the bases.
    """
    if hass is None:
        return ""
    origin = document_origin(*extra, *collect_url_candidates(hass))
    if not origin:
        return ""
    os.environ["FUB_PETITION_BASE_URL"] = (
        f"{origin}/api/placer_probate_monitor/de111"
    )
    os.environ["FUB_DUTIES_BASE_URL"] = (
        f"{origin}/api/placer_probate_monitor/de147"
    )
    if is_nabu_casa_ui_url(origin):
        os.environ["FUB_NABU_CASA_URL"] = nabu_casa_origin(origin) or origin
    else:
        os.environ.pop("FUB_NABU_CASA_URL", None)
    return origin
