from fovea.config import override_settings


def test_health_and_ready(client) -> None:  # type: ignore[no-untyped-def]
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["index_chunks"] > 50
    assert client.get("/ready").json() == {"ready": True}
    assert "fovea_index_chunks" in client.get("/metrics").text


def test_ask_returns_tools_sources_and_grounding(client) -> None:  # type: ignore[no-untyped-def]
    body = {
        "question": "Right eye wet AMD, should we offer anti VEGF?",
        "context": {
            "right": {
                "diagnosis": "wet AMD",
                "bcva": "6/24",
                "permanent_foveal_damage": False,
                "lesion_disc_areas": 2,
                "recent_progression": True,
            }
        },
    }
    data = client.post("/v1/ask", json=body).json()
    assert data["final"]["status"] == "answered"
    assert any(t["tool"] == "therapy_options" for t in data["tools"])
    assert data["sources"][0]["url"].startswith("https://")
    assert client.post("/v1/ask", json=body).json()["cached"] is True


def test_stream_event_order(client) -> None:  # type: ignore[no-untyped-def]
    text = client.post("/v1/ask/stream", json={"question": "Chemical splash with bleach in the eye"}).text
    order = [line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("event: ")]
    assert order[0] == "meta" and order[1] == "emergency" and order[-1] == "final"


def test_tool_endpoints(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post("/v1/tools/acuity", json={"value": "6/12"}).json()["details"]["etdrs_letters"] == 70
    iol = client.post("/v1/tools/biometry", json={"axial_length_mm": 23.5, "k1_d": 44, "k2_d": 44}).json()
    assert 19.5 < iol["details"]["srkt_exact_d"] < 20.5
    grade = client.post("/v1/tools/grading", json={"features": {"irma": True}}).json()
    assert grade["details"]["outcome"] == "R2M0"
    te = client.post(
        "/v1/tools/intervals",
        json={
            "agent": "faricimab",
            "condition": "wet_amd",
            "injections_given": 6,
            "current_interval_weeks": 12,
        },
    ).json()
    assert te["details"]["next_interval_weeks"] == 16
    hcq = client.post(
        "/v1/tools/hydroxychloroquine", json={"weight_kg": 60, "daily_dose_mg": 400, "years_on_treatment": 2}
    ).json()
    assert hcq["details"]["monitoring_due"]
    screen = client.post(
        "/v1/tools/screen", json={"planned": ["timolol"], "context": {"conditions": ["asthma"]}}
    ).json()
    assert screen["findings"][0]["severity"] == "contraindication"
    therapy = client.post(
        "/v1/tools/therapy",
        json={"condition": "dmo", "eye": "left", "context": {"left": {"central_subfield_thickness_um": 420}}},
    ).json()
    assert therapy["details"]["condition"] == "dmo"
    gl = client.post("/v1/tools/glaucoma", json={"iop_mmhg": 26}).json()
    assert gl["cards"][0]["details"]["meets_threshold"]
    assert client.post("/v1/tools/trials", json={"condition": "wet_amd"}).status_code == 200


def test_validation_errors(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post("/v1/tools/acuity", json={"value": "banana"}).status_code == 422
    assert client.post("/v1/tools/glaucoma", json={}).status_code == 422
    assert client.post("/v1/ask", json={"question": "x"}).status_code == 422


def test_feedback_and_governance(client) -> None:  # type: ignore[no-untyped-def]
    answer = client.post("/v1/ask", json={"question": "What did the LiGHT trial show?"}).json()
    rid = answer["final"]["request_id"]
    fb = client.post(
        "/v1/feedback",
        json={
            "request_id": rid,
            "rating": -1,
            "reasons": ["outdated", "nonsense"],
            "comment": "Mr Bob Jones disagreed",
        },
    ).json()
    assert fb["reasons"] == ["outdated"] and "Bob Jones" not in fb["comment"]
    summary = client.get("/v1/audit/summary").json()
    assert summary["answers"] >= 1 and summary["feedback"]["negative"] >= 1
    knowledge = client.get("/v1/knowledge").json()
    assert {r["name"] for r in knowledge["rule_files"]} >= {"therapy_matrix", "safety_rules", "emergencies"}


def test_api_keys_enforced(client, settings) -> None:  # type: ignore[no-untyped-def]
    from dataclasses import asdict

    override_settings(**{**asdict(settings), "api_keys": ["secret"], "admin_api_keys": ["admin"]})
    try:
        assert client.post("/v1/tools/acuity", json={"value": "6/6"}).status_code == 401
        assert (
            client.post(
                "/v1/tools/acuity", json={"value": "6/6"}, headers={"X-API-Key": "secret"}
            ).status_code
            == 200
        )
        assert client.get("/v1/audit/summary", headers={"X-API-Key": "secret"}).status_code == 403
        assert client.get("/v1/audit/summary", headers={"X-API-Key": "admin"}).status_code == 200
    finally:
        override_settings(**asdict(settings))
