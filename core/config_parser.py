"""
ConfigParser — 配置文件管理基类。

提取 Master（config/config.py）和 Killer（config/config.py）中完全重复的：
  - YAML 模板化默认配置创建
  - 配置加载 / 保存
  - 配置文件删除

各项目仅需提供自己的 YAML 模板字符串。
"""

import os

import yaml

from .config import load_yaml_config, save_yaml_config


class ConfigParser:
    """配置文件解析器基类 — Master 和 Killer 的 ConfigParser 共享完全相同的结构。

    子类只需在 __init__ 中设置 self.template 即可。

    使用方法
    --------
    class MyConfigParser(ConfigParser):
        def __init__(self, config_file):
            super().__init__(config_file)
            self.template = \"\"\"...\"\"\"
    """

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
        self.config = load_yaml_config(self.config_file)
        return self.config

    def save_config(self, config):
        """将配置字典写入文件。"""
        save_yaml_config(self.config_file, config)

    def delete_config_file(self):
        """删除配置文件（例如凭据泄露时清理）。"""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
