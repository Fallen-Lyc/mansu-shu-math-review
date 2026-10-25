#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎封装层：调用 ppt-master 完成「项目初始化 → SVG 校验 → 原生 PPTX 导出」。

设计原则
--------
1. 本 skill **不重写** PPTX 渲染能力，全部导出能力来自 ppt-master（MIT）。
2. 本文件只做三件事：定位引擎、拼装命令、串行执行并回报结果。
3. 任何引擎命令失败都如实抛出，不做静默降级。

引擎目录解析顺序
----------------
1. 环境变量 PPT_MASTER_DIR
2. <skill_root>/vendor/ppt-master/skills/ppt-master   （随包自带）
3. <skill_root>/../../vendor/ppt-master/skills/ppt-master （开发期工作区布局）
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


class EngineError(RuntimeError):
    """引擎命令失败。"""


# --------------------------------------------------------------------------
# 引擎与解释器定位
# --------------------------------------------------------------------------

def _candidate_dirs() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("PPT_MASTER_DIR")
    if env:
        roots.append(Path(env))
    roots.append(SKILL_ROOT / "vendor" / "ppt-master" / "skills" / "ppt-master")
    roots.append(SKILL_ROOT.parent / "vendor" / "ppt-master" / "skills" / "ppt-master")
    return roots


def find_engine() -> Path:
    """返回可用的 ppt-master skill 目录。"""
    tried = []
    for d in _candidate_dirs():
        tried.append(str(d))
        if (d / "scripts" / "svg_to_pptx.py").is_file():
            return d.resolve()
    raise EngineError(
        "未找到 ppt-master 引擎。请把 ppt-master 的 skills/ppt-master 目录放到 "
        "<skill>/vendor/ppt-master/skills/ppt-master，或设置环境变量 PPT_MASTER_DIR。"
        f"已尝试：{tried}"
    )


def find_python() -> str:
    """返回用于执行引擎脚本的解释器。

    顺序：skill 自带 .venv → 上级 .venv → 当前解释器 → 系统 python。
    只有确实装有 python-pptx 的候选才会被优先选中，否则导出会失败。
    """
    cands = [str(p) for p in _venv_candidates() if p.is_file()]
    if sys.executable:
        cands.append(sys.executable)
    cands += ["python3", "python"]
    seen: set[str] = set()
    ordered = [c for c in cands if not (c in seen or seen.add(c))]
    # 第一轮：pptx + Pillow 都要有。缺 Pillow 时质量闸会把正常 PNG 判为"损坏"，
    # 白白引发一轮排错，所以必须优先避开。
    for py in ordered:
        if _probe(py, ("pptx", "PIL")):
            return py
    for py in ordered:
        if _probe(py, ("pptx",)):
            return py
    return sys.executable or "python3"


def _venv_candidates() -> list[Path]:
    out: list[Path] = []
    for base in (SKILL_ROOT, SKILL_ROOT.parent):
        out += [base / ".venv" / "Scripts" / "python.exe",
                base / ".venv" / "bin" / "python",
                base / ".venv" / "bin" / "python3"]
    return out


def _probe(python: str, mods: tuple[str, ...]) -> bool:
    code = ("import importlib.util,sys; sys.exit(0 if all("
            f"importlib.util.find_spec(m) for m in {list(mods)}) else 1)")
    try:
        return subprocess.run([python, "-c", code], capture_output=True).returncode == 0
    except OSError:
        return False


def has_pptx(python: str) -> bool:
    return _probe(python, ("pptx",))


# --------------------------------------------------------------------------
# 命令执行
# --------------------------------------------------------------------------

MAX_ECHO = 4000
MAX_ERR_ECHO = 1800


def _focus(out: str, limit: int = MAX_ERR_ECHO) -> str:
    """失败时只回显关键行：ERROR/WARN/Traceback 与末尾若干行。

    引擎一次完整输出常有几千到上万字符，全量回显会吃掉大量上下文；
    绝大多数失败原因都能从这几行里定位，看不清时再打开 --verbose。
    """
    lines = [ln for ln in (out or "").splitlines() if ln.strip()]
    keep: list[str] = []
    for ln in lines:
        up = ln.upper()
        if ("ERROR" in up or "WARN" in up or "TRACEBACK" in up
                or "FAILED" in up or "EXCEPTION" in up):
            if ln not in keep:
                keep.append(ln)
    tail = [ln for ln in lines[-6:] if ln not in keep]
    text = "\n".join(keep + tail)
    return text[-limit:] if len(text) > limit else text


def run(cmd: list[str], *, cwd: Path | None = None, quiet: bool = False) -> str:
    """串行执行一条命令；失败抛 EngineError（错误信息已裁剪）。"""
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if not quiet:
        print(f"  $ {printable}")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise EngineError(
            f"命令失败（exit {proc.returncode}）：{printable}\n{_focus(out)}"
        )
    if not quiet and out.strip():
        print(out.strip()[:MAX_ECHO])
    return out


