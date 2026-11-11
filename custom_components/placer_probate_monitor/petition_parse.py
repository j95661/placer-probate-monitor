"""Parse California DE-111 Petition for Probate text (pypdf extract).

Decedent street address is chosen in this order and never mixed:

1. Item 3.a.(2) estate location (nonresident, left an estate in this county).
2. Item 3c last residence at death, only if 3.a.(2) has no street.
3. Attached CA death-certificate usual / residence-at-death, only if 3a2 and
   3c have no street, the cert decedent matches the estate name, and the
   line is not a facility place of death, informant, or attorney caption.
4. Public DE-160 / DE-161 Inventory and Appraisal real-property situs, only
   if 3a2, 3c, and death-cert usual residence have no street. Prefer a
   residential parcel over bank accounts. Never attorney caption. Never POD.
5. Never item 3 "at (place)" (place of death). That stays in death_place.

Regression cases live in tests/test_de111_address.py. Add a fixture there
before changing this module, or the next PDF will undo the last fix.
"""

from __future__ import annotations

import re
from pathlib import Path

DIED_RE = re.compile(
    r"Decedent died on \(date\):\s*(?P<date>"
    r"\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]+ \d{1,2}, \d{4})"
    r"\s+at \(place\):\s*(?P<place>.+?)(?:\s*\(\s*1\s*\)|\s*a resident|\s*\[\s*_)",
    re.I | re.S,
)
RESIDENT_RE = re.compile(r"\(\s*1\s*\)\s*a resident of the county named above", re.I)
NONRESIDENT_RE = re.compile(
    r"a nonresident of California and left an estate in the county named above",
    re.I,
)
ITEM3A2_RE = re.compile(
    r"\(\s*2\s*\)\s*(?P<mark>.{0,16}?)\s*a\s*nonresident of California and left an estate"
    r".*?located at(?:\s*\([^)]{0,160}\))?\s*:?\s*(?P<body>.+?)"
    r"(?=\n\s*b\.|\n\s*c\.|Street address, city, and county of|"
    r"Decedent was a citizen|Form Adopted)",
    re.I | re.S,
)
ITEM3B_RE = re.compile(
    r"citizen of a country other than the United States\s*\(specify country\):\s*"
    r"(?P<country>[A-Za-z][A-Za-z .'-]{1,80})?",
    re.I,
)
RESIDENCE_RE = re.compile(
    r"(?:c\.\s*)?(?:Street\s*address,\s*city,\s*and\s*county\s*of\s+)?"
    r"(?:decedent'?s?\s*)?"
    r"residence\s*at\s*time\s*of\s*death\s*\(specify\):\s*(?P<body>.+?)"
    r"(?:Form Adopted|FormAdopted|Fonn |Character and estimated value|3\.\s*d\.|"
    r"4\.\s|Publication of Notice|PETITION FOR PROBATE)",
    re.I | re.S,
)
RESIDENCE_MARK_RE = re.compile(
    r"residence\s*at\s*time\s*of\s*death\s*\(specify\):",
    re.I,
)
DEATH_CERT_MARK_RE = re.compile(
    r"certificate\s+of\s+death|certi\S{0,10}deat",
    re.I,
)
_CA_DEATH_CERT_RE = re.compile(
    r"california|countyofplacer|placer\s+county|\bCA\b|certified\s+copy",
    re.I,
)
_FACILITY_PLACE_RE = re.compile(
    r"\b(?:hospital|medical\s+center|med(?:ical)?\s*ctr|regional\s+medical|"
    r"skilled\s+nursing|nursing\s+(?:home|facility)|hospice|acute\s+care|"
    r"clinic|kaiser|sutter|mercy\s+general)\b",
    re.I,
)
_DEATH_CERT_INFORMANT_RE = re.compile(
    r"\b(?:informant|mother|father)\b",
    re.I,
)
_DEATH_CERT_INFORMANT_END_RE = re.compile(
    r"\b(?:chapel|funeral|mortuary|director|residence)\b",
    re.I,
)
US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
STATE_ALIAS = {}
for _code, _name in US_STATE_NAMES.items():
    STATE_ALIAS[_code.lower()] = _code
    STATE_ALIAS[_name.lower()] = _code
