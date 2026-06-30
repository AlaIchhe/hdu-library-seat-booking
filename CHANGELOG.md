# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-30

### Added
- Cookie-based authentication with file and string support
- Seat booking with fixed, random, and weekday rotation strategies
- CLI (`hdu-book`) and TUI (`hdu-tui`) entry points
- Room and seat map caching with throttled refresh
- Smart retry with configurable decider
- Error tracking with callbacks and JSON export
- Api-Token signature generation for booking submission
- Dry-run mode for booking preview
- Scheduled booking with `--at` flag
- WeChat, console, and log file notification channels
- Comprehensive test suite (270+ tests) with unit/integration/e2e separation
- Clean architecture with `core/domain/` (pure), `core/infrastructure/` (protocols + impl), `app/` (services + UI)
- `Instrumentation` Protocol for injectable observability
- `ILibraryGateway` and `ISessionAuthenticator` abstract interfaces
- Type hints throughout with mypy strict mode

[Unreleased]: https://github.com/zhuhe/hdu-library-booking/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/zhuhe/hdu-library-booking/releases/tag/v1.0.0
