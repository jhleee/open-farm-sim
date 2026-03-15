from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from app.domain import CropInstance, Farm, Plot


class FarmStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS farms (
                    farm_id TEXT PRIMARY KEY,
                    owner_token_hash TEXT,
                    state_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def load_farms(self) -> tuple[dict[str, Farm], dict[str, str]]:
        farms: dict[str, Farm] = {}
        owner_hashes: dict[str, str] = {}
        with self._connect() as conn:
            rows = conn.execute("SELECT farm_id, owner_token_hash, state_json FROM farms").fetchall()
        for row in rows:
            farms[row["farm_id"]] = self._deserialize_farm(json.loads(row["state_json"]))
            if row["owner_token_hash"]:
                owner_hashes[row["farm_id"]] = row["owner_token_hash"]
        return farms, owner_hashes

    def save_farm(self, farm: Farm, owner_token_hash: str | None = None) -> None:
        payload = json.dumps(self._serialize_farm(farm), ensure_ascii=False)
        with self._connect() as conn:
            if owner_token_hash is None:
                conn.execute(
                    """
                    INSERT INTO farms (farm_id, owner_token_hash, state_json)
                    VALUES (?, COALESCE((SELECT owner_token_hash FROM farms WHERE farm_id = ?), NULL), ?)
                    ON CONFLICT(farm_id) DO UPDATE SET state_json = excluded.state_json
                    """,
                    (farm.farm_id, farm.farm_id, payload),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO farms (farm_id, owner_token_hash, state_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(farm_id) DO UPDATE SET
                        owner_token_hash = excluded.owner_token_hash,
                        state_json = excluded.state_json
                    """,
                    (farm.farm_id, owner_token_hash, payload),
                )
            conn.commit()

    def set_owner_hash(self, farm_id: str, owner_token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE farms SET owner_token_hash = ? WHERE farm_id = ?", (owner_token_hash, farm_id))
            conn.commit()

    @staticmethod
    def _serialize_farm(farm: Farm) -> dict:
        data = asdict(farm)
        data["applied_idempotency_keys"] = sorted(farm.applied_idempotency_keys)
        return data

    @staticmethod
    def _deserialize_farm(data: dict) -> Farm:
        plots = []
        for p in data["plots"]:
            crop = CropInstance(**p["crop"]) if p["crop"] else None
            plots.append(
                Plot(
                    plot_id=p["plot_id"],
                    soil_type=p["soil_type"],
                    fertility=p["fertility"],
                    moisture=p["moisture"],
                    drainage=p["drainage"],
                    fatigue=p["fatigue"],
                    recent_crop_history=list(p["recent_crop_history"]),
                    crop=crop,
                )
            )
        return Farm(
            farm_id=data["farm_id"],
            user_id=data["user_id"],
            season_id=data["season_id"],
            day=data["day"],
            gold=data["gold"],
            action_points=data["action_points"],
            inventory=dict(data["inventory"]),
            plots=plots,
            harvest_count=data["harvest_count"],
            total_income=data["total_income"],
            action_log=list(data["action_log"]),
            replay_log=list(data["replay_log"]),
            day_open=data["day_open"],
            applied_idempotency_keys=set(data.get("applied_idempotency_keys", [])),
        )
