# 满苏数的练习讲评Skills

把一张小学数学卷子，变成一堂能直接上讲台的讲评 PPT。

给它一张试卷照片、一份 Word 或 PDF，它自己读题、圈条件、找易错点、写解法，
产出一个**原生可编辑**的 `.pptx` —— 目录能点、步骤按点击逐条出现、每页右下角能返回目录。
不是图片拼贴，是真正的 PowerPoint 形状与动画。

基于 2022 版义务教育数学课程标准与苏教版 1–6 年级知识脉络组织讲评内容。

## 它能产出什么

```
封面          卷名、年级班级、日期、题数
目录          题号按钮，点击直达（>12 题自动分页）
每题 2~3 页
  ├ 题目首页    题干(+题图) → 点1 标出条件与问题 → 点2 分析四格 → 点3 易错点
  ├ 解决问题页  标好的题干(+题图) → 每点一下出一个步骤 → 答 → 返回目录
  └ 变式页      变式题(可挂自己的图) → 点一下出提示与答案 → 返回目录
结束页
```

标注样式统一画在文字**下方**，不铺底、不遮字：

| 语义 | 样式 |
|---|---|
| 条件 | 蓝色横线 + ①②③ 序号 |
| 问题 | 红色横线 |
| 关键概念 | 黄色横线 |
| 图形名 | 橙色横线 + 上方小示意图 |

## 安装

把整个目录放到 skills 目录下即可（`~/.workbuddy/skills/满苏数的练习讲评Skills`）。
依赖只有 `python-pptx` 和 `Pillow`，安装版自带 `.venv`；新机器上跑一次：

```bash
python scripts/setup_env.py
```

渲染引擎 `vendor/ppt-master` 已随包携带，不需要另外下载。

## 用法

三条命令走完：

```bash
# 1. 批量裁题图（一次调用裁完，别逐题跑）
python scripts/crop.py <卷子原图> --rotate 90 --outdir <项目>/images \
    --cuts "q1=120,340,520,260; q3=700,340,520,200"

# 2. 生成课件（渲染 → 质量闸 → 导出，一条命令）
python scripts/review_deck.py <项目>/questions.json -o <项目目录> --export

# 3. 出一份 HTML 预览
python scripts/preview.py <项目目录>
```

输入 `questions.json` 支持简写 —— `spans` 留空会自动切分标注，`mistakes`、solution 的
`steps` 可以直接写字符串：

```json
{
  "meta": {"title": "练习四讲评", "subtitle": "五年级上册·多边形的面积", "date": "2026-10-25"},
  "questions": [{
    "no": "1①", "type": "计算",
    "stem": "一个平行四边形的底是12厘米，高是8厘米，面积是多少平方厘米？",
    "stem_image_path": "<绝对路径>/fig_q11.png",
    "knowledge": ["平行四边形面积"],
    "mistakes": ["12×10=120，把邻边当成高来乘了"],
    "solutions": [{"name": "方法一", "steps": ["S = a × h", "= 12 × 8", "= 96（平方厘米）"]}],
    "answer": "答：面积是96平方厘米。"
  }]
}
```

完整字段见 `schema/questions.schema.json`，样例见 `assets/sample_questions.json`。

## 目录

```
SKILL.md                 技能入口（流程、硬规则、排错）
scripts/
  review_deck.py         主生成器：questions.json → 页面+动画 → PPTX
  engine.py              引擎封装：挑解释器、质量闸、导出
  svgkit.py              SVG 构造与配色
  crop.py                批量裁题图
  preview.py             HTML 翻页预览
  setup_env.py           建独立 .venv
references/              知识库（按需读单篇）
  01-输入解析规范.md
  02-讲评内容规范.md
  03-知识点与错因速查.md
  04-版面与引擎排错.md
assets/sample_questions.json
schema/questions.schema.json
vendor/ppt-master/       渲染引擎（勿改）
```

## 几条硬规则

- 渲染与导出只走 `vendor/ppt-master`，不绕过质量闸。
- 质量闸必须 `blocking=0 error=0 warn=0`；不达标就改输入 JSON，**不手工改生成的 SVG**。
- 变式题必须先问再做（用户不回答就全不做变式）。
- 题目有图时，题目首页和解决问题页**都要有图**。
- 面向小学生：不学术化，字号 ≥ 18px。

## 致谢

渲染与导出底座来自 [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) v6.7.3（MIT），
随包携带于 `vendor/ppt-master`，其许可证保留在原目录内。

## 许可

本仓库自身代码遵循 MIT，详见 [LICENSE](LICENSE)。
