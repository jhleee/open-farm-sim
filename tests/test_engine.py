from app.domain import ActionType, EventType, build_season, default_farm
from app.engine import ValidationError, apply_action, end_day, farm_snapshot, restore_last_day


def first_crop_id(season):
    return next(iter(season.crop_pool.keys()))


def test_season_is_deterministic_with_seed_for_weather_event_market_and_crops():
    a = build_season("s", seed=11, total_days=10, crop_count=4)
    b = build_season("s", seed=11, total_days=10, crop_count=4)
    assert a.weather_sequence == b.weather_sequence
    assert a.event_sequence == b.event_sequence
    assert a.market_multiplier == b.market_multiplier
    assert list(a.crop_pool.keys()) == list(b.crop_pool.keys())


def test_growth_has_multiple_stages_and_harvest_path():
    season = build_season("s", seed=1)
    season.event_sequence[:] = [EventType.NONE for _ in season.event_sequence]
    farm = default_farm("f", season.season_id)
    crop_id = first_crop_id(season)
    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    for _ in range(8):
        farm.action_points = 6
        apply_action(farm, season, ActionType.WATER, plot_id=1)
        end_day(farm, season)

    snap = farm_snapshot(farm, season)
    stage = snap["plots"][0]["crop"]["stage"]
    assert stage in {"flower", "fruit", "overgrown"}


def test_action_points_validation():
    season = build_season("s", seed=5)
    farm = default_farm("f", season.season_id)
    crop_id = first_crop_id(season)
    farm.action_points = 1
    try:
        apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert exc.code == "insufficient_ap"


def test_weather_and_event_shared_for_all_farms():
    season = build_season("s", seed=5)
    f1 = default_farm("f1", season.season_id)
    f2 = default_farm("f2", season.season_id)
    s1 = farm_snapshot(f1, season)
    s2 = farm_snapshot(f2, season)
    assert s1["weather_today"] == s2["weather_today"]
    assert s1["event_today"] == s2["event_today"]
    end_day(f1, season)
    end_day(f2, season)
    s1 = farm_snapshot(f1, season)
    s2 = farm_snapshot(f2, season)
    assert s1["weather_today"] == s2["weather_today"]
    assert s1["event_today"] == s2["event_today"]


def test_idempotency_prevents_duplicate_action_side_effect():
    season = build_season("s", seed=2)
    farm = default_farm("f", season.season_id)
    crop_id = first_crop_id(season)

    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id, idempotency_key="k-1")
    gold_after_first = farm.gold
    ap_after_first = farm.action_points
    result = apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id, idempotency_key="k-1")

    assert result["status"] == "deduped"
    assert farm.gold == gold_after_first
    assert farm.action_points == ap_after_first


def test_rollback_restores_previous_day_state():
    season = build_season("s", seed=3)
    farm = default_farm("f", season.season_id)
    crop_id = first_crop_id(season)
    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    prev = farm_snapshot(farm, season)
    end_day(farm, season)
    assert farm.day == 2
    restore_last_day(farm)
    now = farm_snapshot(farm, season)
    assert now["day"] == 1
    assert now["plots"][0]["crop"]["crop_id"] == prev["plots"][0]["crop"]["crop_id"]


def test_water_restriction_event_blocks_water_action():
    season = build_season("s", seed=8)
    # force day 1 event for deterministic test intent
    season.event_sequence[0] = EventType.WATER_RESTRICTION
    farm = default_farm("f", season.season_id)
    crop_id = first_crop_id(season)
    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    try:
        apply_action(farm, season, ActionType.WATER, plot_id=1)
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert exc.code == "water_restricted"
