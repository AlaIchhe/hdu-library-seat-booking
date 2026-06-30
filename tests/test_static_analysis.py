"""静态代码分析测试 — 通过 subprocess 运行 ruff / mypy / bandit 并验证零错误。

所有测试标记为 ``@pytest.mark.static``，CI 中可通过 ``-m "not static"`` 跳过。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _find_tool(module_name: str) -> str | None:
    """定位工具可执行文件：优先 shutil.which，回退到 python -m。"""
    # 1) 在 PATH 中查找（Windows: ruff.exe / mypy.exe / bandit.exe）
    if path := shutil.which(module_name):
        return path
    # 2) 回退到 python -m（要求工具在当前 Python 中可 import）
    return None


def _run_tool(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """在项目根目录运行一个静态分析工具并返回 CompletedProcess。"""
    module_name = args[0]
    tool_path = _find_tool(module_name)
    cmd = [tool_path, *args[1:]] if tool_path else [sys.executable, "-m", *args]
    # 使用 encoding="utf-8" + errors="replace" 避免 Windows GBK 编码问题
    # （subprocess 的 _readerthread 在 GBK locale 下读取 UTF-8 输出会崩溃）
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=timeout,
        env=env,
    )


def _assert_success(proc: subprocess.CompletedProcess[str], tool: str) -> None:
    """断言工具零退出码；失败时打印 stderr + stdout 前 80 行并 raise。

    注意：Windows 上 text=True + capture_output 可能因 GBK 编码问题
    导致 stdout/stderr 为 None，此处做防御性处理。
    """
    if proc.returncode == 0:
        return
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    detail = "\n".join(line for part in (stdout, stderr) if part for line in part.splitlines()[:80])
    pytest.fail(
        f"{tool} 发现错误 (exit={proc.returncode})：\n{detail}\n\n"
        f"--- 完整输出共 {len(stdout.splitlines()) + len(stderr.splitlines())} 行 ---"
    )


# ---------------------------------------------------------------------------
# Ruff
# ---------------------------------------------------------------------------
@pytest.mark.static
def test_ruff_lint() -> None:
    """Ruff 代码风格 & 逻辑错误检查必须零错误。"""
    proc = _run_tool(["ruff", "check", "."])
    _assert_success(proc, "ruff check")


@pytest.mark.static
def test_ruff_format() -> None:
    """Ruff 格式化检查（--diff 模式）必须零差异。"""
    proc = _run_tool(["ruff", "format", "--check", "."])
    _assert_success(proc, "ruff format")


# ---------------------------------------------------------------------------
# Mypy
# ---------------------------------------------------------------------------
@pytest.mark.static
def test_mypy() -> None:
    """Mypy 类型检查必须零错误。"""
    proc = _run_tool(
        ["mypy", ".", "--config-file=pyproject.toml"],
        timeout=180,
    )
    _assert_success(proc, "mypy")


# ---------------------------------------------------------------------------
# Bandit
# ---------------------------------------------------------------------------
@pytest.mark.static
def test_bandit() -> None:
    """Bandit 安全扫描必须零 HIGH / MEDIUM 告警。"""
    proc = _run_tool(
        ["bandit", "-c", "pyproject.toml", "-r", ".", "-ll"],
    )
    # bandit 返回 1 表示发现 issue；返回 2+ 表示工具本身出错
    if proc.returncode >= 2:
        pytest.fail(f"bandit 执行失败 (exit={proc.returncode})：\n{proc.stderr[:2000]}")
    if proc.returncode == 1:
        # 提取 issue 摘要
        stdout = proc.stdout
        lines = stdout.splitlines()
        issue_lines = [
            ln for ln in lines if "Issue:" in ln or "Severity:" in ln or "Confidence:" in ln
        ]
        pytest.fail(f"bandit 发现安全问题 ({len(issue_lines) // 2} 个)：\n" + stdout[-3000:])
    # returncode == 0 → 全部通过
