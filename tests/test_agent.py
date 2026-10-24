import json
import shutil
import pytest
from pathlib import Path
from src.agent import CivicComplaintAgent

TEST_DATA_DIR = Path(__file__).parent / "test_data_agent"
TEST_AMC_PATH = TEST_DATA_DIR / "test_amc.json"

@pytest.fixture(autouse=True)
def setup_agent_test_env(monkeypatch):
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    root_amc = Path(__file__).parent.parent / "data" / "amc.json"
    with open(root_amc, "r", encoding="utf-8") as f:
        seed_data = json.load(f)
    with open(TEST_AMC_PATH, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, indent=2)
    monkeypatch.setenv("AMC_DATA_PATH", str(TEST_AMC_PATH))
    yield
    if TEST_DATA_DIR.exists():
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)


def test_agent_low_confidence_rejection(monkeypatch):
    """Acceptance test 4: Ambiguous/blurry photo -> agent refuses to file and asks a question."""
    agent = CivicComplaintAgent()
    
    monkeypatch.setattr(
        "src.agent.analyze_image",
        lambda img_bytes: {
            "issue": "unclear",
            "confidence": 0.45,
            "description": "Blurry image with unclear road surface"
        }
    )
    
    response = agent.run_turn(image_bytes=b"fake_image_data")
    assert "Cannot proceed with filing" in response
    assert agent.pending_confirmation is None


def test_agent_full_flow_with_confirmation(monkeypatch):
    """Acceptance test 1: Upload photo + Maninagar -> agent confirms -> files -> returns new ID."""
    agent = CivicComplaintAgent()
    
    monkeypatch.setattr(
        "src.agent.analyze_image",
        lambda img_bytes: {
            "issue": "garbage",
            "confidence": 0.95,
            "description": "Overflowing garbage dump on corner"
        }
    )
    
    # Step 1: Upload photo + "Maninagar"
    res1 = agent.run_turn(user_message="Maninagar", image_bytes=b"fake_garbage_image")
    assert "Civic Issue Identified" in res1
    assert "Maninagar" in res1
    assert "Solid Waste Management" in res1
    assert agent.pending_confirmation is not None
    
    # Step 2: Confirm
    res2 = agent.run_turn(user_message="Confirm")
    assert "Complaint Successfully Filed" in res2
    assert "AMC-2026-000124" in res2
    assert agent.last_tracking_id == "AMC-2026-000124"
    
    # Acceptance test 2: "what's the status?" -> returns that complaint's status
    res3 = agent.run_turn(user_message="what's the status?")
    assert "Complaint Status Record" in res3
    assert "AMC-2026-000124" in res3


def test_agent_duplicate_detection(monkeypatch):
    """Acceptance test 6: Filing existing issue in existing ward returns existing ID."""
    agent = CivicComplaintAgent()
    
    monkeypatch.setattr(
        "src.agent.analyze_image",
        lambda img_bytes: {
            "issue": "pothole",
            "confidence": 0.95,
            "description": "Pothole in Navrangpura"
        }
    )
    
    res1 = agent.run_turn(user_message="Navrangpura", image_bytes=b"fake_pothole_image")
    assert agent.pending_confirmation is not None
    
    res2 = agent.run_turn(user_message="Confirm")
    assert "Existing Active Complaint Found" in res2
    assert "AMC-2026-000123" in res2


def test_agent_status_seed_complaint():
    """Acceptance test 3: 'status of AMC-2026-000123' -> returns Assigned."""
    agent = CivicComplaintAgent()
    res = agent.run_turn(user_message="status of AMC-2026-000123")
    assert "AMC-2026-000123" in res
    assert "Assigned" in res
    assert "Roads & Buildings" in res


def test_agent_fake_id_status():
    """Acceptance test 7: Fake ID 'AMC-2026-999999' -> clear not-found message."""
    agent = CivicComplaintAgent()
    res = agent.run_turn(user_message="status of AMC-2026-999999")
    assert "not found" in res.lower()


