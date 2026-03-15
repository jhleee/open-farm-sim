# Open Farm Sim

`prd.md` 기반 구현을 MVP에서 확장해, Phase 0~5 핵심 기능을 실제 동작 가능한 형태로 담았습니다.

## 구현 범위 (Phase 매핑)

- **Phase 0/1**: 도메인 고정 + deterministic 코어 엔진
  - 시즌/농장/토지/작물 모델
  - 상태머신 작물 성장
  - 행동력/행동 검증
- **Phase 2**: 시즌/작물 생성기 + 에이전트 API
  - seed 기반 날씨/이벤트/시장 시퀀스
  - 시즌별 작물 풀 자동 생성(아키타입/희귀도)
- **Phase 3/4**: 관전/경쟁 기능
  - 액션 로그, replay 로그
  - 업적, 점수, 리더보드 tie-break 규칙
  - 시즌 리포트 API
- **Phase 5 안정성 기능 일부**
  - idempotency key 기반 중복 제출 방지
  - rollback(최근 일자 복구) 지원

## API

## 간단 웹페이지

- `GET /web/start`: 첫 사용 방법 + 운영 TODO
- `GET /web/ops`: 리더보드/작업로그 확인 페이지


- `GET /v1/version`
- `GET /v1/season`
- `GET /v1/season/almanac`
- `POST /v1/farms/{farm_id}/join` (optional `x-farm-token` 헤더로 생성 즉시 소유권 설정)
- `POST /v1/farms/{farm_id}/claim`
- `GET /v1/farms/{farm_id}/state`
- `GET /v1/farms/{farm_id}/logs`
- `POST /v1/farms/{farm_id}/actions`
- `POST /v1/farms/{farm_id}/end-day`
- `POST /v1/farms/{farm_id}/rollback`
- `GET /v1/farms/{farm_id}/report`
- `GET /v1/leaderboard`

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

## 샘플 에이전트 실행

```bash
python client/sample_agent.py
```

## 테스트

```bash
pytest -q
```

테스트는 도메인/엔진/API 수준 기능을 포괄하며, 결정성/상태전이/행동력/이벤트 제약/중복제출/롤백/리더보드/리포트 경로를 검증합니다. farm 소유권 claim + 토큰 인증 보호, sqlite 영속화 round-trip도 포함합니다.
추가로 `tests/test_e2e.py`에서 한 시즌 전체를 API로 관통 실행해 상태/로그/리포트/리더보드 일관성을 검증합니다.
`tests/test_scenarios_core.py`와 `tests/test_scenarios_matrix.py`로 시나리오를 분리했습니다. core에서는 페스티벌 수익 보너스, 롤백 정합성, 동일 시퀀스/동일 정책 결과 일치를 검증하고, matrix에서는 100건 시나리오(5개 seed x 20 전략)로 주관적 sanity와 객관적 검토(재현성, 전략 다양성)를 검증합니다.



## 영속화/소유권 인증

- 농장 상태는 기본적으로 `data/farms.sqlite3` 에 저장됩니다. (`FARM_DB_PATH` 환경변수로 변경 가능)
- `POST /v1/farms/{farm_id}/claim` 으로 farm_id 소유권을 claim 할 수 있습니다.
- 이미 claim 된 farm 접근/수정에는 `x-farm-token` 헤더가 필요합니다.

## Docker 빌드/실행

```bash
docker build -t open-farm-sim .
docker run --rm -p 8000:8000 open-farm-sim
```

실행 후 `http://localhost:8000/web/start` 또는 `http://localhost:8000/docs` 로 접속할 수 있습니다.
