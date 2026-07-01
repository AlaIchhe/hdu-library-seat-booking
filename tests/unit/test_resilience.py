"""Tests for hdu_library_booking.resilience — circuit breaker, retry, timeout, cancellation, auth refresher, errors."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from hdu_library_booking.exceptions import (
    BookingCancelled,
    BookingValidationError,
    CookieError,
    HduLibraryError,
    LoginError,
    SeatQueryError,
)
from hdu_library_booking.resilience import (
    CancellationToken,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    Deadline,
    ReauthStrategy,
    TimeoutConfig,
    classify_http_status,
    deadline,
    is_auth_error,
    is_retryable,
    is_retryable_status,
    with_reauth,
)
from hdu_library_booking.resilience.retry import (
    auth_retry,
    booking_retry,
    get_retry_stats,
    make_retry_decorator,
    transport_retry,
)


# ---------------------------------------------------------------------------
# Circuit Breaker Tests
# ---------------------------------------------------------------------------
class TestCircuitBreakerInit:
    def test_default_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_invalid_failure_threshold_raises(self):
        with pytest.raises(ValueError, match="failure_threshold"):
            CircuitBreaker(failure_threshold=0)

    def test_invalid_recovery_timeout_raises(self):
        with pytest.raises(ValueError, match="recovery_timeout"):
            CircuitBreaker(recovery_timeout=0)

    def test_custom_thresholds(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, success_threshold=2)
        assert cb._failure_threshold == 3
        assert cb._recovery_timeout == 10.0
        assert cb._success_threshold == 2


class TestCircuitBreakerTransitions:
    def test_closed_to_open_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count_when_closed(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_success_threshold_greater_than_one(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, success_threshold=3)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_can_execute_refuses_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        assert cb.can_execute() is True
        cb.record_failure()
        assert cb.can_execute() is False

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_execute() is True


class TestCircuitBreakerDecorator:
    def test_decorator_allows_execution_when_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        @cb
        def my_func():
            return "ok"

        assert my_func() == "ok"

    def test_decorator_raises_circuit_open_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()

        @cb
        def my_func():
            return "ok"

        with pytest.raises(CircuitOpenError):
            my_func()

    def test_decorator_records_failure(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        @cb
        def my_func():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            my_func()
        assert cb.failure_count == 1

    def test_decorator_records_success(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        @cb
        def my_func():
            return "ok"

        my_func()
        assert cb.failure_count == 0


class TestCircuitBreakerRepr:
    def test_repr(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
        r = repr(cb)
        assert "closed" in r
        assert "0/3" in r


class TestCircuitBreakerThreadSafety:
    def test_concurrent_failures(self):
        cb = CircuitBreaker(failure_threshold=100, recovery_timeout=60.0)

        def record_failures():
            for _ in range(25):
                cb.record_failure()

        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert cb.failure_count == 100


# ---------------------------------------------------------------------------
# Error Classification Tests
# ---------------------------------------------------------------------------
class TestIsRetryable:
    def test_connection_error_is_retryable(self):
        assert is_retryable(ConnectionError("network down")) is True

    def test_timeout_error_is_retryable(self):
        assert is_retryable(TimeoutError("timed out")) is True

    def test_os_error_is_retryable(self):
        assert is_retryable(OSError("broken pipe")) is True

    def test_login_error_not_retryable(self):
        assert is_retryable(LoginError("bad creds")) is False

    def test_cookie_error_not_retryable(self):
        assert is_retryable(CookieError("expired")) is False

    def test_booking_validation_error_not_retryable(self):
        assert is_retryable(BookingValidationError("invalid time")) is False

    def test_booking_cancelled_not_retryable(self):
        assert is_retryable(BookingCancelled("user cancelled")) is False

    def test_hdu_error_with_retryable_cause(self):
        inner = ConnectionError("reset")
        outer = HduLibraryError("wrapped")
        outer.__cause__ = inner
        assert is_retryable(outer) is True

    def test_hdu_error_with_non_retryable_cause(self):
        inner = ValueError("bad")
        outer = HduLibraryError("wrapped")
        outer.__cause__ = inner
        assert is_retryable(outer) is False

    def test_hdu_error_without_cause_not_retryable(self):
        assert is_retryable(HduLibraryError("generic")) is False

    def test_arbitrary_exception_not_retryable(self):
        assert is_retryable(RuntimeError("unknown")) is False


class TestClassifyHttpStatus:
    def test_success_codes(self):
        assert classify_http_status(200) == "success"
        assert classify_http_status(302) == "success"

    def test_retryable_codes(self):
        for code in [429, 500, 502, 503, 504]:
            assert classify_http_status(code) == "retryable"

    def test_non_retryable_4xx_codes(self):
        for code in [400, 401, 403, 404, 405, 409]:
            assert classify_http_status(code) == "non_retryable"

    def test_unknown_code_is_non_retryable(self):
        assert classify_http_status(599) == "non_retryable"


class TestIsRetryableStatus:
    def test_retryable(self):
        assert is_retryable_status(503) is True
        assert is_retryable_status(429) is True

    def test_non_retryable(self):
        assert is_retryable_status(200) is False
        assert is_retryable_status(404) is False
        assert is_retryable_status(401) is False


# ---------------------------------------------------------------------------
# Retry Decorator Tests
# ---------------------------------------------------------------------------
class TestMakeRetryDecorator:
    def test_succeeds_first_try(self):
        call_count = 0

        @make_retry_decorator(max_attempts=3, max_duration=10, initial_wait=0.01, max_wait=0.05)
        def always_works():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = always_works()
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_transient_error_then_succeeds(self):
        call_count = 0

        @make_retry_decorator(max_attempts=5, max_duration=10, initial_wait=0.01, max_wait=0.05)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "success"

        result = fails_twice()
        assert result == "success"
        assert call_count == 3

    def test_gives_up_after_max_attempts(self):
        call_count = 0

        @make_retry_decorator(max_attempts=3, max_duration=60, initial_wait=0.01, max_wait=0.05)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent")

        with pytest.raises(ConnectionError):
            always_fails()
        assert call_count == 3

    def test_does_not_retry_on_permanent_error(self):
        call_count = 0

        @make_retry_decorator(max_attempts=5, max_duration=60, initial_wait=0.01, max_wait=0.05)
        def permanent_error():
            nonlocal call_count
            call_count += 1
            raise LoginError("bad creds")

        with pytest.raises(LoginError):
            permanent_error()
        assert call_count == 1

    def test_does_not_retry_on_validation_error(self):
        call_count = 0

        @make_retry_decorator(max_attempts=5, max_duration=60, initial_wait=0.01, max_wait=0.05)
        def validation_error():
            nonlocal call_count
            call_count += 1
            raise BookingValidationError("bad time")

        with pytest.raises(BookingValidationError):
            validation_error()
        assert call_count == 1

    def test_reraises_original_exception(self):
        @make_retry_decorator(max_attempts=2, max_duration=10, initial_wait=0.01, max_wait=0.05)
        def raises_value_error():
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            raises_value_error()


class TestRetryStats:
    def test_get_retry_stats_success(self):
        mock_state = MagicMock()
        mock_state.attempt_number = 2
        mock_state.idle_for = 1.23456
        mock_state.outcome.result.return_value = "data"
        mock_state.outcome.failed = False

        stats = get_retry_stats(mock_state)
        assert stats["attempt_number"] == 2
        assert stats["idle_for"] == 1.235
        assert stats["outcome"] == "data"

    def test_get_retry_stats_failure(self):
        mock_state = MagicMock()
        mock_state.attempt_number = 3
        mock_state.idle_for = None
        mock_state.outcome.failed = True
        mock_state.outcome.exception.return_value = RuntimeError("boom")

        stats = get_retry_stats(mock_state)
        assert stats["attempt_number"] == 3
        assert stats["idle_for"] == 0
        assert "boom" in stats["outcome"]


class TestRetryStrategies:
    def test_transport_retry_returns_callable(self):
        r = transport_retry()
        assert callable(r)

    def test_booking_retry_returns_callable(self):
        r = booking_retry()
        assert callable(r)

    def test_auth_retry_returns_callable(self):
        r = auth_retry()
        assert callable(r)


# ---------------------------------------------------------------------------
# Timeout Tests
# ---------------------------------------------------------------------------
class TestTimeoutConfig:
    def test_defaults(self):
        tc = TimeoutConfig()
        assert tc.connect_timeout == 5.0
        assert tc.read_timeout == 10.0
        assert tc.overall_timeout == 300.0

    def test_custom_values(self):
        tc = TimeoutConfig(connect_timeout=2.0, read_timeout=5.0, overall_timeout=60.0)
        assert tc.connect_timeout == 2.0
        assert tc.read_timeout == 5.0
        assert tc.overall_timeout == 60.0

    def test_as_tuple(self):
        tc = TimeoutConfig(connect_timeout=3.0, read_timeout=7.0)
        assert tc.as_tuple == (3.0, 7.0)

    def test_overall_timeout_can_be_none(self):
        tc = TimeoutConfig(overall_timeout=None)
        assert tc.overall_timeout is None

    def test_repr(self):
        tc = TimeoutConfig()
        r = repr(tc)
        assert "TimeoutConfig" in r
        assert "5.0s" in r


class TestDeadline:
    def test_not_expired_immediately(self):
        dl = Deadline(10.0)
        assert dl.is_expired is False
        assert dl.remaining > 0

    def test_expired_after_timeout(self):
        dl = Deadline(0.01)
        time.sleep(0.02)
        assert dl.is_expired is True
        assert dl.remaining == 0.0

    def test_check_raises_when_expired(self):
        dl = Deadline(0.01)
        time.sleep(0.02)
        with pytest.raises(TimeoutError, match="Deadline exceeded"):
            dl.check()

    def test_check_does_not_raise_when_not_expired(self):
        dl = Deadline(60.0)
        dl.check()  # should not raise

    def test_remaining_decreases(self):
        dl = Deadline(10.0)
        r1 = dl.remaining
        time.sleep(0.01)
        r2 = dl.remaining
        assert r2 < r1

    def test_repr(self):
        dl = Deadline(10.0)
        r = repr(dl)
        assert "Deadline" in r
        assert "10.0s" in r


class TestDeadlineContextManager:
    def test_completes_within_deadline(self):
        with deadline(10.0):
            pass  # should not raise

    def test_raises_after_deadline(self):
        with pytest.raises(TimeoutError, match="deadline"):
            with deadline(0.01):
                time.sleep(0.05)


# ---------------------------------------------------------------------------
# CancellationToken Tests
# ---------------------------------------------------------------------------
class TestCancellationToken:
    def test_not_cancelled_initially(self):
        token = CancellationToken()
        assert token.is_cancelled() is False

    def test_cancel_sets_flag(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled() is True

    def test_register_callback_executes_on_cancel(self):
        token = CancellationToken()
        called = []

        def on_cancel():
            called.append(True)

        token.register_callback(on_cancel)
        token.cancel()
        assert len(called) == 1

    def test_multiple_callbacks_all_execute(self):
        token = CancellationToken()
        results = []

        token.register_callback(lambda: results.append(1))
        token.register_callback(lambda: results.append(2))
        token.register_callback(lambda: results.append(3))
        token.cancel()
        assert sorted(results) == [1, 2, 3]

    def test_callback_exception_does_not_affect_others(self):
        token = CancellationToken()
        results = []

        token.register_callback(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        token.register_callback(lambda: results.append("ok"))
        token.cancel()
        assert results == ["ok"]

    def test_callback_registered_after_cancel_executes_immediately(self):
        token = CancellationToken()
        token.cancel()
        called = []
        token.register_callback(lambda: called.append(True))
        assert len(called) == 1

    def test_wait_returns_true_on_cancel(self):
        token = CancellationToken()

        def cancel_after():
            time.sleep(0.01)
            token.cancel()

        threading.Thread(target=cancel_after, daemon=True).start()
        result = token.wait(timeout=1.0)
        assert result is True

    def test_wait_returns_false_on_timeout(self):
        token = CancellationToken()
        result = token.wait(timeout=0.01)
        assert result is False

    def test_repr(self):
        token = CancellationToken()
        assert "cancelled=False" in repr(token)
        token.cancel()
        assert "cancelled=True" in repr(token)


# ---------------------------------------------------------------------------
# Auth Refresher Tests
# ---------------------------------------------------------------------------
class TestWithReauth:
    def test_succeeds_without_reauth(self):
        strategy = MagicMock(spec=ReauthStrategy)

        @with_reauth(strategy, max_reauth=2)
        def my_func():
            return "ok"

        result = my_func()
        assert result == "ok"
        strategy.reauth.assert_not_called()

    def test_reauths_and_retries_on_auth_error(self):
        strategy = MagicMock(spec=ReauthStrategy)
        strategy.can_reauth.return_value = True
        call_count = 0

        @with_reauth(strategy, max_reauth=2)
        def my_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise CookieError("expired")
            return "ok"

        result = my_func()
        assert result == "ok"
        assert call_count == 2
        strategy.reauth.assert_called_once()

    def test_stops_after_max_reauth(self):
        strategy = MagicMock(spec=ReauthStrategy)
        strategy.can_reauth.return_value = True
        call_count = 0

        @with_reauth(strategy, max_reauth=2)
        def my_func():
            nonlocal call_count
            call_count += 1
            raise CookieError("expired")

        with pytest.raises(CookieError):
            my_func()
        assert call_count == 3  # 1 original + 2 reauth attempts
        assert strategy.reauth.call_count == 2

    def test_does_not_reauth_when_strategy_says_no(self):
        strategy = MagicMock(spec=ReauthStrategy)
        strategy.can_reauth.return_value = False
        call_count = 0

        @with_reauth(strategy, max_reauth=2)
        def my_func():
            nonlocal call_count
            call_count += 1
            raise CookieError("expired")

        with pytest.raises(CookieError):
            my_func()
        assert call_count == 1
        strategy.reauth.assert_not_called()

    def test_does_not_reauth_non_hdu_exceptions(self):
        strategy = MagicMock(spec=ReauthStrategy)

        @with_reauth(strategy, max_reauth=2)
        def my_func():
            raise ValueError("not an auth error")

        with pytest.raises(ValueError):
            my_func()
        strategy.reauth.assert_not_called()

    def test_preserves_function_name(self):
        strategy = MagicMock(spec=ReauthStrategy)

        @with_reauth(strategy, max_reauth=1)
        def original_func():
            """Docstring."""
            pass

        assert original_func.__name__ == "original_func"
        assert original_func.__doc__ == "Docstring."


class TestIsAuthError:
    def test_cookie_error_is_auth(self):
        assert is_auth_error(CookieError("expired")) is True

    def test_login_error_is_auth(self):
        assert is_auth_error(LoginError("bad creds")) is True

    def test_matching_keywords(self):
        assert is_auth_error(Exception("登录失败")) is True
        assert is_auth_error(Exception("认证过期")) is True
        assert is_auth_error(Exception("unauthorized")) is True
        assert is_auth_error(Exception("forbidden")) is True

    def test_non_auth_error(self):
        assert is_auth_error(RuntimeError("something else")) is False
        assert is_auth_error(SeatQueryError("seat not found")) is False
