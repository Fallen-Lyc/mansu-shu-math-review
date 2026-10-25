---
name: 满苏数的练习讲评Skills
description: >
  「满苏数的练习讲评Skills」——苏教版小学数学试卷/习题讲评课件生成技能。当用户发来
  图片型、Word 型或 PDF 型的小学数学试卷、练习卷、作业题、错题，要求做「讲评」
  「讲评课件」「评讲」「试卷分析课」「错题讲评」「习题讲解 PPT/PPTX/课件」时使用。
  自主解析题目内容，产出可直接在 PowerPoint 里点击播放的原生可编辑讲评课件：
  封面 → 可点击目录 → 每题「找条件与问题（动画标注）→ 分析 → 易错点 → 解决问题
  （逐步动画，有图必有图）→ 变式」。也用于「把这张卷子做成讲评课件」「讲一下这几道题」
  等表述。基于 2022 版义务教育数学课程标准与苏教版 1–6 年级知识点脉络组织讲评内容。
metadata:
  version: "1.2.0"
  engine: "ppt-master 6.7.3 (MIT, hugohe3/ppt-master) — 随包自带 vendor/"
  canvas: "PPT 16:9 (1280x720)"
---

# 满苏数的练习讲评课件

把一张卷子，变成一堂能直接上讲台的讲评课。

## 1. 硬规则（违反即失败）

| # | 规则 |
|---|---|
| 1 | 渲染与导出只能走随包引擎 `vendor/ppt-master`；不许另写一套导出，不许绕过质量闸 |
| 2 | **路径全部绝对化**：`<SKILL_DIR>` 是本文件所在目录的绝对路径，项目路径也传绝对路径（相对路径会报 `No SVG files found`） |
| 3 | 质量闸必须 `blocking=0 error=0`；达不到就改输入 JSON，**不许手工改生成的 SVG** |
| 4 | **变式题必须先问再做**（Step 4），用户不回答就全部不做变式，并在交付说明里写明 |
| 5 | **图示优先用试卷原图**；有图时题目首页与解决问题页都显示该图 |
| 6 | 一道题最多两种方法；综合算式必须脱式 |
| 7 | 面向小学生：不学术化，字号 ≥ 18px，配色明亮；颜色语义固定（蓝=条件，红=问题，绿=解答） |

## 2. 目录

```
<SKILL_DIR>/
├── scripts/review_deck.py   主生成器：questions.json → 页面+动画 → PPTX（一条命令）
├── scripts/{engine,svgkit,crop,preview}.py   引擎封装 / SVG 构造 / 批量裁图 / HTML 预览
├── references/              知识库（按需读单个文件，见 §6）
├── assets/sample_questions.json   输入样例
├── schema/questions.schema.json   数据模型
└── vendor/ppt-master/skills/ppt-master/      渲染引擎（勿改）
```

脚本自动挑装了 python-pptx + Pillow 的解释器（skill `.venv` → 上级 `.venv` → 当前 → 系统）。
新机器上先跑一次 `python <SKILL_DIR>/scripts/setup_env.py` 建独立 `.venv`；安装版已自带。

## 3. 工作流（命令只有 3 条）

**Step 1 · 拿到题目内容**（卷图只完整读一次）
图片卷 → 视觉读题一次读完所有题，同时记下每张图在卷上的位置；
Word/PDF → `python <SKILL_DIR>/../vendor/ppt-master/skills/ppt-master/scripts/source_to_md.py <文件>`；
粘贴文本 → 直接用。

**Step 2 · 批量裁图**（一次调用出完所有题图，别反复调用）
```bash
python <SKILL_DIR>/scripts/crop.py <原图> --rotate 90 --outdir <项目>/images \
    --cuts "q1=120,340,520,260; q3=700,340,520,200"     # 拿不准像素就用 --cuts-pct 给百分比
```

**Step 3 · 写成 questions.json**（放 `projects/<卷子名>/questions.json`）
支持简写：不写 `spans`（脚本自动切分）、`mistakes` 写字符串、`steps` 写算式字符串数组。最小一份：

