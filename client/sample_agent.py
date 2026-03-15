from __future__ import annotations

import random

import httpx

BASE = "http://127.0.0.1:8000"
FARM_ID = "sample-agent"


def choose_action(state: dict, crop_ids: list[str]) -> dict:
    ap = state["action_points"]
    plots = state["plots"]

    for plot in plots:
        crop = plot["crop"]
        if crop and crop["stage"] in {"fruit", "overgrown"} and ap >= 2:
            return {"action": "harvest", "plot_id": plot["plot_id"]}

    for plot in plots:
        if not plot["crop"] and ap >= 2:
            return {"action": "plant", "plot_id": plot["plot_id"], "crop_id": random.choice(crop_ids)}

    dry_plot = min(plots, key=lambda p: p["moisture"])
    if dry_plot["crop"] and ap >= 1:
        return {"action": "water", "plot_id": dry_plot["plot_id"]}

    return {"action": "inspect", "plot_id": 1} if ap >= 1 else {"action": "rest"}


def run():
    with httpx.Client(timeout=10) as client:
        season = client.get(f"{BASE}/v1/season").json()
        crop_ids = [c["crop_id"] for c in season["crop_pool"]]
        client.post(f"{BASE}/v1/farms/{FARM_ID}/join")

        while True:
            state = client.get(f"{BASE}/v1/farms/{FARM_ID}/state").json()
            if state["day"] > state["total_days"]:
                break
            while state["action_points"] > 0:
                action = choose_action(state, crop_ids)
                action["idempotency_key"] = f"{state['day']}-{state['action_points']}-{random.randint(1000,9999)}"
                client.post(f"{BASE}/v1/farms/{FARM_ID}/actions", json=action)
                state = client.get(f"{BASE}/v1/farms/{FARM_ID}/state").json()
            client.post(f"{BASE}/v1/farms/{FARM_ID}/end-day")

        final_state = client.get(f"{BASE}/v1/farms/{FARM_ID}/state").json()
        print("Final metrics:", final_state["metrics"])


if __name__ == "__main__":
    run()
