"""Address normalization and parcel pick tests."""

from __future__ import annotations

from sweep.parcels import normalize_address, pick_parcel


def test_normalize_suffix_and_city_of():
    n = normalize_address("412 Maple Court, City of Auburn, County of Placer")
    assert n["street_num"] == "412"
    assert n["first_token"] == "MAPLE"
    assert n["suffix"] == "CT"
    assert n["city"] == "AUBURN"


def test_normalize_directionals_and_avenue():
    n = normalize_address("138 Palm Avenue, Auburn, CA 95603")
    assert n["street_num"] == "138"
    assert n["first_token"] == "PALM"
    assert n["suffix"] == "AV"
    assert "AUBURN" in n["city"]


def test_pick_parcel_disambiguates_city():
    features = [
        {
            "attributes": {
                "Apn": "111-111-111-000",
                "SitusAddressFull": "100 MAIN ST, ROSEVILLE, CA",
                "LandValue": "1",
                "Structure": "2",
                "Jurisdiction": "ROSEVILLE",
            }
        },
        {
            "attributes": {
                "Apn": "222-222-222-000",
                "SitusAddressFull": "100 MAIN ST, AUBURN, CA",
                "LandValue": "3",
                "Structure": "4",
                "Jurisdiction": "AUBURN",
            }
        },
    ]
    hit = pick_parcel(features, "100 Main Street, Auburn, CA", apn_source="de111")
    assert hit is not None
    assert hit.apn == "222-222-222-000"
    assert hit.confidence == "high"
    assert hit.apn_source == "de111"


def test_petitioner_source_is_weak():
    features = [
        {
            "attributes": {
                "Apn": "001062015000",
                "SitusAddressFull": "412 MAPLE CT, AUBURN, CA",
                "LandValue": "1",
                "Structure": "2",
                "Jurisdiction": "AUBURN",
            }
        }
    ]
    hit = pick_parcel(features, "412 Maple Ct, Auburn", apn_source="petitioner_address")
    assert hit is not None
    assert hit.apn == "001-062-015-000"
    assert hit.confidence == "weak"
