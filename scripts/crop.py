#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从试卷原图裁出题目图示。

讲评课件要求"尽量使用试卷原图"。这个脚本负责把原图中的一块裁出来，
存成课件能直接引用的 PNG（自动放大到清晰、可选留白）。

用法：
    # 按原图像素坐标：左,上,宽,高
    python scripts/crop.py 试卷.jpg --box 120,340,520,260 --out 项目/images/q3.png

    # 按百分比（0~1）：左,上,宽,高
    python scripts/crop.py 试卷.jpg --box-pct 0.08,0.45,0.42,0.22 --out 项目/images/q3.png

    # 批量：从一个 JSON 清单裁（[{"src":..,"box":[..],"out":..}]）
    python scripts/crop.py --list cuts.json

    # 一次裁多块（同一张原图，推荐：只调用一次就出完所有题图）
    python scripts/crop.py 试卷.jpg --outdir 项目/images \\
        --cuts "q1=120,340,520,260; q3=700,340,520,200"

    # 手机拍摄的竖图先转正：--rotate 90 / 180 / 270
    python scripts/crop.py 试卷.jpg --rotate 90 --outdir 项目/images \\
        --cuts-pct "q1=0.08,0.45,0.42,0.22"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("[ERR] 需要 Pillow：pip install Pillow")
    raise SystemExit(1)

MIN_EDGE = 320      # 裁出来太小就放大，保证投影清晰
PAD = 8             # 四周留白，避免贴边


def _parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [float(x) for x in str(text).replace("，", ",").split(",")]
    if len(parts) != 4:
        raise ValueError("--box 需要 4 个数：左,上,宽,高")
    return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])


def crop_one(src: Path, box, out: Path, *, pct: bool = False,
             rotate: int | None = None, src_img=None) -> Path:
    img = src_img if src_img is not None else Image.open(src)
    if rotate:
        # 手机 albums 常见侧向拍摄；转正后页 top-bottom 才是对的
        img = img.rotate(-int(rotate), expand=True) if rotate in (90, 180, 270) else img
    W, H = img.size
    if pct:
        x, y, w, h = box
        box = (int(x * W), int(y * H), int(w * W), int(h * H))
    x, y, w, h = box
    # 夹到图像内并留白
    x0 = max(0, x - PAD)
    y0 = max(0, y - PAD)
    x1 = min(W, x + w + PAD)
    y1 = min(H, y + h + PAD)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"裁剪区域落在图外：{box}（图 {W}x{H}）")
    piece = img.crop((x0, y0, x1, y1))

    # 太小就等比放大
    cw, chh = piece.size
    scale = max(1.0, MIN_EDGE / max(cw, chh))
    if scale > 1.0:
        piece = piece.resize((int(cw * scale), int(chh * scale)), Image.LANCZOS)

    out.parent.mkdir(parents=True, exist_ok=True)
    if piece.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", piece.size, (255, 255, 255))
        piece = piece.convert("RGBA")
        bg.paste(piece, mask=piece.split()[-1])
        piece = bg
    else:
        piece = piece.convert("RGB")
    piece.save(out, "PNG")
    print(f"[OK] {out}  ({piece.size[0]}x{piece.size[1]})  ← {src.name} {box}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="满苏数的练习讲评Skills：从试卷原图裁出题目图示")
    ap.add_argument("src", nargs="?", help="原图路径")
    ap.add_argument("--box", help="像素坐标 左,上,宽,高")
    ap.add_argument("--box-pct", dest="box_pct", help="百分比坐标 左,上,宽,高（0~1）")
    ap.add_argument("--out", help="输出 PNG 路径")
    ap.add_argument("--list", dest="list_file", help="批量清单 JSON")
    ap.add_argument("--cuts", dest="cuts",
                    help='一次裁多块："名字=左,上,宽,高; 名字2=左,上,宽,高"')
    ap.add_argument("--cuts-pct", dest="cuts_pct", help="同上，坐标为 0~1 百分比")
    ap.add_argument("--outdir", dest="outdir", help="--cuts 的输出目录")
    ap.add_argument("--rotate", dest="rotate", type=int, default=None,
                    help="先把原图转正的角度：90 / 180 / 270")
    args = ap.parse_args(argv)

    if args.cuts or args.cuts_pct:
        if not args.outdir:
            ap.error("--cuts 需要配合 --outdir")
        outdir = Path(args.outdir)
        raw = args.cuts or args.cuts_pct
        pct = bool(args.cuts_pct)
        base = Path(args.src)
        src_img = Image.open(base)
        if args.rotate:
            src_img = src_img.rotate(-int(args.rotate), expand=True)
        done = 0
        for chunk in str(raw).replace("；", ";").split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, _, nums = chunk.partition("=")
            name, nums = name.strip(), nums.strip()
            if not name or not nums:
                ap.error(f'--cuts 片段无法解析："{chunk}"，应为 名字=左,上,宽,高')
            parts = [float(v) for v in nums.replace("，", ",").split(",")]
            if len(parts) != 4:
                ap.error(f'"{name}" 的裁剪框需要 4 个数')
            crop_one(base, tuple(parts), outdir / f"{name}.png", pct=pct,
                     src_img=src_img)
            done += 1
        print(f"[OK] 共 {done} 张 → {outdir}")
        return 0

    if args.list_file:
        items = json.loads(Path(args.list_file).read_text(encoding="utf-8"))
        for it in items:
            crop_one(Path(it["src"]), tuple(it["box"]), Path(it["out"]),
                     pct=bool(it.get("pct")))
        return 0

    if not args.src or not args.out or not (args.box or args.box_pct):
        ap.error("需要 src + (--box 或 --box-pct) + --out，或用 --list")
    src = Path(args.src)
    if not src.is_file():
        print(f"[ERR] 原图不存在：{src}")
        return 1
    if args.box_pct:
        parts = [float(x) for x in args.box_pct.replace("，", ",").split(",")]
        if len(parts) != 4:
            print("[ERR] --box-pct 需要 4 个数")
            return 1
        crop_one(src, tuple(parts), Path(args.out), pct=True, rotate=args.rotate)
    else:
        crop_one(src, _parse_box(args.box), Path(args.out), rotate=args.rotate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
