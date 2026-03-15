from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from app.domain import (
    ACTION_COST,
    ActionType,
    CropInstance,
    CropStage,
    EventType,
    Farm,
    Season,
    Weather,
)


class ValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def apply_action(
    farm: Farm,
    season: Season,
    action: ActionType,
    plot_id: int | None = None,
    crop_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    _guard_day_open(farm)
    if farm.day > season.total_days:
        raise ValidationError("season_ended", "Season already ended")
    if idempotency_key:
        if idempotency_key in farm.applied_idempotency_keys:
            return {"status": "deduped", "action_points": farm.action_points, "day": farm.day}
        farm.applied_idempotency_keys.add(idempotency_key)

    cost = ACTION_COST[action]
    if farm.action_points < cost:
        raise ValidationError("insufficient_ap", "Not enough action points")

    plot = None
    if plot_id is not None:
        plot = next((p for p in farm.plots if p.plot_id == plot_id), None)
        if not plot:
            raise ValidationError("invalid_plot", "Plot does not exist")

    event = season.event_sequence[farm.day - 1]

    if action == ActionType.PLANT:
        if not plot or plot.crop:
            raise ValidationError("plot_occupied", "Plot already has a crop")
        if crop_id not in season.crop_pool:
            raise ValidationError("invalid_crop", "Unknown crop")
        farm.gold -= 10
        plot.crop = CropInstance(crop_id=crop_id)
        plot.fatigue += 0.1
        plot.recent_crop_history = (plot.recent_crop_history + [crop_id])[-3:]

    elif action == ActionType.WATER:
        if not plot or not plot.crop:
            raise ValidationError("no_crop", "No crop on this plot")
        if event == EventType.WATER_RESTRICTION:
            raise ValidationError("water_restricted", "Watering is restricted today")
        plot.moisture = min(1.3, plot.moisture + 0.25)
        plot.crop.stress = max(0, plot.crop.stress - 1)

    elif action == ActionType.FERTILIZE:
        if not plot or not plot.crop:
            raise ValidationError("no_crop", "No crop on this plot")
        bonus = 0.12 if event == EventType.FERTILITY_SUBSIDY else 0.08
        plot.fertility = min(1.5, plot.fertility + bonus)

    elif action == ActionType.HARVEST:
        if not plot or not plot.crop:
            raise ValidationError("no_crop", "No crop on this plot")
        if plot.crop.stage not in {CropStage.FRUIT, CropStage.OVERGROWN}:
            raise ValidationError("not_harvestable", "Crop is not harvestable")
        income = _sell_price(plot.crop, season, farm.day - 1)
        farm.gold += income
        farm.total_income += income
        farm.harvest_count += 1
        plot.crop.harvested = True
        plot.crop = None

    elif action == ActionType.INSPECT:
        pass

    farm.action_points -= cost
    action_result = {
        "day": farm.day,
        "action": action,
        "plot_id": plot_id,
        "action_points": farm.action_points,
        "gold": farm.gold,
    }
    farm.action_log.append(action_result)
    return action_result


def end_day(farm: Farm, season: Season) -> None:
    if farm.day > season.total_days:
        return

    weather = season.weather_sequence[farm.day - 1]
    event = season.event_sequence[farm.day - 1]

    farm.replay_log.append(
        {
            "day": farm.day,
            "weather": weather,
            "event": event,
            "pre_state": _serialize_plots(farm),
            "farm_state": {
                "gold": farm.gold,
                "total_income": farm.total_income,
                "harvest_count": farm.harvest_count,
                "action_log_len": len(farm.action_log),
            },
        }
    )

    for plot in farm.plots:
        _apply_weather(plot, weather, season)
        _apply_event(plot, event)
        if plot.crop:
            _grow_crop(plot, season)
        plot.moisture = max(0.0, min(1.5, plot.moisture - 0.1))
        plot.fatigue = min(1.0, plot.fatigue + 0.02)

    farm.day += 1
    farm.action_points = 6
    farm.day_open = True


def lock_day(farm: Farm) -> None:
    farm.day_open = False


def restore_last_day(farm: Farm) -> None:
    if not farm.replay_log:
        raise ValidationError("rollback_unavailable", "No replay state available")
    last = farm.replay_log.pop()
    farm.day = last["day"]
    farm.gold = last["farm_state"]["gold"]
    farm.total_income = last["farm_state"]["total_income"]
    farm.harvest_count = last["farm_state"]["harvest_count"]
    farm.action_log = farm.action_log[: last["farm_state"]["action_log_len"]]
    for plot, state in zip(farm.plots, last["pre_state"], strict=True):
        plot.fertility = state["fertility"]
        plot.moisture = state["moisture"]
        plot.drainage = state["drainage"]
        plot.fatigue = state["fatigue"]
        plot.recent_crop_history = list(state["recent_crop_history"])
        crop_state = state["crop"]
        plot.crop = CropInstance(**crop_state) if crop_state else None
    farm.action_points = 6
    farm.day_open = True


def _serialize_plots(farm: Farm) -> list[dict]:
    rows = []
    for p in farm.plots:
        rows.append(
            {
                "fertility": p.fertility,
                "moisture": p.moisture,
                "drainage": p.drainage,
                "fatigue": p.fatigue,
                "recent_crop_history": deepcopy(p.recent_crop_history),
                "crop": asdict(p.crop) if p.crop else None,
            }
        )
    return rows


def _guard_day_open(farm: Farm):
    if not farm.day_open:
        raise ValidationError("day_closed", "Day is closed; call end-day first")


def _apply_weather(plot, weather: Weather, season: Season):
    if weather == Weather.RAIN:
        plot.moisture += 0.2
    elif weather == Weather.HEATWAVE:
        plot.moisture -= 0.25
        if plot.crop:
            profile = season.crop_pool[plot.crop.crop_id]
            plot.crop.stress += profile.drought_sensitivity
    elif weather == Weather.STORM:
        plot.moisture += 0.25
        if plot.crop:
            profile = season.crop_pool[plot.crop.crop_id]
            net = max(0, profile.storm_sensitivity - int(plot.drainage))
            plot.crop.stress += net + 1


def _apply_event(plot, event: EventType):
    if event == EventType.PEST_ALERT and plot.crop:
        plot.crop.stress += 1
    elif event == EventType.FERTILITY_SUBSIDY:
        plot.fertility = min(1.6, plot.fertility + 0.02)


def _grow_crop(plot, season: Season):
    crop = plot.crop
    if not crop:
        return
    profile = season.crop_pool[crop.crop_id]
    crop.age += 1

    growth = 1 + (plot.fertility - 1.0) * 2 - plot.fatigue
    if abs(plot.fertility - profile.soil_preference) <= 0.2:
        growth += 0.6

    if 0.4 <= plot.moisture <= 1.1:
        growth += 1
    else:
        crop.stress += 1

    if crop.stress > 4:
        crop.quality = max(0.5, crop.quality - 0.04)

    crop.growth_points += max(0, int(round(growth)))


def _sell_price(crop: CropInstance, season: Season, day_index: int) -> int:
    definition = season.crop_pool[crop.crop_id]
    quality_factor = max(0.4, crop.quality - crop.stress * 0.03)
    overgrown_penalty = 0.8 if crop.stage == CropStage.OVERGROWN else 1.0
    market = season.market_multiplier[min(day_index, len(season.market_multiplier) - 1)]
    event = season.event_sequence[min(day_index, len(season.event_sequence) - 1)]
    event_bonus = 1.15 if event == EventType.FESTIVAL else 1.0
    return int(definition.market_base * quality_factor * overgrown_penalty * market * event_bonus)


def calculate_achievements(farm: Farm, season: Season) -> list[str]:
    badges: list[str] = []
    if farm.harvest_count >= 3:
        badges.append("steady_harvester")
    if farm.total_income >= 120:
        badges.append("market_master")
    if any(plot.crop and plot.crop.stress == 0 for plot in farm.plots):
        badges.append("gentle_hand")
    if farm.day > season.total_days:
        badges.append("season_finisher")
    return badges


def farm_snapshot(farm: Farm, season: Season) -> dict:
    weather = season.weather_sequence[farm.day - 1] if farm.day <= season.total_days else None
    event = season.event_sequence[farm.day - 1] if farm.day <= season.total_days else None
    avg_quality = 1.0
    live_crops = [p.crop for p in farm.plots if p.crop]
    if live_crops:
        avg_quality = round(sum(c.quality for c in live_crops) / len(live_crops), 3)

    score = (
        farm.gold
        + farm.total_income * season.scoring_rules.income_weight
        + farm.harvest_count * season.scoring_rules.harvest_weight
        + int(avg_quality * season.scoring_rules.quality_weight)
    )

    return {
        "farm_id": farm.farm_id,
        "season_id": farm.season_id,
        "day": farm.day,
        "total_days": season.total_days,
        "action_points": farm.action_points,
        "gold": farm.gold,
        "weather_today": weather,
        "event_today": event,
        "market_multiplier": season.market_multiplier[farm.day - 1] if farm.day <= season.total_days else None,
        "plots": [
            {
                "plot_id": p.plot_id,
                "soil_type": p.soil_type,
                "fertility": round(p.fertility, 2),
                "moisture": round(p.moisture, 2),
                "drainage": p.drainage,
                "fatigue": round(p.fatigue, 2),
                "recent_crop_history": p.recent_crop_history,
                "crop": asdict(p.crop) | {"stage": p.crop.stage} if p.crop else None,
            }
            for p in farm.plots
        ],
        "metrics": {
            "harvest_count": farm.harvest_count,
            "total_income": farm.total_income,
            "average_live_quality": avg_quality,
            "score": score,
            "achievements": calculate_achievements(farm, season),
        },
    }
