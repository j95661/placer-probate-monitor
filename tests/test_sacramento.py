"""Sacramento notice, portal, and Follow Up Boss tag tests.

Fixtures only. These tests do not call the live court site.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasources import fub_tags, keywords_for_county, stamp_fub_tags  # noqa: E402
from fub_client import (  # noqa: E402
    build_event,
    build_person,
    case_portal_url,
    gate_reason,
    put_person,
    sources_payload,
)
from placer_probate_monitor import extract_case, normalize_notice_text, notice_fields  # noqa: E402
from sacramento_portal import _parse_search, parse_summary  # noqa: E402
from sacramento_probate_monitor import extract_sacramento_case  # noqa: E402

FOLSOM = """
L0010608
26PR002037
NOTICE OF PETITION TO ADMINISTER ESTATE OF
SUZANNE GAIL MAGTALAS
CASE NO. 26PR002037
1. To all heirs, beneficiaries, creditors, contingent creditors, and persons who may otherwise be interested in the will or estate, or both, of: SUZANNE GAIL MAGTALAS,
2. A PETITION FOR PROBATE has been filed by: GERMANE SMITH in the Superior Court of California, County of SACRAMENTO
3. The Petition for Probate requests that: GERMANE SMITH be appointed as personal representative to administer the estate of the decedent.
5. THE PETITION requests authority to administer the estate under the Independent Administration of Estates Act.
6. A HEARING on the petition will be held in this court as follows: August 26, 2026 at 1:30 PM in Dept. 126 located at Superior Court of California, County of Sacramento, William R. Ridgeway Family Relations Courthouse, 3341 Power Inn Road, Sacramento, CA 95826
7. IF YOU OBJECT to the granting of the petition, you should appear at the hearing.
10. Attorney for Petitioner:HEATHER S. MAYER, SBN 272665, MAYER & YOUNG, PC, 400 PLAZA DRIVE, SUITE 145, FOLSOM, CA, 95630
Phone No.: 916-631-1996
PUBLISHED IN FOLSOM TELEGRAPH ON JULY 31, AUGUST 7, 14, 2026
"""

BEE = """
NOTICE OF PETITION TO ADMINISTER ESTATE OF:
Helen Row
CASE NUMBER
26PR001581
To all heirs, beneficiaries, creditors, contingent creditors, and persons who may otherwise be interested in the will or estate, or both, of, Helen Row
A PETITION FOR PROBATE has been filed by Wayne Row in the Superior Court of California, County of Sacramento.
THE PETITION requests the decedent's will and codicils, if any, be admitted to probate.
THE PETITION requests authority to administer the estate under the Independent Administration of Estates Act.
A HEARING on the petition will be held in this court as follows:
Date: September 08 2026 Time: 9:00am Dept: 126
Address of the Court:
3341 Power Inn Rd, #214
Sacramento, CA, 95826
IF YOU OBJECT to the granting of the petition, you should appear at the hearing.
Attorney for Petitioner: Wayne Row
13950 N Point Ct
Pine Grove, CA, 95665
Telephone: 916-335-3753
IPL0360651
Aug 5,12,19 2026
"""

PLACER = """
NOTICE OF PETITION TO ADMINISTER ESTATE OF
JANE Q DOE
CASE NO. S-PR-0014250
1. To all heirs, beneficiaries, creditors, and persons who may otherwise be interested in the will or estate, or both, of: JANE Q DOE
2. A PETITION FOR PROBATE has been filed by: JOHN DOE in the Superior Court of California, County of PLACER
6. A HEARING on the petition will be held in this court as follows: October 1, 2026 at 8:30 AM in Dept. 40
7. IF YOU OBJECT to the granting of the petition, you should appear at the hearing.
The petition requests the decedent's will and codicils, if any, be admitted to probate.
Attorney for Petitioner: ANN LAWYER, SBN 1, EXAMPLE FIRM
Phone No.: (916) 555-0100
PUBLISHED IN PLACER HERALD ON OCTOBER 1, 2026
"""

SUMMARY = """
<table class="caseHeader" style="width:100%;">
 <tr><td class="caseheaderXLtext" colspan="3"><b>26PR001581</b> ESTATE OF: HELEN ROW</td></tr>
 <tr>
  <td><b>Probate</b> (<span title="Probate of Will &amp; Letters Testamentary">Probate of Will...</span>)</td>
  <td><span title="William R. Ridgeway Family Relations Courthouse">William R...</span> / DEPT 126 - HON. Heath T. Langle</td>
 </tr>
 <tr>
  <td><span title="Date Filed">Filed: 06/04/2026</span></td>
  <td><span title="Next Event 11/18/2026 9:00 AM General Probate Amended Petition in Department 126">Next Hearing: 11/18/2026</span></td>
 </tr>
