from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from random import Random


class Weather(StrEnum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAIN = "rain"
    HEATWAVE = "heatwave"
    STORM = "storm"


class EventType(StrEnum):
    NONE = "none"
    PEST_ALERT = "pest_alert"
    FESTIVAL = "festival"
    FERTILITY_SUBSIDY = "fertility_subsidy"
    WATER_RESTRICTION = "water_restriction"


class CropStage(StrEnum):
    SEED = "seed"
    SPROUT = "sprout"
    VEGETATIVE = "vegetative"
    FLOWER = "flower"
    FRUIT = "fruit"
    OVERGROWN = "overgrown"
    DEAD = "dead"


class ActionType(StrEnum):
    PLANT = "plant"
    WATER = "water"
    FERTILIZE = "fertilize"
    HARVEST = "harvest"
    INSPECT = "inspect"
    REST = "rest"


ACTION_COST = {
    ActionType.PLANT: 2,
    ActionType.WATER: 1,
    ActionType.FERTILIZE: 2,
    ActionType.HARVEST: 2,
    ActionType.INSPECT: 1,
    ActionType.REST: 0,
}


@dataclass(frozen=True)
class CropDefinition:
    crop_id: str
    name: str
    archetype: str
    rarity: str
    grow_threshold: int
    drought_sensitivity: int
    storm_sensitivity: int
    market_base: int
    soil_preference: float


@dataclass
class CropInstance:
    crop_id: str
    age: int = 0
    growth_points: int = 0
    stress: int = 0
    quality: float = 1.0
    harvested: bool = False

    @property
    def stage(self) -> CropStage:
        if self.harvested:
            return CropStage.DEAD
        if self.stress >= 12:
            return CropStage.DEAD
        if self.age >= 13:
            return CropStage.OVERGROWN
        if self.growth_points >= 10:
            return CropStage.FRUIT
        if self.growth_points >= 8:
            return CropStage.FLOWER
        if self.growth_points >= 5:
            return CropStage.VEGETATIVE
        if self.growth_points >= 2:
            return CropStage.SPROUT
        return CropStage.SEED


@dataclass
class Plot:
    plot_id: int
    soil_type: str
    fertility: float
    moisture: float
    drainage: float
    fatigue: float = 0.0
    recent_crop_history: list[str] = field(default_factory=list)
    crop: CropInstance | None = None


@dataclass
class Farm:
    farm_id: str
    user_id: str
    season_id: str
    day: int = 1
    gold: int = 120
    action_points: int = 6
    inventory: dict[str, int] = field(default_factory=dict)
    plots: list[Plot] = field(default_factory=list)
    harvest_count: int = 0
    total_income: int = 0
    action_log: list[dict] = field(default_factory=list)
    replay_log: list[dict] = field(default_factory=list)
    day_open: bool = True
    applied_idempotency_keys: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ScoringRules:
    harvest_weight: int = 20
    quality_weight: int = 60
    income_weight: int = 1


@dataclass(frozen=True)
class Season:
    season_id: str
    theme: str
    total_days: int
    seed: int
    weather_sequence: list[Weather]
    event_sequence: list[EventType]
    market_multiplier: list[float]
    crop_pool: dict[str, CropDefinition]
    scoring_rules: ScoringRules


ARCHETYPES = [
    ("grain", 27, 7, 2, 2, 1.0),
    ("fruit", 39, 10, 1, 3, 1.1),
    ("berry", 34, 9, 2, 2, 0.9),
    ("pepper", 32, 8, 3, 1, 1.0),
]

NAMES = {
    "grain": ["Amber Wheat", "Rust Rye", "Ivory Barley"],
    "fruit": ["River Melon", "Sky Pumpkin", "Sun Pear"],
    "berry": ["Glass Berry", "Mist Plum", "Dawn Cherry"],
    "pepper": ["Moon Pepper", "Torch Chili", "Storm Capsa"],
}

RARITIES = ["common", "common", "rare", "epic"]


def generate_crop_pool(seed: int, size: int = 4) -> dict[str, CropDefinition]:
    rng = Random(seed + 719)
    pool: dict[str, CropDefinition] = {}
    for idx in range(size):
        archetype, base, threshold, drought, storm, soil_pref = rng.choice(ARCHETYPES)
        name = rng.choice(NAMES[archetype])
        rarity = rng.choice(RARITIES)
        rarity_bonus = {"common": 0, "rare": 3, "epic": 6}[rarity]
        crop_id = f"{name.lower().replace(' ', '_')}_{idx + 1}"
        pool[crop_id] = CropDefinition(
            crop_id=crop_id,
            name=name,
            archetype=archetype,
            rarity=rarity,
            grow_threshold=threshold,
            drought_sensitivity=drought,
            storm_sensitivity=storm,
            market_base=base + rarity_bonus,
            soil_preference=soil_pref,
        )
    return pool


def build_season(season_id: str, seed: int = 42, total_days: int = 14, crop_count: int = 4) -> Season:
    rng = Random(seed)
    weather_weights = [
        Weather.SUNNY,
        Weather.SUNNY,
        Weather.CLOUDY,
        Weather.RAIN,
        Weather.HEATWAVE,
        Weather.STORM,
    ]
    event_weights = [
        EventType.NONE,
        EventType.NONE,
        EventType.NONE,
        EventType.PEST_ALERT,
        EventType.FESTIVAL,
        EventType.FERTILITY_SUBSIDY,
        EventType.WATER_RESTRICTION,
    ]
    weather = [rng.choice(weather_weights) for _ in range(total_days)]
    events = [rng.choice(event_weights) for _ in range(total_days)]
    multipliers = [round(rng.uniform(0.8, 1.3), 2) for _ in range(total_days)]
    crop_pool = generate_crop_pool(seed, crop_count)

    return Season(
        season_id=season_id,
        theme="deterministic-lab",
        total_days=total_days,
        seed=seed,
        weather_sequence=weather,
        event_sequence=events,
        market_multiplier=multipliers,
        crop_pool=crop_pool,
        scoring_rules=ScoringRules(),
    )


def default_farm(farm_id: str, season_id: str) -> Farm:
    return Farm(
        farm_id=farm_id,
        user_id=farm_id,
        season_id=season_id,
        plots=[
            Plot(plot_id=1, soil_type="loam", fertility=1.1, moisture=0.5, drainage=0.8),
            Plot(plot_id=2, soil_type="silt", fertility=1.0, moisture=0.5, drainage=1.0),
            Plot(plot_id=3, soil_type="sand", fertility=0.9, moisture=0.6, drainage=1.2),
        ],
    )
