#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""苏教版小学数学讲评课件生成器。

输入：一份结构化 JSON（由 agent 解析试卷/习题后产出，见 schema/questions.schema.json）
输出：svg_output/*.svg + animations.json，再由 engine.py 导出原生可编辑 PPTX

页面编排（固定顺序，超链接依赖最终页序，故先排 roster 再渲染）
------------------------------------------------------------------
  1                   封面：告诉学生讲的是哪张卷子
  2（可多页）          目录：题目按钮，点击直达对应题目首页
  每题 2~3 页          ① 题目首页：题干 →（点击）圈画条件与问题 →（点击）分析 →（点击）易错点
                       ② 解决问题页：圈好画的题干 +（逐步点击）解题过程 + 返回目录
                       ③ 变式页（仅在用户确认需要变式的题目上生成）
  末页（可选）          结束页

动画契约
--------
  * 圈画层是覆盖在文字上的标注，声明 data-pptx-role="decoration" 以获得
    ppt-master 的重叠豁免；在 animations.json 中显式命名即可被动画化。
  * slide key 用文件名主干（不含 .svg）。
  * 需要"点一下出一个"的单元各自独立成顶层组，order 递增。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import svgkit as k  # noqa: E402
from svgkit import Theme as T, num  # noqa: E402

# 条件序号：①②③…（不画圆圈底，只是序号字符）
_CIRCLED = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤", 6: "⑥",
            7: "⑦", 8: "⑧", 9: "⑨"}

W, H = k.CANVAS_W, k.CANVAS_H
MARGIN = 56
CONTENT_W = W - MARGIN * 2


# --------------------------------------------------------------------------
# 富文本排版：把题干切成片段并记住每片坐标，供圈画定位
# --------------------------------------------------------------------------

def layout_rich(spans, x0, y0, size, max_w, lh):
    """返回 (parts, end_y)；parts = [(text, x, y, width, kind)]。"""
    parts: list[tuple[str, float, float, float, str]] = []
    cx, cy = x0, y0
    limit = max_w * k.FIT_SAFE
    for sp in spans:
        text = str(sp.get("text", ""))
        kind = sp.get("kind", "none")
        buf = ""
        for ch in text:
            if buf and k.text_width(buf + ch, size) > limit - (cx - x0):
                parts.append((buf, cx, cy, k.text_width(buf, size), kind))
                cy += lh
                cx = x0
                buf = ""
            buf += ch
        if buf:
            parts.append((buf, cx, cy, k.text_width(buf, size), kind))
            cx += k.text_width(buf, size)
    return parts, cy


# 图形名称 → 小图标（画在词语上方，让"什么图形"一眼可见）
SHAPE_ICONS = {
    "正方形": "square", "长方形": "rect", "矩形": "rect", "三角形": "tri",
    "圆": "circle", "圆形": "circle", "半圆": "semicircle",
    "平行四边形": "para", "梯形": "trapezoid", "菱形": "rhombus",
    "扇形": "sector", "正方体": "cube", "长方体": "cuboid",
    "圆柱": "cylinder", "圆锥": "cone",
}


def shape_icon(name: str, cx: float, cy: float, r: float, color: str) -> str:
    """按图形名画一个铅笔线风格的小示意图；识别不出就返回空串。"""
    # 先精确匹配，再按"包含"匹配（"正方形石砖"也要能出正方形图标）
    key = str(name).strip()
    t = SHAPE_ICONS.get(key)
    if not t:
        for cand in sorted(SHAPE_ICONS, key=len, reverse=True):
            if cand in key:
                t = SHAPE_ICONS[cand]
                break
    if not t:
        return ""
    st = f'fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round"'
    if t == "square":
        return f'<rect x="{num(cx - r)}" y="{num(cy - r)}" width="{num(2 * r)}" ' \
               f'height="{num(2 * r)}" {st}/>'
    if t == "rect":
        return f'<rect x="{num(cx - r * 1.35)}" y="{num(cy - r * 0.7)}" ' \
               f'width="{num(2.7 * r)}" height="{num(1.4 * r)}" {st}/>'
    if t == "circle":
        return f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" {st}/>'
    if t == "tri":
        p = f"{num(cx)},{num(cy - r)} {num(cx + r)},{num(cy + r * 0.8)} " \
            f"{num(cx - r)},{num(cy + r * 0.8)}"
        return f'<polygon points="{p}" {st}/>'
    if t == "semicircle":
        d = (f"M {num(cx - r)} {num(cy + r * 0.55)} A {num(r)} {num(r)} 0 0 1 "
             f"{num(cx + r)} {num(cy + r * 0.55)} Z")
        return f'<path d="{d}" {st}/>'
    if t == "para":
        p = (f"{num(cx - r)},{num(cy + r * 0.7)} {num(cx + r * 0.55)},{num(cy + r * 0.7)} "
             f"{num(cx + r)},{num(cy - r * 0.7)} {num(cx - r * 0.45)},{num(cy - r * 0.7)}")
        return f'<polygon points="{p}" {st}/>'
    if t == "trapezoid":
        p = (f"{num(cx - r * 0.55)},{num(cy - r * 0.7)} {num(cx + r * 0.55)},"
             f"{num(cy - r * 0.7)} {num(cx + r)},{num(cy + r * 0.7)} "
             f"{num(cx - r)},{num(cy + r * 0.7)}")
        return f'<polygon points="{p}" {st}/>'
    if t == "rhombus":
        p = (f"{num(cx)},{num(cy - r)} {num(cx + r * 0.85)},{num(cy)} "
             f"{num(cx)},{num(cy + r)} {num(cx - r * 0.85)},{num(cy)}")
        return f'<polygon points="{p}" {st}/>'
    if t == "sector":
        d = (f"M {num(cx)} {num(cy + r * 0.8)} L {num(cx - r * 0.9)} {num(cy + r * 0.1)} "
             f"A {num(r)} {num(r)} 0 0 1 {num(cx + r * 0.9)} {num(cy + r * 0.1)} Z")
        return f'<path d="{d}" {st}/>'
    if t in ("cube", "cuboid"):
        w = 2.6 * r if t == "cuboid" else 1.7 * r
        hh = 1.3 * r
        front = (f'<rect x="{num(cx - w / 2)}" y="{num(cy - hh / 2)}" width="{num(w)}" '
                 f'height="{num(hh)}" {st}/>')
        back = (f'<path d="M {num(cx - w / 2)} {num(cy - hh / 2)} L '
                f'{num(cx - w / 2 + r * 0.6)} {num(cy - hh / 2 - r * 0.6)} L '
                f'{num(cx + w / 2 + r * 0.6)} {num(cy - hh / 2 - r * 0.6)} L '
                f'{num(cx + w / 2)} {num(cy - hh / 2)} M {num(cx + w / 2)} '
                f'{num(cy - hh / 2)} L {num(cx + w / 2 + r * 0.6)} '
                f'{num(cy - hh / 2 - r * 0.6)} L {num(cx + w / 2 + r * 0.6)} '
                f'{num(cy + hh / 2 - r * 0.6)} L {num(cx + w / 2)} '
                f'{num(cy + hh / 2)}" {st}/>')
        return back + front
    if t == "cylinder":
        hh, rr = 1.5 * r, r * 0.85
        return (f'<ellipse cx="{num(cx)}" cy="{num(cy - hh / 2)}" rx="{num(rr)}" '
                f'ry="{num(rr * 0.38)}" {st}/>'
                f'<path d="M {num(cx - rr)} {num(cy - hh / 2)} L {num(cx - rr)} '
                f'{num(cy + hh / 2)} M {num(cx + rr)} {num(cy - hh / 2)} L '
                f'{num(cx + rr)} {num(cy + hh / 2)}" {st}/>'
                f'<path d="M {num(cx - rr)} {num(cy + hh / 2)} A {num(rr)} '
                f'{num(rr * 0.38)} 0 0 0 {num(cx + rr)} {num(cy + hh / 2)}" {st}/>')
    if t == "cone":
        return (f'<path d="M {num(cx)} {num(cy - r)} L {num(cx + r * 0.9)} '
                f'{num(cy + r * 0.75)} L {num(cx - r * 0.9)} {num(cy + r * 0.75)} Z" {st}/>'
                f'<ellipse cx="{num(cx)}" cy="{num(cy + r * 0.75)}" rx="{num(r * 0.9)}" '
                f'ry="{num(r * 0.3)}" {st}/>')
    return ""


def _img_aspect(path):
    """返回图片宽高比；读不到就返回 1.4（普通面板比例）。"""
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(path) as im:
            w, h = im.size
        return w / max(1, h)
    except Exception:
        return 1.4


def rich_text_svg(parts, size, *, color=None):
    """题干富文本：每个片段一个 <text>，配色区分条件/问题/关键概念/图形名。

    注：曾尝试把整段并进一个 <text>+<tspan>，结果质量闸反而报"无法解析续行几何"
    并触发纵向溢出，故保持每片段独立的写法（该条告警是建议性的，不影响导出）。
    """
    def _fill(kind: str) -> str:
        if color:
            return color
        return {"cond": T.BLUE, "ques": T.RED, "key": T.INK,
                "fig": T.ORANGE}.get(kind, T.INK)

    # 同一片段换行产生的多行合并成一个 <text>（tspan 续行），
    # 否则质量闸会提示"段落被拆散"；不同片段仍各自成段，配色不丢。
    body: list[str] = []
    i = 0
    fills = [_fill(p[4]) for p in parts]
    uniform = len(set(fills)) == 1
    while i < len(parts):
        text0, x0, y0, _w, kind = parts[i]
        j = i + 1
        while (j < len(parts) and parts[j][4] == kind
               and abs(parts[j][1] - x0) < 0.6 and parts[j][2] > parts[j - 1][2]):
            j += 1
        grp = parts[i:j]
        _c = None if uniform else _fill(kind)
        if len(grp) == 1:
            body.append(k.text(x0, y0, text0, size=size, fill=_c))
        else:
            body.append(k.text(x0, y0, "\n".join(g[0] for g in grp), size=size,
                               fill=_c,
                               line_height=round(grp[1][2] - grp[0][2], 1)))
        i = j
    out = "".join(body)
    # 整段同色时不逐字重复 fill，提到包一层 <g> 上（消除"冗余继承"告警）
    return f'<g fill="{fills[0]}">{out}</g>' if (uniform and parts) else out


def marks_fill(parts) -> str | None:
    """所有标注同色时返回该色（可提到父组上），否则 None。"""
    colors = {"cond": T.BLUE, "ques": T.RED, "key": T.YELLOW, "fig": T.ORANGE}
    seen = {colors[p[4]] for p in parts if p[4] in colors}
    return seen.pop() if len(seen) == 1 else None


def marks_svg(parts, size, numbering=True, hoist: str | None = None):
    """标注：条件画蓝色横线（不画框，带序号①②③）、问题画红色横线（不画圈）、
    关键词黄横线、图形名橙横线+上方小图形；返回 (svg, bounds)。

    hoist 给出颜色时，元素不再重复写 fill（由父组统一继承），避免"冗余继承"告警。
    """
    body = []
    min_x = min_y = 1e9
    max_x = max_y = -1e9
    seq = 0
    for text, x, y, w, kind in parts:
        if kind == "none":
            continue
        top = y - size * 0.86
        h = size * 1.22
        left = x - 6
        ww = w + 12
        _fc = lambda c: (None if hoist else c)  # noqa: E731
        if kind == "cond":
            seq += 1
            # 横线标注：文字下方的粗横线（不再用方框圈住文字）
            body.append(k.rect(left, y + size * 0.16, ww, 5, fill=_fc(T.BLUE), rx=2.5))
            if numbering and seq <= 6:
                body.append(k.text(left + 2, top - 4, _CIRCLED[seq], size=15,
                                   fill=_fc(T.BLUE), weight="bold"))
            min_y = min(min_y, top - 24)
        elif kind == "ques":
            # 问题同样用横线标注，不画圈：红线画在文字下方，略粗以示强调
            body.append(k.rect(left, y + size * 0.12, ww, 6, fill=_fc(T.RED), rx=3))
            min_y = min(min_y, top - 4)
        elif kind == "key":
            # 关键概念同样不铺底色盖字：文字下方画黄色横线
            body.append(k.rect(left, y + size * 0.16, ww, 5, fill=_fc(T.YELLOW),
                               rx=2.5))
            min_y = min(min_y, top - 4)
        elif kind == "fig":
            # 图形名：只用橙色横线标（不铺底色，避免盖住文字）+ 上方小示意图
            body.append(k.rect(left, y + size * 0.16, ww, 5, fill=_fc(T.ORANGE),
                               rx=2.5))
            icon = shape_icon(text, left + ww / 2, top - 9, size * 0.42,
                              hoist or T.ORANGE)
            if icon:
                body.append(icon)
                min_y = min(min_y, top - 24)
            else:
                min_y = min(min_y, top - 4)
        min_x = min(min_x, left)
        max_x = max(max_x, left + ww)
        max_y = max(max_y, top + h)
    if min_x > max_x:
        return "", (0, 0, 0, 0)
    return "".join(body), (min_x, min_y, max_x - min_x, max_y - min_y)


# --------------------------------------------------------------------------
# 通用零件
# --------------------------------------------------------------------------

def backdrop():
    """页面底色：根级 primitive，引擎会提升为幻灯片背景。"""
    return k.rect(0, 0, W, H, fill=T.BG)


def corner_decor(seed=0):
    """低龄友好的角部装饰（纯几何，避免图片依赖）。"""
    pts = [(1215, 88, 96, T.BG_TINT), (66, 652, 78, T.BLUE_SOFT),
           (1196, 664, 60, T.ORANGE_SOFT)]
    cx, cy, r, fill = pts[seed % len(pts)]
    # 根级装饰元素必须带结构角色与稳定 id，否则会被判为"未分组的顶层元素"
    tag = f"decor-{seed}"
    return (k.circle(cx, cy, r, fill=fill, opacity=0.55, role="decoration",
                     eid=f"{tag}-a")
            + k.circle(cx - r * 0.45, cy - r * 0.4, r * 0.28, fill=T.CARD, opacity=0.6,
                       role="decoration", eid=f"{tag}-b"))


def card(x, y, w, h, *, fill=T.CARD, stroke=T.LINE, sw=2, rx=18):
    return k.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, rx=rx)


def title_band(x, y, label, *, size=22):
    """小标题条：色块 + 文字。填充色交给外层组继承，避免重复声明。"""
    return (k.rect(x, y - size * 0.75, 6, size * 1.25, fill=None, rx=3)
            + k.text(x + 16, y, label, size=size, fill=None, weight="bold"))


def back_button(x, y, target, label="返回目录"):
    """可点击的返回按钮（整组包 <a>）。"""
    w, h = 168, 52
    body = (k.rect(x, y, w, h, fill=T.BLUE, rx=26)
            + k.text(x + w / 2, y + h / 2 + 8, label, size=22, fill="#FFFFFF",
                     anchor="middle", weight="bold"))
    return body, (x, y, w, h)


# --------------------------------------------------------------------------
# 页面渲染
# --------------------------------------------------------------------------

class Deck:
    def __init__(self, data: dict):
        self.meta = data.get("meta", {}) or {}
        self.questions = data.get("questions", []) or []
        self.slides: list[dict] = []   # {"file":..., "svg":..., "anim":...}
        self.index: dict[str, int] = {}  # 逻辑 key -> 1-based 页号

    # ---------------- roster ----------------

    def plan(self):
        """先排页序，确定每张逻辑页的最终页码（超链接要用）。"""
        plan: list[tuple[str, str]] = []   # (key, filename)
        plan.append(("cover", "cover"))
        toc_pages = self._toc_pages()
        for i in range(toc_pages):
            plan.append((f"toc{i}", f"toc{i}"))
        for qi, q in enumerate(self.questions, 1):
            tag = f"q{qi:02d}"
            plan.append((f"{tag}-stem", f"{tag}_stem"))
            plan.append((f"{tag}-solve", f"{tag}_solve"))
            if q.get("variants"):
                plan.append((f"{tag}-var", f"{tag}_var"))
        if self.meta.get("ending_note"):
            plan.append(("ending", "ending"))
        self.plan_list = plan
        for i, (key, _f) in enumerate(plan, 1):
            self.index[key] = i
        return plan

    def _toc_pages(self) -> int:
        per = 12
        n = len(self.questions)
        return max(1, (n + per - 1) // per)

    def slide_no(self, key: str) -> int:
        return self.index[key]

    def link(self, key: str) -> str:
        return f"#slide-{self.index[key]}"

    # ---------------- 封面 ----------------

    def render_cover(self):
        m = self.meta
        title = m.get("paper_title") or "练习讲评"
        sub = " · ".join([s for s in [
            m.get("grade_label") or (f"{m['grade']}年级" if m.get("grade") else ""),
            m.get("term_label") or (f"{m.get('term', '')}册" if m.get("term") else ""),
            m.get("unit") or "",
        ] if s])
        size = k.fit_font_size(title, 60, W - MARGIN * 2 - 260, min_size=34)
        lines = k.wrap_text(title, size, W - MARGIN * 2 - 240)
        y = 250 if len(lines) == 1 else 214
        body = [backdrop(), corner_decor(0), corner_decor(1)]
        # 右侧徽记：圆 + 字合成一个装饰组（它压在标题区右侧，必须声明装饰角色）
        body.append(k.group("cover-emblem",
                            k.circle(1090, 300, 150, fill=T.BG_TINT, opacity=0.8)
                            + k.circle(1090, 300, 96, fill=T.ORANGE_SOFT, opacity=0.7)
                            + k.text(1090, 312, "讲", size=76, fill=T.ORANGE,
                                     anchor="middle", weight="bold"),
                            (940, 150, 300, 300), role="decoration"))

        chip_svg, chip_w = k.chip(MARGIN, 150, "小学数学讲评", fill=T.ORANGE_SOFT,
                                  color=T.ORANGE, size=22, h=40)
        body.append(k.group("cover-chip", chip_svg, (MARGIN, 150, chip_w, 40)))
        # 多行标题写进同一个 <text>（tspan 续行），不要拆成兄弟 <text>
        body.append(k.group("cover-title",
                            k.text(MARGIN, y, "\n".join(lines), size=size, fill=T.INK,
                                   weight="bold", line_height=round(size * 1.35)),
                            (MARGIN, max(y - size * 1.25, 196), W - MARGIN * 2 - 200,
                             len(lines) * size * 1.35 + size * 0.6)))
        meta_lines = []
        if sub:
            meta_lines.append(sub)
        extra = " ".join([s for s in [m.get("class"), m.get("date"),
                                      f"共 {len(self.questions)} 题"] if s])
        if extra:
            meta_lines.append(extra)
        # 同一段落的多行必须写进一个 <text>，拆成兄弟 <text> 会被判为断行
        body.append(k.group("cover-meta",
                            k.rect(MARGIN, 424, 96, 6, fill=T.ORANGE, rx=3)
                            + k.text(MARGIN, 452, "\n".join(meta_lines), size=26,
                                     fill=T.INK_SOFT, line_height=44),
                            (MARGIN, 418, W - MARGIN * 2 - 200,
                             44 * len(meta_lines) + 44)))
        return k.page("cover", "".join(body))

    # ---------------- 目录 ----------------

    def render_toc(self, page_i: int, total_pages: int):
        per = 12
        start = page_i * per
        items = self.questions[start:start + per]
        body = [backdrop(), corner_decor(2)]
        body.append(k.group("toc-head",
                            k.text(MARGIN, 96, "目录", size=44, fill=T.INK, weight="bold")
                            + k.rect(MARGIN, 116, 84, 6, fill=T.ORANGE, rx=3),
                            (MARGIN, 46, 420, 84)))
        cols = 4
        cw = (CONTENT_W - (cols - 1) * 20) / cols
        ch = 118
        for i, q in enumerate(items):
            r, c = divmod(i, cols)
            x = MARGIN + c * (cw + 20)
            y = 160 + r * (ch + 18)
            no = str(q.get("no", start + i + 1))
            # 目录只放题号：不显示题干、不显示题型，点一下直达该题
            bw, bh = 92, 62
            bx = x + (cw - bw) / 2
            by = y + (ch - bh) / 2
            inner = (k.rect(x, y, cw, ch, fill=T.CARD, stroke=T.LINE, sw=2, rx=16)
                     + k.rect(bx, by, bw, bh, fill=T.ORANGE_SOFT, rx=14)
                     + k.text(x + cw / 2, by + bh / 2 + 13, no, size=34, fill=T.ORANGE,
                              weight="bold", anchor="middle"))
            qi = start + i + 1
            target = f"q{qi:02d}-stem"
            body.append(k.group(f"toc-btn-{start + i + 1}", inner,
                                (x, y, cw, ch), link=self.link(target)))
        # 翻页
        if total_pages > 1:
            nav = []
            if page_i > 0:
                nav.append(k.group("toc-prev",
                                   k.rect(MARGIN, 648, 150, 46, fill=T.CARD_SOFT, rx=23)
                                   + k.text(MARGIN + 75, 678, "上一页", size=20,
                                            fill=T.INK_SOFT, anchor="middle"),
                                   (MARGIN, 648, 150, 46), link=self.link(f"toc{page_i - 1}")))
            if page_i < total_pages - 1:
                nav.append(k.group("toc-next",
                                   k.rect(MARGIN + 170, 648, 150, 46, fill=T.CARD_SOFT,
                                          rx=23)
                                   + k.text(MARGIN + 245, 678, "下一页", size=20,
                                            fill=T.INK_SOFT, anchor="middle"),
                                   (MARGIN + 170, 648, 150, 46),
                                   link=self.link(f"toc{page_i + 1}")))
            body.extend(nav)
        return k.page("toc", "".join(body))

    def _brief(self, q) -> str:
        s = str(q.get("stem", "")).replace("\n", " ")
        s = s[:26] + ("…" if len(s) > 26 else "")
        return s or "题目"

    # ---------------- 题目首页 ----------------

    def render_stem(self, q, qi: int):
        tag = f"q{qi:02d}"
        anim = {}
        body = [backdrop()]
        no = str(q.get("no", qi))
        head = [k.badge(MARGIN, 30, no, fill=T.BLUE)]
        hx = MARGIN + 68
        if q.get("type"):
            head.append(k.text(hx, 66, str(q["type"]), size=24, fill=T.INK_SOFT))
            hx += k.text_width(str(q["type"]), 24) + 16
        for kn in (q.get("knowledge") or [])[:3]:
            cs, cw = k.chip(hx, 44, str(kn), fill=T.PURPLE_SOFT, color=T.PURPLE, size=18,
                            h=32)
            head.append(cs)
            hx += cw + 10
        body.append(k.group(f"{tag}-head", "".join(head), (MARGIN, 30, min(hx, W - MARGIN) - MARGIN, 60)))

        # 题干（有图则左右分栏；特别宽的条形图放到卡片底部全宽显示）
        img = q.get("stem_image")
        img_aspect = _img_aspect(img) if img else None
        wide_img = img is not None and img_aspect is not None and img_aspect > 3.0
        text_w = CONTENT_W - 32
        if img and not wide_img:
            text_w = CONTENT_W * 0.56 - 32
        size = 32
        spans = q.get("spans")
        if not spans:
            spans = [{"text": str(q.get("stem", "")), "kind": "none"}]
        card_x, card_y = MARGIN, 104
        card_h = 244
        tx = card_x + 28
        ty = card_y + 54
        max_w = text_w - 24
        size = int(k.fit_font_size("".join(s["text"] for s in spans), 32, max_w * 3.2,
                                   min_size=20))
        lh = round(size * 1.55)
        parts, end_y = layout_rich(spans, tx, ty, size, max_w, lh)
        needed = end_y - ty + size + 54
        card_h = max(150, min(240, needed + 40))
        if len({p[2] for p in parts}) > 4:
            size = int(k.fit_font_size("".join(s["text"] for s in spans), size,
                                       max_w * 4.4, min_size=18))
            lh = round(size * 1.5)
            parts, end_y = layout_rich(spans, tx, ty, size, max_w, lh)
            card_h = max(150, min(240, end_y - ty + size + 74))

        # 题干卡片、文字、图示必须是同一个顶层组：拆成多组会因 bounds 重叠被闸口拒收
        card_body = card(card_x, card_y, CONTENT_W, card_h) + rich_text_svg(parts, size)
        if img and wide_img:
            # 宽条形图：文字下方全宽放置（meet 保证不变形）
            ih2 = max(56, min(150, (CONTENT_W - 56) / img_aspect))
            card_h = min(330, max(card_h, needed + ih2 + 24))
            ih2 = max(40, card_h - needed - 18)
            card_body = (card(card_x, card_y, CONTENT_W, card_h)
                         + rich_text_svg(parts, size)
                         + k.image(card_x + 28, card_y + needed + 4,
                                   CONTENT_W - 56, ih2, img))
        elif img:
            # 右侧图区：按原比例缩放后居中，外面套一层浅色图框
            iw = CONTENT_W * 0.40
            ih = card_h - 40
            aw = min(iw, ih * max(0.4, img_aspect))
            ah = aw / max(0.4, img_aspect)
            ix = card_x + CONTENT_W * 0.58 + (iw - aw) / 2
            iy = card_y + (card_h - ah) / 2
            card_body += (k.rect(ix - 8, iy - 8, aw + 16, ah + 16, fill=T.CARD_SOFT,
                                 stroke=T.LINE, sw=2, rx=14)
                          + k.image(ix, iy, aw, ah, img))
        body.append(k.group(f"{tag}-stem-card", card_body,
                            (card_x, card_y, CONTENT_W, card_h)))

        # 圈画覆盖层（点击 1 次全部出现）
        mf = marks_fill(parts)
        ms, mb = marks_svg(parts, size, hoist=mf)
        if ms:
            body.append(k.group(f"{tag}-marks", ms, mb, role="decoration", fill=mf))
            anim[f"{tag}-marks"] = {"effect": "entrance_appear", "trigger": "on-click",
                                    "order": 1, "duration": 0.4}

        # 分析区
        ay = card_y + card_h + 20
        an = q.get("analysis") or {}
        blocks = [
            ("考什么", an.get("exam_point"), T.BLUE, T.BLUE_SOFT),
            ("重点条件", an.get("key_conditions"), T.ORANGE, T.ORANGE_SOFT),
            ("条件怎么连", an.get("relation"), T.GREEN, T.GREEN_SOFT),
            ("数量关系", an.get("quantity_relation"), T.PURPLE, T.PURPLE_SOFT),
        ]
        blocks = [b for b in blocks if b[1]]
        bw = (CONTENT_W - 16) / 2
        bh = 92
        inner = []
        for i, (lab, val, color, soft) in enumerate(blocks):
            r, c = divmod(i, 2)
            x = MARGIN + c * (bw + 16)
            y = ay + r * (bh + 12)
            # 换行宽度留足余量：checker 的文本宽度估算比本文件的估算略宽
            vsize = int(k.fit_font_size(str(val), 22, bw - 76, min_size=16))
            vlines = k.wrap_text(str(val), vsize, bw - 76)
            # 两行合写进一个 <text>（\n 换行），拆成兄弟 <text> 会被判为段落断行
            txt = k.text(x + 20, y + 52, "\n".join(vlines[:2]), size=vsize,
                         fill=T.INK, line_height=round(vsize * 1.3))
            inner.append(card(x, y, bw, bh, fill=soft, stroke=None, rx=14))
            inner.append(k.rect(x, y, 5, bh, fill=color, rx=2))
            inner.append(k.text(x + 20, y + 28, lab, size=19, fill=color, weight="bold"))
            inner.append(txt)
        rows = (len(blocks) + 1) // 2 if blocks else 0
        ah = rows * bh + max(0, rows - 1) * 12
        if inner:
            body.append(k.group(f"{tag}-analysis", "".join(inner),
                                (MARGIN, ay, CONTENT_W, max(bh, ah))))
            anim[f"{tag}-analysis"] = {"effect": "entrance_fade", "trigger": "on-click",
                                       "order": 2, "duration": 0.45}

        # 易错点
        mk = q.get("mistakes") or []
        if mk:
            my = min(ay + ah + 8, H - 50 - 88)
            lines: list[str] = []
            for m in mk[:2]:
                wrong = str(m.get("wrong", ""))
                reason = str(m.get("reason", "")) or str(m.get("fix", ""))
                line = (f"错例 {wrong}   原因：{reason}"
                        if (wrong and reason) else (wrong or reason))
                ls = int(k.fit_font_size(line, 22, CONTENT_W - 130, min_size=16))
                lines.append(k.wrap_text(line, ls, CONTENT_W - 130)[0])
            ls_final = int(k.fit_font_size(max(lines, key=len) if lines else "", 22,
                                           CONTENT_W - 130, min_size=16))
            # 多行写进同一个 <text>（tspan 续行），避免被判为"段落被拆散"
            items = [
                card(MARGIN, my, CONTENT_W, 88, fill=T.RED_SOFT, stroke=None, rx=14),
                k.text(MARGIN + 20, my + 36, "易错点", size=19, fill=T.RED, weight="bold"),
                k.text(MARGIN + 56, my + 36, "\n".join(lines), size=ls_final, fill=T.INK,
                       line_height=30),
            ]
            body.append(k.group(f"{tag}-mistake", "".join(items),
                                (MARGIN, my, CONTENT_W, 88)))
            anim[f"{tag}-mistake"] = {"effect": "entrance_fade", "trigger": "on-click",
                                      "order": 3, "duration": 0.45}

        # 提示条
        hint_y = H - 42
        body.append(k.group(f"{tag}-hint",
                            k.text(MARGIN, hint_y, "点击鼠标，一步一步看讲评", size=18,
                                   fill=T.MUTED),
                            (MARGIN, hint_y - 18, 400, 26)))
        return k.page("content", "".join(body)), anim

    # ---------------- 解决问题页 ----------------

    def render_solve(self, q, qi: int):
        tag = f"q{qi:02d}"
        anim = {}
        body = [backdrop()]
        no = str(q.get("no", qi))
        head = (k.badge(MARGIN, 30, no, fill=T.GREEN)
                + k.text(MARGIN + 68, 66, "解决问题", size=24, fill=T.GREEN, weight="bold"))
        body.append(k.group(f"{tag}-solve-head", "".join(head) if isinstance(head, list)
                            else head, (MARGIN, 30, 320, 60)))

        # 题干（静态圈画态；有图按比例放置）
        spans = q.get("spans")
        if not spans:
            spans = [{"text": str(q.get("stem", "")), "kind": "none"}]
        img = q.get("stem_image")
        img_aspect = _img_aspect(img) if img else None
        wide_img = img is not None and img_aspect is not None and img_aspect > 3.0
        tx0, max_w0 = MARGIN + 28, CONTENT_W - 56
        if img and not wide_img:
            max_w0 = CONTENT_W * 0.52 - 40
        size = int(k.fit_font_size("".join(s["text"] for s in spans), 24,
                                   min(max_w0 * 2.6, CONTENT_W * 0.72), min_size=16))
        lh = round(size * 1.5)
        parts, end_y = layout_rich(spans, tx0, 160, size, max_w0, lh)
        ch = min(190, max(96, end_y - 160 + size + 56))
        stem_body = card(MARGIN, 104, CONTENT_W, ch) + rich_text_svg(parts, size)
        if img and not wide_img:
            # 独立图区：右侧面板（含 10px 留白），图片按原比例铺满可用范围。
            # 高度上限 150：再高会挤掉下方解题步骤的可读空间。
            aw = min(CONTENT_W * 0.42 - 20, 150 * max(0.4, img_aspect))
            ah = aw / max(0.4, img_aspect)
            pw, ph = aw + 20, ah + 20
            ch = max(ch, min(212, ph + 28))
            px = MARGIN + CONTENT_W * 0.56
            py = 104 + (ch - ph) / 2
            stem_body = (card(MARGIN, 104, CONTENT_W, ch)
                         + rich_text_svg(parts, size)
                         + k.rect(px, py, pw, ph, fill=T.CARD_SOFT, stroke=T.LINE,
                                  sw=2, rx=14)
                         + k.image(px + 10, py + 10, aw, ah, img))
        elif img and wide_img:
            ih2 = max(56, min(150, (CONTENT_W - 56) / img_aspect))
            ch = min(238, max(ch, end_y - 160 + size + ih2 + 26))
            ih2 = max(44, ch - (end_y - 160 + size) - 20)
            stem_body = (card(MARGIN, 104, CONTENT_W, ch)
                         + rich_text_svg(parts, size)
                         + k.rect(MARGIN + 22, end_y + size + 2, CONTENT_W - 44,
                                  ih2 + 16, fill=T.CARD_SOFT, stroke=T.LINE, sw=2,
                                  rx=14)
                         + k.image(MARGIN + 30, end_y + size + 10, CONTENT_W - 60,
                                   ih2, img))
        body.append(k.group(f"{tag}-solve-stem", stem_body,
                            (MARGIN, 104, CONTENT_W, ch)))
        mf = marks_fill(parts)
        ms, mb = marks_svg(parts, size, numbering=False, hoist=mf)
        if ms:
            body.append(k.group(f"{tag}-solve-marks", ms, mb, role="decoration",
                                fill=mf))

        # 步骤区
        sy = 104 + ch + 18
        left_w = CONTENT_W * 0.62
        right_x = MARGIN + left_w + 22
        right_w = CONTENT_W - left_w - 22
        sols = [s for s in (q.get("solutions") or []) if s][:2]
        if not sols and q.get("answer"):
            sols = [{"name": "解答", "steps": [], "answer": q.get("answer")}]

        # 可用高度自适应：二分出最大的可行缩放，保证整列正好落在可用区里，
        # 绝不溢出画布、绝不压到返回按钮（溢出会被质量闸判为阻塞错误）。
        bottom = H - 78
        avail = max(120, bottom - sy)

        # 单列装不下时，把步骤左右分栏——靠无限压缩字号的排版是不可读的
        if len(sols) == 1 and self._col_total(sols[0], 0, 1, q, 1.0) > avail:
            steps = sols[0].get("steps") or []
            if len(steps) >= 3:
                half = (len(steps) + 1) // 2
                head = dict(sols[0])
                head["steps"] = steps[:half]
                tail_col = {"name": "", "steps": steps[half:],
                            "answer": sols[0].get("answer")}
                sols = [head, tail_col]
                left_w = right_w = (CONTENT_W - 22) / 2
                right_x = MARGIN + left_w + 22

        order = 1
        for si, sol in enumerate(sols):
            col_x = MARGIN if si == 0 else right_x
            col_w = left_w if si == 0 else right_w
            items, scale = self._fit_column(sol, si, len(sols), q, avail)
            y = sy
            for item in items:
                kind, h = item[0], item[1]
                if kind == "name":
                    body.append(k.group(f"{tag}-sol{si}-name",
                                        title_band(col_x, y + 18, str(item[2])),
                                        (col_x, y, col_w, max(30, h)),
                                        fill=T.GREEN if si == 0 else T.PURPLE))
                elif kind == "step":
                    st = item[2]
                    ri = item[3]
                    body.append(k.group(f"{tag}-s{si}-{ri}",
                                        self._step_svg(st, col_x, y, col_w, h, scale),
                                        (col_x, y, col_w, h)))
                    anim[f"{tag}-s{si}-{ri}"] = {"effect": "entrance_fade",
                                                 "trigger": "on-click", "order": order,
                                                 "duration": 0.4}
                    order += 1
                else:
                    tail = item[2]
                    fs = int(min(23, h * 0.36))
                    tsvg = (card(col_x, y, col_w, h, fill=T.GREEN_SOFT, stroke=None,
                                 rx=14)
                            + k.text(col_x + 22, y + h / 2 + fs * 0.35, str(tail),
                                     size=fs, fill=T.GREEN, weight="bold"))
                    gid = f"{tag}-ans{si}"
                    body.append(k.group(gid, tsvg, (col_x, y, col_w, h)))
                    anim[gid] = {"effect": "entrance_fade", "trigger": "on-click",
                                 "order": order, "duration": 0.4}
                    order += 1
                y += h + max(4, round(8 * scale))

        btn, bx = back_button(W - MARGIN - 168, H - 74, None)
        body.append(k.group(f"{tag}-back", btn, bx, link=self.link("toc0")))
        return k.page("content", "".join(body)), anim

    def _step_height(self, st) -> int:
        lines = st.get("lines") or []
        head = 44 if str(st.get("label", "")).strip() else 12
        if lines:
            return head + len(lines) * 34
        return 64

    def _col_total(self, sol, si, n_sols, q, scale: float) -> float:
        items = self._column_items(sol, si, n_sols, q, scale)
        gap = max(4, round(8 * scale))
        return sum(it[1] for it in items) + gap * max(0, len(items) - 1)

    def _column_items(self, sol, si, n_sols, q, scale: float):
        """按给定缩放列出本列要画的单元：(kind, height, payload…)。"""
        items: list[tuple] = []
        if str(sol.get("name", "")).strip():
            items.append(("name", max(30, round(34 * scale)), str(sol["name"])))
        for ri, st in enumerate((sol.get("steps") or [])[:6]):
            items.append(("step", max(34, round(self._step_height(st) * scale)), st, ri))
        tail = sol.get("answer") or (q.get("answer") if si == n_sols - 1 else None)
        if tail:
            items.append(("ans", max(46, round(62 * scale)), tail))
        return items

    def _fit_column(self, sol, si, n_sols, q, avail: float):
        """二分出最大缩放，使该列总高（含间距）不超过可用高度。"""
        total = lambda s: self._col_total(sol, si, n_sols, q, s)  # noqa: E731

        if total(1.0) <= avail:
            return self._column_items(sol, si, n_sols, q, 1.0), 1.0
        lo, hi, best = 0.3, 1.0, 0.3
        for _ in range(16):
            mid = (lo + hi) / 2
            if total(mid) <= avail:
                best, lo = mid, mid
            else:
                hi = mid
        items = self._column_items(sol, si, n_sols, q, best)
        # 极端情况仍放不下：从末尾裁掉单元，宁可少讲一步也不越界
        while items and sum(it[1] for it in items) + 4 * (len(items) - 1) > avail:
            if len(items) > 1:
                items.pop()
            else:
                items[0] = (items[0][0], int(avail)) + items[0][2:]
                break
        return items, best

    def _step_svg(self, st, x, y, w, h, scale: float = 1.0):
        label = str(st.get("label", "")).strip()
        out = card(x, y, w, h, fill=T.CARD, stroke=T.LINE, sw=2, rx=14)
        lx = x + 18
        if label:
            cs, cw = k.chip(lx, y + 14, label, fill=T.BLUE_SOFT, color=T.BLUE, size=19,
                            h=32, pad_x=12)
            out += cs
            lx += cw + 14
        lines = st.get("lines")
        if lines:
            n = len(lines)
            # 标签胶囊占顶部，正文排在它下面，避免压字
            head = 44 if label else 12
            avail_h = max(22, h - head - 6)
            lh = max(18, round(34 * scale))
            fs = int(max(15, round(24 * scale)))
            # 文字块实际占位（含升部/降部），在此基础上收缩行距与字号，
            # 保证绝不超出卡片 bounds —— 超界会被质量闸判为阻塞错误。
            text_h = fs * 1.1 + (n - 1) * lh
            if text_h > avail_h and n > 1:
                lh = max(15, (avail_h - fs * 1.1) / (n - 1))
                text_h = fs * 1.1 + (n - 1) * lh
            if text_h > avail_h:
                fs = int(max(13, (avail_h - (n - 1) * lh) / 1.1))
                text_h = fs * 1.1 + (n - 1) * lh
            y0 = y + head + max(fs * 0.85, (avail_h - text_h) / 2 + fs * 0.85)
            # 同一段落的多行必须写进一个 <text>（换行用 \n），拆成兄弟 <text> 会被判为断行
            out += k.text(x + 26, y0, "\n".join(str(ln) for ln in lines),
                          size=fs, fill=T.INK, line_height=round(lh, 1))
        else:
            expr = str(st.get("expr", ""))
            value = st.get("value")
            unit = st.get("unit") or ""
            tail = ""
            if value is not None and str(value) != "":
                tail = f" = {value}{('（' + unit + '）') if unit else ''}"
            line = f"{expr}{tail}"
            base_fs = max(18, round(26 * scale))
            fs = int(k.fit_font_size(line, base_fs, w - (lx - x) - 30, min_size=16))
            note = st.get("note")
            if note:
                out += k.text(lx, y + h - 9, str(note), size=int(max(13, 16 * scale)),
                              fill=T.MUTED)
                cy = y + (h - 20) / 2
            else:
                cy = y + h / 2
            out += k.text(lx, cy + fs * 0.35, line, size=fs, fill=T.INK)
        return out

    # ---------------- 变式页 ----------------

    def render_variant(self, q, qi: int):
        tag = f"q{qi:02d}"
        anim = {}
        body = [backdrop()]
        no = str(q.get("no", qi))
        head = (k.badge(MARGIN, 30, no, fill=T.ORANGE)
                + k.text(MARGIN + 68, 66, "变式练习", size=24, fill=T.ORANGE,
                         weight="bold"))
        body.append(k.group(f"{tag}-var-head", head, (MARGIN, 30, 320, 60)))

        items = q.get("variants") or []
        y = 118
        order = 1
        bottom = H - 78
        for i, v in enumerate(items[:3]):
            # 预估本条高度，放不下就停止，绝不压到返回按钮
            probe = str(v.get("stem", ""))
            tw = CONTENT_W - 56 - (CONTENT_W * 0.30 if v.get("image") else 0)
            fs_probe = int(k.fit_font_size(probe, 28, tw, min_size=18))
            probe_h = 46 + len(k.wrap_text(probe, fs_probe, tw)) * fs_probe * 1.45
            if v.get("hint") or v.get("answer"):
                probe_h += 66
            if y + probe_h > bottom:
                break
            stem = str(v.get("stem", ""))
            fs = int(k.fit_font_size(stem, 28, tw, min_size=18))
            lines = k.wrap_text(stem, fs, tw)
            lh = round(fs * 1.45)
            vh = 46 + len(lines) * lh
            # 多行写进一个 <text>（tspan 续行），避免被判为"段落被拆散"
            txt = k.text(MARGIN + 28, y + 40, "\n".join(lines), size=fs, fill=T.INK,
                         line_height=lh)
            extra_img = ""
            if v.get("image"):
                aw = min(CONTENT_W * 0.26, (vh - 24) * 1.6)
                ah = min(aw / 1.6, vh - 24)
                aw = ah * 1.6
                extra_img = k.image(MARGIN + CONTENT_W - aw - 24, y + (vh - ah) / 2,
                                    aw, ah, v["image"])
            body.append(k.group(f"{tag}-var{i}-stem",
                                card(MARGIN, y, CONTENT_W, vh)
                                + k.circle(MARGIN + 20, y + 22, 12, fill=T.ORANGE_SOFT)
                                + txt + extra_img,
                                (MARGIN, y, CONTENT_W, vh)))
            y += vh + 12
            ans = v.get("answer")
            hint = v.get("hint")
            extra = []
            if hint:
                extra.append(f"提示：{hint}")
            if ans:
                extra.append(f"答案：{ans}")
            if extra:
                line = "    ".join(extra)
                fs2 = int(k.fit_font_size(line, 22, CONTENT_W - 60, min_size=16))
                ah = 54
                gid = f"{tag}-var{i}-ans"
                body.append(k.group(gid,
                                    card(MARGIN, y, CONTENT_W, ah, fill=T.ORANGE_SOFT,
                                         stroke=None, rx=14)
                                    + k.text(MARGIN + 22, y + 35, line, size=fs2,
                                             fill=T.ORANGE, weight="bold"),
                                    (MARGIN, y, CONTENT_W, ah)))
                if ans or v.get("reveal", True):
                    anim[gid] = {"effect": "entrance_fade", "trigger": "on-click",
                                 "order": order, "duration": 0.4}
                    order += 1
                y += ah + 12
        btn, bx = back_button(W - MARGIN - 168, H - 74, None)
        body.append(k.group(f"{tag}-vback", btn, bx, link=self.link("toc0")))
        return k.page("content", "".join(body)), anim

    # ---------------- 结束页 ----------------

    def render_ending(self):
        note = str(self.meta.get("ending_note", ""))
        body = [backdrop(), corner_decor(1)]
        body.append(k.group("ending-title",
                            k.text(W / 2, 320, note or "订正完再交，错题要弄懂", size=46,
                                   fill=T.INK, weight="bold", anchor="middle"),
                            (MARGIN, 260, CONTENT_W, 90)))
        btn, bx = back_button(W / 2 - 84, 420, None)
        body.append(k.group("ending-back", btn, bx, link=self.link("toc0")))
        return k.page("ending", "".join(body))

    # ---------------- 组装 ----------------

    def build(self):
        # 关键：deck 级默认必须是 none，否则封面、目录、题干卡片也会被套上入场动画。
        # 只有下面显式写进 groups 的单元才动。
        anims = {"defaults": {"animation": {"effect": "none"}}, "slides": {}}
        out: list[tuple[str, str]] = []
        for i, (key, fname) in enumerate(self.plan_list, 1):
            slide_key = f"{i:02d}_{fname}"   # animations.json 的 slide key = 文件名主干
            if key == "cover":
                svg = self.render_cover()
            elif key.startswith("toc"):
                svg = self.render_toc(int(key[3:]), self._toc_pages())
            elif key.endswith("-stem"):
                svg, a = self.render_stem(self.questions[int(key[1:3]) - 1],
                                          int(key[1:3]))
                if a:
                    anims["slides"][slide_key] = {"groups": a}
            elif key.endswith("-solve"):
                svg, a = self.render_solve(self.questions[int(key[1:3]) - 1],
                                           int(key[1:3]))
                if a:
                    anims["slides"][slide_key] = {"groups": a}
            elif key.endswith("-var"):
                svg, a = self.render_variant(self.questions[int(key[1:3]) - 1],
                                             int(key[1:3]))
                if a:
                    anims["slides"][slide_key] = {"groups": a}
            else:
                svg = self.render_ending()
            out.append((f"{slide_key}.svg", svg))
        return out, anims


# --------------------------------------------------------------------------
# 输入归一化：允许"简写"，脚本自动补齐，减少 agent 书写量
# --------------------------------------------------------------------------

# 题干里出现的图形名（用于自动标 fig）
_FIG_WORDS = tuple(sorted(SHAPE_ICONS, key=len, reverse=True))
# 问句标志
_Q_MARKS = ("？", "?", "多少", "几", "求", "是多少", "谁", "哪", "是否", "能不能")


def _shape_split(seg: str) -> list[tuple[str, str | None]]:
    """把一段里的图形名单独切出来（其余部分 kind 待定，返回 None）。"""
    out: list[tuple[str, str | None]] = []
    rest = seg
    while rest:
        hit_i, hit_w = -1, ""
        for w in _FIG_WORDS:
            i = rest.find(w)
            if i >= 0 and (hit_i < 0 or i < hit_i
                           or (i == hit_i and len(w) > len(hit_w))):
                hit_i, hit_w = i, w
        if hit_i < 0:
            out.append((rest, None))
            break
        if hit_i > 0:
            out.append((rest[:hit_i], None))
        out.append((hit_w, "fig"))
        rest = rest[hit_i + len(hit_w):]
    return [(t, k) for t, k in out if t]


def auto_spans(stem: str) -> list[dict]:
    """没写 spans 时自动切分：数字/单位段=条件，问句=问题，图形名单独成 fig 片段。"""
    import re

    text = str(stem or "").replace("\n", "")
    if not text:
        return []
    # 按逗号、句号、分号切成语义段，标点归到前一段
    segs = [s for s in re.split(r"(?<=[，。；、！？!])", text) if s] or [text]
    out: list[dict] = []
    for seg in segs:
        base = "ques" if any(m in seg for m in _Q_MARKS) else (
            "cond" if re.search(r"\d", seg) else "none")
        for piece, kind in _shape_split(seg):
            # 相邻的同类型碎片合并，避免被图形名切碎后产生一堆零碎标号
            if (kind is None and out and out[-1]["kind"] == base):
                out[-1]["text"] += piece
            else:
                out.append({"text": piece, "kind": kind or base})
    return out


def _as_steps(obj) -> list[dict]:
    """把步骤的简写形式统一成 dict 列表。"""
    if obj is None:
        return []
    if isinstance(obj, str):
        return [{"expr": ln.strip()} for ln in obj.splitlines() if ln.strip()]
    if isinstance(obj, dict):
        return [obj]
    steps: list[dict] = []
    for it in obj:
        if isinstance(it, str):
            steps.append({"expr": it})
        elif isinstance(it, dict):
            steps.append(it)
    return steps


def _as_list(obj) -> list:
    if obj is None:
        return []
    return obj if isinstance(obj, list) else [obj]


def normalize(data: dict) -> dict:
    """把"简写版"输入补全成完整结构；已是完整结构的原样返回。"""
    if not isinstance(data, dict):
        return data
    for q in data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        stem = str(q.get("stem", "")).strip()
        q["stem"] = stem
        if not q.get("spans"):
            q["spans"] = auto_spans(stem) or [{"text": stem, "kind": "none"}]

        # solutions：允许 {"steps": ["a","b"]} / ["a","b"] / "a\nb"
        sols = q.get("solutions")
        if isinstance(sols, dict):
            sols = [sols]
        if isinstance(sols, str):
            sols = [{"steps": sols}]
        sols = _as_list(sols)
        fixed: list[dict] = []
        for s in sols:
            if not isinstance(s, dict):
                s = {"steps": s}
            s = dict(s)
            s["steps"] = _as_steps(s.get("steps"))
            fixed.append(s)
        q["solutions"] = [s for s in fixed if s.get("steps") or s.get("answer")]

        # mistakes：允许 ["错例…", "…"] 或 [{"wrong":..,"reason":..}]
        mks = []
        for m in _as_list(q.get("mistakes")):
            if isinstance(m, str):
                mks.append({"wrong": "", "reason": m})
            elif isinstance(m, dict):
                mks.append(m)
        q["mistakes"] = mks

        # variants：允许 ["题干", …] 或 [{"stem":..,"answer":..}]
        vs = []
        for v in _as_list(q.get("variants")):
            if isinstance(v, str):
                vs.append({"stem": v})
            elif isinstance(v, dict):
                vs.append(v)
        q["variants"] = vs

        if isinstance(q.get("analysis"), str):
            q["analysis"] = {"exam_point": q["analysis"]}
        if q.get("knowledge") is not None:
            q["knowledge"] = _as_list(q["knowledge"])
    return data


# --------------------------------------------------------------------------
# 输入校验
# --------------------------------------------------------------------------

def validate(data: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["输入必须是 JSON 对象"]
    qs = data.get("questions")
    if not isinstance(qs, list) or not qs:
        errs.append("questions 必须是非空数组")
        return errs
    for i, q in enumerate(qs, 1):
        if not str(q.get("stem", "")).strip():
            errs.append(f"第 {i} 题缺少 stem（题干）")
        if not (q.get("solutions") or q.get("answer")):
            errs.append(f"第 {i} 题缺少 solutions 或 answer（必须有解答）")
    return errs


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_project(data: dict, project_dir: Path, *, source_files=None,
                  quiet: bool = True) -> Path:
    """渲染页面并写入 ppt-master 项目；返回项目路径。"""
    import engine

    data = normalize(data)
    errs = validate(data)
    if errs:
        raise ValueError("输入校验失败：\n  - " + "\n  - ".join(errs))

    proj = engine.init_project(project_dir, quiet=quiet)

    # 试卷原图：先拷贝到项目 images/，SVG 里用 images/<name> 引用（渲染前完成）
    images_dir = proj / "images"

    def stage(q_item: dict, key_path: str, key_out: str) -> None:
        src = q_item.get(key_path) or q_item.get(key_out)
        if src and Path(src).is_file():
            images_dir.mkdir(parents=True, exist_ok=True)
            dst = images_dir / Path(src).name
            if not dst.is_file():
                shutil.copy2(src, dst)
            # 引擎按「SVG 所在目录」解析 href，而 SVG 在 svg_output/ 下，
            # 所以必须写成 ../images/xxx.png，且解析后仍在项目内
            q_item[key_out] = f"../images/{dst.name}"
        elif q_item.get(key_out) and not str(q_item[key_out]).startswith("../images/"):
            # 已是项目内相对路径则保持，否则视为不可用
            q_item[key_out] = None

    for q in data.get("questions", []):
        stage(q, "stem_image_path", "stem_image")
        for v in q.get("variants") or []:
            if isinstance(v, dict):
                stage(v, "image_path", "image")

    deck = Deck(data)
    deck.plan()
    pages, anims = deck.build()

    out = proj / "svg_output"
    for f in out.glob("*.svg"):
        f.unlink()
    for name, svg in pages:
        (out / name).write_text(svg, encoding="utf-8")
    (proj / "animations.json").write_text(
        json.dumps(anims, ensure_ascii=False, indent=2), encoding="utf-8")

    if source_files:
        engine.import_sources(proj, [str(s) for s in source_files], quiet=quiet)
    return proj


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="满苏数的练习讲评Skills：生成苏教版小学数学讲评课件")
    ap.add_argument("input", help="题目 JSON 路径")
    ap.add_argument("-o", "--out", default="projects/jiangping", help="输出项目目录")
    ap.add_argument("--export", action="store_true", help="同时导出 PPTX")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="回显引擎完整输出（排错用，默认只打摘要）")
    args = ap.parse_args(argv)
    quiet = not args.verbose

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    proj = build_project(data, Path(args.out), quiet=quiet)
    pages = len(list((proj / "svg_output").glob("*.svg")))
    print(f"[OK] 页面 {pages} 页 → {proj}/svg_output")

    import engine
    s = engine.quality_summary(engine.check_quality(proj, quiet=quiet))
    print(f"[OK] 质量闸 blocking={s['blocking']} error={s['error']} "
          f"warn={s['warn']} / {s['pages']} 页")
    if s["blocking"]:
        raise engine.EngineError(
            f"质量闸有 {s['blocking']} 项阻塞问题，请用 -v 重跑查看明细")
    engine.validate_animations(proj, quiet=quiet)
    if args.export:
        p = engine.export(proj, quiet=quiet)
        print(f"[OK] PPTX：{p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
