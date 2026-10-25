#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境准备：确保本机有能跑 ppt-master 导出的 Python 环境。

首次使用本 skill 前跑一次即可：

    python <SKILL_DIR>/scripts/setup_env.py

逻辑：
  1. 已有可用环境（能 import pptx）→ 直接报告，什么都不装。
  2. 否则在本 skill 目录内建 .venv（不污染系统 Python），装最小依赖
     python-pptx / XlsxWriter / PyYAML / Pillow（国内走清华源，失败回默认源）。
  3. 仍失败 → 打印手工安装命令，不做静默降级。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEPS = ["python-pptx>=0.6.21", "XlsxWriter>=3.0.0", "PyYAML", "Pillow"]
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def _has_pptx(py: str) -> bool:
    """就绪判定：python-pptx 负责导出，Pillow 负责让质量闸正确读取 PNG。"""
    code = ("import importlib.util,sys; sys.exit(0 if all("
            "importlib.util.find_spec(m) for m in ('pptx','PIL')) else 1)")
    try:
        return subprocess.run([py, "-c", code], capture_output=True).returncode == 0
    except OSError:
        return False


def _venv_python(root: Path) -> Path | None:
    for rel in ("Scripts/python.exe", "bin/python", "bin/python3"):
        p = root / ".venv" / rel
        if p.is_file():
            return p
    return None


def _pip_install(py: str, extra_index: bool) -> bool:
    cmd = [py, "-m", "pip", "install", "-q"]
    if extra_index:
        cmd += ["-i", MIRROR]
    cmd += DEPS
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 and extra_index:
        # 镜像不可用就回默认源
        return subprocess.run([py, "-m", "pip", "install", "-q"] + DEPS,
                              capture_output=True).returncode == 0
    return r.returncode == 0


def main() -> int:
    # 1) 只认「跟着 skill 走」的环境。当前解释器可用不算数：
    #    其他 agent 多半用另一个 Python 调起本 skill，那时它依然缺 python-pptx。
    for base in (SKILL_ROOT, SKILL_ROOT.parent):
        vp = _venv_python(base)
        if vp and _has_pptx(str(vp)):
            print(f"[OK] 已就绪：{vp}")
            return 0

    # 2) 建 skill 内 .venv
    print("[..] 在本 skill 目录内准备独立环境（不改动系统 Python）…")
    r = subprocess.run([sys.executable, "-m", "venv", str(SKILL_ROOT / ".venv")],
                       capture_output=True)
    if r.returncode != 0:
        print("[ERR] 创建 .venv 失败：", r.stderr.decode("utf-8", "replace")[:400])
        return 1
    vp = _venv_python(SKILL_ROOT)
    if not vp:
        print("[ERR] .venv 里找不到解释器")
        return 1
    print(f"[..] 安装依赖：{' '.join(DEPS)}")
    if not _pip_install(str(vp), extra_index=True):
        print("[ERR] 依赖安装失败，请手工执行：")
        print(f'      "{vp}" -m pip install {" ".join(DEPS)}')
        return 1
    print(f"[OK] 环境就绪：{vp}")
    print("     之后直接用任意 agent 调用本 skill 即可，无需再跑此脚本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
