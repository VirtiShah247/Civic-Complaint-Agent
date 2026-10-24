import os
import json
import shutil
import pytest
from pathlib import Path

# Paths for testing
TEST_DATA_DIR = Path(__file__).parent / "test_data"
TEST_AMC_PATH = TEST_DATA_DIR / "test_amc.json"
TEST_GEOCACHE_PATH = TEST_DATA_DIR / "test_geocache.json"

@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up clean isolated test data directory and environment before each test."""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy fresh seed amc.json to test path
    root_amc = Path(__file__).parent.parent / "data" / "amc.json"
    with open(root_amc, "r", encoding="utf-8") as f:
        seed_data = json.load(f)
    with open(TEST_AMC_PATH, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, indent=2)
        
    # Remove test geocache if exists
    if TEST_GEOCACHE_PATH.exists():
        TEST_GEOCACHE_PATH.unlink()
        
    # Monkeypatch paths in tools module
    monkeypatch.setenv("AMC_DATA_PATH", str(TEST_AMC_PATH))
    monkeypatch.setenv("GEOCACHE_PATH", str(TEST_GEOCACHE_PATH))
    
    yield
    
    # Cleanup
    if TEST_DATA_DIR.exists():
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)


def test_resolve_ward_cg_road_and_variants():
    """Acceptance test 5: 'CG Road' and 'C.G. Road' resolve to W12."""
    from src.tools import resolve_ward
    
    res1 = resolve_ward(area_text="CG Road")
    assert "error" not in res1, f"Failed for 'CG Road': {res1}"
    assert res1["ward_id"] == "W12"
    assert res1["ward_name"] == "Navrangpura"
    
    res2 = resolve_ward(area_text="C.G. Road")
    assert "error" not in res2, f"Failed for 'C.G. Road': {res2}"
    assert res2["ward_id"] == "W12"
    assert res2["ward_name"] == "Navrangpura"

    res3 = resolve_ward(area_text="cg road")
    assert res3["ward_id"] == "W12"


def test_resolve_ward_other_areas():
    """Test resolution of various area aliases in Ahmedabad."""
    from src.tools import resolve_ward
    
    # Maninagar areas
    res_mani = resolve_ward(area_text="Kankaria")
    assert res_mani["ward_id"] == "W27"
    assert res_mani["ward_name"] == "Maninagar"
    
    res_jawahar = resolve_ward(area_text="jawahar chowk")
    assert res_jawahar["ward_id"] == "W27"

    # Bodakdev
    res_sbr = resolve_ward(area_text="Sindhu Bhavan Road")
    assert res_sbr["ward_id"] == "W05"
    assert res_sbr["ward_name"] == "Bodakdev"


def test_resolve_ward_unknown_area():
    """Never invent a ward for unknown areas; return clear error."""
    from src.tools import resolve_ward
    
    res = resolve_ward(area_text="Antarctica Penguin Zone 99")
    assert "error" in res
    assert "ward_id" not in res


def test_file_complaint_generates_sequential_id():
    """Acceptance test 1: Generates next ID (AMC-2026-000124) and records complaint."""
    from src.tools import file_complaint, get_status
    
    result = file_complaint(
        ward_id="W12",
        issue="garbage",
        description="Overflowing garbage bin near stadium"
    )
    
    assert result["trackingId"] == "AMC-2026-000124"
    assert result["department"] == "Solid Waste Management"
    assert result["status"] == "Assigned"
    assert result["is_duplicate"] is False
    
    # Verify it is retrievable via get_status
    status_record = get_status(tracking_id="AMC-2026-000124")
    assert status_record["trackingId"] == "AMC-2026-000124"
    assert status_record["ward_id"] == "W12"
    assert status_record["issue"] == "garbage"


def test_file_complaint_duplicate_prevention():
    """Acceptance test 6: Filing the same issue in the same ward returns the existing ID."""
    from src.tools import file_complaint
    
    # Seed already has: AMC-2026-000123 with W12, pothole, Assigned
    dup_result = file_complaint(
        ward_id="W12",
        issue="pothole",
        description="Another report of pothole in Navrangpura"
    )
    
    assert dup_result["trackingId"] == "AMC-2026-000123"
    assert dup_result["is_duplicate"] is True
    assert dup_result["status"] == "Assigned"


def test_get_status_existing_seed():
    """Acceptance test 3: 'status of AMC-2026-000123' -> returns Assigned."""
    from src.tools import get_status
    
    res = get_status(tracking_id="AMC-2026-000123")
    assert res["trackingId"] == "AMC-2026-000123"
    assert res["status"] == "Assigned"
    assert res["department"] == "Roads & Buildings"


def test_get_status_default_session():
    """Acceptance test 2: When tracking_id is None, returns most recent session complaint."""
    from src.tools import file_complaint, get_status
    
    # File a new complaint
    new_c = file_complaint(ward_id="W27", issue="streetlight", description="Dark street in Maninagar")
    tid = new_c["trackingId"]
    
    # Query without ID, passing session_last_id
    res = get_status(tracking_id=None, session_last_id=tid)
    assert res["trackingId"] == tid
    assert res["status"] == "Assigned"


def test_get_status_fake_id_not_found():
    """Acceptance test 7: Fake ID 'AMC-2026-999999' -> clear not-found message."""
    from src.tools import get_status
    
    res = get_status(tracking_id="AMC-2026-999999")
    assert "error" in res
    assert "not found" in res["error"].lower()


def test_geocache_deduplication(monkeypatch):
    """Amendment 4: Two identical reverse-geocode requests produce one network call (cache hit)."""
    from src.geocoding import reverse_geocode_nominatim
    
    network_call_count = 0
    
    def mock_nominatim_get(url, headers, params, timeout):
        nonlocal network_call_count
        network_call_count += 1
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "address": {
                        "suburb": "Navrangpura",
                        "city": "Ahmedabad",
                        "state": "Gujarat"
                    }
                }
        return MockResponse()
        
    import requests
    monkeypatch.setattr(requests, "get", mock_nominatim_get)
    
    lat, lon = 23.0373, 72.5562
    
    # Call 1: network call
    res1 = reverse_geocode_nominatim(lat, lon, cache_file=str(TEST_GEOCACHE_PATH))
    assert res1["suburb"] == "Navrangpura"
    assert network_call_count == 1
    
    # Call 2: cache hit, should NOT call network
    res2 = reverse_geocode_nominatim(lat, lon, cache_file=str(TEST_GEOCACHE_PATH))
    assert res2["suburb"] == "Navrangpura"
    assert network_call_count == 1  # Still 1!


def test_resolve_ward_gps_high_and_low_confidence(monkeypatch):
    """Amendment 4: EXIF GPS with Ahmedabad coordinates resolves to a ward or asks for area."""
    from src.tools import resolve_ward
    import src.geocoding
    
    # Mock reverse geocode returning Navrangpura
    monkeypatch.setattr(
        src.geocoding,
        "reverse_geocode_nominatim",
        lambda lat, lon, cache_file=None: {"suburb": "Navrangpura"}
    )
    
    res = resolve_ward(exif_gps=(23.0373, 72.5562))
    assert res["ward_id"] == "W12"
    assert res["ward_name"] == "Navrangpura"
    assert res["source"] == "gps"
    
    # Mock reverse geocode returning ambiguous / low confidence location
    monkeypatch.setattr(
        src.geocoding,
        "reverse_geocode_nominatim",
        lambda lat, lon, cache_file=None: {"suburb": "Unknown Faraway Outpost"}
    )
    
    res_unknown = resolve_ward(exif_gps=(23.5, 72.9))
    assert "error" in res_unknown
    assert "confirm or enter your area" in res_unknown["error"]