STATE_ALT = "|".join(
    sorted(US_STATE_NAMES.values(), key=len, reverse=True)
    + sorted(US_STATE_NAMES.keys(), key=len, reverse=True)
)
# Require a word break so FL/PA/OR do not match Flathead/Placer/Oregon.
ROAD = (
    r"(?:County\s+Rout[e]?|Route|Rte|Rout|"
    r"Road|Rd|Lane|Ln|Drive|Dr|Street|St|Way|Court|Ct|Avenue|Ave|"
    r"Place|Pl|Circle|Cir|Boulevard|Blvd|Highway|Hwy)\.?"
)
_GLUED_ROAD_RE = re.compile(
    r"([A-Za-z]{2,})(Street|Road|Lane|Drive|Way|Court|Avenue|Place|Circle|"
    r"Boulevard|Highway)\b",
    re.I,
)
_SKIP_AFTER_ROAD = {
    "restaurant",
    "hospital",
    "occupation",
    "informant",
    "residence",
    "county",
    "certificate",
    "caucasian",
    "married",
    "chapel",
    "funeral",
    "mother",
    "father",
    "medical",
    "teacher",
    "chef",
    "never",
    "placer",
    "adult",
}
UNIT = r"(?:\s*,?\s*(?:Suite|Ste\.?|Unit|Apt\.?|#)\s*[A-Z0-9\-]+)"
_ADDR_TAIL = (
    rf"(?P<city>(?!Placer(?:\s+County)?\b)[A-Za-z][A-Za-z .'-]+?)\s*,\s*"
    rf"(?:(?P<county>[A-Za-z][A-Za-z .'-]+?)\s+County\s*,\s*)?"
    rf"(?P<state>{STATE_ALT})\b\.?\s*"
    rf"(?P<zip>\d{{5}}(?:-\d{{4}})?)?"
)
ITEM3C_ADDR_RE = re.compile(
    rf"(?P<street>\d{{1,6}}\s+(?!\d+\s)(?:[A-Za-z0-9.'#\-]+\s+)*{ROAD}{UNIT}?)\s*,\s*"
    rf"{_ADDR_TAIL}",
    re.I,
)
# "1206 Donahue Way, Roseville, Placer" — county with no CA/ZIP.
PLACER_CITY_RE = re.compile(
    rf"(?P<street>\d{{1,6}}\s+(?!\d+\s)(?:[A-Za-z0-9.'#\-]+\s+)*{ROAD}{UNIT}?)\s*,\s*"
    rf"(?P<city>(?!Placer(?:\s+County)?\b)[A-Za-z][A-Za-z .'-]+?)\s*,\s*"
    rf"Placer(?:\s+County)?\b",
    re.I,
)
US_LINE_RE = re.compile(
    rf"(?P<street>\d{{1,6}}\s+(?!\d+\s)[^,\n]{{2,60}}?)\s*,\s*"
    rf"{_ADDR_TAIL}",
    re.I,
)
PHONE_RE = re.compile(
    r"(?:Telephone(?:\s+no\.?)?|Phone(?:\s+no\.?)?|Tel\.?)\s*:?\s*"
    r"(?P<phone>\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
    re.I,
)
EMAIL_RE = re.compile(
    r"(?:E-?mail(?:\s+address)?\s*:?\s*)?"
    r"(?P<email>[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
    re.I,
)
PETITIONER_ITEM_RE = re.compile(
    r"(?:1|2)\.?\s*Petitioner\s*(?:\([^)]*name[^)]*\))?\s*:?\s*(?P<body>.+?)"
    r"(?=requests that|2\.\s*Petitioner\s+is\b|2\.\s*[a-d]\.|3\.\s*Decedent|"
    r"Publication of Notice|Character and estimated value)",
    re.I | re.S,
)
# Page footer / form chrome that pypdf often inserts between item 2 names
# and "requests that" (e.g. DE-111 [Rev. July 1, 2017)).
ITEM2_CHROME_RE = re.compile(
    r"DE-111\s*\[?\s*Rev|"
    r"Form\s+Adopted|"
    r"PETITION\s+FOR\s+PROBATE|"
    r"\(Probate[^\n]{0,40}Estates\)|"
    r"ATTORNEY\s+OR\s+PARTY\s+WITHOUT\s+ATTORNEY|"
    r"STATE\s+BAR\s+NO|"
    r"FIRM\s+NAME|"
    r"ATTORNEY\s+F[OQ]R\s*\(\s*name\s*\)",
    re.I,
)
# DE-111 item 1/2 checkbox prose that pypdf/CNPA sometimes treat as the petitioner.
FORM_BOILERPLATE_NAME_RE = re.compile(
    r"admitted\s+to\s+probate|"
    r"will\s+and\s+codicils|"
    r"\bcodicils\b|"
    r"letters\s+(?:testamentary|of\s+administration)|"
    r"independent\s+administration\s+of\s+estates|"
    r"notice\s+of\s+petition|"
    r"to\s+all\s+heirs|"
    r"\bif\s+any\b.{0,80}\badmitted\b",
    re.I,
)
# DE-111 header OCR glued onto a real name: "Edward P. Stanfield HEARING DATE AND TIME: DEPT".
NAME_FORM_TAIL_RE = re.compile(
    r"[\s,;:./|-]*"
    r"(?:"
    r"hearing\s*date(?:\s*and)?\s*time|"
    r"hearingdate(?:and)?time|"
    r"case\s*numbers?|"
    r"casenumber"
    r")"
    r"\b.*",
    re.I | re.S,
)
# "Bradley Stoltz, Sr" is western order plus suffix, not Last, First.
NAME_SUFFIX_COMMA_RE = re.compile(
    r",\s*(jr\.?|sr\.?|ii|iii|iv|esq\.?)\s*$",
    re.I,
)
# "Mearah Laure Todd, aka: Mearah Laure Dugan" — keep the petition name, drop aliases.
NAME_AKA_TAIL_RE = re.compile(
    r"[\s,;:]*"
    r"(?:"
    r"a/?k/?a\.?|"
    r"also\s+known\s+as|"
    r"formerly\s+known\s+as|"
    r"f/?k/?a\.?"
    r")"
    r"\b.*",
    re.I | re.S,
)
# Form captions OCR glues into firstName/lastName (EstateOfName, HearingDateAndTime).
_CAPTION_PERSON_PHRASES = frozenset(
    {
        "estate of",
        "estate of name",
        "name",
        "case number",
        "casenumber",
        "case",
        "number",
        "dept",
        "department",
        "petitioner",
        "county of",
        "county",
        "superior court of california",
        "superior court",
        "hearing date and time",
        "hearing date",
        "hearing",
        "decedent",
    }
)
_CAPTION_NAME_PARTS = frozenset(
    {
        "estate",
        "of",
        "name",
        "case",
        "number",
        "dept",
        "department",
        "petitioner",
        "county",
        "decedent",
        "casenumber",
        "hearing",
        "date",
        "time",
        "superior",
        "court",
        "california",
        "and",
    }
)
_CAPTION_PERSON_COMPACT = frozenset(
    re.sub(r"[^a-z]", "", phrase) for phrase in _CAPTION_PERSON_PHRASES
)
_NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "esq", "esq."})
_FIRM_CAPTION_RE = re.compile(
    r"\b(?:llp|l\.l\.p|p\.c\.|law\s+(?:office|firm|group)|"
    r"attorneys?\s+at\s+law|superior\s+court|county\s+of|"
    r"firm\s+name)\b",
    re.I,
)
_UUID_STREET_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
_LEGAL_DESC_RE = re.compile(
    r"\b(?:lot\s+\d+|block\s+\d+|parcel\s+(?:no\.?|number|#)?\s*\d+|apn\b|"
    r"assessor'?s?\s+parcel|more\s+particularly\s+described|"
    r"thence\s+(?:north|south|east|west)|metes\s+and\s+bounds|"
    r"beginning\s+at\s+(?:a\s+)?point)\b",
    re.I,
)
_WILL_STREET_RE = re.compile(
    r"^(?:will(?:\s+and(?:\s+codicils?)?)?|codicils?)$",
    re.I,
)
_FORM_MAILING_BLOB_RE = re.compile(
    r"at\s*\(?\s*place\s*\)?|"
    r"resident of the county named above|"
    r"left an estate in the county|"
    r"decedent was a citizen|"
    r"street address,?\s*city,?\s*and county of decedent|"
    r"publication in the newspaper named",
    re.I,
)
ITEM2_NAMES_RE = re.compile(
    r"Petitioner\s*\(\s*name\s*each\s*\)\s*:?\s*(?P<names>.+?)\s*"
    r"(?=requests\s*that|DE-111\s*\[?\s*Rev|Form\s+Adopted|PETITION\s+FOR\s+PROBATE|"
    r"ATTORNEY\s+OR\s+PARTY|STATE\s+BAR\s+NO|FIRM\s+NAME)",
    re.I | re.S,
)
ITEM2_SECTION_RE = re.compile(
    r"2\.\s*Petitioner\s*\(name each\)(?P<body>.+?)"
    r"(?=\n\s*3\.\s*(?:a\.)?\s*Decedent died|\n\s*3\.\s*Decedent)",
    re.I | re.S,
)
ITEM2B_NAME_RE = re.compile(
    r"\bb\.\s*\(\s*name\s*\)\s*:?\s*(?P<name>.+?)\s+be\s+appointed",
    re.I | re.S,
)
# Petitioner / DE-111 item 2.b skip offices. Do not run this on the full petition
# or attached will: family forms often say "bank or trust company" in boilerplate.
# CLPF / PFB license tags are California Licensed Professional Fiduciary numbers
# (item 2 names or item 8 "Proposed Administrator … Fiduciary CLPF #").
PROFESSIONAL_FIDUCIARY_RE = re.compile(
    r"licensed\s+professional\s+fiduciary|"
    r"private\s+professional\s+fiduciary|"
    r"professional\s+fiduciary\s+bureau|"
    r"professional\s+fiduciary|"
    r"public\s+administrator|"
    r"public\s+guardian|"
    r"fiduciary\s+services|"
    r"(?:licensed\s+)?fiduciar(?:y|ies)\s+bureau|"
    r"corporate\s+trustee|"
    r"trust\s+company|"
    r"bank\s+and\s+trust|"
    r"national\s+association|"
    r"\bclpf\s*#?\s*\d*|"
    r"\bpfb\s*(?:license|lic\.?|#|no\.?|number)?\s*\d*|"
    r"\bpf\s*(?:#|no\.?|number)\s*\d*|"
    r"fiduciary\s*(?:license|lic\.?|#)\s*\d*",
    re.I,
)
# Item 8 only: family "Proposed Administrator" is not a skip unless that row
# also identifies the person as a fiduciary / CLPF / PFB.
ITEM8_PROPOSED_ADMIN_FID_RE = re.compile(
    r"proposed\s+administrator.{0,180}(?:"
    r"clpf|pfb|\bfiduciary\b|professional\s+fiduciary|"
    r"licensed\s+professional|\bpf\s*(?:#|no\.?)"
    r")|"
    r"(?:clpf|pfb|\bfiduciary\b|professional\s+fiduciary).{0,180}"
    r"proposed\s+administrator",
    re.I | re.S,
)
PUBLIC_REPORTS_NEWSPAPER = "Sacramento Superior Court Public Reports"
POBOX_OCR_RE = re.compile(r"P\.\s*[O0]\.\s*Box", re.I)
POBOX_ADDR_RE = re.compile(
    rf"(?P<street>P\.O\.\s*Box\s+\d+)\s*,\s*{_ADDR_TAIL}",
    re.I,
)
# Adult OCR often reads AdIJIt; street may wrap to the next line. Do not
# treat house-number digits as the Age column.
ITEM8_REL = (
    r"son|daughter|spouse|wife|husband|child|mother|father|"
    r"brother|sister|friend|niece|nephew|grandchild|cousin|partner|parent"
)
ITEM8_AGE = r"(?:Adult|Minor|Ad\s*[Ilj1]{2,4}t|(?<!\d)\d{1,3}(?!\d))"
ITEM8_NAME = r"(?P<name>[A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){0,5})"
ITEM8_REL_OPT = rf"(?:\s*,?\s*(?i:(?:{ITEM8_REL})s?))?"
ITEM8_STREET_CITY = (
    r"(?P<street>(?:P\.O\.\s*Box\s+\d+|\d[\dA-Za-z.'#/\- ]{1,80}?))"
    r"(?:\s*\n\s*|\s*,\s*)"
    rf"(?:(?i:{ITEM8_REL})s?\s+)?"
    r"(?P<cityline>[A-Za-z][A-Za-z .'-]+,\s*(?:[A-Z]{2}|[A-Za-z]{3,})\s*,?\s*"
    r"\d{5}(?:-\d{4})?)"
)
ITEM8_ROW_RE = re.compile(
    ITEM8_NAME
    + ITEM8_REL_OPT
    + r"(?:\n(?!\s*(?:Adult|Minor|\d|Ad))[^\n]{0,32})?"
    + rf"\s+(?i:{ITEM8_AGE})\s*"
    + ITEM8_STREET_CITY
)
# OCR sometimes reads Name / street, city ZIP / #unit / Adult instead of Age then street.
ITEM8_ROW_ADDR_THEN_AGE_RE = re.compile(
    ITEM8_NAME
    + ITEM8_REL_OPT
    + r"\s+"
    + ITEM8_STREET_CITY
    + r"(?:\s*\n\s*(?:#\s*)?(?P<unit>\d[\w\-]{0,12}))?"
    + rf"\s+(?i:{ITEM8_AGE})"
)
ITEM8_RE = re.compile(
    r"8\.\s*(?:"
    r"Name\s*and\s*relationship\s*to\s*decedent|"
    r"Nameandrelationshiptodecedent|"
    r"Listed\s*on\s*the\s*next\s*page|"
    r"Listedonthenextpage"
    r")(?P<header>)(?P<body>.+?)"
    r"(?:Continued\s*on\s*Attachment\s*8|ContinuedonAttachment8|"
    r"Number of pages attached|"
    r"I declare under penalty|TYPE OR PRINT NAME)",
    re.I | re.S,
)
_ITEM8_SKIP_ADDR = ("douglas boulevard", "justice center")
ITEM3H_RE = re.compile(
    r"nonresident of California\s*\(specify permanent address\):\s*(?P<body>.{0,400}?)"
    r"(?=resident of the United|nonresident of the United|4\.\s|8\.\s|DE-111|Form Adopted)",
    re.I | re.S,
)
PERMANENT_ADDR_RE = re.compile(
    r"permanent address\)\s*:\s*(?P<body>.{0,200})",
    re.I | re.S,
)
CAPTION_ADDR_RE = re.compile(
    r"STREET ADDRESS:\s*(?P<street>[^\n]+?)\s+"
    r"CITY:\s*(?P<city>[A-Za-z .'-]+)\s+"
    r"STATE:\s*(?P<state>[A-Z]{2})\s+"
    r"(?:ZIP|[Z2]IP|Z1P)(?:\s*CODE)?:\s*(?P<zip>\d{5}(?:-\d{4})?)",
    re.I,
)
IN_PRO_PER_RE = re.compile(
    r"ATTORNEY\s+F[OQ]R\s*\(\s*name\s*\)\s*:?\s*(?P<who>[^\n]{0,120})",
    re.I,
)
_ATTORNEY_FOR_GENERIC_RE = re.compile(
    r"^(?:the\s+)?(?:petitioners?|applicant|plaintiff|client|n/?a)$",
    re.I,
)
ADDR_PATTERNS = [
    re.compile(
        rf"(?P<street>\d{{1,6}}(?:\s+[A-Za-z0-9.'#\-]+)+\s+{ROAD}{UNIT}?)"
        rf"\s*,?\s*(?P<city>[A-Za-z][A-Za-z .'-]+?)\s*,\s*Placer(?:\s+County)?\b",
        re.I,
    ),
    re.compile(
        rf"(?P<street>\d{{1,6}}(?:\s+[A-Za-z0-9.'#\-]+)+\s+{ROAD}{UNIT}?)"
        rf"\s*,?\s*(?P<city>[A-Za-z][A-Za-z .'-]+?),\s*"
        rf"(?P<state>{STATE_ALT})\b\s*(?P<zip>\d{{5}}(?:-\d{{4}})?)?",
        re.I,
    ),
    re.compile(
        rf"(?P<street>\d{{1,6}}(?:\s+[A-Za-z0-9.'#\-]+)+\s+{ROAD}{UNIT}?)"
        rf"\s+(?P<city>[A-Za-z][A-Za-z .'-]+?)"
        rf"\s+(?:Placer(?:\s+County)?\s+)?(?P<state>{STATE_ALT})\b\s+"
        rf"(?P<zip>\d{{5}}(?:-\d{{4}})?)(?:\s*\(Placer County\))?",
        re.I,
    ),
    re.compile(
        rf"(?P<street>\d{{1,6}}\s+[^\n]+?{ROAD}{UNIT}?)\s+"
        r"(?P<city>[A-Za-z][A-Za-z .'-]+),\s*"
        rf"(?P<state>{STATE_ALT})\b\s*(?P<zip>\d{{5}}(?:-\d{{4}})?)?",
        re.I,
    ),
]
COUNTY_NOISE_RE = re.compile(r",?\s*Placer(?:\s+County)?\b,?", re.I)
NOT_CITIES = {"placer", "placer county", "county", "california"}


