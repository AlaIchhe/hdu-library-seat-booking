"""Tests for core.settings — 配置加载、键映射、工厂方法。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.settings import (
    BookingConfig,
    HTTPConfig,
    Settings,
    StrategyConfig,
    _deep_update,
    _flatten_yaml,
    _unflatten_keys,
)

# ---------------------------------------------------------------------------
# _flatten_yaml — 旧版 YAML key 映射
# ---------------------------------------------------------------------------


class TestFlattenYaml:
    def test_flattens_nested_dict(self):
        data = {"http": {"timeout": 30, "verify": True}}
        result = _flatten_yaml(data)
        assert result == {"http__timeout": 30, "http__verify": True}

    def test_maps_old_request_key_to_http(self):
        """旧版 'request' key 应映射到 'http'。"""
        data = {"request": {"timeout": 20}}
        result = _flatten_yaml(data)
        assert result == {"http__timeout": 20}

    def test_maps_old_user_info_key_to_auth(self):
        """旧版 'user_info' key 应映射到 'auth'。"""
        data = {"user_info": {"uid": "12345", "name": "张三"}}
        result = _flatten_yaml(data)
        assert result == {"auth__uid": "12345", "auth__name": "张三"}

    def test_maps_old_session_key_to_http(self):
        """旧版 'session' key 应映射到 'http'。"""
        data = {"session": {"timeout": 15}}
        result = _flatten_yaml(data)
        assert result == {"http__timeout": 15}

    def test_passes_through_scalar_values(self):
        """标量值直接保留。"""
        data = {"dry_run": True}
        result = _flatten_yaml(data)
        assert result == {"dry_run": True}

    def test_empty_dict(self):
        assert _flatten_yaml({}) == {}

    def test_mixed_old_and_new_keys(self):
        data = {
            "request": {"timeout": 30},
            "auth": {"uid": "1"},
            "booking": {"max_trials": 3},
        }
        result = _flatten_yaml(data)
        assert result == {
            "http__timeout": 30,
            "auth__uid": "1",
            "booking__max_trials": 3,
        }


# ---------------------------------------------------------------------------
# _unflatten_keys — 双下划线分隔符转嵌套
# ---------------------------------------------------------------------------


class TestUnflattenKeys:
    def test_unflattens_nested_key(self):
        result = _unflatten_keys({"booking__max_trials": 20})
        assert result == {"booking": {"max_trials": 20}}

    def test_unflatten_handles_single_level_only(self):
        """_unflatten_keys 仅处理单层分隔符。"""
        result = _unflatten_keys({"a__b__c": 1})
        assert result == {"a": {"b__c": 1}}

    def test_passes_through_flat_key(self):
        result = _unflatten_keys({"key": "value"})
        assert result == {"key": "value"}

    def test_mixed_nested_and_flat(self):
        result = _unflatten_keys({"booking__max_trials": 5, "dry_run": True})
        assert result == {"booking": {"max_trials": 5}, "dry_run": True}

    def test_empty_dict(self):
        assert _unflatten_keys({}) == {}


# ---------------------------------------------------------------------------
# _deep_update — 递归更新
# ---------------------------------------------------------------------------


class TestDeepUpdate:
    def test_updates_scalar(self):
        base = {"a": 1, "b": 2}
        _deep_update(base, {"b": 99})
        assert base == {"a": 1, "b": 99}

    def test_recursively_updates_nested(self):
        base = {"booking": {"max_trials": 5, "retry_delay": 1.0}}
        _deep_update(base, {"booking": {"max_trials": 10}})
        assert base == {"booking": {"max_trials": 10, "retry_delay": 1.0}}

    def test_adds_new_keys(self):
        base = {"a": 1}
        _deep_update(base, {"b": 2})
        assert base == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Settings.defaults — 默认值
# ---------------------------------------------------------------------------


class TestSettingsDefaults:
    def test_default_http_timeout(self):
        s = Settings()
        assert s.http.timeout == 10

    def test_default_booking_max_trials(self):
        s = Settings()
        assert s.booking.max_trials == 5

    def test_default_strategy_type(self):
        s = Settings()
        assert s.strategy.type == "fixed"

    def test_urls_property_returns_dict(self):
        s = Settings()
        urls = s.urls
        assert isinstance(urls, dict)
        assert "book_seat" in urls
        assert "login" in urls

    def test_default_auth_org_id(self):
        s = Settings()
        assert s.auth.org_id == "104"


# ---------------------------------------------------------------------------
# Settings.from_yaml — YAML 加载
# ---------------------------------------------------------------------------


class TestSettingsFromYaml:
    def _write_yaml(self, tmpdir: str, content: str) -> str:
        path = os.path.join(tmpdir, "config.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_from_yaml_with_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_yaml(
                tmp,
                """
                auth:
                  uid: "12345"
                  name: "张三"
                http:
                  timeout: 30
                booking:
                  max_trials: 3
                """,
            )
            s = Settings.from_yaml(path)
            assert s.auth.uid == "12345"
            assert s.auth.name == "张三"
            assert s.http.timeout == 30
            assert s.booking.max_trials == 3

    def test_from_yaml_with_old_keys(self):
        """旧版 YAML key 应被映射到新版模型。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_yaml(
                tmp,
                """
                request:
                  timeout: 25
                user_info:
                  uid: "99999"
                """,
            )
            s = Settings.from_yaml(path)
            assert s.http.timeout == 25
            assert s.auth.uid == "99999"

    def test_from_yaml_missing_file_returns_defaults(self):
        s = Settings.from_yaml("/nonexistent/path/config.yaml")
        assert s.http.timeout == 10  # 默认值

    def test_from_yaml_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_yaml(tmp, "")
            s = Settings.from_yaml(path)
            assert s.http.timeout == 10

    def test_from_yaml_with_pathlib_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_yaml(tmp, "booking:\n  dry_run: true\n")
            s = Settings.from_yaml(Path(path))
            assert s.booking.dry_run is True


