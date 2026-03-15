from fastapi.testclient import TestClient

from app.main import FARMS, app


client = TestClient(app)


def setup_function():
    FARMS.clear()


def _choose_action(state: dict, crop_id: str, step_idx: int) -> dict:
    ap = state["action_points"]
    plots = state["plots"]

    for plot in plots:
        crop = plot["crop"]
        if crop and crop["stage"] in {"fruit", "overgrown"} and ap >= 2:
            return {"action": "harvest", "plot_id": plot["plot_id"], "idempotency_key": f"{state['day']}-h-{step_idx}"}

    for plot in plots:
        if not plot["crop"] and ap >= 2:
            return {
                "action": "plant",
                "plot_id": plot["plot_id"],
                "crop_id": crop_id,
                "idempotency_key": f"{state['day']}-p-{plot['plot_id']}-{step_idx}",
            }

    for plot in sorted(plots, key=lambda p: p["moisture"]):
        if plot["crop"] and ap >= 1:
            return {"action": "water", "plot_id": plot["plot_id"], "idempotency_key": f"{state['day']}-w-{plot['plot_id']}-{step_idx}"}

    if ap >= 1:
        return {"action": "inspect", "plot_id": 1, "idempotency_key": f"{state['day']}-i-{step_idx}"}

    return {"action": "rest", "idempotency_key": f"{state['day']}-r-{step_idx}"}


def _play_full_season(farm_id: str) -> dict:
    season = client.get("/v1/season").json()
    crop_id = season["crop_pool"][0]["crop_id"]
    total_days = season["total_days"]

    assert client.post(f"/v1/farms/{farm_id}/join").status_code == 200

    safety = 0
    while True:
        safety += 1
        assert safety < 1000, "loop safety triggered"

        state = client.get(f"/v1/farms/{farm_id}/state").json()
        if state["day"] > total_days:
            break

        step = 0
        while state["action_points"] > 0:
            step += 1
            action = _choose_action(state, crop_id, step)
            resp = client.post(f"/v1/farms/{farm_id}/actions", json=action)
            # 이벤트에 따라 물 제한이 걸릴 수 있으므로 우회 액션 수행
            if resp.status_code == 400 and "water_restricted" in str(resp.json()):
                fallback = {
                    "action": "inspect",
                    "plot_id": 1,
                    "idempotency_key": f"{state['day']}-fb-{step}",
                }
                resp = client.post(f"/v1/farms/{farm_id}/actions", json=fallback)
            assert resp.status_code == 200
            state = client.get(f"/v1/farms/{farm_id}/state").json()

        assert client.post(f"/v1/farms/{farm_id}/end-day").status_code == 200

    final_state = client.get(f"/v1/farms/{farm_id}/state").json()
    assert final_state["day"] == total_days + 1
    return final_state


def test_end_to_end_season_run_and_cross_surface_consistency():
    final_state = _play_full_season("e2e-agent")

    report = client.get("/v1/farms/e2e-agent/report")
    assert report.status_code == 200
    report_data = report.json()

    logs = client.get("/v1/farms/e2e-agent/logs")
    assert logs.status_code == 200
    logs_data = logs.json()

    leaderboard = client.get("/v1/leaderboard")
    assert leaderboard.status_code == 200
    entries = leaderboard.json()["entries"]
    assert entries and entries[0]["farm_id"] == "e2e-agent"

    assert report_data["metrics"]["score"] == final_state["metrics"]["score"]
    assert report_data["metrics"]["harvest_count"] == final_state["metrics"]["harvest_count"]
    assert len(logs_data["replay"]) == final_state["total_days"]
    assert len(logs_data["actions"]) >= final_state["total_days"]
    assert "season_finisher" in final_state["metrics"]["achievements"]