def _strip_county_noise(text: str) -> str:
    text = COUNTY_NOISE_RE.sub(",", text)
    text = re.sub(r"\s*,\s*,+", ",", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


_REL_CITY_PREFIX_RE = re.compile(rf"^(?:{ITEM8_REL})s?\s+", re.I)


def _usable_city(city: str) -> str:
    city = _REL_CITY_PREFIX_RE.sub("", city or "").strip()
    parts = city.split()
    if parts and len(re.sub(r"[^A-Za-z]", "", parts[0])) <= 1:
        city = " ".join(parts[1:]).strip()
    low = re.sub(r"\s+", " ", (city or "").strip().lower())
    if not low or low in NOT_CITIES or low.endswith(" county"):
        return ""
    return (city or "").strip()


def _state_code(raw: str) -> str:
    key = re.sub(r"\s+", " ", (raw or "").strip().lower())
    if key in STATE_ALIAS:
        return STATE_ALIAS[key]
    return (raw or "").strip().upper()[:2]


def split_de111_address(line: str) -> dict:
    """Parse DE-111 §3c lines like '1728 6th Street, Lincoln, Placer County, California 95648'."""
    text = re.sub(r"[ \t]+", " ", (line or "").replace("\n", " ")).strip(" .")
    text = POBOX_OCR_RE.sub("P.O. Box", text)
    text = re.sub(r"\s+,", ",", text)
    if not text:
        return {}
    match = (
        POBOX_ADDR_RE.search(text)
        or ITEM3C_ADDR_RE.search(text)
        or US_LINE_RE.search(text)
    )
    if not match:
        stripped = _strip_county_noise(text)
        match = ITEM3C_ADDR_RE.search(stripped) or US_LINE_RE.search(stripped)
    if not match:
        placer = PLACER_CITY_RE.search(text)
        if placer:
            city = _usable_city(placer.group("city"))
            street = re.sub(r"\s+", " ", placer.group("street")).strip(" ,.")
            if street and city:
                return {
                    "street": street,
                    "city": city,
                    "county": "Placer",
                    "state": "CA",
                    "zip": "",
                }
        return {}
    city = _usable_city(match.group("city"))
    street = re.sub(r"\s+", " ", match.group("street")).strip(" ,.")
    if not street or not city:
        return {}
    return {
        "street": street,
        "city": city,
        "county": re.sub(r"\s+", " ", (match.group("county") or "")).strip(),
        "state": _state_code(match.group("state")),
        "zip": (match.group("zip") or "").strip(),
    }


# Thousands: 770,000 / 770, 000 / 770.000 (period used as a comma).
# OCR often reads 0 as O/U ($516,0UU).
_MONEY_AMT = (
    r"(?P<amt>0(?:\.0+)?|[0-9OUou]{1,3}(?:[.,]\s*[0-9OUou]{3})+(?:\.\d{2})?|"
    r"[0-9]+(?:\.\d{2})?|[OUou])"
)
_GMV_AFTER = r"\s*:?\s*-?\s*(?:\$\s*)?"
PERSONAL_RE = re.compile(
    r"Personal property:\s*\$?\s*" + _MONEY_AMT,
    re.I,
)
REAL_RE = re.compile(
    r"Gross fair market value of real property" + _GMV_AFTER + _MONEY_AMT,
    re.I,
)
# Extra OCR method: Tesseract often glues the item-3(4) label.
REAL_FLEX_RE = re.compile(
    r"Gross\s*fair\s*market\s*value\s*of\s*real\s*property"
    + _GMV_AFTER
    + _MONEY_AMT,
    re.I,
)
GMV_TRUST_MIN = 10000.0


def parse_money_amount(raw) -> float | None:
    if raw in (None, "", [], {}) or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = re.sub(r"\s+", " ", str(raw)).strip()
    if not text:
        return None
    token = re.sub(r"[^A-Za-z0-9.]", "", text.split()[0] if text else "")
    if token.lower() in {"o", "u", "v"}:
        return 0.0
    mapped = re.sub(r"[OUou]", "0", text)
    cleaned = re.sub(r"[^0-9.,]", "", mapped)
    if not cleaned:
        return None
    try:
        if "," in cleaned:
            return float(cleaned.replace(",", ""))
        if "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                last = parts[-1]
                head, *groups = parts[:-1]
                if len(last) == 2 and not groups:
                    return float(cleaned)
                if len(last) == 2 and groups and all(len(g) == 3 for g in groups):
                    return float(head + "".join(groups) + "." + last)
                if all(len(p) == 3 for p in parts[1:]):
                    return float("".join(parts))
        return float(cleaned)
    except ValueError:
        return None


def is_placeholder_estate_real(amount: float | None) -> bool:
    """True for tiny OCR crumbs ($1/$2/$6/$9), not a real property value.

    $0 is a parsed zero (below-min). Values like $770 stay as-is and fail the
    $200k gate — do not invent $770,000 from a dropped-thousands guess.
    """
    if amount is None:
        return False
    return 0 < float(amount) < 10


def is_truncated_estate_real(amount: float | None) -> bool:
    """True for $10–$9,999 crumbs that still need GMV OCR ($516,0UU → 516)."""
    if amount is None:
        return False
    return 10 <= float(amount) < GMV_TRUST_MIN


def estate_real_needs_gmv_ocr(raw) -> bool:
    """True when estate_real is empty, a $1–$9 crumb, or a truncated thousands."""
    if raw in (None, "", [], {}):
        return True
    amount = parse_money_amount(raw)
    if amount is None:
        return True
    if is_placeholder_estate_real(amount) or is_truncated_estate_real(amount):
        return True
    return False


def _caption_name_key(name: str) -> str:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name or ""))
    spaced = re.sub(r"[^A-Za-z]+", " ", spaced)
    return re.sub(r"\s+", " ", spaced).strip().lower()


def is_caption_person_name(name: str) -> bool:
    """True when the whole string is a DE-111/court caption, not a person."""
    key = _caption_name_key(name)
    if not key:
        return False
    compact = re.sub(r"[^a-z]", "", key)
    if key in _CAPTION_PERSON_PHRASES or compact in _CAPTION_PERSON_COMPACT:
        return True
    parts = key.split()
    return bool(parts) and all(part in _CAPTION_NAME_PARTS for part in parts)


def is_caption_name_part(part: str) -> bool:
    key = _caption_name_key(part)
    if not key:
        return False
    if " " in key:
        return is_caption_person_name(part)
    return key in _CAPTION_NAME_PARTS or key in _CAPTION_PERSON_PHRASES


def is_court_or_firm_caption_name(name: str) -> bool:
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text:
        return False
    if is_caption_person_name(text):
        return True
    return bool(_FIRM_CAPTION_RE.search(text))


def is_junk_mailing_street(street: str) -> bool:
    """Reject legal-description, Will-form, and UUID-like streets as mailing."""
    text = re.sub(r"\s+", " ", str(street or "")).strip(" ,.")
    if not text:
        return True
    head = text.split(",")[0].strip()
    if _WILL_STREET_RE.match(head):
        return True
    if _UUID_STREET_RE.search(text):
        return True
    if _LEGAL_DESC_RE.search(text):
        return True
    if _FORM_MAILING_BLOB_RE.search(text):
        return True
    return False


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u2019", "'")
    return re.sub(r"[ \t]+", " ", text)


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            parts.append("")
    page_text = "\n".join(parts)
    field_lines: list[str] = []
    try:
        fields = reader.get_fields() or {}
    except Exception:  # noqa: BLE001
        fields = {}
    for key, field in fields.items():
        value = _field_value(field) if isinstance(field, dict) else ""
        if not value:
            continue
        field_lines.append(f"{key}: {value}")
    if not field_lines:
        return page_text
    blob = "\n".join(field_lines)
    marker = re.search(r"8\.\s*Name and relationship to decedent", page_text, re.I)
    if marker:
        at = marker.end()
        return page_text[:at] + "\n" + blob + "\n" + page_text[at:]
    return (
        page_text
        + "\n8. Name and relationship to decedent Age Address\n"
        + blob
        + "\nI declare under penalty\n"
    )


def _address_from_groups(street: str, city: str, state: str, zipp: str, *, prefix: str) -> dict:
    street = POBOX_OCR_RE.sub("P.O. Box", street or "")
    street = re.sub(r"\b(?:Adult|Minor|Age)\b", " ", street, flags=re.I)
    street = re.sub(r"\s+", " ", street).strip(" ,.")
    city = _usable_city(city)
    if not street or not city or city.lower() in {"road", "street", "lane", "drive", "way", "court"}:
        return {}
    if is_junk_mailing_street(street):
        return {}
    state = _state_code(state or "CA") or "CA"
    zipp = zipp or ""
    line = f"{street}, {city}"
    if state:
        line += f", {state}"
    if zipp:
        line += f" {zipp}"
    if prefix == "mailing":
        return {
            "mailing_address": line,
            "mailing_city": city,
            "mailing_state": state,
            "mailing_zip": zipp,
        }
    return {
        "decedent_residence": line,
        "decedent_city": city,
        "decedent_state": state,
        "decedent_zip": zipp,
    }


def _parse_address(body: str, *, prefix: str = "decedent") -> dict:
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(
        r",\s+(Road|Rd\.?|Lane|Ln\.?|Drive|Dr\.?|Street|St\.?|Way|Court|Ct\.?|"
        r"Avenue|Ave\.?|Place|Pl\.?|Circle|Cir\.?)\b",
        r" \1",
        body,
        flags=re.I,
    )
    split = split_de111_address(body)
    if split:
        return _address_from_groups(
            split["street"],
            split["city"],
            split.get("state") or "CA",
            split.get("zip") or "",
            prefix=prefix,
        )
    stripped = _strip_county_noise(body)
    for pattern in ADDR_PATTERNS:
        addr = pattern.search(stripped)
        if not addr:
            continue
        parsed = _address_from_groups(
            addr.group("street"),
            addr.group("city"),
            addr.groupdict().get("state") or "CA",
            addr.groupdict().get("zip") or "",
            prefix=prefix,
        )
        if parsed:
            return parsed
    return {}


def _is_self_represented(text: str) -> bool:
    listed = IN_PRO_PER_RE.search(text or "")
    who = listed.group("who").strip().lower() if listed else ""
    return any(
        token in who
        for token in ("pro per", "propria", "self-represented", "in pro per")
    )


