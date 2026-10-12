def _discover(client):
    return client.post("/api/stories/discover", json={"connector": "library", "query": ""}).json()


def test_discovery_records_provenance_and_never_auto_approves(client):
    results = _discover(client)
    assert len(results) == 3
    for r in results:
        s = r["story"]
        assert r["status"] == "created"
        assert s["rights_status"] == "review_required"  # a claim exists, a human must verify it
        assert s["license_evidence_url"].startswith("https://www.gutenberg.org/")
        assert s["content_hash"]


def test_rediscovery_is_deduplicated(client):
    _discover(client)
    again = _discover(client)
    assert {r["status"] for r in again} == {"duplicate"}


def test_project_requires_approved_rights(client):
    story = _discover(client)[0]["story"]
    r = client.post("/api/projects", json={"source_id": story["id"]})
    assert r.status_code == 422
    assert "not approved" in r.json()["detail"]


def test_approval_requires_license_and_evidence(client):
    r = client.post("/api/stories/upload", json={"title": "My story", "text": "word " * 80, "license_type": None})
    sid = r.json()["story"]["id"]
    assert r.json()["story"]["rights_status"] == "pending"
    r = client.post(f"/api/stories/{sid}/rights", json={"status": "approved"})
    assert r.status_code == 422
    r = client.post(f"/api/stories/{sid}/rights", json={"status": "approved", "license_type": "cc_by_nd",
                                                       "notes": "checked"})
    assert r.status_code == 422 and "adaptation" in r.json()["detail"]
    r = client.post(f"/api/stories/{sid}/rights", json={"status": "approved", "license_type": "user_owned",
                                                       "notes": "I wrote it"})
    assert r.status_code == 200 and r.json()["rights_status"] == "approved"
