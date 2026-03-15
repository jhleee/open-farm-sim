from fastapi.testclient import TestClient

from app.main import FARMS, app


client = TestClient(app)


def setup_function():
    FARMS.clear()


def test_join_state_and_version_endpoints():
    rv = client.get("/v1/version")
    assert rv.status_code == 200
    assert rv.json()["api_version"] == "v1"

    join = client.post("/v1/farms/a/join")
    assert join.status_code == 200
    state = client.get("/v1/farms/a/state")
    assert state.status_code == 200
    assert state.json()["farm_id"] == "a"


def test_almanac_and_season_payload_include_full_sequences():
    season = client.get("/v1/season").json()
    almanac = client.get("/v1/season/almanac").json()
    assert len(almanac["days"]) == season["total_days"]
    assert len(season["crop_pool"]) == 4


def test_action_flow_and_logs_report_leaderboard():
    join = client.post("/v1/farms/x/join").json()
    crop_id = client.get("/v1/season").json()["crop_pool"][0]["crop_id"]

    r1 = client.post(
        "/v1/farms/x/actions",
        json={"action": "plant", "plot_id": 1, "crop_id": crop_id, "idempotency_key": "abc-1234"},
    )
    assert r1.status_code == 200
    # duplicate same key deduped
    r2 = client.post(
        "/v1/farms/x/actions",
        json={"action": "plant", "plot_id": 2, "crop_id": crop_id, "idempotency_key": "abc-1234"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "deduped"

    assert client.post("/v1/farms/x/end-day").status_code == 200
    logs = client.get("/v1/farms/x/logs").json()
    assert len(logs["actions"]) >= 1
    assert len(logs["replay"]) >= 1

    report = client.get("/v1/farms/x/report")
    assert report.status_code == 200
    assert "metrics" in report.json()

    lb = client.get("/v1/leaderboard")
    assert lb.status_code == 200
    assert lb.json()["entries"][0]["farm_id"] == "x"


def test_rollback_endpoint_recovers_day():
    crop_id = client.get("/v1/season").json()["crop_pool"][0]["crop_id"]
    client.post("/v1/farms/r/join")
    client.post("/v1/farms/r/actions", json={"action": "plant", "plot_id": 1, "crop_id": crop_id})
    client.post("/v1/farms/r/end-day")
    state_after = client.get("/v1/farms/r/state").json()
    assert state_after["day"] == 2

    rb = client.post("/v1/farms/r/rollback")
    assert rb.status_code == 200
    state_now = rb.json()
    assert state_now["day"] == 1


def test_web_pages_are_served():
    start = client.get('/web/start')
    assert start.status_code == 200
    assert '첫 사용 방법' in start.text

    ops = client.get('/web/ops')
    assert ops.status_code == 200
    assert '랭킹 / 작업로그' in ops.text