def _attorney_for_client_name(text: str) -> str:
    """Client named on ATTORNEY FOR (name). Empty if in pro per or a form label."""
    if _is_self_represented(text):
        return ""
    listed = IN_PRO_PER_RE.search(text or "")
    raw = re.sub(r"\s+", " ", (listed.group("who") if listed else "") or "").strip(" :.")
    if not raw or _ATTORNEY_FOR_GENERIC_RE.match(raw):
        return ""
    if is_court_or_firm_caption_name(raw):
        return ""
    return clean_person_name(raw)


def _caption_street_clean(street: str) -> str:
    raw = re.sub(r"\s+", " ", street or "").strip(" :.")
    match = re.search(
        rf"^(\d{{1,6}}\s+(?:[A-Za-z0-9.'#\-]+\s+)*{ROAD}{UNIT}?)",
        raw,
        re.I,
    )
    return match.group(1).strip() if match else raw


def _parse_caption_mailing(text: str) -> dict:
    if not _is_self_represented(text):
        return {}
    cap = CAPTION_ADDR_RE.search(text)
    if not cap:
        return {}
    return _address_from_groups(
        _caption_street_clean(cap.group("street")),
        cap.group("city"),
        cap.group("state"),
        cap.group("zip") or "",
        prefix="mailing",
    )


def _item1_body(text: str) -> str:
    pet = PETITIONER_ITEM_RE.search(text)
    if pet:
        return pet.group("body")
    fallback = re.search(
        r"(?:1|2)\.?\s*Petitioner\b(.{0,3000}?)(?:\n\s*2\.|\n\s*3\.\s*Decedent|requests that)",
        text,
        re.I | re.S,
    )
    return fallback.group(1) if fallback else ""


def _name_tokens(name: str) -> set[str]:
    skip = {
        "the",
        "estate",
        "of",
        "decedent",
        "petitioner",
        "and",
        "aka",
        "a/k/a",
        "jr",
        "sr",
        "ii",
        "iii",
    }
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "")
    return {
        part.lower()
        for part in re.findall(r"[A-Za-z']{2,}", spaced)
        if part.lower() not in skip
    }


def _name_parts(name: str) -> list[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "")
    skip = {
        "the",
        "estate",
        "of",
        "decedent",
        "petitioner",
        "and",
        "aka",
        "jr",
        "sr",
        "ii",
        "iii",
        "son",
        "daughter",
        "spouse",
        "adult",
        "minor",
    }
    return [
        part.lower()
        for part in re.findall(r"[A-Za-z']{2,}", spaced)
        if part.lower() not in skip
    ]


# Leading/trailing Tesseract junk. Keep internal hyphens and apostrophes.
_OCR_NAME_EDGE_JUNK = ';:.,|/\\*~`"«»“”‘’•·#@!?()[]{}<>_＿：；=+^'
_DATE_TOKEN = r"\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?"
_DATE_EDGE_RE = re.compile(rf"^(?:{_DATE_TOKEN})\s+|\s+(?:{_DATE_TOKEN})$")
_DATE_ONLY_RE = re.compile(rf"^{_DATE_TOKEN}$")


def strip_ocr_name_junk(name: str) -> str:
    """Strip OCR punctuation and date fragments glued to a person name."""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text:
        return ""
    text = NAME_FORM_TAIL_RE.sub("", text)
    text = NAME_AKA_TAIL_RE.sub("", text)
    # DE-111 item 2.b checkbox numbers OCR'd onto the name: "Sabin Toderean (1) []".
    text = re.sub(r"\(\s*\d+\s*\)", " ", text)
    text = re.sub(r"\[\s*\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?:[\s#]+|#)\d{1,2}$", "", text).strip()
    text = re.sub(r"(?<=[A-Za-z.'-])\d{1,2}$", "", text)
    text = NAME_SUFFIX_COMMA_RE.sub(r" \1", text).strip(_OCR_NAME_EDGE_JUNK + " -")
    if not text:
        return ""
    while text:
        stripped = text.strip(_OCR_NAME_EDGE_JUNK + " -")
        if stripped and _DATE_ONLY_RE.fullmatch(stripped):
            return ""
        dated = _DATE_EDGE_RE.sub("", stripped).strip(_OCR_NAME_EDGE_JUNK + " -")
        if dated == text:
            break
        text = dated
        if not text:
            return ""
    return text


def _pretty_ocr_name(name: str) -> str:
    text = strip_ocr_name_junk(re.sub(r"\s+", " ", name or ""))
    if " " not in text:
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # OCR of Roman II / III (uppercase I + lowercase L).
    text = re.sub(r"\bIl\b", "II", text)
    text = re.sub(r"\bIil\b", "III", text)
    return strip_ocr_name_junk(text)


def is_form_boilerplate_person_name(name: str) -> bool:
    """True when a 'person' string is petition checkbox/notice chrome, not a name."""
    text = re.sub(r"\s+", " ", str(name or "")).strip(" :.,")
    if not text:
        return False
    if ITEM2_CHROME_RE.search(text) or FORM_BOILERPLATE_NAME_RE.search(text):
        return True
    return is_caption_person_name(text)


def clean_person_name(name: str) -> str:
    text = strip_ocr_name_junk(re.sub(r"\s+", " ", str(name or "")))
    text = ITEM2_CHROME_RE.split(text, maxsplit=1)[0]
    text = strip_ocr_name_junk(text)
    if not text or is_form_boilerplate_person_name(text):
        return ""
    return text


def stored_person_name(name: str) -> str:
    """Person string safe to keep on a listing or send to FUB (not a form caption)."""
    text = clean_person_name(name)
    text = re.sub(r"^(?:the\s+)?estate\s+of\s+", "", text, flags=re.I).strip(" ,.")
    if not text or is_form_boilerplate_person_name(text) or is_caption_person_name(text):
        return ""
    if is_court_or_firm_caption_name(text):
        return ""
    return text


def usable_go_person_name(name: str) -> bool:
    """True when a string can supply Path A first+last (not caption/suffix-only)."""
    text = clean_person_name(name)
    if not text or is_caption_person_name(text) or is_court_or_firm_caption_name(text):
        return False
    parts = [part for part in re.split(r"\s+", text) if part]
    while parts and parts[0].rstrip(".").lower() in _NAME_SUFFIXES:
        parts.pop(0)
    if len(parts) < 2:
        return False
    if is_caption_name_part(parts[0]) or is_caption_name_part(parts[-1]):
        return False
    return True


def _item2_name_polluted(name: str) -> bool:
    return is_form_boilerplate_person_name(name)


def _item8_names_match(person: str, petitioner_name: str) -> bool:
    """True when an item-8 heir name is the same person as the petitioner."""
    pet = _name_parts(petitioner_name)
    heir = _name_parts(person)
    if len(pet) < 2 or len(heir) < 2:
        return False
    last = pet[-1]
    first = pet[0]
    if last not in heir:
        return False
    if first in heir:
        return True
    for token in heir:
        if token == last:
            continue
        n = 0
        for left, right in zip(first, token):
            if left != right:
                break
            n += 1
        if n >= 4:
            return True
    return False


def _item2_names(text: str) -> str:
    match = ITEM2_NAMES_RE.search(text)
    if not match:
        return ""
    names = ITEM2_CHROME_RE.split(match.group("names") or "", maxsplit=1)[0]
    names = _pretty_ocr_name(names)
    if _item2_name_polluted(names):
        return ""
    if len(names) > 200:
        return names[:200]
    return names


def _item2_section(text: str) -> str:
    match = ITEM2_SECTION_RE.search(text or "")
    if match:
        return match.group(0)
    start = re.search(r"2\.\s*Petitioner\s*\(name each\)", text or "", re.I)
    if not start:
        return ""
    at = start.start()
    return (text or "")[at : at + 1800]


def _item2b_name(text: str) -> str:
    section = _item2_section(text) or text or ""
    match = ITEM2B_NAME_RE.search(section)
    if not match:
        return ""
    name = _pretty_ocr_name(re.sub(r"\s+", " ", match.group("name")).strip(" :."))
    placeholders = (
        (r"licensed\s+professional\s+fiduciary", "\x00LICPF\x00"),
        (r"private\s+professional\s+fiduciary", "\x00PRIVPF\x00"),
        (r"professional\s+fiduciary\s+bureau", "\x00PFB\x00"),
        (r"professional\s+fiduciary", "\x00PF\x00"),
        (r"public\s+administrator", "\x00PUBADMIN\x00"),
        (r"public\s+guardian", "\x00PUBGUARD\x00"),
        (r"fiduciary\s+services", "\x00FIDSVC\x00"),
        (r"(?:licensed\s+)?fiduciar(?:y|ies)\s+bureau", "\x00FIDBUR\x00"),
        (r"\bclpf\s*#?\s*\d*", "\x00CLPF\x00"),
        (r"corporate\s+trustee", "\x00CORPTR\x00"),
        (r"trust\s+company", "\x00TRUSTCO\x00"),
        (r"bank\s+and\s+trust", "\x00BANKTR\x00"),
        (r"national\s+association", "\x00NATLASSN\x00"),
    )
    protected = name
    for pattern, token in placeholders:
        protected = re.sub(pattern, token, protected, flags=re.I)
    protected = re.split(
        r"(?:\(\s*\d+\s*\)|\[\s*\]|\bexecutor\b|\badministrator with|\badministrator\b)",
        protected,
        maxsplit=1,
        flags=re.I,
    )[0]
    restore = {
        "\x00LICPF\x00": "Licensed Professional Fiduciary",
        "\x00PRIVPF\x00": "Private Professional Fiduciary",
        "\x00PFB\x00": "Professional Fiduciary Bureau",
        "\x00PF\x00": "Professional Fiduciary",
        "\x00PUBADMIN\x00": "Public Administrator",
        "\x00PUBGUARD\x00": "Public Guardian",
        "\x00FIDSVC\x00": "Fiduciary Services",
        "\x00FIDBUR\x00": "Fiduciary Bureau",
        "\x00CLPF\x00": "CLPF",
        "\x00CORPTR\x00": "Corporate Trustee",
        "\x00TRUSTCO\x00": "Trust Company",
        "\x00BANKTR\x00": "Bank and Trust",
        "\x00NATLASSN\x00": "National Association",
    }
    for token, label in restore.items():
        protected = protected.replace(token, label)
    name = strip_ocr_name_junk(protected.strip(" :.,"))
    if is_form_boilerplate_person_name(name):
        return ""
    if len(name) > 160:
        return name[:160]
    return name