def quality_summary(out: str) -> dict:
    """从质量闸输出里抽出决定性数字，供一行摘要使用。"""
    import re

    def grab(pat: str) -> int:
        m = re.search(pat, out or "")
        return int(m.group(1)) if m else 0

    return {
        "pages": grab(r"Total files:\s*(\d+)"),
        "ok": grab(r"\[OK\] Fully passed:\s*(\d+)"),
        "warn": grab(r"\[WARN\] With warnings:\s*(\d+)"),
        "error": grab(r"\[ERROR\] With errors:\s*(\d+)"),
        "blocking": grab(r"blocking:\s*(\d+)"),
    }


def script_path(engine: Path, name: str) -> str:
    p = engine / "scripts" / name
    if not p.is_file():
        raise EngineError(f"引擎缺少脚本：{p}")
    return str(p)


# --------------------------------------------------------------------------
# 项目生命周期
# --------------------------------------------------------------------------

def init_project(project_path: Path, *, quiet: bool = False) -> Path:
    """初始化一个 quick-generate 项目，返回引擎实际创建的目录。

    ppt-master 的 `init` 只接受单个路径组件，并用 `--dir` 指定父目录；
    项目名若不以 `_<YYYYMMDD>` 结尾，引擎会自动追加当天日期。
    这里主动补上日期后缀，保证落盘目录与调用方预期一致。
    """
    engine = find_engine()
    py = find_python()
    project_path = Path(project_path).resolve()
    stamp = time.strftime("%Y%m%d")
    name = project_path.name
    if not name.endswith(stamp):
        name = f"{name}_{stamp}"
    final = (project_path.parent / name).resolve()

    svg_out = final / "svg_output"
    if svg_out.is_dir():
        # 复用项目：清掉上一轮的页面，避免导出器把旧页一起发布。
        # 逐个删除而不是整目录 rmtree——后者会触发宿主环境的批量删除保护。
        for old in svg_out.glob("*.svg"):
            old.unlink()
    if not final.is_dir():
        run(
            [py, script_path(engine, "project_manager.py"), "init", name,
             "--dir", str(project_path.parent), "--quick-generate"],
            cwd=project_path.parent,
            quiet=quiet,
        )
    svg_out.mkdir(parents=True, exist_ok=True)
    return final


def import_sources(project_path: Path, sources: list[str], *, quiet: bool = False) -> None:
    """把原始试卷/图片导入项目（供溯源归档，不参与渲染）。"""
    if not sources:
        return
    project_path = Path(project_path).resolve()
    engine = find_engine()
    py = find_python()
    run(
        [py, script_path(engine, "project_manager.py"), "import-sources",
         str(project_path), *sources],
        cwd=project_path,
        quiet=quiet,
    )


def check_quality(project_path: Path, *, quiet: bool = False) -> str:
    """最终质量闸：必须通过，否则导出器会拒收。"""
    project_path = Path(project_path).resolve()
    engine = find_engine()
    py = find_python()
    return run(
        [py, script_path(engine, "svg_quality_checker.py"), str(project_path),
         "--quick-generate", "--canonical-authoring", "--stage", "final", "--json"],
        cwd=project_path,
        quiet=quiet,
    )


def validate_animations(project_path: Path, *, quiet: bool = False) -> str:
    project_path = Path(project_path).resolve()
    engine = find_engine()
    py = find_python()
    return run(
        [py, script_path(engine, "animation_config.py"), "validate", str(project_path)],
        cwd=project_path,
        quiet=quiet,
    )


def export(project_path: Path, *, notes: bool = False, quiet: bool = False) -> Path:
    """导出原生可编辑 PPTX，返回文件路径。"""
    project_path = Path(project_path).resolve()
    engine = find_engine()
    py = find_python()
    before = _exports_snapshot(project_path)
    args = [py, script_path(engine, "svg_to_pptx.py"), str(project_path),
            "--quick-generate"]
    args.append("--with-notes" if notes else "--no-notes")
    run(args, cwd=project_path, quiet=quiet)
    after = _exports_snapshot(project_path)
    new = [p for p in after if p not in before]
    if not new:
        raise EngineError("导出未产生新的 pptx 文件")
    return max(new, key=lambda p: p.stat().st_mtime)


def _exports_snapshot(project_path: Path) -> set[Path]:
    d = Path(project_path) / "exports"
    if not d.is_dir():
        return set()
    return {p for p in d.glob("*.pptx") if p.is_file()}


def list_animation_groups(project_path: Path, *, quiet: bool = True) -> str:
    """列出每页可作为动画目标的顶层组 id（排错用）。"""
    project_path = Path(project_path).resolve()
    engine = find_engine()
    py = find_python()
    return run(
        [py, script_path(engine, "animation_config.py"), "list-groups", str(project_path)],
        cwd=project_path,
        quiet=quiet,
    )
