"""Test progress endpoints for Guesstimate."""
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_progress_guesstimate():
    response = client.get("/api/progress/guesstimate")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "timeline" in data
    assert "summary" in data
    summary = data["summary"]
    assert "weighting_metadata" in summary
    assert summary["weighting_metadata"]["mece"] == 35
    assert summary["weighting_metadata"]["assumption"] == 25
    assert summary["weighting_metadata"]["math"] == 20
    assert summary["weighting_metadata"]["sanity"] == 20

    print("[OK] /api/progress/guesstimate returned 200 with complete summary & weighting metadata.")
    if data["timeline"]:
        latest = data["timeline"][-1]
        print(f"[OK] Latest point: score={latest['score']}, mece={latest['structure_score']}, proxy={latest['proxy_score']}, math={latest['math_score']}, sanity={latest['sanity_score']}")

if __name__ == "__main__":
    test_progress_guesstimate()
