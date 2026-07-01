"""配置解析器（向后兼容 shim，核心功能由 hdu_library_booking.config.settings.Settings 替代）。"""

from __future__ import annotations

import os

from hdu_library_booking.observability._error_tracker import ErrorCategory, error_tracker

from .yaml import load_yaml_config, save_yaml_config


class ConfigParser:
    """配置解析器 — 向后兼容。

    新代码请使用 ``hdu_library_booking.config.settings.Settings``。
    """

    def __init__(self, config_file: str, template: str | None = None) -> None:
        self.config_file = config_file
        self.config: dict | None = None
        self.template = template

    def create_config(self) -> None:
        """根据模板 YAML 创建默认配置文件。"""
        import yaml

        self.config = yaml.safe_load(self.template)
        save_yaml_config(self.config_file, self.config)

    def parse_config(self) -> dict:
        """从文件加载 YAML 配置。"""
        try:
            self.config = load_yaml_config(self.config_file)
        except Exception as exc:
            error_tracker.record(
                ErrorCategory.CONFIG,
                f"配置解析失败：{self.config_file}",
                exc,
                module=__name__,
            )
            raise
        return self.config

    def save_config(self, config: dict) -> None:
        """将配置字典写入文件。"""
        save_yaml_config(self.config_file, config)

    def delete_config_file(self) -> None:
        """删除配置文件（例如凭据泄露时清理）。"""
        if os.path.exists(self.config_file):
            try:
                os.remove(self.config_file)
            except OSError as exc:
                error_tracker.record(
                    ErrorCategory.CONFIG,
                    f"删除配置文件失败：{self.config_file}",
                    exc,
                    module=__name__,
                )
                raise
