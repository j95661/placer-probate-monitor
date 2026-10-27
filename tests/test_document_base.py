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
sys.path.insert(0, str(ROOT / "custom_components" / "placer_probate_monitor"))

from document_base import (  # noqa: E402
    apply_document_base,
    choose_document_base,
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


if __name__ == "__main__":
    unittest.main()
