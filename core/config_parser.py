import os

import yaml

from .config import load_yaml_config, save_yaml_config
from .metrics import ErrorCategory, error_tracker


class ConfigParser:
    def __init__(self, config_file, template=None):
        """初始化配置解析器。

        参数
        ----------
        config_file : str
            配置文件路径。
        template : str, optional
            YAML 模板字符串。也可由子类在 __init__ 中设置。
        """
        self.config_file = config_file
        self.config = None
        self.template = template

    def create_config(self):
        """根据模板 YAML 创建默认配置文件。"""
        self.config = yaml.safe_load(self.template)
        save_yaml_config(self.config_file, self.config)

    def parse_config(self):
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

    def save_config(self, config):
        """将配置字典写入文件。"""
        save_yaml_config(self.config_file, config)

    def delete_config_file(self):
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
