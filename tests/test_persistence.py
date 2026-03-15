from app.domain import build_season, default_farm
from app.engine import ActionType, apply_action
from app.persistence import FarmStore


def test_farm_store_round_trip(tmp_path):
    db_path = tmp_path / 'farms.sqlite3'
    store = FarmStore(str(db_path))
    season = build_season('season-001', seed=2026, total_days=14, crop_count=4)
    farm = default_farm('persist-a', season.season_id)
    crop_id = next(iter(season.crop_pool))

    apply_action(farm, season, ActionType.PLANT, plot_id=1, crop_id=crop_id)
    store.save_farm(farm, owner_token_hash='hash-1')

    farms, owners = store.load_farms()
    restored = farms['persist-a']

    assert owners['persist-a'] == 'hash-1'
    assert restored.farm_id == farm.farm_id
    assert restored.gold == farm.gold
    assert restored.plots[0].crop is not None
    assert restored.plots[0].crop.crop_id == crop_id
    assert restored.applied_idempotency_keys == farm.applied_idempotency_keys
