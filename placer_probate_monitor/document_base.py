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
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _add_url(found: list[str], value) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    if "://" in text or NABU_UI_HOST in text or text.startswith("hooks."):
        if "://" not in text:
            text = "https://" + text.lstrip("/")
        found.append(text)


def urls_from_cloud_object(cloud) -> list[str]:
    """Remote UI and cloudhook URLs stored on ``hass.data['cloud']``."""
    found: list[str] = []
    if cloud is None:
        return found
    remote = _attr(cloud, "remote")
    for name in ("instance_domain", "remote_ui_url", "ui_url", "remote_domain"):
        _add_url(found, _attr(remote, name))
        _add_url(found, _attr(cloud, name))
    client = _attr(cloud, "client")
    prefs = _attr(client, "prefs")
    _add_url(found, _attr(prefs, "remote_domain"))
    _add_url(found, _attr(prefs, "remote_ui_url"))
    raw_prefs = _attr(prefs, "_prefs")
    if isinstance(raw_prefs, dict):
        _add_url(found, raw_prefs.get("remote_domain"))
    _add_url(found, _attr(remote, "_instance_domain"))
    aliases = _attr(remote, "alias")
    if aliases is None:
        aliases = _attr(remote, "_alias")
    if isinstance(aliases, (list, tuple)):
        for alias in aliases:
            if isinstance(alias, str) and NABU_UI_HOST in alias:
                _add_url(found, alias)
    for source in (
        _attr(prefs, "cloudhooks"),
        _attr(client, "cloudhooks"),
        _attr(cloud, "cloudhooks"),
    ):
        if isinstance(source, dict):
            hooks = list(source.values())
        elif isinstance(source, (list, tuple)):
            hooks = list(source)
        else:
            continue
        for hook in hooks:
            if isinstance(hook, str):
                _add_url(found, hook)
            elif isinstance(hook, dict):
                _add_url(found, hook.get("cloudhook_url") or hook.get("url"))
            else:
                _add_url(found, _attr(hook, "cloudhook_url"))
                _add_url(found, _attr(hook, "url"))
    return found


def urls_from_cloud_storage(path) -> list[str]:
    """``remote_domain`` saved in ``.storage/cloud``.

    Cloudhook URLs in that file are ignored. They are ``hooks.nabu.casa``
    webhook addresses, not the document API, and they carry webhook secrets.
    """
    found: list[str] = []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return found
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return found
    _add_url(found, data.get("remote_domain"))
    return found


def _cloud_storage_urls(hass) -> list[str]:
    config = getattr(hass, "config", None)
    path_fn = _attr(config, "path")
    if not callable(path_fn):
        return []
    for parts in ((".storage", "cloud"), (".storage/cloud",)):
        try:
            raw_path = path_fn(*parts)
        except TypeError:
            continue
        except Exception:
            return []
        found = urls_from_cloud_storage(raw_path)
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


def collect_url_candidates(hass) -> list[str]:
    """External URL, cloud remote UI, stored remote domain, then LAN fallbacks.

    ``get_url(prefer_external=True)`` returns the LAN address when the
    external URL is unset or is itself a private IP. The Nabu Casa remote UI
    is still collected from the cloud integration and from ``.storage/cloud``
    so it can win over that LAN address.
    """
    candidates: list[str] = []
    config = getattr(hass, "config", None)
    external = _attr(config, "external_url")
    internal = _attr(config, "internal_url")
    if external:
        candidates.append(str(external))
    cloud = None
    data = getattr(hass, "data", None)
    if data is not None:
        try:
            cloud = data.get("cloud")
        except Exception:
            cloud = None
    candidates.extend(urls_from_cloud_object(cloud))
    candidates.extend(_cloud_storage_urls(hass))
    if internal:
        candidates.append(str(internal))
    _append_remote_ui_url(candidates, hass)
    try:
        from homeassistant.helpers.network import get_url

        for kwargs in (
            {"prefer_external": True, "prefer_cloud": True},
            {"prefer_external": True, "require_cloud": True},
            {"prefer_external": True},
        ):
            try:
                found = get_url(hass, **kwargs)
            except Exception:
                continue
            if found:
                candidates.append(str(found))
    except Exception:
        pass
    return [item for item in candidates if str(item or "").strip()]


def peek_nabu_casa_origin(hass, request_url: str = "") -> str:
    """Nabu Casa remote origin, or ``""`` when it is not configured.

    Meant to run on the Home Assistant event loop, where
    ``async_remote_ui_url`` can see the live cloud object. A LAN request URL
    is not returned.
    """
    candidates: list[str] = []
    if request_url and is_nabu_casa_ui_url(request_url):
        candidates.append(str(request_url))
    if hass is not None:
        candidates.extend(collect_url_candidates(hass))
    origin = document_origin(*candidates)
    if not is_nabu_casa_ui_url(origin):
        return ""
    return nabu_casa_origin(origin)


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