```json
{
  "meta": {"title": "练习四讲评", "subtitle": "五年级上册·多边形的面积", "date": "2026-10-25"},
  "questions": [{
    "no": "1①", "type": "计算",
    "stem": "一个平行四边形的底是12厘米，高是8厘米，面积是多少平方厘米？",
    "stem_image_path": "<绝对路径>/fig_q11.png",
    "knowledge": ["平行四边形面积"],
    "analysis": {"exam_point": "用底×高求面积", "key_conditions": "底12厘米、高8厘米是必须用的",
                 "relation": "平行四边形面积 = 底 × 高", "quantity_relation": "S = ah"},
    "mistakes": ["12×10=120，把邻边当成高来乘了"],
    "solutions": [{"name": "方法一", "steps": ["S = a × h", "= 12 × 8", "= 96（平方厘米）"]}],
    "answer": "答：面积是96平方厘米。"
  }]
}
```
内容怎么写：**必读** `references/02-讲评内容规范.md`。

**Step 4 · ⛔ 停下来问用户一次**（三件事一起问，不要分多次）
① 哪些题要变式（必须问，给题号清单让用户勾）② 封面信息（卷名/年级班级/日期，没说就合理推断）
③ 讲评范围（默认全卷）。用户不回答 → 不做变式。

**Step 5 · 生成并交付**
```bash
python <SKILL_DIR>/scripts/review_deck.py <项目>/questions.json -o <项目目录> --export
python <SKILL_DIR>/scripts/preview.py <项目目录>
```
一条命令内部串行：排页序 → 渲染 SVG → 写 `animations.json` → 质量闸 → 动画校验 → 导出 PPTX。
默认只输出三行摘要（排错加 `-v`）。失败时报错已裁剪关键行，按报错改输入 JSON。
把 `exports/*.pptx` 与 `preview.html` 一起交付，并说明：卷名、题数、页数、哪些题有变式、
怎么点（题目首页点 3 下：标注 → 分析 → 易错点；解题页点一下出一步；每页右下角"返回目录"）。

## 4. 课件编排（生成器固定）

```
1          封面        卷名、年级班级、日期、题数
2（可多页） 目录        题号按钮，点击直达；>12 题自动分页
每题 2~3 页
  ├ 题目首页   题干(+题图) →点1：条件与问题一次性标出 →点2：分析四格 →点3：易错点
  ├ 解决问题页 标好画的题干(+题图) →每点一下出一个步骤 →答 →返回目录
  └ 变式页     变式题(可挂自己的图) →点一下出提示与答案 →返回目录
末页        结束页
```
动画是点击触发的原生动画（标注层 `entrance_appear`，其余 `entrance_fade`）；
deck 级默认 `none`，未列出的单元绝不动。
**标注样式**（都画在文字下方，不铺底不遮字）：条件=蓝横线+①②③，问题=红横线，
关键概念=黄横线，图形名=橙横线+上方小图形示意。

## 5. 排错速查

| 现象 | 原因 / 处理 |
|---|---|
| `No SVG files found` | 用了相对路径 → 传绝对路径 |
| bounds overlaps | 两个顶层组几何重叠 → 覆盖层加 `role="decoration"`；图片要和所在卡片同一组 |
| `exceeds <g> data-pptx-bounds` | 文字超界 → 缩短该格文字（分析四格限 30 字）或缩短步骤行 |
| `animations.json references missing slide` | slide key 必须是文件名主干（带序号前缀、不带 .svg） |
| 预览页看不到图 | 重跑一次 `preview.py`（它会把 SVG 里的图片路径改成预览可用的相对路径） |
| 图片被判 corrupt | 解释器缺 Pillow → 脚本会自动挑带 Pillow 的解释器，必要时跑 `setup_env.py` |

## 6. 参考文档（按需读单个文件，不要一次全读）

| 文件 | 什么时候读 |
|---|---|
| `references/01-输入解析规范.md` | 解析图片/PDF/Word 卷时 |
| `references/02-讲评内容规范.md` | **写每题讲评内容时必读** |
| `references/03-知识点与错因速查.md` | 判年段、写数量关系公式、写易错点时 |
| `references/04-版面与引擎排错.md` | 调配色版面、手写 SVG、直接调引擎脚本时 |

## 7. 省时省调用的做法

- 卷图**只读一次**，读的时候就把所有题图的位置一起记下来。
- 裁图、生成、预览**各一次调用**，不要逐题反复跑命令。
- JSON 用简写（`spans` 留空自动切、串式 `mistakes`/`steps`），不写冗余字段。
- 命令默认静默，只有三行摘要；要看完整引擎输出才加 `-v`。
- 让生成器自己挑解释器，别手动指定 python（除非排错）。
