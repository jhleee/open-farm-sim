import pytest

from tests.scenario_utils import run_strategy


SEEDS = [300, 301, 302, 303, 304]  # 5 seeds

# 20 strategies => 100 scenarios with 5 seeds
STRATEGIES = [
    {"name": f"s{i}", "fert_every": fert_every, "water_threshold": wt, "inspect_bias": ib}
    for i, (fert_every, wt, ib) in enumerate(
        [
            (1, 0.4, True), (1, 0.5, True), (1, 0.6, True), (1, 0.7, True), (1, 0.8, True),
            (2, 0.4, True), (2, 0.5, True), (2, 0.6, True), (2, 0.7, True), (2, 0.8, True),
            (3, 0.4, True), (3, 0.5, True), (3, 0.6, True), (3, 0.7, True), (3, 0.8, True),
            (2, 0.5, False), (2, 0.7, False), (3, 0.5, False), (4, 0.6, False), (5, 0.7, False),
        ],
        start=1,
    )
]

SCENARIO_CASES = [(seed, strat) for seed in SEEDS for strat in STRATEGIES]


@pytest.mark.parametrize("seed,strategy", SCENARIO_CASES, ids=lambda x: x if isinstance(x, int) else x["name"])
def test_scenario_matrix_100_cases_subjective_sanity(seed: int, strategy: dict):
    snap = run_strategy(seed=seed, strategy=strategy, days=10)

    # 주관적 타당성 기준
    assert snap["metrics"]["score"] >= snap["gold"]
    assert snap["action_points"] >= 0
    assert 1 <= snap["day"] <= snap["total_days"] + 1
    assert 0.4 <= snap["metrics"]["average_live_quality"] <= 1.0


def test_objective_review_reproducibility_same_seed_strategy_same_result():
    s = STRATEGIES[0]
    a = run_strategy(seed=SEEDS[0], strategy=s, days=10)
    b = run_strategy(seed=SEEDS[0], strategy=s, days=10)
    assert a["gold"] == b["gold"]
    assert a["metrics"]["score"] == b["metrics"]["score"]


def test_objective_review_strategy_diversity_non_trivial():
    # 객관 검토: 서로 다른 전략이 완전히 동일한 평균 결과만 내면 이상
    averages = []
    for strat in STRATEGIES:
        scores = [run_strategy(seed=seed, strategy=strat, days=10)["metrics"]["score"] for seed in SEEDS]
        averages.append(round(sum(scores) / len(scores), 2))

    assert len(set(averages)) >= 3
