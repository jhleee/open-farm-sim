from fastapi.testclient import TestClient

from app.domain import ActionType, EventType, build_season, default_farm
from app.engine import apply_action, end_day, farm_snapshot, restore_last_day
from app.main import FARMS, app


client = TestClient(app)


def setup_function():
    FARMS.clear()


def _first_crop_id(season_data: dict) -> str:
    return season_data["crop_pool"][0]["crop_id"]


def test_scenario_festival_day_increases_harvest_value_vs_non_festival():
    season = build_season("s", seed=44, total_days=14)
    crop_id = next(iter(season.crop_pool.keys()))

    farm_a = default_farm("a", season.season_id)
    farm_b = default_farm("b", season.season_id)

    apply_action(farm_a, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    apply_action(farm_b, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    for _ in range(6):
        farm_a.action_points = 6
        farm_b.action_points = 6
        end_day(farm_a, season)
        end_day(farm_b, season)

    plot_a = farm_a.plots[0]
    plot_b = farm_b.plots[0]
    plot_a.crop.age = plot_b.crop.age = 5
    plot_a.crop.stress = plot_b.crop.stress = 0
    plot_a.crop.quality = plot_b.crop.quality = 1.0
    plot_a.crop.growth_points = plot_b.crop.growth_points = 10

    day_idx = farm_a.day - 1
    season.event_sequence[day_idx] = EventType.FESTIVAL
    apply_action(farm_a, season, ActionType.HARVEST, plot_id=1)
    festival_gold = farm_a.gold

    season.event_sequence[day_idx] = EventType.NONE
    apply_action(farm_b, season, ActionType.HARVEST, plot_id=1)
    normal_gold = farm_b.gold

    assert festival_gold > normal_gold


def test_scenario_rollback_restores_farm_level_metrics_and_logs():
    season = build_season("s", seed=55)
    crop_id = next(iter(season.crop_pool.keys()))
    farm = default_farm("roll", season.season_id)

    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    pre = farm_snapshot(farm, season)
    pre_gold = farm.gold
    pre_income = farm.total_income
    pre_harvest = farm.harvest_count
    pre_action_log_len = len(farm.action_log)

    end_day(farm, season)
    restore_last_day(farm)

    after = farm_snapshot(farm, season)
    assert after["day"] == pre["day"]
    assert farm.gold == pre_gold
    assert farm.total_income == pre_income
    assert farm.harvest_count == pre_harvest
    assert len(farm.action_log) == pre_action_log_len


def test_scenario_two_agents_same_sequence_same_outcome():
    season = client.get("/v1/season").json()
    crop_id = _first_crop_id(season)

    for farm_id in ["alpha", "beta"]:
        assert client.post(f"/v1/farms/{farm_id}/join").status_code == 200

    for day in range(1, 5):
        for farm_id in ["alpha", "beta"]:
            if day == 1:
                client.post(
                    f"/v1/farms/{farm_id}/actions",
                    json={"action": "plant", "plot_id": 1, "crop_id": crop_id, "idempotency_key": f"{farm_id}-{day}-p"},
                )
            client.post(
                f"/v1/farms/{farm_id}/actions",
                json={"action": "inspect", "plot_id": 1, "idempotency_key": f"{farm_id}-{day}-i1"},
            )
            wr = client.post(
                f"/v1/farms/{farm_id}/actions",
                json={"action": "water", "plot_id": 1, "idempotency_key": f"{farm_id}-{day}-w"},
            )
            if wr.status_code == 400:
                client.post(
                    f"/v1/farms/{farm_id}/actions",
                    json={"action": "inspect", "plot_id": 1, "idempotency_key": f"{farm_id}-{day}-i2"},
                )
            client.post(f"/v1/farms/{farm_id}/end-day")

    a = client.get("/v1/farms/alpha/state").json()
    b = client.get("/v1/farms/beta/state").json()

    assert a["day"] == b["day"]
    assert a["gold"] == b["gold"]
    assert a["metrics"]["score"] == b["metrics"]["score"]
