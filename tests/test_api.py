from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_health_and_empty_state(client):
    assert client.get("/health").json()["status"] == "ok"
    o = client.get("/overview").json()
    assert o["sessions"] == 0 and o["waste_token_pct"] == 0.0
    assert client.get("/daily").json() == []
    assert client.get("/users").json() == []
    assert client.get("/forecast").json()["projected_tokens"] == 0
    assert client.get("/validation").json()["precision_pct"] is None


def test_seed_is_idempotent_and_flagged_simulated(client):
    a = client.post("/demo/seed").json()
    b = client.post("/demo/seed").json()
    assert a["sessions"] == b["sessions"] > 100
    assert b["removed"] == a["sessions"]
    o = client.get("/overview").json()
    assert o["has_simulated"] and not o["has_real"]
    assert 5 < o["waste_token_pct"] < 60  # plausible, not absurd
    assert o["waste_tokens"] <= o["total_tokens"] and o["waste_cost"] <= o["total_cost"]
    assert client.get("/overview?source=real").json()["sessions"] == 0


def test_team_view_matches_designed_habits(client):
    client.post("/demo/seed")
    users = {u["user"]: u for u in client.get("/users").json()}
    assert len(users) == 6
    assert users["meera"]["waste_token_pct"] < users["aarav"]["waste_token_pct"]
    assert users["kabir"]["waste_cost"] > 0


def test_findings_filters_and_session_detail(client):
    client.post("/demo/seed")
    loops = client.get("/findings?rule=agent_loop").json()
    assert loops and all(f["rule"] == "agent_loop" for f in loops)
    assert client.get("/findings?rule=nope").status_code == 422
    top = client.get("/sessions?limit=1").json()[0]
    detail = client.get(f"/sessions/{top['id']}").json()
    assert len(detail["turn_data"]) == detail["turns"]
    assert client.get("/sessions/does-not-exist").status_code == 404


def test_upload_claude_code_log(client):
    with open(FIXTURE, "rb") as fh:
        r = client.post("/import/claude-code", files={"files": ("s.jsonl", fh)}, data={"user": "Gunesh"})
    assert r.status_code == 200
    assert r.json()["sessions_new"] == 1 and r.json()["turns"] == 3
    with open(FIXTURE, "rb") as fh:  # re-import replaces, never duplicates
        r2 = client.post("/import/claude-code", files={"files": ("s.jsonl", fh)}, data={"user": "gunesh"})
    assert r2.json()["sessions_replaced"] == 1
    o = client.get("/overview?source=real").json()
    assert o["sessions"] == 1 and o["turns"] == 3


def test_upload_garbage_file(client):
    r = client.post("/import/claude-code", files={"files": ("bad.jsonl", b"\x00\xff not a log\n{}")})
    assert r.status_code == 200 and r.json()["empty_files"] == 1


def test_generic_session_validation(client):
    ok = {"id": "api-1", "user": "Bot", "turns": [{"timestamp": "2026-11-10T05:00:00Z", "model": "gpt-4o", "input_tokens": 500, "output_tokens": 50}]}
    assert client.post("/sessions", json=ok).status_code == 201
    assert client.post("/sessions", json={**ok, "turns": []}).status_code == 422
    bad = {**ok, "turns": [{**ok["turns"][0], "input_tokens": -5}]}
    assert client.post("/sessions", json=bad).status_code == 422


def test_labels_measure_rule_precision(client):
    client.post("/demo/seed")
    queue = client.get("/validation").json()["queue"]
    a, b = queue[0], queue[1]
    assert client.post("/labels", json={"session_id": a["session_id"], "rule": a["rule"], "is_waste": True}).status_code == 200
    client.post("/labels", json={"session_id": b["session_id"], "rule": b["rule"], "is_waste": False})
    v = client.get("/validation").json()
    assert v["labeled"] == 2 and v["confirmed"] == 1 and v["precision_pct"] == 50.0
    client.post("/labels", json={"session_id": b["session_id"], "rule": b["rule"], "is_waste": True})  # change verdict
    assert client.get("/validation").json()["precision_pct"] == 100.0
    assert client.post("/labels", json={"session_id": "x", "rule": a["rule"], "is_waste": True}).status_code == 404
