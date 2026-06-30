"""
配置文件读写。

提供简单的 YAML 加载 / 保存函数。
"""

from pathlib import Path

import yaml

from .metrics import ErrorCategory, error_tracker


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
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        error_tracker.record(
            ErrorCategory.CONFIG,
            f"配置文件不存在：{path}",
            module=__name__,
        )
        raise
    except Exception as exc:
        error_tracker.record(
            ErrorCategory.CONFIG,
            f"配置文件读取失败：{path}",
            exc,
            module=__name__,
        )
        raise


def save_yaml_config(path, data):
    """将配置字典写入 YAML 文件。

    参数
    ----------
    path : str or Path
        目标文件路径。
    data : dict
        要保存的配置数据。
    """
    try:
        with Path(path).open("w", encoding="utf-8") as f:
            yaml.dump(data, f, encoding="utf-8", allow_unicode=True)
    except Exception as exc:
        error_tracker.record(
            ErrorCategory.CONFIG,
            f"配置文件写入失败：{path}",
            exc,
            module=__name__,
        )
        raise


def create_default_config(path, template_yaml):
    """利用 YAML 模板字符串创建默认配置文件。

    参数
    ----------
    path : str or Path
        配置文件路径。
    template_yaml : str
        YAML 模板字符串。
    """
    try:
        config = yaml.safe_load(template_yaml)
    except Exception as exc:
        error_tracker.record(
            ErrorCategory.CONFIG,
            "模板 YAML 解析失败",
            exc,
            module=__name__,
        )
        raise
    save_yaml_config(path, config)
    return config