</table>
<div class="tabpane" id="pane.form.1">
 <table class="table"><tr><td></td><td>Filed / Status Date</td><td>Name</td><td>Filed By</td></tr>
  <tr><td></td><td>10/06/2026</td><td>Amended Petition</td><td>Wayne L Row (Petitioner)</td><td>9</td></tr>
  <tr><td></td><td>06/04/2026</td><td>Petition for Probate of Will &amp; Letters Testamentary</td><td>Wayne L Row (Petitioner)</td><td>10</td></tr>
  <tr><td></td><td>06/04/2026</td><td>Not Viewable</td><td>Clerk</td><td></td></tr>
 </table>
</div>
<div class="tabpane" id="pane.form.2"><table class="table"><tr><td>Date</td><td>Message</td></tr></table></div>
<div class="tabpane" id="pane.form.3">
 <table class="table"><tr><td></td><td>Name</td><td>AKA/DBA</td><td>Role</td></tr>
  <tr><td></td><td>Wayne L Row (Petitioner)</td><td></td><td>Petitioner</td></tr>
  <tr><td></td><td>Helen Row (Decedent)</td><td></td><td>Decedent</td></tr>
 </table>
</div>
<div class="tabpane" id="pane.form.4">
 <table class="table">
  <tr><td></td><td>Name</td><td>Date/Time</td><td>Status</td><td>Department</td></tr>
  <tr><td></td><td>General Probate Amended Petition</td><td>11/18/2026 09:00 AM</td><td>Scheduled</td><td>Dept 126 / William R. Ridgeway Family Relations</td></tr>
  <tr><td></td><td>General Probate</td><td>09/08/2026 09:00 AM</td><td>Rescheduled</td><td>Dept 126 / William R. Ridgeway Family Relations</td></tr>
 </table>
