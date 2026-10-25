#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG 构造工具：只产出 ppt-master 契约允许的元素与属性。

硬性约束（来自 ppt-master scripts/docs/svg-contract.md）：
  * 禁止 <style> 块、class 属性、<foreignObject>、<textPath>、SMIL 动画、<script>
  * 禁止 <mask>；filter 仅受控用法（本文件不使用）
  * 数值不带单位（字号写 28 而非 28px），最多两位小数
  * 顶层 <g> 必须有唯一 id 与 data-pptx-bounds="x y w h"
  * 多行文本用 <tspan x=".." dy="..">，禁止绝对 y 换行
  * <image href> 相对项目根（images/xxx.png），必须有 width/height
  * 同册跳转 href 必须是 "#slide-N"（1-based 最终页序）
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape as _xml_escape

CANVAS_W = 1280
CANVAS_H = 720

# --------------------------------------------------------------------------
# 主题：明亮、低龄友好、不学术化
# --------------------------------------------------------------------------

class Theme:
    FONT = "Microsoft YaHei"

    BG = "#FFFBF2"
    BG_TINT = "#FFEFD6"
    CARD = "#FFFFFF"
    CARD_SOFT = "#FFF7E8"
    INK = "#2C3542"
    INK_SOFT = "#5C6875"
    MUTED = "#8A94A0"
    LINE = "#E7DFCF"

    BLUE = "#2F80ED"       # 条件
    BLUE_SOFT = "#DCEBFF"
    RED = "#E4573D"        # 问题 / 易错
    RED_SOFT = "#FFE3DC"
    ORANGE = "#F2994A"     # 重点
    ORANGE_SOFT = "#FFE9CF"
    GREEN = "#2FA36B"      # 正确 / 解答
    GREEN_SOFT = "#DDF3E7"
    PURPLE = "#8B5CF6"
    PURPLE_SOFT = "#EDE4FF"
    YELLOW = "#F2C94C"
    PEN = "#FFD9B0"


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def esc(text: str) -> str:
    """XML 转义（命名实体如 &mdash; 被禁止，只使用原始 Unicode 字符）。"""
    return _xml_escape(str(text), {"'": "&apos;", '"': "&quot;"})


def num(v: float) -> str:
    """输出最多两位小数的数值字符串（禁止科学计数法、前导 +、百分号）。"""
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"非法数值：{v}")
    r = round(f, 2)
    if r == int(r):
        return str(int(r))
    return f"{r:.2f}".rstrip("0").rstrip(".")


def is_wide(ch: str) -> bool:
    """判断是否为全角字符（中文、全角标点等）。"""
    o = ord(ch)
    return (
        0x1100 <= o <= 0x115F      # 韩文
        or 0x2E80 <= o <= 0xA4CF   # CJK 及全角符号
        or 0xAC00 <= o <= 0xD7A3   # 韩文音节
        or 0xF900 <= o <= 0xFAFF
        or 0xFE30 <= o <= 0xFE4F   # CJK 兼容形式
        or 0xFF00 <= o <= 0xFF60   # 全角形式
        or 0xFFE0 <= o <= 0xFFE6
        or 0x20000 <= o <= 0x3FFFD
    )


def char_width(ch: str, size: float) -> float:
    if ch == " ":
        return size * 0.30
    if is_wide(ch):
        return size
    if ch.isdigit():
        return size * 0.56
    if ch.isupper():
        return size * 0.66
    return size * 0.55


def text_width(text: str, size: float) -> float:
    return sum(char_width(c, size) for c in str(text))


# 质量闸的文本宽度估算比本模块略宽（含安全余量）。统一按这个系数收紧，
# 让"我们算能放下"在闸口那里也放得下，避免 1%~2% 的溢出告警带来的返工。
FIT_SAFE = 0.96


def wrap_text(text: str, size: float, max_width: float) -> list[str]:
    """按估算宽度换行；优先在标点后断开。"""
    if not text:
        return [""]
    limit = max_width * FIT_SAFE
    lines: list[str] = []
    buf = ""
    for ch in str(text):
        if ch == "\n":
            lines.append(buf)
            buf = ""
            continue
        if text_width(buf + ch, size) > limit and buf:
            lines.append(buf)
            buf = ""
        buf += ch
    if buf or not lines:
        lines.append(buf)
    return lines


def fit_font_size(text: str, size: float, max_width: float, min_size: float = 14.0) -> float:
    """文本超宽时逐级缩小字号（同样按 FIT_SAFE 收紧）。"""
    s = size
    limit = max_width * FIT_SAFE
    while s > min_size and text_width(text, s) > limit:
        s -= 1
    return s


# --------------------------------------------------------------------------
# 原子元素
# --------------------------------------------------------------------------

def rect(x, y, w, h, *, fill="#FFFFFF", stroke=None, sw=0, rx=None, opacity=None,
         role=None) -> str:
    a = [f'x="{num(x)}"', f'y="{num(y)}"', f'width="{num(w)}"', f'height="{num(h)}"']
    if fill:
        a.append(f'fill="{fill}"')
    if stroke:
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{num(sw)}"')
    if rx:
        a.append(f'rx="{num(rx)}"')
        a.append(f'ry="{num(rx)}"')
    if opacity is not None:
        a.append(f'opacity="{num(opacity)}"')
    return f"<rect {' '.join(a)}/>"


