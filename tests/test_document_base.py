#!/usr/bin/env python3
"""Document links use Nabu Casa instead of the Home Assistant LAN address."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
# Root copies own the shared Nabu Casa helpers. The installed 1.3.155
# component is a different tree and is exercised by its own regression test.
sys.path.insert(0, str(ROOT))

from document_base import (  # noqa: E402
    apply_document_base,
    choose_document_base,
    discover_nabu_origin,
    document_origin,
    public_document_url,
    rewrite_local_document_url,
    urls_from_cloud_object,
)
from fub_client import (  # noqa: E402
    form_public_uri,
    listing_document_links,
    publicize_listing_row,
)

PRIVATE_HREF = re.compile(
    r"(192\.168\.|10\.\d+\.|172\.(1[6-9]|2\d|3[0-1])\.|127\.|0\.0\.0\.0|localhost|\[::1\]|:8123\b)",
    re.I,
)

LOCAL = "http://192.168.1.23:8123"
LOCAL_DE111 = LOCAL + "/api/placer_probate_monitor/de111"
LOCAL_FILE = (
    LOCAL + "/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf"
)
NABU_A = "https://alpha.ui.nabu.casa"
NABU_B = "https://bravo.ui.nabu.casa"


class _FakeHass:
    def __init__(self, external=None, internal=None, cloud=None):
        self.config = SimpleNamespace(external_url=external, internal_url=internal)
        self.data = {"cloud": cloud} if cloud is not None else {}


def _cloud(domain="", hook=""):
    hooks = {}
    if hook:
        hooks["probate"] = {"cloudhook_url": hook}
    prefs = SimpleNamespace(remote_domain=domain, cloudhooks=hooks)
    client = SimpleNamespace(prefs=prefs, cloudhooks=hooks)
    remote = SimpleNamespace(instance_domain=domain)
    return SimpleNamespace(remote=remote, client=client)


class DocumentBaseTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "FUB_PETITION_BASE_URL",
                "FUB_DUTIES_BASE_URL",
                "FUB_NABU_CASA_URL",
                "FUB_PETITION_TOKEN_SECRET",
            )
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_local_ip_base_is_not_chosen_when_nabu_casa_is_available(self):
        for host in (NABU_A, NABU_B):
            chosen = choose_document_base(LOCAL, host)
            self.assertEqual(chosen, host)
            self.assertNotIn("192.168", chosen)
            replaced = choose_document_base(LOCAL_DE111, host)
            self.assertEqual(
                replaced,
                host + "/api/placer_probate_monitor/de111",
            )
            self.assertNotIn("192.168", replaced)
            self.assertFalse(chosen.startswith("http://192.168"))

    def test_local_document_url_is_replaced_with_nabu_casa(self):
        rewritten = rewrite_local_document_url(LOCAL_FILE, NABU_A)
        self.assertEqual(
            rewritten,
            NABU_A + "/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf",
        )
        self.assertNotIn("192.168", rewritten)

    def test_local_fallback_when_nabu_casa_is_not_configured(self):
        chosen = choose_document_base(LOCAL_DE111)
        self.assertEqual(chosen, LOCAL_DE111)

    def test_external_nabu_casa_beats_internal_lan_and_get_url(self):
        origin = document_origin(
            LOCAL,
            "https://cabin.ui.nabu.casa/",
            "http://10.0.0.8:8123",
        )
        self.assertEqual(origin, "https://cabin.ui.nabu.casa")

    def test_cloud_remote_beats_local_ip(self):
        urls = urls_from_cloud_object(_cloud("home.ui.nabu.casa", "https://hooks.nabu.casa/abc"))
        origin = document_origin(LOCAL, *urls, "http://10.1.1.5:8123")
        self.assertEqual(origin, "https://home.ui.nabu.casa")
        self.assertNotIn("192.168", origin)
        self.assertNotIn("hooks.nabu.casa", origin)

    def test_cloudhook_on_remote_ui_host_is_used(self):
        urls = urls_from_cloud_object(
            _cloud("", "https://delta.ui.nabu.casa/api/webhook/abc")
        )
        chosen = choose_document_base(LOCAL_DE111, *urls)
        self.assertEqual(
            chosen,
            "https://delta.ui.nabu.casa/api/placer_probate_monitor/de111",
        )

    def test_hooks_nabu_casa_is_not_the_document_host(self):
        urls = urls_from_cloud_object(_cloud("", "https://hooks.nabu.casa/abc"))
        chosen = choose_document_base(LOCAL_DE111, *urls)
        self.assertEqual(chosen, LOCAL_DE111)
        self.assertNotIn("hooks.nabu.casa", chosen)

    def test_apply_document_base_prefers_cloud_over_lan(self):
        os.environ["FUB_NABU_CASA_URL"] = "https://stale.example"
        hass = _FakeHass(
            external="http://192.168.1.23:8123",
            internal="http://192.168.1.23:8123",
            cloud=_cloud("house.ui.nabu.casa"),
        )
        origin = apply_document_base(hass)
        self.assertEqual(origin, "https://house.ui.nabu.casa")
        self.assertEqual(
            os.environ["FUB_PETITION_BASE_URL"],
            "https://house.ui.nabu.casa/api/placer_probate_monitor/de111",
        )
        self.assertEqual(
            os.environ["FUB_DUTIES_BASE_URL"],
            "https://house.ui.nabu.casa/api/placer_probate_monitor/de147",
        )
        self.assertNotIn("192.168", os.environ["FUB_PETITION_BASE_URL"])
        self.assertEqual(os.environ["FUB_NABU_CASA_URL"], "https://house.ui.nabu.casa")

    def test_apply_document_base_falls_back_to_lan_without_nabu(self):
        os.environ["FUB_NABU_CASA_URL"] = NABU_A
        hass = _FakeHass(internal="http://192.168.1.23:8123")
        origin = apply_document_base(hass)
        self.assertEqual(origin, LOCAL)
        self.assertEqual(
            os.environ["FUB_PETITION_BASE_URL"],
            LOCAL + "/api/placer_probate_monitor/de111",
        )
        self.assertNotIn("FUB_NABU_CASA_URL", os.environ)

    def test_form_public_uri_replaces_local_base(self):
        os.environ["FUB_PETITION_BASE_URL"] = LOCAL_DE111
        os.environ["FUB_NABU_CASA_URL"] = NABU_B
        os.environ["FUB_PETITION_TOKEN_SECRET"] = "test-secret"
        uri = form_public_uri("S-PR-0012345", "de111")
        self.assertTrue(
            uri.startswith(
                "https://bravo.ui.nabu.casa/api/placer_probate_monitor/de111/"
            )
        )
        self.assertTrue(uri.endswith("/S-PR-0012345.pdf"))
        self.assertNotIn("192.168", uri)

    def test_listing_document_link_replaces_local_ip(self):
        os.environ["FUB_PETITION_BASE_URL"] = LOCAL_DE111
        os.environ["FUB_DUTIES_BASE_URL"] = (
            LOCAL + "/api/placer_probate_monitor/de147"
        )
        os.environ["FUB_NABU_CASA_URL"] = NABU_A
        links = listing_document_links(
            {
                "case_number": "S-PR-0012345",
                "documents": [
                    {"label": "DE-111", "url": LOCAL_FILE},
                    {
                        "label": "eCourt",
                        "url": "https://webportal.placerco.org/eCourtPublic/downloadFile/1",
                    },
                ],
            }
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["label"], "DE-111")
        self.assertTrue(links[0]["url"].startswith(NABU_A + "/api/"))
        self.assertNotIn("192.168", links[0]["url"])
        self.assertNotIn("placerco.org", links[0]["url"])

    def test_listings_document_href_is_not_a_private_ip_when_nabu_is_configured(self):
        """The Documents column hrefs are absolute Nabu Casa API URLs.

        Home Assistant external/internal URLs are the LAN address, which is
        what get_url(prefer_external=True) returns. The remote UI host is
        only in .storage/cloud. Every href the listings page would render
        must still be https://<instance>.ui.nabu.casa/api/placer_probate_monitor/...
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / ".storage"
            storage.mkdir()
            (storage / "cloud").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "key": "cloud",
                        "data": {
                            "remote_domain": "house.ui.nabu.casa",
                            "remote_enabled": True,
                            "cloudhooks": {
                                "probate": {
                                    "cloudhook_url": "https://hooks.nabu.casa/secret-token"
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            hass = _FakeHass(
                external="http://192.168.1.23:8123",
                internal="http://10.0.0.8:8123",
            )
            hass.config.path = lambda *parts: str(root.joinpath(*parts))
            origin = apply_document_base(hass)
            self.assertEqual(origin, "https://house.ui.nabu.casa")
            self.assertNotIn("hooks.nabu.casa", origin)

        row = publicize_listing_row(
            {
                "case_number": "S-PR-0012345",
                "de111_url": LOCAL_FILE,
                "de147_url": (
                    "http://10.0.0.8:8123/api/placer_probate_monitor/de147/"
                    "def/S-PR-0012345.pdf"
                ),
                "documents": [
                    {
                        "label": "DE-111",
                        "url": (
                            "http://172.16.5.4:8123/api/placer_probate_monitor/"
                            "de111/tok172/S-PR-0012345.pdf"
                        ),
                    },
                    {
                        "label": "DE-147",
                        "url": (
                            "http://127.0.0.1:8123/api/placer_probate_monitor/"
                            "de147/tok127/S-PR-0012345.pdf"
                        ),
                    },
                    {
                        "label": "DE-111",
                        "url": "/api/placer_probate_monitor/de111/tokrel/S-PR-0012345.pdf",
                    },
                    {
                        "label": "DE-111",
                        "url": (
                            "http://ha-server:8123/api/placer_probate_monitor/"
                            "de111/tokhost/S-PR-0012345.pdf"
                        ),
                    },
                ],
            },
            "https://house.ui.nabu.casa",
        )
        hrefs = [row["de111_url"], row["de147_url"]]
        hrefs.extend(doc["url"] for doc in row["documents"])
        self.assertGreaterEqual(len(hrefs), 2)
        for href in hrefs:
            self.assertTrue(
                href.startswith(
                    "https://house.ui.nabu.casa/api/placer_probate_monitor/"
                ),
                href,
            )
            self.assertIsNone(PRIVATE_HREF.search(href), href)
            self.assertNotIn("hooks.nabu.casa", href)
            self.assertFalse(href.startswith("/"))

    def test_relative_and_bare_host_8123_become_absolute_nabu_urls(self):
        relative = public_document_url(
            "/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf",
            NABU_A,
        )
        bare = public_document_url(
            "ha-server:8123/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf",
            NABU_B,
        )
        self.assertEqual(
            relative,
            NABU_A + "/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf",
        )
        self.assertEqual(
            bare,
            NABU_B + "/api/placer_probate_monitor/de111/abc123/S-PR-0012345.pdf",
        )
        self.assertIsNone(PRIVATE_HREF.search(relative))
        self.assertIsNone(PRIVATE_HREF.search(bare))

    def test_cloud_prefs_dict_beats_lan_when_instance_domain_is_empty(self):
        prefs = SimpleNamespace(_prefs={"remote_domain": "cabin.ui.nabu.casa"})
        remote = SimpleNamespace(instance_domain=None, _instance_domain=None)
        cloud = SimpleNamespace(remote=remote, client=SimpleNamespace(prefs=prefs))
        hass = _FakeHass(
            external="http://192.168.1.23:8123",
            internal="http://192.168.1.23:8123",
            cloud=cloud,
        )
        origin = apply_document_base(hass)
        self.assertEqual(origin, "https://cabin.ui.nabu.casa")
        self.assertNotIn("192.168", os.environ["FUB_PETITION_BASE_URL"])

    def test_storage_cloudhook_alone_is_not_the_document_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / ".storage"
            storage.mkdir()
            (storage / "cloud").write_text(
                json.dumps(
                    {
                        "data": {
                            "cloudhooks": {
                                "probate": {
                                    "cloudhook_url": "https://hooks.nabu.casa/secret"
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            hass = _FakeHass(internal=LOCAL)
            hass.config.path = lambda *parts: str(root.joinpath(*parts))
            origin = apply_document_base(hass)
        self.assertEqual(origin, LOCAL)
        self.assertNotIn("hooks.nabu.casa", os.environ.get("FUB_PETITION_BASE_URL", ""))
        self.assertNotIn("FUB_NABU_CASA_URL", os.environ)

    def _listing_hrefs(self, row):
        hrefs = [row.get("de111_url") or "", row.get("de147_url") or ""]
        for doc in row.get("documents") or []:
            if isinstance(doc, dict):
                hrefs.append(doc.get("url") or "")
            elif isinstance(doc, str):
                hrefs.append(doc)
        return [href for href in hrefs if href]

    def test_private_get_url_does_not_win_over_cloud_remote_domain(self):
        """Documents hrefs stay on Nabu Casa when get_url and internal_url are LAN.

        The listings page is opened at http://192.168.x.x:8123. Home Assistant
        still reports that address from internal_url and get_url. The remote
        UI host is cloud remote_domain, and every href must be absolute.
        """
        import sys
        import types

        saved = {name: sys.modules.get(name) for name in (
            "homeassistant",
            "homeassistant.helpers",
            "homeassistant.helpers.network",
            "homeassistant.components",
            "homeassistant.components.cloud",
        )}
        network = types.ModuleType("homeassistant.helpers.network")
        network.get_url = lambda hass, **kwargs: "http://192.168.1.23:8123"
        cloud_mod = types.ModuleType("homeassistant.components.cloud")
        cloud_mod.async_remote_ui_url = lambda hass: "http://10.0.0.8:8123"
        helpers = types.ModuleType("homeassistant.helpers")
        components = types.ModuleType("homeassistant.components")
        ha = types.ModuleType("homeassistant")
        helpers.network = network
        components.cloud = cloud_mod
        ha.helpers = helpers
        ha.components = components
        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.network"] = network
        sys.modules["homeassistant.components"] = components
        sys.modules["homeassistant.components.cloud"] = cloud_mod
        try:
            remote = SimpleNamespace(
                instance_domain=None,
                remote_domain="house.ui.nabu.casa",
                remote_ui="https://house.ui.nabu.casa",
            )
            prefs = SimpleNamespace(_prefs={"remote_domain": "prefs.ui.nabu.casa"})
            hass = _FakeHass(
                external="http://192.168.1.23:8123",
                internal="http://10.0.0.8:8123",
                cloud=SimpleNamespace(remote=remote, client=SimpleNamespace(prefs=prefs)),
            )
            origin, error = discover_nabu_origin(
                hass,
                "http://192.168.1.50:8123/api/placer_probate_monitor/listings",
            )
            self.assertEqual(origin, "https://house.ui.nabu.casa")
            self.assertEqual(error, "")
            self.assertNotIn("192.168", origin)
            self.assertNotIn("hooks.nabu.casa", origin)
            row = publicize_listing_row(
                {
                    "case_number": "S-PR-0012345",
                    "de111_url": LOCAL_FILE,
                    "de147_url": (
                        "http://10.0.0.8:8123/api/placer_probate_monitor/de147/"
                        "def/S-PR-0012345.pdf"
                    ),
                    "documents": [
                        {
                            "label": "DE-111",
                            "url": "/api/placer_probate_monitor/de111/tokrel/S-PR-0012345.pdf",
                        },
                        {
                            "label": "DE-147",
                            "url": (
                                "ha-server:8123/api/placer_probate_monitor/de147/"
                                "tokhost/S-PR-0012345.pdf"
                            ),
                        },
                        {
                            "label": "DE-111",
                            "url": (
                                "http://172.16.5.4:8123/api/placer_probate_monitor/"
                                "de111/tok172/S-PR-0012345.pdf"
                            ),
                        },
                    ],
                },
                origin,
            )
            hrefs = self._listing_hrefs(row)
            self.assertGreaterEqual(len(hrefs), 3)
            blob = json.dumps(row)
            self.assertIsNone(PRIVATE_HREF.search(blob), blob)
            for href in hrefs:
                self.assertTrue(
                    href.startswith(
                        "https://house.ui.nabu.casa/api/placer_probate_monitor/"
                    ),
                    href,
                )
                self.assertFalse(href.startswith("/"))
                self.assertNotIn("hooks.nabu.casa", href)
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_remote_ui_and_storage_beat_private_get_url(self):
        import sys
        import types

        saved = sys.modules.get("homeassistant.helpers.network")
        network = types.ModuleType("homeassistant.helpers.network")
        network.get_url = lambda hass, **kwargs: "http://192.168.4.4:8123"
        sys.modules["homeassistant.helpers.network"] = network
        parent = sys.modules.get("homeassistant")
        helpers = sys.modules.get("homeassistant.helpers")
        if parent is None:
            parent = types.ModuleType("homeassistant")
            sys.modules["homeassistant"] = parent
        if helpers is None:
            helpers = types.ModuleType("homeassistant.helpers")
            sys.modules["homeassistant.helpers"] = helpers
        parent.helpers = helpers
        helpers.network = network
        try:
            remote = SimpleNamespace(instance_domain=None, remote_ui="https://remoteui.ui.nabu.casa")
            hass = _FakeHass(
                external="http://192.168.1.23:8123",
                internal="http://10.1.1.1:8123",
                cloud=SimpleNamespace(remote=remote, client=SimpleNamespace(prefs=SimpleNamespace())),
            )
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://remoteui.ui.nabu.casa", error)
            self.assertIsNone(PRIVATE_HREF.search(origin))
        finally:
            if saved is None:
                sys.modules.pop("homeassistant.helpers.network", None)
            else:
                sys.modules["homeassistant.helpers.network"] = saved

    def test_storage_remote_ui_beats_private_internal_and_get_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / ".storage"
            storage.mkdir()
            (storage / "cloud").write_text(
                json.dumps(
                    {
                        "data": {
                            "google_enabled": True,
                            "remote_domain": None,
                            "remote_ui": "cabin.ui.nabu.casa",
                            "cloudhooks": {
                                "probate": {
                                    "cloudhook_url": "https://hooks.nabu.casa/secret-token"
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            hass = _FakeHass(
                external="http://192.168.1.23:8123",
                internal="http://10.0.0.8:8123",
            )
            hass.config.path = lambda *parts: str(root.joinpath(*parts))
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://cabin.ui.nabu.casa", error)
            self.assertNotIn("hooks.nabu.casa", origin)
            self.assertNotIn("secret", origin or "")
            row = publicize_listing_row(
                {
                    "de111_url": "http://192.168.1.23:8123/api/placer_probate_monitor/de111/abc/S-PR-1.pdf",
                    "documents": [
                        {
                            "label": "DE-111",
                            "url": "http://127.0.0.1:8123/api/placer_probate_monitor/de111/abc/S-PR-1.pdf",
                        }
                    ],
                },
                origin,
            )
            blob = json.dumps(row)
            self.assertIsNone(PRIVATE_HREF.search(blob), blob)
            self.assertTrue(
                row["de111_url"].startswith(
                    "https://cabin.ui.nabu.casa/api/placer_probate_monitor/de111/"
                )
            )

    def test_host_order_is_remote_then_external_then_storage_then_prefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / ".storage"
            storage.mkdir()
            (storage / "cloud").write_text(
                json.dumps({"data": {"remote_domain": "storage.ui.nabu.casa", "google_enabled": True}}),
                encoding="utf-8",
            )
            remote = SimpleNamespace(instance_domain="alpha.ui.nabu.casa", remote_ui=None)
            prefs = SimpleNamespace(remote_domain="prefs.ui.nabu.casa", _prefs={})
            hass = _FakeHass(
                external="https://external.ui.nabu.casa",
                internal="http://192.168.1.23:8123",
                cloud=SimpleNamespace(remote=remote, client=SimpleNamespace(prefs=prefs)),
            )
            hass.config.path = lambda *parts: str(root.joinpath(*parts))
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://alpha.ui.nabu.casa", error)

            remote.instance_domain = None
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://external.ui.nabu.casa", error)

            hass.config.external_url = "http://192.168.1.23:8123"
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://storage.ui.nabu.casa", error)

            (storage / "cloud").write_text(
                json.dumps({"data": {"google_enabled": True, "remote_domain": None}}),
                encoding="utf-8",
            )
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://prefs.ui.nabu.casa", error)

    def test_certificate_common_name_beats_private_get_url(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cloud_dir = root / ".cloud"
            cloud_dir.mkdir()
            cert = cloud_dir / "remote_fullchain.pem"
            subprocess.check_call(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(cloud_dir / "key.pem"),
                    "-out",
                    str(cert),
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=certname.ui.nabu.casa",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            hass = _FakeHass(
                external="http://192.168.1.23:8123",
                internal="http://192.168.1.23:8123",
            )
            hass.config.config_dir = str(root)
            hass.config.path = lambda *parts: str(root.joinpath(*parts))
            origin, error = discover_nabu_origin(hass)
            self.assertEqual(origin, "https://certname.ui.nabu.casa", error)

    def test_missing_nabu_does_not_keep_a_private_document_href(self):
        hass = _FakeHass(
            external="http://192.168.1.23:8123",
            internal="http://10.0.0.8:8123",
        )
        origin, error = discover_nabu_origin(hass)
        self.assertEqual(origin, "")
        self.assertIn("No Nabu Casa remote UI host", error)
        self.assertIn("private", error.lower())
        self.assertNotIn("hooks.nabu.casa/", error)
        row = publicize_listing_row(
            {
                "case_number": "S-PR-0012345",
                "de111_url": LOCAL_FILE,
                "de147_url": "http://ha-server:8123/api/placer_probate_monitor/de147/abc/S-PR-0012345.pdf",
                "documents": [
                    {
                        "label": "DE-111",
                        "url": "/api/placer_probate_monitor/de111/rel/S-PR-0012345.pdf",
                    }
                ],
            },
            origin,
        )
        blob = json.dumps(row)
        self.assertIsNone(PRIVATE_HREF.search(blob), blob)
        for href in self._listing_hrefs(row):
            self.assertFalse(href.startswith("http://192.168"))
            self.assertNotIn(":8123", href)
        self.assertTrue(any(doc.get("path", "").startswith("/api/placer_probate_monitor/") for doc in row["documents"]))


if __name__ == "__main__":
    unittest.main()
