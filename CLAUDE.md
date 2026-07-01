# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**hdu-library-booking** — 杭州电子科技大学图书馆座位自动预约系统。Automates seat reservations for the HDU (Hangzhou Dianzi University) library platform via its 慧图 (Huitu) web API. Python 3.10+, managed with `uv`.

Two entry points:
- `hdu-book` (`hdu_library_booking.cli:main`) — one-shot CLI for scripts/cron
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
uv run ruff check src/ tests/                # lint
uv run ruff check --fix src/ tests/          # auto-fix
uv run ruff format src/ tests/               # format (double quotes, space indent)
uv run mypy src/                             # type-check (strict; tests excluded)

# Pre-commit (all of the above)
uv run pre-commit run --all-files
```

## Architecture

Clean architecture with strict layering using `src/` layout. Package name: `hdu_library_booking`.

### `src/hdu_library_booking/` — the main package

- **Top-level modules** — cross-cutting:
  - `version.py` — `__version__`
  - `constants.py` — API URLs, headers (simulates WeChat Android client), error message strings that drive retry decisions
  - `types.py` — `Result[T,E]` generic (replaces None/exception-driven errors), `UserInfo` TypedDict, API type aliases (`SeatPoi`, `FloorInfo`, etc.)
  - `exceptions.py` — `HduLibraryError` hierarchy (Login, Cookie, RoomQuery, SeatQuery, Booking, BookingValidation, BookingCancelled)
  - `auth.py` — `generate_api_token` (HMAC-style signing for booking submissions)

- **`config/`** — configuration management:
  - `settings.py` — `Settings` (pydantic-settings), layered config: CLI > env (`HDU_` prefix, `__` nested delimiter) > `.env` > `config.yaml` > defaults. Singleton via `get_settings()`.
  - `yaml.py` — `load_yaml_config`, `save_yaml_config`, `create_default_config`
  - `parser.py` — `ConfigParser` backward-compat shim (delegates to `settings.Settings`)

- **`models/`** — domain models + pure functions, zero infrastructure dependencies. Safe to unit-test in isolation.
  - `plan.py` — `BookingPlan` dataclass (core domain object), `Weekday` IntEnum, `PlanStatus`. Compact code format: `roomType:floorId:seatNum:startHour:durationHours`.
  - `booking_result.py` — parses API response dicts (`booking_failed`, `booking_message`, error classifiers)
  - `time_utils.py` — `build_begin_time`, `parse_plan_code`, `build_execute_datetime` (CST/UTC+8)
  - `seat_lookup.py` — seat search helpers

- **`gateways/`** — protocols (abstract) + concrete implementations.
  - `protocols.py` — `ILibraryGateway`, `ISessionAuthenticator`, `Instrumentation`, `NullInstrumentation`
  - `library.py` — `HduLibraryGateway`: room/seat/booking API orchestration (combines transport + auth)
  - `http_transport.py` — `HttpTransport`: thin `requests.Session` wrapper, records network/json errors
  - `session_auth.py`, `user_info.py` — cookie/UID handling

- **`api/`** — external HTTP API facade:
  - `client.py` — `HduLibraryClient`: unified API client implementing `ISessionAuthenticator` + `ILibraryGateway`
  - `room_cache.py` — `RoomCache`: batch room query with delay
  - `password_auth.py` — `PasswordAuthClient` (reference only, not in main flow)

- **`observability/`** — structured logging, metrics, correlation tracing:
  - `_error_tracker.py` — `ErrorTracker` singleton (`error_tracker`), thread-safe categorized error recording with callbacks/JSON export
  - `logging.py` — `configure_logging`, `get_logger` (structlog setup)
  - `metrics.py` — `MetricsCollector` singleton (`metrics_collector`), extends ErrorTracker with counters/gauges/histograms + Prometheus output
  - `correlation.py` — `set_correlation_id` / `get_correlation_id` (ContextVar-based request tracing)

- **`resilience/`** — fault tolerance:
  - `errors.py` — error classification (`is_retryable`, `classify_http_status`, status code sets)
  - `retry.py` — `make_retry_decorator` (tenacity-based exponential backoff + jitter)
  - `circuit_breaker.py` — `CircuitBreaker` (3-state CLOSED/OPEN/HALF_OPEN)
  - `timeout.py` — `TimeoutConfig` + `deadline()` + `Deadline` (3-layer timeout control)
  - `cancellation.py` — `CancellationToken` (thread-safe with callbacks)
  - `auth_refresher.py` — `with_reauth` decorator + `ReauthStrategy` protocol

- **`services/`** — application services:
  - `interfaces.py` — abstract contracts: `IPlanRepository`, `ISeatSelectionStrategy`, `INotificationChannel`, `IUserInterface`, `ITaskCancellation`
  - `booking.py` — `BookingOrchestrator`: the main booking flow (room query → seat map → strategy select → submit), smart retry via `RetryDecision` (CONTINUE/SKIP/STOP based on server error messages), scheduled booking (`book_at`), cancellation support
  - `plan.py` / `yaml_plan.py` — plan CRUD with YAML persistence
  - `auth.py` / `notifications.py` — auth flow + multi-channel notifier (console/log/WeChat)

- **`strategies/`** — `ISeatSelectionStrategy` implementations:
  - `fixed.py` — exact floor+seat match
  - `random_range.py` — random seat in range
  - `weekday.py` — per-weekday seat config

- **`cli/`` — user interfaces:
  - `__init__.py` — CLI entry (`hdu-book`), argparse-based one-shot executor for scripts/cron
  - `terminal.py` — interactive menu-driven TUI
  - `helpers.py` — logging config & terminal progress spinner

### Key Design Patterns

- **Dependency injection** — `BookingOrchestrator` receives `gateway`, `strategy`, `notifier`, `retry_decider`, `cancellation` via constructor. Never instantiates them internally.
- **Strategy pattern** — seat selection is swappable; add new strategies by implementing `ISeatSelectionStrategy`.
- **Result type** — domain operations return `Result[T, E]` instead of raising or returning None. Check `is_success`/`is_failure`, access `value`/`error`.
- **Repository pattern** — plans are persisted via `IPlanRepository` (YAML implementation); swap for other backends.
- **Instrumentation protocol** — `Instrumentation` is a Structural Protocol; `NullInstrumentation` is used in tests to avoid touching the global `error_tracker`.

## Testing Conventions

- Tests are directory-split by isolation level: `unit/` (fast, fully mocked), `integration/` (mocked HTTP, tests service wiring), `e2e/` (contract + smoke tests requiring real credentials, gated by markers).
- `tests/conftest.py` provides shared fixtures: `sample_plan`, `minimal_plan`, `mock_client` (spec=`HduLibraryClient`), `mock_gateway` (spec=`ILibraryGateway`), `sample_floors`, `mock_orchestrator`, `inmemory_repo`/`plan_service`/`populated_service`, `fixed_time` (patches `hdu_library_booking.models.time_utils.now_cst`).
- Use `spec=` when mocking to catch API drift. Prefer `NullInstrumentation` over the global tracker in tests.
- Ruff relaxations for `tests/`: asserts allowed (`S101`), relaxed pytest fixture rules, `E402` for sys.path/dotenv setup.

## Configuration Precedence (high → low)

CLI args → env vars (`HDU_*`, `__` = nested) → `.env` → `config.yaml` → code defaults. YAML keys are auto-mapped from legacy names (`request`→`http`, `user_info`→`auth`). Credentials (`.env`, `config.yaml`, `plans.yaml`, `tests/cookies.json`) are gitignored.