def circle(cx, cy, r, *, fill="#FFFFFF", stroke=None, sw=0, opacity=None,
           role=None, eid=None) -> str:
    a = [f'cx="{num(cx)}"', f'cy="{num(cy)}"', f'r="{num(r)}"', f'fill="{fill}"']
    if eid:
        a.insert(0, f'id="{eid}"')
    if stroke:
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{num(sw)}"')
    if opacity is not None:
        a.append(f'opacity="{num(opacity)}"')
    if role:
        a.append(f'data-pptx-role="{role}"')
    return f"<circle {' '.join(a)}/>"


def ellipse(cx, cy, rx, ry, *, fill="none", stroke=None, sw=2, opacity=None) -> str:
    a = [f'cx="{num(cx)}"', f'cy="{num(cy)}"', f'rx="{num(rx)}"', f'ry="{num(ry)}"',
         f'fill="{fill}"']
    if stroke:
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{num(sw)}"')
    if opacity is not None:
        a.append(f'opacity="{num(opacity)}"')
    return f"<ellipse {' '.join(a)}/>"


def line(x1, y1, x2, y2, *, stroke="#E7DFCF", sw=2, dash=None) -> str:
    a = [f'x1="{num(x1)}"', f'y1="{num(y1)}"', f'x2="{num(x2)}"', f'y2="{num(y2)}"',
         f'stroke="{stroke}"', f'stroke-width="{num(sw)}"']
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    return f"<line {' '.join(a)}/>"


def polyline(points: list[tuple[float, float]], *, stroke="#E4573D", sw=3,
             fill="none") -> str:
    pts = " ".join(f"{num(x)},{num(y)}" for x, y in points)
    return f'<polyline points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{num(sw)}"/>'


def text(x, y, content, *, size=24, fill=Theme.INK, weight="normal", anchor="start",
         family=None, opacity=None, line_height=None) -> str:
    """单行文本。content 内换行符会被拆成 tspan 续行。"""
    lh = line_height or round(size * 1.42)
    parts = str(content).split("\n")
    a = [f'x="{num(x)}"', f'y="{num(y)}"']
    if family:
        a.append(f'font-family="{family}"')
    a.append(f'font-size="{num(size)}"')
    if fill:
        a.append(f'fill="{fill}"')
    if weight != "normal":
        a.append(f'font-weight="{weight}"')
    if anchor != "start":
        a.append(f'text-anchor="{anchor}"')
    if opacity is not None:
        a.append(f'opacity="{num(opacity)}"')
    body = esc(parts[0])
    for extra in parts[1:]:
        body += f'<tspan x="{num(x)}" dy="{num(lh)}">{esc(extra)}</tspan>'
    return f"<text {' '.join(a)}>{body}</text>"


def image(x, y, w, h, href) -> str:
    return (f'<image x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" '
            f'href="{esc(href)}" preserveAspectRatio="xMidYMid meet"/>')


def group(gid: str, body: str, bounds: tuple[float, float, float, float],
          *, link: str | None = None, role: str | None = None,
          fill: str | None = None) -> str:
    """顶层组：必须有 id 与 data-pptx-bounds；可选超链接/结构角色/组级填充。"""
    bx, by, bw, bh = (num(v) for v in bounds)
    attrs = [f'id="{gid}"', f'data-pptx-bounds="{bx} {by} {bw} {bh}"']
    if role:
        attrs.append(f'data-pptx-role="{role}"')
    if fill:
        attrs.append(f'fill="{fill}"')
    inner = f"<g {' '.join(attrs)}>{body}</g>"
    if link:
        return f'<a href="{esc(link)}">{inner}</a>'
    return inner


def page(role: str, body: str, *, w=CANVAS_W, h=CANVAS_H, family=None) -> str:
    """根 <svg>：viewBox 是画布权威；font-family 必须在根上声明一次作为默认值。"""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'xml:lang="zh-CN" font-family="{family or Theme.FONT}" '
        f'data-pptx-page-role="{role}">{body}</svg>'
    )


def badge(x, y, label, *, fill=Theme.BLUE, size=26, r=30, color="#FFFFFF") -> str:
    """圆形题号徽章。"""
    return (circle(x + r, y + r, r, fill=fill)
            + text(x + r, y + r + size * 0.35, label, size=size, fill=color,
                   weight="bold", anchor="middle"))


def chip(x, y, label, *, fill=Theme.BLUE_SOFT, color=Theme.BLUE, size=20,
         pad_x=12, h=34, radius=17) -> tuple[str, float]:
    """胶囊标签，返回 (svg, 宽度)。"""
    w = text_width(label, size) + pad_x * 2
    body = (rect(x, y, w, h, fill=fill, rx=radius)
            + text(x + w / 2, y + h / 2 + size * 0.35, label, size=size, fill=color,
                   weight="bold", anchor="middle"))
    return body, w