</div>
"""

SEARCH = """
<a href="?q=node/430/2506537">26PR001581</a>
<a href="?q=node/430/2506537">ESTATE OF: HELEN ROW</a>
<a href="/public-portal/?q=node/429/1/82309/ASCEND">Case Number</a>
"""

OBSERVER = """
NOTICE OF PETITION TOADMINISTER ESTATE OFROBERT EUGENE HANLEYCASE NO. 26PR002445Superior Court of California
To all heirs, beneficiaries, creditors, and contingent creditors and persons who may be otherwise interested in the will or estate, or both of: ROBERT EUGENE HANLEY
A Petition for Probate has been filed by MICHAEL G. LEE in the Superior Court of California, County of SACRAMENTO.
The petition requests the decedent's will and codicils, if any, be admitted to probate.
The petition requests authority to administer the estate under the Independent Administration of Estates Act.
A hearing on the petition will be held in this court as follows:SEPTEMBER 29 2026 at 9:00 AMin Dept. No. 1263341 Power Inn Road Sacramento, CA 95826
IF YOU OBJECT to the granting of the petition, you should appear at the hearing.
Petitioner or Attorney for PetitionerMichael G. Lee109 Flint Rock CtRoseville, CA 95747
"""

SAC_URL = (
    "https://prod-portal-sacramento-ca.journaltech.com/public-portal/?q=node/397/2506537"
)


class NoticeParseTests(unittest.TestCase):
    def test_sacramento_numbered_notice(self):
        fields = notice_fields(FOLSOM, extract_sacramento_case)
        self.assertEqual(fields["case_number"], "26PR002037")
        self.assertEqual(fields["decedent"], "SUZANNE GAIL MAGTALAS")
        self.assertEqual(fields["petitioner"], "GERMANE SMITH")
        self.assertEqual(fields["court_county"], "SACRAMENTO")
        self.assertIn("August 26, 2026", fields["hearing"])
        self.assertNotIn("IF YOU OBJECT", fields["hearing"])
        self.assertIn("HEATHER S. MAYER", fields["attorney"])
        self.assertIn("916-631-1996", fields["attorney_phone"])
        self.assertTrue(fields["iaea_requested"])
        self.assertFalse(fields["will_offered"])
        self.assertIn("FOLSOM TELEGRAPH", fields["publication_line"])

    def test_sacramento_bee_layout(self):
        fields = notice_fields(BEE, extract_sacramento_case)
        self.assertEqual(fields["case_number"], "26PR001581")
        self.assertEqual(fields["decedent"], "Helen Row")
        self.assertEqual(fields["petitioner"], "Wayne Row")
        self.assertEqual(fields["court_county"], "Sacramento")
        self.assertIn("September 08 2026", fields["hearing"])
        self.assertIn("Wayne Row", fields["attorney"])
        self.assertIn("916-335-3753", fields["attorney_phone"])
        self.assertTrue(fields["will_offered"])
        self.assertTrue(fields["iaea_requested"])

    def test_observer_glued_words(self):
        fields = notice_fields(OBSERVER, extract_sacramento_case)
        self.assertEqual(fields["case_number"], "26PR002445")
        self.assertEqual(fields["decedent"], "ROBERT EUGENE HANLEY")
        self.assertEqual(fields["petitioner"], "MICHAEL G. LEE")
        self.assertIn("Michael G. Lee", fields["attorney"])
        self.assertTrue(fields["will_offered"])

    def test_spacing_does_not_split_ordinary_words(self):
        text = normalize_notice_text(
            "LAW OFFICE OF THERESA at 9:00 a.m. in Dept. 129. Esq.1960 stays a phone (916) 572-1998."
        )
        self.assertIn("LAW OFFICE OF THERESA", text)
        self.assertIn("9:00 a.m.", text)
        self.assertIn("Esq. 1960", text)
        self.assertIn("(916) 572-1998", text)

    def test_case_padding(self):
        self.assertEqual(extract_sacramento_case("case 26PR1581 and 26PR001581"), "26PR001581")

    def test_placer_notice_still_parses(self):
        fields = notice_fields(PLACER, extract_case)
        self.assertEqual(fields["case_number"], "S-PR-0014250")
        self.assertEqual(fields["decedent"], "JANE Q DOE")
        self.assertEqual(fields["petitioner"], "JOHN DOE")
        self.assertEqual(fields["court_county"], "PLACER")
        self.assertIn("October 1, 2026", fields["hearing"])
        self.assertIn("ANN LAWYER", fields["attorney"])
        self.assertIn("916", fields["attorney_phone"])
        self.assertTrue(fields["will_offered"])
        self.assertIn("PLACER HERALD", fields["publication_line"])


class FubTagTests(unittest.TestCase):
    def test_sacramento_adds_tag_beside_probate(self):
        self.assertEqual(fub_tags("Placer"), ["probate"])
        self.assertEqual(fub_tags("sacramento"), ["probate", "sacramento"])
        rows = stamp_fub_tags([{"case_number": "26PR002445"}], "Sacramento")
        self.assertEqual(rows[0]["tags"], ["probate", "sacramento"])
        self.assertIn("probate", rows[0]["tags"])
        self.assertEqual(rows[0]["source_id"], "sacramento")

    def test_keywords_swap_only_the_failing_default(self):
        long_phrase = '"NOTICE OF PETITION TO ADMINISTER ESTATE"'
        short_phrase = '"NOTICE OF PETITION"'
        self.assertEqual(keywords_for_county("Sacramento", long_phrase), short_phrase)
        self.assertEqual(keywords_for_county("Sacramento", ""), short_phrase)
        self.assertEqual(keywords_for_county("Sacramento", '"custom phrase"'), '"custom phrase"')
        self.assertEqual(keywords_for_county("Placer", ""), long_phrase)
        self.assertEqual(keywords_for_county("Placer", long_phrase), long_phrase)

    def test_person_payload_keeps_both_tags(self):
        row = {
            "case_number": "26PR001581",
            "petitioner": "Wayne Row",
            "tags": ["probate", "sacramento"],
            "source_id": "sacramento",
        }
        mapping = {
            "send": {"firstName": True, "lastName": True, "custom_fields": True},
            "custom_fields": {"case_number": "tags"},
            "skip_petitioner_contains": [],
        }
        person = build_person(row, mapping, {"assigned_to": "", "stage": ""})
        self.assertEqual(person["tags"][:2], ["probate", "sacramento"])
        self.assertIn("probate", person["tags"])
        event = build_event(row, mapping, {"event_type": "Seller Inquiry", "source": "probate"}, person=person)
        self.assertEqual(event["person"]["tags"], person["tags"])
        self.assertIn("sacramento", event["person"]["tags"])

    def test_put_person_merges_tags(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"id": 9}
        with patch("fub_client.requests.put", return_value=response) as put:
            put_person(
                "https://api.followupboss.com/v1",
                "test-key",
                9,
                {"firstName": "Wayne", "tags": ["probate", "sacramento"]},
                "PlacerProbateMonitor",
            )
        self.assertEqual(put.call_args.kwargs["params"], {"mergeTags": "true"})
        self.assertTrue(put.call_args.args[0].endswith("/people/9"))
        with patch("fub_client.requests.put", return_value=response) as put_plain:
            put_person(
                "https://api.followupboss.com/v1",
                "test-key",
                9,
                {"firstName": "Wayne"},
                "PlacerProbateMonitor",
            )
        self.assertIsNone(put_plain.call_args.kwargs["params"])

    def test_sacramento_go_without_mailing_address(self):
        mapping = {"skip_petitioner_contains": []}
        sac = {
            "case_number": "26PR001581",
            "petitioner": "Wayne Row",
            "source_id": "sacramento",
            "tags": ["probate", "sacramento"],
        }
        self.assertIsNone(
            gate_reason(sac, {"cases": {}}, mapping, strict_property=False, existing_id=None)
        )
        placer = {"case_number": "S-PR-0014250", "petitioner": "John Doe", "source_id": "placer"}
        self.assertEqual(
            gate_reason(placer, {"cases": {}}, mapping, strict_property=False, existing_id=None),
            "missing_petitioner_address",
        )

    def test_sources_payload_marks_sacramento_live(self):
        payload = sources_payload({"county": "Sacramento", "keywords": '"NOTICE OF PETITION TO ADMINISTER ESTATE"'})
        self.assertEqual(payload["active"], "sacramento")
        by_id = {item["id"]: item for item in payload["sources"]}
        self.assertEqual(by_id["sacramento"]["status"], "live")
        self.assertEqual(by_id["nevada"]["status"], "coming_soon")
        self.assertEqual(by_id["placer"]["status"], "live")
        self.assertEqual(payload["settings"]["keywords"], '"NOTICE OF PETITION"')
        placer = sources_payload({"county": "Placer"})
        self.assertEqual(placer["active"], "placer")


class PortalParseTests(unittest.TestCase):
    def test_search_hit(self):
        hit = _parse_search(SEARCH, "26PR001581")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["summary_id"], "2506537")
        self.assertEqual(hit["caption"], "ESTATE OF: HELEN ROW")
        self.assertIn("node/397/2506537", hit["court_url"])

    def test_summary_maps_to_dossier_fields(self):
        parsed = parse_summary(SUMMARY)
        self.assertEqual(parsed["caption"], "ESTATE OF: HELEN ROW")
        self.assertEqual(parsed["case_type"], "Probate")
        self.assertIn("Letters Testamentary", parsed["category"])
        self.assertEqual(parsed["filed"], "06/04/2026")
        self.assertIn("11/18/2026", parsed["next_event"])
        self.assertIn("Petitioner — Wayne L Row", parsed["parties"])
        self.assertIn("Decedent — Helen Row", parsed["parties"])
        self.assertTrue(any("Amended Petition" in line for line in parsed["hearings"]))
        self.assertTrue(parsed["hearing_history"])
        self.assertTrue(any(line.startswith("06/04/2026 Petition for Probate") for line in parsed["documents"]))
        self.assertFalse(any("Not Viewable" in line for line in parsed["documents"]))
        self.assertEqual(parsed["fees"], [])
        from fub_client import portal_petitioner

        self.assertEqual(portal_petitioner(parsed), "Wayne L Row")

    def test_case_portal_url_leaves_sacramento_node_397(self):
        row = {"court_url": SAC_URL, "case_number": "26PR001581"}
        self.assertEqual(case_portal_url(row), SAC_URL)
        self.assertNotIn("placerco.org", case_portal_url(row))
        self.assertNotIn("node/45", case_portal_url(row))
        placer = case_portal_url({"court_url": "https://webportal.placerco.org/eCourtPublic/?q=node/45/1322377"})
        self.assertEqual(
            placer,
            "https://webportal.placerco.org/eCourtPublic/?q=node/45/1322377",
        )
        rewritten = case_portal_url(
            {"url": "https://webportal.placerco.org/eCourtPublic/?q=downloadFile/99/1322377"}
        )
        self.assertEqual(
            rewritten,
            "https://webportal.placerco.org/eCourtPublic/?q=node/45/1322377",
        )


if __name__ == "__main__":
    unittest.main()