# ---------------------------------------------------------------------------
# Settings.from_cli — CLI 参数创建
# ---------------------------------------------------------------------------


class TestSettingsFromCli:
    def test_from_cli_with_overrides(self):
        s = Settings.from_cli(auth__uid="cli_uid", booking__max_trials=7)
        assert s.auth.uid == "cli_uid"
        assert s.booking.max_trials == 7

    def test_from_cli_ignores_none_values(self):
        s = Settings.from_cli(auth__uid=None, booking__max_trials=7)
        assert s.auth.uid is None
        assert s.booking.max_trials == 7


# ---------------------------------------------------------------------------
# Settings.with_cli_overrides — 覆盖工厂
# ---------------------------------------------------------------------------


class TestSettingsWithCliOverrides:
    def test_with_cli_overrides_returns_new_instance(self):
        base = Settings.from_cli(booking__max_trials=5)
        overridden = base.with_cli_overrides(booking__max_trials=20)
        assert overridden is not base
        assert overridden.booking.max_trials == 20
        # 原实例不变
        assert base.booking.max_trials == 5

    def test_with_cli_overrides_preserves_other_fields(self):
        base = Settings.from_cli(auth__uid="user1", booking__max_trials=5)
        overridden = base.with_cli_overrides(booking__max_trials=10)
        assert overridden.auth.uid == "user1"
        assert overridden.booking.max_trials == 10

    def test_with_cli_overrides_ignores_none(self):
        base = Settings.from_cli(booking__max_trials=5)
        overridden = base.with_cli_overrides(booking__max_trials=None)
        assert overridden.booking.max_trials == 5  # 不变


# ---------------------------------------------------------------------------
# 子配置模型验证
# ---------------------------------------------------------------------------


class TestSubConfigValidation:
    def test_http_config_timeout_bounds(self):
        """timeout 超出 [1, 120] 应报错。"""
        with pytest.raises(ValidationError):
            HTTPConfig(timeout=0)
        with pytest.raises(ValidationError):
            HTTPConfig(timeout=200)

    def test_booking_config_max_trials_bounds(self):
        with pytest.raises(ValidationError):
            BookingConfig(max_trials=0)

    def test_strategy_config_valid_types(self):
        s1 = StrategyConfig(type="fixed")
        s2 = StrategyConfig(type="random")
        s3 = StrategyConfig(type="weekday")
        assert s1.type == "fixed"
        assert s2.type == "random"
        assert s3.type == "weekday"

    def test_strategy_config_invalid_type(self):
        with pytest.raises(ValidationError):
            StrategyConfig(type="invalid")
