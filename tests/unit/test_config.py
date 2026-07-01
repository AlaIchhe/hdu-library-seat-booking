"""Tests for hdu_library_booking.config — YAML config I/O."""

import os
import tempfile

import pytest
import yaml

from hdu_library_booking.config import (
    ConfigParser,
    create_default_config,
    load_yaml_config,
    save_yaml_config,
)


class TestLoadYamlConfig:
    def test_load_valid_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("key: value\nlist:\n  - a\n  - b\n")
            path = f.name
        try:
            data = load_yaml_config(path)
            assert data["key"] == "value"
            assert data["list"] == ["a", "b"]
        finally:
            os.unlink(path)

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_yaml_config("/nonexistent/path/config.yaml")


class TestSaveYamlConfig:
    def test_save_and_reload(self):
        data = {"user": {"name": "test", "uid": "123"}}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            save_yaml_config(path, data)
            reloaded = load_yaml_config(path)
            assert reloaded["user"]["name"] == "test"
        finally:
            os.unlink(path)


class TestCreateDefaultConfig:
    def test_creates_from_template(self):
        template = "default_key: default_value\nversion: 1\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            config = create_default_config(path, template)
            assert config["default_key"] == "default_value"
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_invalid_template_raises(self):
        with pytest.raises(yaml.YAMLError):
            create_default_config("/nonexistent/dir/config.yaml", ":: invalid yaml ::")


class TestConfigParser:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "config.yaml")

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_config(self):
        parser = ConfigParser(self.config_path, template="key: value\n")
        parser.create_config()
        assert os.path.exists(self.config_path)
        assert parser.config["key"] == "value"

    def test_parse_config(self):
        # 先写入配置文件
        save_yaml_config(self.config_path, {"name": "test"})
        parser = ConfigParser(self.config_path)
        result = parser.parse_config()
        assert result["name"] == "test"

    def test_save_config(self):
        parser = ConfigParser(self.config_path)
        parser.save_config({"saved": True})
        assert os.path.exists(self.config_path)
        reloaded = load_yaml_config(self.config_path)
        assert reloaded["saved"] is True

    def test_delete_config_file(self):
        save_yaml_config(self.config_path, {"x": 1})
        parser = ConfigParser(self.config_path)
        parser.delete_config_file()
        assert not os.path.exists(self.config_path)

    def test_delete_nonexistent_no_error(self):
        parser = ConfigParser("/nonexistent/path/ghost.yaml")
        # 不应抛出异常
        parser.delete_config_file()
