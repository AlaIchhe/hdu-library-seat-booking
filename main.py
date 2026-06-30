#!/usr/bin/env python3
"""
HDU 图书馆座位预约系统 — 终端交互入口。

使用方法:
    uv run hdu-tui              # 启动终端交互菜单
    uv run hdu-book --help      # 查看 CLI 帮助
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录的 .env（在 import app 之前执行）
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


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
    from app.services import (
        AuthService,
        PlanService,
        YamlPlanRepository,
    )
    from app.ui.terminal import TerminalUI
    from core import HduLibraryClient, get_settings

    # 加载统一配置
    settings = get_settings()

    # 初始化
    client = HduLibraryClient(settings=settings)
    auth = AuthService(client)

    # 方案存储
    repo = YamlPlanRepository(settings.plans.file)
    plan_service = PlanService(repo)

    # 启动 UI
    ui = TerminalUI(client, plan_service, auth)
    sys.exit(ui.run())


if __name__ == "__main__":
    main()
