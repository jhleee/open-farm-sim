from __future__ import annotations

from app.domain import ActionType, build_season, default_farm
from app.engine import apply_action, end_day, farm_snapshot


def safe_water_or_inspect(farm, season):
    try:
        apply_action(farm, season, ActionType.WATER, plot_id=1)
    except Exception:
        apply_action(farm, season, ActionType.INSPECT, plot_id=1)


def run_strategy(seed: int, strategy: dict, days: int = 10) -> dict:
    season = build_season(f"sim-{seed}", seed=seed, total_days=14)
    crop_id = next(iter(season.crop_pool.keys()))
    farm = default_farm(f"farm-{seed}-{strategy['name']}", season.season_id)

    for day_i in range(days):
        if farm.day > season.total_days:
            break

        p1 = farm.plots[0]
        if p1.crop is None and farm.action_points >= 2:
            apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)

        while farm.action_points > 0:
            p1 = farm.plots[0]
            if p1.crop and p1.crop.stage in {"fruit", "overgrown"} and farm.action_points >= 2:
                apply_action(farm, season, ActionType.HARVEST, plot_id=1)
                continue

            if p1.crop and farm.action_points >= 2 and day_i % strategy["fert_every"] == 0:
                apply_action(farm, season, ActionType.FERTILIZE, plot_id=1)
                continue

            if p1.crop and farm.action_points >= 1 and p1.moisture < strategy["water_threshold"]:
                safe_water_or_inspect(farm, season)
                continue

            # REST는 AP를 소모하지 않으므로 루프 정체를 피하기 위해 INSPECT로 소모
            if farm.action_points >= 1:
                apply_action(farm, season, ActionType.INSPECT, plot_id=1)

        end_day(farm, season)

    return farm_snapshot(farm, season)
