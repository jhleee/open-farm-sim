from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.domain import ActionType, build_season, default_farm
from app.engine import ValidationError, apply_action, end_day, farm_snapshot, restore_last_day

app = FastAPI(title="Open Farm Sim API", version="2.0.0")

SEASON = build_season("season-001", seed=2026, total_days=14, crop_count=4)
FARMS = {}


class ActionRequest(BaseModel):
    action: ActionType
    plot_id: int | None = Field(default=None)
    crop_id: str | None = Field(default=None)
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)


@app.get("/v1/version")
def version_info():
    return {"api_version": "v1", "sim_version": "2.0.0", "season_id": SEASON.season_id}


@app.get("/v1/season")
def get_season_info():
    return {
        "season_id": SEASON.season_id,
        "theme": SEASON.theme,
        "total_days": SEASON.total_days,
        "seed": SEASON.seed,
        "crop_pool": [asdict(c) for c in SEASON.crop_pool.values()],
        "scoring_rules": asdict(SEASON.scoring_rules),
    }


@app.get("/v1/season/almanac")
def get_season_almanac():
    return {
        "season_id": SEASON.season_id,
        "days": [
            {
                "day": i + 1,
                "weather": SEASON.weather_sequence[i],
                "event": SEASON.event_sequence[i],
                "market_multiplier": SEASON.market_multiplier[i],
            }
            for i in range(SEASON.total_days)
        ],
    }


@app.post("/v1/farms/{farm_id}/join")
def join_season(farm_id: str):
    if farm_id not in FARMS:
        FARMS[farm_id] = default_farm(farm_id, SEASON.season_id)
    return farm_snapshot(FARMS[farm_id], SEASON)


@app.get("/v1/farms/{farm_id}/state")
def get_state(farm_id: str):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    return farm_snapshot(farm, SEASON)


@app.get("/v1/farms/{farm_id}/logs")
def get_logs(farm_id: str):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    return {
        "farm_id": farm_id,
        "actions": farm.action_log,
        "replay": farm.replay_log,
    }


@app.post("/v1/farms/{farm_id}/actions")
def submit_action(farm_id: str, payload: ActionRequest):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    try:
        return apply_action(
            farm,
            SEASON,
            payload.action,
            payload.plot_id,
            payload.crop_id,
            payload.idempotency_key,
        )
    except ValidationError as exc:
        raise HTTPException(400, {"code": exc.code, "message": exc.message}) from exc


@app.post("/v1/farms/{farm_id}/end-day")
def submit_end_day(farm_id: str):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    end_day(farm, SEASON)
    return farm_snapshot(farm, SEASON)


@app.post("/v1/farms/{farm_id}/rollback")
def rollback(farm_id: str):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    try:
        restore_last_day(farm)
    except ValidationError as exc:
        raise HTTPException(400, {"code": exc.code, "message": exc.message}) from exc
    return farm_snapshot(farm, SEASON)


@app.get("/v1/farms/{farm_id}/report")
def farm_report(farm_id: str):
    farm = FARMS.get(farm_id)
    if not farm:
        raise HTTPException(404, "farm_not_found")
    snap = farm_snapshot(farm, SEASON)
    return {
        "farm_id": farm_id,
        "season_id": SEASON.season_id,
        "final_day": snap["day"],
        "metrics": snap["metrics"],
        "log_count": len(farm.action_log),
    }


@app.get("/v1/leaderboard")
def leaderboard():
    board = []
    for farm in FARMS.values():
        snap = farm_snapshot(farm, SEASON)
        board.append(
            {
                "farm_id": farm.farm_id,
                "score": snap["metrics"]["score"],
                "gold": farm.gold,
                "harvest_count": farm.harvest_count,
                "achievements": snap["metrics"]["achievements"],
            }
        )
    board.sort(key=lambda x: (-x["score"], -x["harvest_count"], x["farm_id"]))
    return {
        "season_id": SEASON.season_id,
        "entries": board,
        "tie_break_rule": "score desc -> harvest_count desc -> farm_id asc",
    }


@app.get("/")
def web_root():
    return RedirectResponse(url="/web/start")


@app.get("/web/start")
def web_start_page():
    return FileResponse("app/web/first_steps.html")


@app.get("/web/ops")
def web_ops_page():
    return FileResponse("app/web/ops.html")
