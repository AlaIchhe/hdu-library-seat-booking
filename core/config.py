"""
配置文件读写。

提供简单的 YAML 加载 / 保存函数，替代各项目中重复的 ConfigParser 类。
"""

import yaml
from pathlib import Path


def load_yaml_config(path):
    """从 YAML 文件加载配置。

    参数
    ----------
    path : str or Path
        配置文件路径。

    返回
    -------
    dict
        解析后的配置字典。
    """
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml_config(path, data):
    """将配置字典写入 YAML 文件。

    参数
    ----------
    path : str or Path
        目标文件路径。
    data : dict
        要保存的配置数据。
    """
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, encoding="utf-8", allow_unicode=True)


def create_default_config(path, template_yaml):
    """利用 YAML 模板字符串创建默认配置文件。

    参数
    ----------
    path : str or Path
        配置文件路径。
    template_yaml : str
        YAML 模板字符串（各项目可自定义内容）。
    """
    config = yaml.safe_load(template_yaml)
    save_yaml_config(path, config)
    return config
