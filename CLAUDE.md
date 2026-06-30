# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**hdu-library-booking** — 杭州电子科技大学图书馆座位自动预约系统。Automates seat reservations for the HDU (Hangzhou Dianzi University) library platform via its 慧图 (Huitu) web API. Python 3.10+, managed with `uv`.

Two entry points:
- `hdu-book` (`app.ui.cli:main`) — one-shot CLI for scripts/cron
- `hdu-tui` (`main:main`) — interactive terminal UI

## Common Commands

```bash
# Setup
uv sync                         # install deps from uv.lock (creates .venv)
uv sync --all-extras            # include dev deps (pytest, ruff, mypy, bandit)

# Run
uv run hdu-tui                                   # interactive TUI
uv run hdu-book --cookie "uid=;auth=" --plan "1:1558:296:13:9"   # one-shot booking
uv run hdu-book --cookie "..." --plan "..." --dry-run             # preview only
uv run hdu-book --cookie "..." --plan "..." --at "19:59:30"       # scheduled
uv run python main.py --cli --report                              # error tracker summary

# Tests (split by directory; markers: smoke, contract, slow, static)
uv run pytest tests/unit/ -x -q              # unit only (fast, no network)
uv run pytest tests/unit/test_strategies.py::TestFixedSeatStrategy::test_select_seat_found -xvs  # single test
uv run pytest tests/integration/ -x -q       # integration (mocked HTTP)
uv run pytest -m "not smoke and not contract" -q  # exclude tests needing real creds

# Lint / format / type-check
uv run ruff check core/ app/ tests/          # lint
uv run ruff check --fix core/ app/ tests/    # auto-fix
uv run ruff format core/ app/ tests/         # format (double quotes, space indent)
uv run mypy core/ app/                       # type-check (strict; tests excluded)

# Pre-commit (all of the above)
uv run pre-commit run --all-files
```

## Architecture

Clean architecture with strict layering. Dependencies point **inward only**: `app/` → `core/`, never the reverse.

### `core/` — domain + infrastructure (no application logic)

- **`core/domain/`** — pure functions, zero infrastructure dependencies. Safe to unit-test in isolation.
  - `booking_result.py` — parses API response dicts (`booking_failed`, `booking_message`, error classifiers)
  - `time.py` — `build_begin_time`, `parse_plan_code`, `build_execute_datetime` (CST/UTC+8)
  - `seat_lookup.py` — seat search helpers
- **`core/infrastructure/`** — protocols (abstract) + concrete implementations.
  - `protocols.py` — `ILibraryGateway`, `ISessionAuthenticator`, `Instrumentation`, `NullInstrumentation`
  - `library_gateway.py` — `HduLibraryGateway`: room/seat/booking API orchestration (combines transport + auth)
  - `http_transport.py` — `HttpTransport`: thin `requests.Session` wrapper, records network/json errors
  - `session_auth.py`, `user_info.py` — cookie/UID handling
- **`core/` (top-level)** — cross-cutting:
  - `settings.py` — `Settings` (pydantic-settings), layered config: CLI > env (`HDU_` prefix, `__` nested delimiter) > `.env` > `config.yaml` > defaults. Singleton via `get_settings()`.
  - `types.py` — `Result[T,E]` generic (replaces None/exception-driven errors), `UserInfo` TypedDict, API type aliases (`SeatPoi`, `FloorInfo`, etc.)
  - `constants.py` — API URLs, headers (simulates WeChat Android client), error message strings that drive retry decisions
  - `exceptions.py` — `HduLibraryError` hierarchy (Login, Cookie, RoomQuery, SeatQuery, Booking, BookingValidation, BookingCancelled)
  - `metrics.py` — `error_tracker` singleton (`ErrorTracker`), thread-safe categorized error recording with callbacks/JSON export
  - `auth.py` — `generate_api_token` (HMAC-style signing for booking submissions)

### `app/` — application services + UI (depends on `core/`)

- **`app/models/plan.py`** — `BookingPlan` dataclass (core domain object), `Weekday` IntEnum, `PlanStatus`. Compact code format: `roomType:floorId:seatNum:startHour:durationHours`.
- **`app/services/`**
  - `base.py` — abstract contracts: `IPlanRepository`, `ISeatSelectionStrategy`, `INotificationChannel`, `IUserInterface`, `ITaskCancellation`
  - `booking_service.py` — `BookingOrchestrator`: the main booking flow (room query → seat map → strategy select → submit), smart retry via `RetryDecision` (CONTINUE/SKIP/STOP based on server error messages), scheduled booking (`book_at`), cancellation support
  - `plan_service.py` / `plan_repository.py` — plan CRUD with YAML persistence
  - `auth_service.py` / `notification_service.py` — auth flow + multi-channel notifier (console/log/WeChat)
- **`app/strategies/`** — `ISeatSelectionStrategy` implementations:
  - `fixed_seat.py` — exact floor+seat match
  - `random_range.py` — random seat in range
  - `weekday_rotation.py` — per-weekday seat config
- **`app/ui/`** — `cli.py` (argparse, `hdu-book`) and `terminal.py` (TUI)

### Key Design Patterns

- **Dependency injection** — `BookingOrchestrator` receives `gateway`, `strategy`, `notifier`, `retry_decider`, `cancellation` via constructor. Never instantiates them internally.
- **Strategy pattern** — seat selection is swappable; add new strategies by implementing `ISeatSelectionStrategy`.
- **Result type** — domain operations return `Result[T, E]` instead of raising or returning None. Check `is_success`/`is_failure`, access `value`/`error`.
- **Repository pattern** — plans are persisted via `IPlanRepository` (YAML implementation); swap for other backends.
- **Instrumentation protocol** — `Instrumentation` is a Structural Protocol; `NullInstrumentation` is used in tests to avoid touching the global `error_tracker`.

## Testing Conventions

- Tests are directory-split by isolation level: `unit/` (fast, fully mocked), `integration/` (mocked HTTP, tests service wiring), `e2e/` (contract + smoke tests requiring real credentials, gated by markers).
- `tests/conftest.py` provides shared fixtures: `sample_plan`, `minimal_plan`, `mock_client` (spec=`HduLibraryClient`), `mock_gateway` (spec=`ILibraryGateway`), `sample_floors`, `mock_orchestrator`, `inmemory_repo`/`plan_service`/`populated_service`, `fixed_time` (patches `core.domain.time.now_cst`).
- Use `spec=` when mocking to catch API drift. Prefer `NullInstrumentation` over the global tracker in tests.
- Ruff relaxations for `tests/`: asserts allowed (`S101`), relaxed pytest fixture rules, `E402` for sys.path/dotenv setup.

## Configuration Precedence (high → low)

CLI args → env vars (`HDU_*`, `__` = nested) → `.env` → `config.yaml` → code defaults. YAML keys are auto-mapped from legacy names (`request`→`http`, `user_info`→`auth`). Credentials (`.env`, `config.yaml`, `plans.yaml`, `tests/cookies.json`) are gitignored.
