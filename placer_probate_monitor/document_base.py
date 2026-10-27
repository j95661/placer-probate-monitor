"""Pick the public Home Assistant origin used in probate document links.

Nabu Casa remote UI (``https://*.ui.nabu.casa``) wins over a LAN address.
A specific instance hostname is never hardcoded. ``hooks.nabu.casa`` cloudhooks
are not the document API; they are only a signal to read the remote UI host
from the cloud integration.
"""

from __future__ import annotations

import ipaddress
import os
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
    text = str(url or "").strip()
    if not text or not is_local_or_private_url(text):
        return text
    if not is_nabu_casa_ui_url(nabu_base):
        return text
    origin = nabu_casa_origin(nabu_base)
    if not origin:
        return text
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


def collect_url_candidates(hass) -> list[str]:
    """External URL, cloud remote UI, cloudhooks, then ``get_url`` fallbacks."""
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
    if internal:
        candidates.append(str(internal))
    try:
        from homeassistant.components.cloud import async_remote_ui_url

        candidates.append(str(async_remote_ui_url(hass)))
    except Exception:
        pass
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


def apply_document_base(hass) -> str:
    """Point DE-111 and DE-147 links at Nabu Casa when that remote URL exists.

    Returns the origin that was selected. An empty string means nothing was
    configured; callers leave any previous base alone only when ``hass`` is
    missing. When ``hass`` is present and no URL can be resolved, the caller
    may clear the bases.
    """
    if hass is None:
        return ""
    origin = document_origin(*collect_url_candidates(hass))
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