def is_fiduciary_petitioner_name(name: str) -> bool:
    """True when this petitioner / item 2.b name is a skip fiduciary office.

    Matches public administrator, professional fiduciary, CLPF / PFB license
    tags, bank/trust company as PR, corporate trustee, Fiduciary Services, and
    licensed fiduciary bureau. Will-form boilerplate such as "bank or trust
    company" is not a skip unless that phrase is the petitioner name itself.
    "Proposed Administrator" alone is not a skip.
    """
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    return bool(text and PROFESSIONAL_FIDUCIARY_RE.search(text))


def _item8_fiduciary_region(text: str) -> str:
    raw = text or ""
    match = ITEM8_RE.search(raw)
    if match:
        return f"{match.group('header') or ''}\n{match.group('body') or ''}"
    start = re.search(r"8\.\s*Name\s+and\s+relationship", raw, re.I)
    if start:
        return raw[start.start() : start.start() + 4500]
    if len(raw) < 900 and re.search(r"proposed\s+administrator|\bclpf\b", raw, re.I):
        return raw
    return ""


def is_professional_fiduciary_item8(text: str, petitioner_name: str = "") -> bool:
    """True when the item-8 petitioner row is a licensed/professional fiduciary.

    Catches OCR that puts CLPF on the heirs table instead of item 2.b.
    Family proposed-administrator rows without fiduciary/CLPF/PFB are kept.
    """
    body = _item8_fiduciary_region(text)
    if not body:
        return False
    chunks: list[str] = []
    person = re.sub(r"\s+", " ", petitioner_name or "").strip()
    last = person.split()[-1] if person else ""
    if last and len(last) > 2:
        for match in re.finditer(re.escape(last), body, re.I):
            chunks.append(body[max(0, match.start() - 80) : match.end() + 240])
    if ITEM8_PROPOSED_ADMIN_FID_RE.search(body):
        return True
    if not chunks and len(body) < 900:
        chunks = [body]
    return any(is_fiduciary_petitioner_name(chunk) for chunk in chunks)


def is_professional_fiduciary_item2(text: str) -> bool:
    """True when DE-111 item 2.b (or the same person on item 2 names) is a skip office.

    Professional Fiduciary, Public Administrator / Guardian, CLPF / PFB,
    bank or trust company named as PR, corporate trustee, Fiduciary Services,
    licensed fiduciary bureau. Attorney-caption text is ignored unless it is
    also the item 2.b / petitioner name. Attached-will boilerplate is ignored.
    """
    section = _item2_section(text)
    names = _item2_names(section) or _item2_names(text or "")
    name2b = _item2b_name(section) if section else _item2b_name(text or "")
    if is_fiduciary_petitioner_name(name2b or ""):
        return True
    if is_fiduciary_petitioner_name(names or ""):
        if not name2b:
            return True
        left = _name_tokens(PROFESSIONAL_FIDUCIARY_RE.sub(" ", names))
        right = _name_tokens(PROFESSIONAL_FIDUCIARY_RE.sub(" ", name2b))
        if left & right or not right:
            return True
    if is_professional_fiduciary_item8(text, names or name2b or ""):
        return True
    return False


def row_indicates_professional_fiduciary(row: dict) -> bool:
    """CNPA and node/415 share this skip: petitioner, parties, caption, DE-111."""
    if not isinstance(row, dict):
        return False
    if row.get("professional_fiduciary"):
        return True
    values = [
        row.get("petitioner"),
        row.get("petitioner_name"),
        row.get("item2b_name"),
        row.get("item2_names"),
        row.get("caption"),
        row.get("extra"),
    ]
    parties = row.get("parties") or []
    if isinstance(parties, (list, tuple)):
        values.extend(parties)
    else:
        values.append(parties)
    if any(is_fiduciary_petitioner_name(str(value or "")) for value in values):
        return True
    paper = str(row.get("newspaper") or "")
    if paper == PUBLIC_REPORTS_NEWSPAPER:
        blob = " ".join(
            str(row.get(key) or "") for key in ("raw_text", "snippet", "caption", "extra")
        )
        if is_fiduciary_petitioner_name(blob):
            return True
    petition = str(row.get("petition_text") or row.get("de111_text") or "")
    if petition and is_professional_fiduciary_item2(petition):
        return True
    return False


def stamp_row_professional_fiduciary(row: dict) -> dict:
    """Set professional_fiduciary on harvest rows before GO / FUB."""
    if row_indicates_professional_fiduciary(row):
        row["professional_fiduciary"] = True
    return row


def _estate_of_name(text: str) -> str:
    match = re.search(
        r"ESTATE\s*OF\s*\(\s*name\s*\)\s*:?\s*(?P<name>[^\n]{3,90})",
        text or "",
        re.I,
    )
    if not match:
        match = re.search(
            r"ESTATE\s*OF\s*\(\s*name\s*\)\s*:?\s*(?P<name>[^\n]{3,90})",
            _space_jammed_ocr(text or ""),
            re.I,
        )
    if not match:
        return ""
    name = _pretty_ocr_name(match.group("name"))
    name = re.split(r"\bAKA\b", name, maxsplit=1, flags=re.I)[0].strip(" :.")
    if len(name) < 3 or re.search(r"\d{3,}", name):
        return ""
    if is_caption_person_name(name) or is_form_boilerplate_person_name(name):
        return ""
    return name


def _first_parsed_address(body: str, *, prefix: str) -> dict:
    split = split_de111_address(body)
    if split:
        return _address_from_groups(
            split["street"],
            split["city"],
            split.get("state") or "CA",
            split.get("zip") or "",
            prefix=prefix,
        )
    return _parse_address(body, prefix=prefix)


def _parsed_from_addr_match(hit: re.Match, *, prefix: str) -> dict:
    return _address_from_groups(
        hit.group("street"),
        hit.group("city"),
        hit.group("state"),
        hit.group("zip") or "",
        prefix=prefix,
    )


