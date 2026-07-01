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


def main() -> None:
    """主入口：默认启动终端 UI，带 --cli 进入命令行模式。"""
    _configure_observability()

    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        from hdu_library_booking.cli import main as cli_main

        sys.exit(cli_main())  # type: ignore[func-returns-value]
    else:
        _run_terminal()


def _configure_observability() -> None:
    """初始化可观测性（结构化日志）。"""
    from hdu_library_booking.config import get_settings
    from hdu_library_booking.observability import configure_from_config

    settings = get_settings()
    configure_from_config(settings.logging_cfg)


def _run_terminal() -> None:
    """启动终端交互界面。"""
    from hdu_library_booking.api import HduLibraryClient
    from hdu_library_booking.cli.terminal import TerminalUI
    from hdu_library_booking.config import get_settings
    from hdu_library_booking.services import (
        AuthService,
        PlanService,
        YamlPlanRepository,
    )

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
