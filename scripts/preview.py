#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 svg_output/ 里的页面排成一个可翻页的 HTML 预览，供教师投屏核对版面。

用法：
    python scripts/preview.py <project_path> [-o preview.html]
"""

from __future__ import annotations

import argparse
from pathlib import Path

HEAD = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>满苏数的练习讲评课件 · 预览</title>
<style>
  body{margin:0;background:#1b2027;font-family:"Microsoft YaHei",sans-serif;color:#e8ecf1}
  .bar{position:fixed;top:0;left:0;right:0;height:52px;background:#11151b;display:flex;
       align-items:center;gap:12px;padding:0 16px;z-index:9}
  .bar b{font-size:15px}
  .bar button{background:#2f80ed;color:#fff;border:0;border-radius:8px;padding:7px 14px;
       font-size:14px;cursor:pointer}
  .bar span{font-size:14px;opacity:.8}
  .stage{padding:66px 0 40px;display:flex;justify-content:center}
  .page{width:min(96vw,1280px);aspect-ratio:16/9;background:#fff;border-radius:12px;
        overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5)}
  .page svg{width:100%;height:100%;display:block}
  .hidden{display:none}
</style></head><body>
<div class="bar">
  <b>讲评课件预览</b>
  <button onclick="go(-1)">上一页</button>
  <button onclick="go(1)">下一页</button>
  <span id="ind"></span>
  <span style="opacity:.6">← → 方向键翻页</span>
</div><div class="stage">
"""

TAIL = """
</div>
<script>
const pages=[...document.querySelectorAll('.page')];
let i=0;
function show(n){i=Math.max(0,Math.min(pages.length-1,n));
  pages.forEach((p,k)=>p.classList.toggle('hidden',k!==i));
  document.getElementById('ind').textContent=(i+1)+' / '+pages.length;}
function go(d){show(i+d);}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight')go(1); if(e.key==='ArrowLeft')go(-1);});
show(0);
</script></body></html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="满苏数的练习讲评Skills：生成讲评课件 HTML 预览")
    ap.add_argument("project", help="ppt-master 项目目录")
    ap.add_argument("-o", "--out", default=None, help="输出 HTML（默认写在项目根）")
    args = ap.parse_args(argv)

    proj = Path(args.project).resolve()
    src = proj / "svg_output"
    files = sorted(src.glob("*.svg"))
    if not files:
        print(f"[ERR] 没有页面：{src}")
        return 1
    out = Path(args.out) if args.out else proj / "preview.html"

    # SVG 内联进 HTML 后，相对路径按 HTML 所在目录（项目根）解析；
    # 页面里写的 ../images/ 是相对 svg_output/ 的，这里必须改回 images/。
    def _inline(f: Path) -> str:
        return f.read_text(encoding="utf-8").replace('"../images/', '"images/')

    body = "".join(f'<div class="page{" " if i == 0 else " hidden"}" '
                   f'data-name="{f.name}">{_inline(f)}</div>'
                   for i, f in enumerate(files))
    out.write_text(HEAD + body + TAIL, encoding="utf-8")
    print(f"[OK] 预览：{out}（{len(files)} 页）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