def _iter_us_addresses(blob: str, *, prefix: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    search_from = 0
    while True:
        hit = (
            POBOX_ADDR_RE.search(blob, search_from)
            or ITEM3C_ADDR_RE.search(blob, search_from)
            or US_LINE_RE.search(blob, search_from)
        )
        if not hit:
            break
        search_from = hit.end()
        parsed = _parsed_from_addr_match(hit, prefix=prefix)
        key = str(parsed.get("mailing_address") or parsed.get("decedent_residence") or "")
        if not parsed or key in seen:
            continue
        seen.add(key)
        found.append(parsed)
    return found


def _space_jammed_ocr(text: str) -> str:
    """Insert spaces in DE-111 item 8 OCR that glues names, Adult, and street."""
    out = text or ""
    held: list[str] = []

    def _hold_unit(match: re.Match) -> str:
        held.append(match.group(0))
        return f"@@@{len(held) - 1}@@@"

    out = re.sub(r"#\s*\d+[A-Za-z]?", _hold_unit, out)
    out = re.sub(r"([A-Za-z])(\d)", r"\1 \2", out)
    out = re.sub(r"(\d)(?!(?:st|nd|rd|th)\b)([A-Za-z])", r"\1 \2", out)
    out = re.sub(r"([a-z])([A-Z])", r"\1 \2", out)
    out = re.sub(r",([A-Za-z])", r", \1", out)
    out = re.sub(r"([A-Za-z]{2})(\d{5})\b", r"\1 \2", out)
    for index, unit in enumerate(held):
        out = out.replace(f"@@@{index}@@@", unit)
    return out


def _item8_addr_ok(parsed: dict) -> bool:
    line = parsed.get("mailing_address") or ""
    if not line:
        return False
    if any(bit in line.lower() for bit in _ITEM8_SKIP_ADDR):
        return False
    return not is_junk_mailing_street(line)


def _item8_people(header: str) -> list[str]:
    people: list[str] = []
    for raw in (header or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" .")
        if not line:
            continue
        low = line.lower()
        if any(
            bit in low
            for bit in ("age", "adult", "minor", "relationship", "decedent", "name and", "address")
        ):
            continue
        if re.search(r"\d{5}", line) or re.match(r"\d", line):
            continue
        if len(_name_tokens(line)) >= 2:
            people.append(line)
    return people


def _normalize_item8_blob(blob: str) -> str:
    """Join street / city ZIP line-breaks and strip DE-111 Age-column crumbs."""
    text = POBOX_OCR_RE.sub("P.O. Box", blob or "")
    text = re.sub(
        rf"((?:P\.O\.\s*Box\s+\d+|\d[^\n]{{0,80}}{ROAD}{UNIT}?\.?))\s*\n\s*(?=[A-Za-z])",
        r"\1, ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(?:Adult|Minor)\b", " ", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _item8_row_from_match(match: re.Match) -> tuple[str, dict] | None:
    street = re.sub(r"\s+", " ", match.group("street") or "").strip(" ,.")
    unit = ""
    if "unit" in match.groupdict() and match.group("unit"):
        unit = str(match.group("unit")).strip()
        if unit and unit.lower() not in street.lower():
            street = f"{street} #{unit}" if not street.endswith(unit) else street
    cityline = re.sub(r"\s+", " ", match.group("cityline") or "").strip(" ,.")
    parsed = _first_parsed_address(f"{street}, {cityline}", prefix="mailing")
    if not parsed:
        parsed = _parse_address(f"{street}, {cityline}", prefix="mailing")
    if not parsed or not _item8_addr_ok(parsed):
        return None
    name = re.sub(r"\s+", " ", match.group("name") or "").strip(" ,.")
    if not name:
        return None
    return name, parsed


def _item8_table_rows(body: str) -> list[tuple[str, dict]]:
    blob = POBOX_OCR_RE.sub("P.O. Box", body or "")
    blob = _space_jammed_ocr(blob)
    rows: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for rx in (ITEM8_ROW_RE, ITEM8_ROW_ADDR_THEN_AGE_RE):
        for match in rx.finditer(blob):
            parsed_row = _item8_row_from_match(match)
            if not parsed_row:
                continue
            name, parsed = parsed_row
            key = str(parsed.get("mailing_address") or "").lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append((name, parsed))
    return rows


def _item8_pick_for_petitioner(
    people_addrs: list[tuple[str, dict]],
    petitioner_name: str,
) -> dict:
    """Mailing is the item-8 row whose name matches the petitioner — never another heir."""
    if not petitioner_name:
        return {}
    for person, addr in people_addrs:
        if _item8_names_match(person, petitioner_name) and _item8_addr_ok(addr):
            return addr
    return {}


def _item8_petitioner_address(text: str, petitioner_name: str = "") -> dict:
    if not petitioner_name:
        return {}
    match = ITEM8_RE.search(text)
    region = f"{match.group('header') or ''}\n{match.group('body') or ''}" if match else text
    rows = _item8_table_rows(region)
    picked = _item8_pick_for_petitioner(rows, petitioner_name)
    if picked:
        return picked
    if not match:
        return {}
    blob = _normalize_item8_blob(_space_jammed_ocr(match.group("body") or ""))
    addrs = [addr for addr in _iter_us_addresses(blob, prefix="mailing") if _item8_addr_ok(addr)]
    people = _item8_people(_space_jammed_ocr(region))
    if people and addrs:
        return _item8_pick_for_petitioner(list(zip(people, addrs)), petitioner_name)
    return {}


def _item3h_address(text: str) -> dict:
    match = ITEM3H_RE.search(text) or PERMANENT_ADDR_RE.search(text)
    if not match:
        return {}
    body = _space_jammed_ocr(match.group("body") or "")[:500]
    body = re.sub(r"\(\s*\d+\s*\)\s*[xX]?", " ", body)
    body = re.sub(r"\s+", " ", body).strip(" ,")
    parsed = _first_parsed_address(body, prefix="mailing")
    if parsed and _item8_addr_ok(parsed):
        return parsed
    extra = _contact_from_blob(body)
    if extra and _item8_addr_ok(extra):
        return extra
    return {}


def _checkbox_marked(mark: str) -> bool:
    blob = re.sub(r"\s+", "", mark or "")
    if not blob or re.fullmatch(r"[\[\]Il1|_-]+", blob):
        return False
    return bool(
        re.search(
            r"[xX✓✔☒☑√×✗■●▪◼◆•*]|\ufffd|\u25a0|\u2713|\u2714|\u2611",
            blob,
        )
    )


def _looks_like_place_of_death(line: str, death_place: str = "") -> bool:
    """True when a value is item 3 'at (place)', not a street in 3.a.(2) or 3c."""
    text = re.sub(r"\s+", " ", (line or "")).strip().lower()
    if not text:
        return False
    if not re.search(r"\d{1,6}\s+\S+", text):
        return True
    place = re.sub(r"\s+", " ", (death_place or "")).strip().lower()
    return bool(place and text == place)


def _looks_like_facility_place(text: str) -> bool:
    return bool(_FACILITY_PLACE_RE.search(text or ""))


def _prepare_addr_blob(text: str) -> str:
    blob = _space_jammed_ocr(text or "")
    blob = re.sub(r"(\d{1,2}/\d{1,2}/\d{2,4})(\d{3,6}\s)", r"\1 \2", blob)
    blob = _GLUED_ROAD_RE.sub(r"\1 \2", blob)

    def _city_comma(match: re.Match) -> str:
        city = match.group(2)
        if city.lower() in NOT_CITIES or city.lower() in _SKIP_AFTER_ROAD:
            return match.group(0)
        return f"{match.group(1)}, {city},"

    blob = re.sub(rf"({ROAD})\s+([A-Z]{{3,}})\b", _city_comma, blob, flags=re.I)
    blob = re.sub(r"\s+,", ",", blob)
    blob = re.sub(r",+", ",", blob)
    blob = re.sub(r"\s+", " ", blob)
    return blob.strip(" ,")


def _usable_decedent_addr(parsed: dict, nearby: str = "", death_place: str = "") -> dict:
    line = parsed.get("decedent_residence") or ""
    if not line:
        return {}
    hay = f"{line} {nearby}"
    if _looks_like_place_of_death(line, death_place):
        return {}
    if _looks_like_facility_place(hay):
        return {}
    low = line.lower()
    if any(bit in low for bit in _ITEM8_SKIP_ADDR):
        return {}
    return parsed


def _informant_spans(region: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for hit in _DEATH_CERT_INFORMANT_RE.finditer(region or ""):
        end_hit = _DEATH_CERT_INFORMANT_END_RE.search(region, hit.end())
        end = end_hit.start() if end_hit else min(len(region), hit.end() + 280)
        spans.append((hit.start(), end))
    return spans


def _in_spans(idx: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= idx < end for start, end in spans)


def _death_cert_regions(text: str) -> list[str]:
    blob = _space_jammed_ocr(text or "")
    starts = [m.start() for m in DEATH_CERT_MARK_RE.finditer(blob)]
    regions: list[str] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else min(len(blob), start + 4500)
        chunk = blob[start:end]
        compact = re.sub(r"\s+", "", chunk)
        if len(compact) < 100:
            continue
        if re.search(r"attached to this petition", chunk, re.I) and len(compact) < 400:
            continue
        if not _CA_DEATH_CERT_RE.search(chunk) and "california" not in compact.lower():
            continue
        regions.append(chunk)
    return regions


def _death_cert_header(region: str) -> str:
    head = region[:900]
    cut = re.search(
        r"\b(?:chef|occupation|informant|mother|father|restaurant|married|"
        r"caucasian|graduate)\b|\d{1,6}\s+[A-Za-z]",
        head,
        re.I,
    )
    if cut:
        head = head[: cut.start()]
    return head


def _estate_first_last(estate: str) -> tuple[str, str]:
    """First token (name or initial) and last name from an estate / cert caption."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", estate or "")
    skip = {
        "the",
        "estate",
        "of",
        "decedent",
        "aka",
        "jr",
        "sr",
        "ii",
        "iii",
    }
    tokens = [
        part.lower()
        for part in re.findall(r"[A-Za-z]+", spaced)
        if part.lower() not in skip
    ]
    if len(tokens) < 2:
        return "", ""
    return tokens[0], tokens[-1]


def _death_cert_name_words(header: str) -> list[str]:
    junk = {
        "county",
        "of",
        "placer",
        "california",
        "certificate",
        "death",
        "case",
        "decedent",
        "auburn",
        "state",
    }
    words: list[str] = []
    for tok in re.findall(r"[A-Za-z]+", header or ""):
        low = tok.lower()
        if low in junk or low.startswith("cert"):
            continue
        words.append(low)
    return words


def _death_cert_matches_estate(region: str, estate: str) -> bool:
    """True when cert header is the DE-111 decedent (last + first or first initial)."""
    first, last = _estate_first_last(estate)
    if not first or not last:
        return False
    words = _death_cert_name_words(_death_cert_header(region))
    compact = "".join(words)
    last_ok = last in words or last in compact
    if not last_ok:
        return False
    if len(first) >= 2:
        if first in words:
            return True
        return any(word.startswith(first) for word in words) or compact.startswith(first)
    initial = first[0]
    if initial in words:
        return True
    return any(
        word != last and len(word) >= 3 and word.startswith(initial) for word in words
    )


def _city_after_street(after: str) -> tuple[str, str]:
    tokens = re.findall(r"[A-Za-z]{2,}|9\d{4}", after or "")
    city = ""
    zip_code = ""
    for tok in tokens:
        if tok.isdigit():
            if tok.startswith("9") and len(tok) == 5 and not zip_code:
                zip_code = tok
            continue
        low = tok.lower()
        if low in {"ca", "california"} or low in NOT_CITIES or low in _SKIP_AFTER_ROAD:
            continue
        if not city:
            city = tok.title()
    return city, zip_code


def _parse_death_cert_hit(region: str, hit: re.Match) -> dict:
    street = _GLUED_ROAD_RE.sub(r"\1 \2", hit.group(0))
    street = re.sub(r"\s+", " ", street).strip(" ,")
    street = " ".join(
        part.capitalize() if not part.isdigit() else part for part in street.split()
    )
    house = re.match(r"(\d+)", street)
    if not house or not (3 <= len(house.group(1)) <= 5):
        return {}
    city, zip_code = _city_after_street(
        _space_jammed_ocr(region[hit.end() : hit.end() + 140])
    )
    if not city:
        return {}
    line = f"{street}, {city}, CA"
    if zip_code:
        line += f" {zip_code}"
    return _parse_address(line, prefix="decedent")


def _death_cert_residence(text: str, estate: str, death_place: str = "") -> dict:
    """Usual / residence-at-death from an attached CA certificate of death."""
    if not estate:
        return {}
    best: tuple[int, dict] | None = None
    road = r"(?:Street|Road|Lane|Drive|Way|Court|Avenue|Place|Circle|Boulevard|Highway)"
    for region in _death_cert_regions(text):
        if not _death_cert_matches_estate(region, estate):
            continue
        informant = _informant_spans(region)
        labeled = list(
            re.finditer(
                r"(?:usual\s+residence|residence(?:\s+at\s+(?:time\s+of\s+)?death)?)\s*:?\s*"
                r"(?P<body>.{0,280})",
                region,
                re.I | re.S,
            )
        )
        hits = list(
            re.finditer(
                rf"\d{{3,5}}\s+[A-Za-z0-9.'#\- ]{{2,40}}{road}",
                region,
                re.I,
            )
        )
        for hit in hits:
            if _in_spans(hit.start(), informant):
                continue
            window = region[max(0, hit.start() - 70) : min(len(region), hit.end() + 90)]
            parsed = _parse_death_cert_hit(region, hit)
            if not parsed:
                parsed = _parse_address(_prepare_addr_blob(window) + ", CA", prefix="decedent")
            usable = _usable_decedent_addr(parsed, window, death_place)
            if not usable:
                continue
            house = re.match(r"(\d+)", usable.get("decedent_residence") or "")
            digits = len(house.group(1)) if house else 0
            score = digits
            if any(hit.start() >= lab.start() and hit.start() <= lab.end() for lab in labeled):
                score += 2
            if re.search(
                r"\b(?:chef|occupation|restaurant)\b",
                region[: hit.start()][-80:],
                re.I,
            ):
                score += 3
            if best is None or score > best[0]:
                best = (score, usable)
    if not best:
        return {}
    out = dict(best[1])
    out["decedent_address_source"] = "death_cert"
    return out


def _item3c_body(text: str) -> str:
    blob = text or ""
    res = RESIDENCE_RE.search(blob)
    if res:
        return res.group("body") or ""
    marker = RESIDENCE_MARK_RE.search(blob)
    if not marker:
        return ""
    tail = blob[marker.end() : marker.end() + 400]
    cut = re.search(
        r"Form Adopted|FormAdopted|Fonn |Character and estimated value|3\.\s*d\.|"
        r"8\.\s|I declare under penalty|PETITION FOR PROBATE",
        tail,
        re.I,
    )
    if cut:
        tail = tail[: cut.start()]
    return tail[:250]


def _item3c_residence(text: str, death_place: str = "") -> dict:
    bodies = [_item3c_body(text or ""), _item3c_body(_space_jammed_ocr(text or ""))]
    for body in bodies:
        if not body.strip():
            continue
        for candidate in (body, _space_jammed_ocr(body)):
            parsed = _parse_address(candidate, prefix="decedent")
            usable = _usable_decedent_addr(parsed, candidate, death_place)
            if usable:
                usable["decedent_address_source"] = "3c"
                return usable
    return {}


def _item3a2_estate_address(text: str) -> dict:
    bodies: list[str] = []
    match = ITEM3A2_RE.search(text or "")
    marked = bool(match and _checkbox_marked(match.group("mark") or ""))
    if match:
        bodies.append(match.group("body") or "")
    fallback = re.search(
        r"left an estate in the county named above.{0,240}?located at"
        r"(?:\s*\([^)]{0,200}\))?\s*:?\s*(?P<body>.+?)"
        r"(?=c\.?\s*Street address|Street address, city, and county of|"
        r"decedent'?s?\s+residence at time of death|Form Adopted)",
        text or "",
        re.I | re.S,
    )
    if fallback:
        bodies.append(fallback.group("body") or "")
    parsed: dict = {}
    for body in bodies:
        parsed = _parse_address(body[:400], prefix="decedent")
        if parsed.get("decedent_residence"):
            break
    if marked or parsed.get("decedent_residence"):
        return parsed
    return {}


def parse_de111_text(text: str, petitioner_name: str = "") -> dict:
    text = _clean(text)
    out: dict = {}
    died = DIED_RE.search(text)
    if died:
        out["decedent_died"] = died.group("date").strip()
        out["death_place"] = re.sub(r"\s+", " ", died.group("place")).strip(" .")
    item3a2 = _item3a2_estate_address(text)
    item3a2_box = ITEM3A2_RE.search(text)
    if item3a2 or (
        item3a2_box and _checkbox_marked(item3a2_box.group("mark") or "")
    ):
        out["county_resident"] = False
    elif NONRESIDENT_RE.search(text) and re.search(
        r"\[\s*[xX✓✔]\s*\][^\n]{0,80}nonresident of California", text
    ):
        out["county_resident"] = False
    elif RESIDENT_RE.search(text) or re.search(
        r"\[\s*[xX✓✔]\s*\][^\n]{0,80}a resident of the county named above", text
    ):
        out["county_resident"] = True
    citizen = ITEM3B_RE.search(text)
    if citizen:
        country = re.sub(r"\s+", " ", (citizen.group("country") or "")).strip(" .")
        if (
            country
            and country.lower() not in {"specify country", "street address"}
            and not re.match(r"^c\.?\s", country, re.I)
            and "street address" not in country.lower()
        ):
            out["decedent_citizenship"] = country
    estate = _estate_of_name(text)
    if estate and not is_caption_person_name(estate):
        out["decedent_name"] = estate
    if item3a2.get("decedent_residence") and not _looks_like_place_of_death(
        item3a2.get("decedent_residence") or "",
        out.get("death_place") or "",
    ):
        out.update(item3a2)
        out["decedent_address_source"] = "3a2"
    else:
        item3c = _item3c_residence(text, out.get("death_place") or "")
        if item3c:
            out.update(item3c)
    if not out.get("decedent_residence"):
        cert = _death_cert_residence(
            text,
            out.get("decedent_name") or "",
            out.get("death_place") or "",
        )
        if cert:
            out.update(cert)
    if out.get("decedent_residence") and _looks_like_place_of_death(
        out.get("decedent_residence") or "",
        out.get("death_place") or "",
    ):
        for key in (
            "decedent_residence",
            "decedent_city",
            "decedent_state",
            "decedent_zip",
            "decedent_address_source",
        ):
            out.pop(key, None)
    body = _item1_body(text)
    names = _item2_names(text)
    item2b = _item2b_name(text)
    if item2b:
        out["item2b_name"] = item2b
    attorney_for = _attorney_for_client_name(text)
    if attorney_for:
        out["attorney_for_name"] = attorney_for
    if (not names or _item2_name_polluted(names)) and item2b:
        names = item2b
    if (not names or _item2_name_polluted(names)) and attorney_for:
        names = attorney_for
    names = clean_person_name(names or petitioner_name or attorney_for)
    if names:
        out["petitioner_name"] = names
    if is_professional_fiduciary_item2(text) or is_fiduciary_petitioner_name(
        names or item2b or petitioner_name or ""
    ):
        out["professional_fiduciary"] = True
    if not out.get("decedent_name"):
        estate = _estate_of_name(text)
        if estate and not is_caption_person_name(estate):
            out["decedent_name"] = estate
    mailing = _item3h_address(text)
    if mailing and _mailing_is_attorney_caption(mailing, text):
        mailing = {}
    if not mailing:
        mailing = _item8_petitioner_address(text, names)
    if mailing and _mailing_is_attorney_caption(mailing, text):
        mailing = {}
    if not mailing and body:
        mailing = _parse_address(body, prefix="mailing")
        if mailing and (
            _mailing_is_attorney_caption(mailing, text)
            or is_junk_mailing_street(str(mailing.get("mailing_address") or ""))
        ):
            mailing = {}
    out.update(mailing)
    skip_phones = _caption_phones(text)
    phone = _petitioner_phone_from_text(text, skip=skip_phones)
    if phone:
        out["petitioner_phone"] = phone
    if not out.get("petitioner_email"):
        email = EMAIL_RE.search(body) if body else None
        if not email and _is_self_represented(text):
            email = EMAIL_RE.search((text or "")[:2500])
        if email and (_is_self_represented(text) or _parse_caption_mailing(text)):
            out["petitioner_email"] = email.group("email").strip()
    if not out.get("mailing_address"):
        out.update(_parse_caption_mailing(text))
    personal = PERSONAL_RE.search(text)
    if personal:
        out["estate_personal"] = personal.group("amt").replace(",", "")
    real = REAL_RE.search(text)
    if not real:
        real = REAL_FLEX_RE.search(text) or REAL_FLEX_RE.search(_space_jammed_ocr(text))
    if real:
        amount = parse_money_amount(real.group("amt"))
        if amount is not None and not is_placeholder_estate_real(amount):
            if amount == int(amount):
                out["estate_real"] = str(int(amount))
            else:
                out["estate_real"] = f"{amount:.2f}".rstrip("0").rstrip(".")
    return out


def _field_value(field) -> str:
    if not isinstance(field, dict):
        return ""
    value = field.get("/V")
    if value in (None, ""):
        return ""
    return str(value).strip()


def _mailing_from_form_fields(path: Path) -> dict:
    from pypdf import PdfReader

    try:
        fields = PdfReader(str(path)).get_fields() or {}
    except Exception:  # noqa: BLE001
        return {}
    blobs: list[str] = []
    for key, field in fields.items():
        name = str(key or "").lower()
        if any(bit in name for bit in ("atty", "attorney", "counsel", "firm")):
            continue
        if not any(
            bit in name
            for bit in (
                "petitioner",
                "partywithoutattorney",
                "inproper",
                "item1",
                "item2",
                "item8",
                "attachment8",
                "permanentaddress",
                "3h",
                "nameeach",
            )
        ):
            continue
        value = _field_value(field)
        if value:
            blobs.append(value)
    if not blobs:
        return {}
    return _parse_address("\n".join(blobs), prefix="mailing")


def _residence_from_form_fields(path: Path) -> dict:
    from pypdf import PdfReader

    try:
        fields = PdfReader(str(path)).get_fields() or {}
    except Exception:  # noqa: BLE001
        return {}
    blobs: list[str] = []
    for key, field in fields.items():
        name = str(key or "").lower()
        if any(bit in name for bit in ("atty", "attorney", "counsel", "firm", "petitioner")):
            continue
        if any(
            bit in name
            for bit in (
                "residence",
                "3c",
                "item3c",
                "decedentaddr",
                "decedent_addr",
                "lastaddress",
                "streetaddresscityandcounty",
            )
        ):
            value = _field_value(field)
            if value:
                blobs.append(value)
    if not blobs:
        return {}
    return _parse_address("\n".join(blobs), prefix="decedent")


def _pdf_field_pairs(path: Path) -> list[tuple[str, str]]:
    from pypdf import PdfReader

    try:
        fields = PdfReader(str(path)).get_fields() or {}
    except Exception:  # noqa: BLE001
        return []
    rows: list[tuple[str, str]] = []
    for key, field in fields.items():
        value = _field_value(field)
        if value:
            rows.append((str(key or ""), value))
    return rows


def _caption_street(text: str) -> str:
    cap = CAPTION_ADDR_RE.search(text or "")
    if not cap:
        return ""
    return re.sub(r"\s+", " ", cap.group("street")).strip().lower()


def _mailing_is_attorney_caption(parsed: dict, text: str) -> bool:
    """True when Path A mailing is the attorney caption suite, not a home street."""
    if _is_self_represented(text):
        return False
    line = str(parsed.get("mailing_address") or "").lower()
    if not line:
        return False
    cap = _caption_street(text)
    if cap and cap in line:
        return True
    return is_junk_mailing_street(line)


def _is_skip_address_field(name: str) -> bool:
    low = (name or "").lower()
    return any(
        bit in low
        for bit in (
            "atty",
            "attorney",
            "counsel",
            "firm",
            "lawyer",
            "court",
            "branch",
            "forcourtuse",
        )
    )


def _pick_mailing_from_fields(
    path: Path,
    petitioner_name: str,
    page_text: str,
) -> dict:
    pairs = _pdf_field_pairs(path)
    if not pairs:
        return {}
    tokens = _name_tokens(petitioner_name)
    first = (petitioner_name.split() or [""])[0].lower()
    attorney = _caption_street(page_text)
    best: tuple[int, dict] | None = None
    for idx, (name, value) in enumerate(pairs):
        if _is_skip_address_field(name):
            continue
        chunk = value
        if idx + 1 < len(pairs):
            chunk = f"{value}, {pairs[idx + 1][1]}"
        parsed = _first_parsed_address(value, prefix="mailing") or _first_parsed_address(
            chunk, prefix="mailing"
        )
        if not parsed:
            continue
        line = str(parsed.get("mailing_address") or "").lower()
        if attorney and attorney in line:
            continue
        if "101 maple" in line or "justice center" in line:
            continue
        if is_junk_mailing_street(parsed.get("mailing_address") or ""):
            continue
        neighbor = " ".join(
            pairs[j][1] for j in range(max(0, idx - 3), min(len(pairs), idx + 4))
        )
        window = f"{name} {neighbor}"
        window_tokens = _name_tokens(window)
        overlap = tokens & window_tokens if tokens else set()
        if first and len(first) > 2 and first not in window_tokens:
            continue
        score = len(overlap)
        low_name = name.lower()
        if any(bit in low_name for bit in ("item8", "att8", "heir", "interested")):
            score += 3
        if best is None or score > best[0]:
            best = (score, parsed)
    if not best:
        return {}
    if tokens and best[0] < 1:
        return {}
    return best[1]


def parse_de111_pdf(path: Path, petitioner: str = "", *, text: str | None = None) -> dict:
    if text is None:
        text = extract_pdf_text(path)
    out = parse_de111_text(text, petitioner_name=petitioner)
    if not out.get("mailing_address"):
        out.update(_mailing_from_form_fields(path))
    if not out.get("mailing_address"):
        out.update(_pick_mailing_from_fields(path, petitioner or _item2_names(text), text))
    if out.get("decedent_address_source") != "3a2" and not out.get("decedent_residence"):
        extra = _residence_from_form_fields(path)
        if extra.get("decedent_residence") and not _looks_like_place_of_death(
            extra.get("decedent_residence") or "",
            out.get("death_place") or "",
        ):
            out.update(extra)
    return out


def looks_like_probate_petition(name: str) -> bool:
    low = (name or "").lower()
    compact = low.replace(" ", "").replace("-", "")
    if "de111" in compact:
        return True
    if "petition for probate" in low:
        return True
    if not low.startswith("petition"):
        return False
    return any(
        token in low
        for token in (
            "probate of will",
            "letters of administration",
            "letters testamentary",
            "petition for probate",
        )
    )


def looks_like_duties_form(name: str) -> bool:
    low = (name or "").lower()
    compact = re.sub(r"[^a-z0-9]", "", low)
    if "de147s" in compact:
        return False
    if "de-147" in low or "de147" in low:
        return True
    return "duties" in low and "personal representative" in low


def looks_like_inventory_form(name: str) -> bool:
    """True for public DE-160 / DE-161 Inventory and Appraisal docket titles."""
    low = (name or "").lower()
    compact = re.sub(r"[^a-z0-9]", "", low)
    if "de147s" in compact or "confidential" in low:
        return False
    if "de160" in compact or "de161" in compact:
        return True
    return "inventory and appraisal" in low or "inventoryandappraisal" in compact


_LETTERS_SKIP_RE = re.compile(
    r"petition|objection|declaration|proof of|waiver|supplement|"
    r"proposed|nomination|consent|special",
    re.I,
)


def looks_like_issued_letters(name: str) -> bool:
    """True for issued Letters (DE-150), not the petition that requests them."""
    low = (name or "").lower().strip()
    compact = re.sub(r"[^a-z0-9]", "", low)
    if not low or "de147s" in compact or "confidential" in low:
        return False
    if looks_like_probate_petition(name):
        return False
    if _LETTERS_SKIP_RE.search(low):
        return False
    if "de150" in compact:
        return True
    return bool(re.match(r"^letters\b", low))


_DE160_NONREAL_RE = re.compile(
    r"\b(?:checking|savings|money\s+market|certificate of deposit|"
    r"\bCDs?\b|IRA|401\s*\(?k\)?|brokerage|mutual\s+funds?|"
    r"credit\s+union|life\s+insurance|annuity|vehicle|automobile|"
    r"VIN\b|cash(?:\s+on\s+hand)?|currency|coins?|safe\s+deposit|"
    r"bank\s+account|financial\s+institution)\b",
    re.I,
)
_DE160_RESIDENTIAL_RE = re.compile(
    r"\b(?:single[-\s]?family|residence|residential|dwelling|"
    r"condominium|townhome|townhouse|duplex)\b",
    re.I,
)
_DE160_REAL_RE = re.compile(
    r"\b(?:real\s+propert(?:y|ies)|real\s+estate|improved\s+real|"
    r"unimproved\s+real|APN|assessor'?s?\s+parcel|parcel\s+(?:no|number))\b",
    re.I,
)
_DE160_ITEM_RE = re.compile(r"(?m)^\s*\d{1,3}\.\s+")


def _de160_item_chunks(text: str) -> list[str]:
    blob = _space_jammed_ocr(text or "")
    start = re.search(
        r"Item\s*No\.|ATTACHMENT\s*NO|INVENTORY AND APPRAISAL ATTACHMENT",
        blob,
        re.I,
    )
    region = blob[start.start() :] if start else blob
    parts = _DE160_ITEM_RE.split(region)
    chunks = [part.strip() for part in parts if len(part.strip()) >= 12]
    return chunks or ([region.strip()] if region.strip() else [])


def parse_de160_text(text: str, death_place: str = "") -> dict:
    """Decedent home / real-property situs from DE-160/DE-161 inventory text."""
    attorney = _caption_street(text)
    best: tuple[int, dict] | None = None
    for chunk in _de160_item_chunks(text):
        if _DE160_NONREAL_RE.search(chunk) and not _DE160_REAL_RE.search(chunk):
            continue
        cleaned = re.sub(r"\bAPN\b[:\s]*[\dA-Za-z\-]+", " ", chunk, flags=re.I)
        cleaned = _prepare_addr_blob(cleaned)
        parsed: dict = {}
        for candidate in _iter_us_addresses(cleaned, prefix="decedent"):
            usable = _usable_decedent_addr(candidate, chunk, death_place)
            if usable:
                parsed = usable
                break
        if not parsed:
            parsed = _usable_decedent_addr(
                _parse_address(cleaned, prefix="decedent"),
                chunk,
                death_place,
            )
        line = str(parsed.get("decedent_residence") or "").lower()
        if not line:
            continue
        if attorney and attorney in line:
            continue
        score = 1
        if _DE160_REAL_RE.search(chunk):
            score += 3
        if _DE160_RESIDENTIAL_RE.search(chunk):
            score += 4
        if _DE160_NONREAL_RE.search(chunk):
            score -= 2
        if best is None or score > best[0]:
            best = (score, parsed)
    if not best:
        return {}
    out = dict(best[1])
    out["decedent_address_source"] = "de160"
    return out


def parse_de160_pdf(path: Path, death_place: str = "") -> dict:
    return parse_de160_text(extract_pdf_text(path), death_place=death_place)


DE147_CONTACT_RE = re.compile(
    r"My address and telephone number are\s*\(specify\)\s*:?\s*(?P<body>.+?)"
    r"(?:I acknowledge|acknowledge that|3\.\s|CONFIDENTIAL INFORMATION|Date:|pate:)",
    re.I | re.S,
)
BARE_PHONE_RE = re.compile(
    r"(?P<phone>\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"
)
CAPTION_PHONE_RE = re.compile(
    r"TELEPHONE NO\.\s*:?\s*(?P<phone>\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
    re.I,
)
FAX_PHONE_RE = re.compile(
    r"FAX NO[^0-9]{0,24}(?P<phone>\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
    re.I,
)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _format_phone(raw: str) -> str:
    digits = _normalize_phone(raw)
    if len(digits) != 10:
        return re.sub(r"\s+", " ", (raw or "")).strip()
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _caption_phones(text: str) -> set[str]:
    if _is_self_represented(text):
        return set()
    found: set[str] = set()
    for rx in (CAPTION_PHONE_RE, FAX_PHONE_RE):
        for match in rx.finditer(text or ""):
            found.add(_normalize_phone(match.group("phone")))
    head = (text or "")[:1800]
    for match in BARE_PHONE_RE.finditer(head):
        if "attorney" in head.lower() or "telephone no" in head.lower():
            found.add(_normalize_phone(match.group("phone")))
    return {item for item in found if item}


def _contact_from_blob(body: str) -> dict:
    out: dict = {}
    blob = re.sub(r"\s+", " ", body or "").strip()
    phone = BARE_PHONE_RE.search(blob)
    rest = blob
    if phone:
        out["petitioner_phone"] = _format_phone(phone.group("phone"))
        rest = (blob[: phone.start()] + blob[phone.end() :]).strip()
    email = EMAIL_RE.search(rest)
    if email:
        out["petitioner_email"] = email.group("email").strip()
        rest = rest.replace(email.group("email"), " ")
    rest = re.sub(r"[\s;]+$", "", rest).strip(" ;,")
    parsed = _parse_address(rest, prefix="mailing") if rest else {}
    if parsed:
        out.update(parsed)
    return out


def _petitioner_phone_from_text(text: str, skip: set[str] | None = None) -> str:
    skip_n = set(skip or ())
    windows: list[str] = []
    for rx in (DE147_CONTACT_RE, ITEM3H_RE, ITEM8_RE, PERMANENT_ADDR_RE):
        match = rx.search(text or "")
        if match:
            windows.append(match.group(0))
    for label in (
        "ACKNOWLEDGMENT OF RECEIPT",
        "address and telephone number",
        "permanent address",
        "8. Name and relationship",
    ):
        idx = (text or "").lower().find(label.lower())
        if idx >= 0:
            windows.append(text[idx : idx + 800])
    for window in windows:
        for match in BARE_PHONE_RE.finditer(window):
            digits = _normalize_phone(match.group("phone"))
            if digits and digits not in skip_n:
                return _format_phone(match.group("phone"))
    if _is_self_represented(text or ""):
        for match in CAPTION_PHONE_RE.finditer(text or ""):
            digits = _normalize_phone(match.group("phone"))
            if digits and digits not in skip_n:
                return _format_phone(match.group("phone"))
    return ""


CONTACT_KEYS = (
    "mailing_address",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
    "petitioner_phone",
    "petitioner_email",
)


def contact_fields(data: dict | None) -> dict:
    out: dict = {}
    for key in CONTACT_KEYS:
        value = (data or {}).get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    return out


def merge_petitioner_contact(*parts: dict) -> dict:
    """Use any petitioner address/phone/email found on DE-111, DE-147, or the row."""
    filled = [contact_fields(part) for part in parts]
    out: dict = {}
    for part in filled:
        line = str(part.get("mailing_address") or "")
        if line and is_junk_mailing_street(line):
            continue
        for key in ("mailing_address", "mailing_city", "mailing_state", "mailing_zip"):
            if key in part and key not in out:
                out[key] = part[key]
    for key in ("petitioner_phone", "petitioner_email"):
        for part in reversed(filled):
            if key in part:
                out[key] = part[key]
                break
    return out


def parse_de147_text(text: str) -> dict:
    text = _clean(text)
    out: dict = {}
    match = DE147_CONTACT_RE.search(text)
    if match:
        out.update(_contact_from_blob(match.group("body")))
    if not out.get("mailing_address"):
        idx = text.lower().find("address and telephone number")
        if idx >= 0:
            out.update(_contact_from_blob(text[idx : idx + 500]))
    skip = _caption_phones(text)
    phone = out.get("petitioner_phone") or ""
    if not phone or _normalize_phone(phone) in skip:
        out.pop("petitioner_phone", None)
        phone = _petitioner_phone_from_text(text, skip=skip)
        if phone:
            out["petitioner_phone"] = phone
    return out


def parse_de147_pdf(path: Path, *, text: str | None = None) -> dict:
    if text is None:
        text = extract_pdf_text(path)
    return parse_de147_text(text)
