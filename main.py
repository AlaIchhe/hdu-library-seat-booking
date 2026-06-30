#!/usr/bin/env python3
"""
HDU 图书馆座位预约系统 — 终端交互入口。

使用方法:
    python main.py              # 启动终端交互菜单
    python main.py --help       # 查看 CLI 帮助
    python main.py --cli ...    # 命令行一次性执行
"""

import sys


def main():
    """主入口：默认启动终端 UI，带 --cli 进入命令行模式。"""
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        from app.ui.cli import main as cli_main

        sys.exit(cli_main())
    else:
        _run_terminal()


def _run_terminal():
    """启动终端交互界面。"""
    import os
    from pathlib import Path

    from app.services import (
        AuthService,
        PlanService,
        YamlPlanRepository,
    )
    from app.ui.terminal import TerminalUI
    from core import HduLibraryClient
    from core.config import load_yaml_config

    # 加载配置
    config_path = Path(os.environ.get("HDU_CONFIG", "config.yaml"))
    config = {}
    if config_path.exists():
        try:
            config = load_yaml_config(config_path)
        except Exception:
            from core.metrics import ErrorCategory, error_tracker

            error_tracker.record(
                ErrorCategory.CONFIG,
                f"入口配置文件加载失败：{config_path}",
                module=__name__,
            )

    # 初始化
    client = HduLibraryClient(config)
    auth = AuthService(client)

    # 方案存储
    plans_file = config.get("plans_file", "plans.yaml")
    repo = YamlPlanRepository(plans_file)
    plan_service = PlanService(repo)

    # 启动 UI
    ui = TerminalUI(client, plan_service, auth)
    sys.exit(ui.run())


if __name__ == "__main__":
    main()
