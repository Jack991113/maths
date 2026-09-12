# Word 与数学配图输出

`build_documents.py` 只排版已核验的内容，不负责 OCR、原创出题、核实真题或判断学生错因。这些工作由调用本技能的模型先完成；如果调用外部 API，返回内容同样必须审核。

## 运行接口

使用安装器提供的 Python 启动方式，或已安装 python-docx 与 Pillow 的 Python 3.10+：

```sh
python scripts/run.py build_documents --input paper.json --out-dir output/run-id --mode paper
python scripts/run.py build_documents --input mistakes.json --out-dir output/run-id --mode mistakes
```

每次使用新的运行目录，避免覆盖历史成品。`paper` 输出同一份 Word，前半为题目，后半为答案、详细解析、解答题分步得分点。`mistakes` 输出错题总结 Word。PNG 同时嵌入 Word 和保存到 `figures/`，manifest 记录文件与题号；manifest 初始状态不是质量验收通过。

## 出卷 JSON

完整可运行例见 `assets/example-paper.json`。该例是自拟的 26 题、140 分、90 分钟原创训练规格，题型分配为 8 选择、10 填空、8 解答；不能声称它就是徐州官方题型数量、考试时间或难度标定。

顶层字段：

- `title`、`topic`：具体标题与知识范围。
- `question_count`、`total_points`、`minutes`：通常为 26、140、90。
- `notice`：准确说明原创、变式或核实的题源；演示要说明没有个人诊断依据。
- `sections`：按选择、填空、解答排序的数组。每节有 `title`、`kind`、`questions`；`page_before: true` 可以另起一页。

每道题：

```json
{
  "id": 1,
  "points": 3,
  "stem": [["反比例函数 ", {"math": ["y=", {"frac": ["k", "x"]}]}, " 经过点（2，3），求 k。"]],
  "answer": [{"math": "k=6"}],
  "solution": [["由 ", {"math": "k=xy=2×3=6"}, "，得 k=6。"]],
  "scoring": [{"points": 3, "text": "写出 k=6。"}],
  "source": {"kind": "original", "label": "maths 原创题"},
  "space_lines": 2
}
```

`stem` 和 `solution` 都是段落数组。`options` 是恰好 4 个富文本段落，按 A 至 D 排列。`space_lines` 是答题留白行数，每行 18 磅；按题目思考量调整。`paper_page_before`、`answer_page_before` 可控制分页。不要为了压页数挤掉必要的作答空间。题干、选项、配图设为相邻段落保持同页；长题仍须渲染检查。

出卷校验要求题号从 1 连续、题数匹配、各题分值之和等于总分、每题得分点相加等于该题分值。单一得分点的选择和填空题在答案题头显示总分，不重复印相同的评分说明。校验不等于答案正确：每题还须独立验算，检验定义域、等号能否取到、几何存在性、多解漏解、选项唯一性、单位和数据条件。

`source.kind` 只能是 `original`、`variant`、`user_upload`、`verified_past_paper`；最后一种必须附可追溯 `reference`。变式附原错题记录标识。脚本不联网核实题源，标注真实性由模型负责。

## 原生 Word 数学公式

字符串是普通正文。一个富文本段落可以是字符串与 `{"math": ...}` 混合的数组。数学表达式可为文字、表达式数组或以下树结构，直接输出可编辑 OMML，不用普通 `/` 冒充分式。

| 表达 | JSON |
| --- | --- |
| 分式 | `{"frac":["a","b"]}` |
| 上标 | `{"sup":["x","2"]}` |
| 下标 | `{"sub":["x","1"]}` |
| 平方根 | `{"sqrt":"5"}` |
| 组合 | `["y=", {"frac":["6","x"]}]` |
| 分数的幂 | `{"sup":[["(",{"frac":["1","2"]},")"],"−1"]}` |

树可嵌套。小数、负号、等式、区间可放入数学字符串。复杂大括号、矩阵、几何特殊符号不能凭空声称已支持：选择已有 OMML 路径扩展后渲染验证，或在明确不要求可编辑时按 documents 技能使用高分辨率公式 PNG 回退。坐标与短公式优先放在同一个 math 节点，避免分裂到两行。

## PNG 图形

`figure` 支持以下确定性坐标结构：

```json
{
  "bounds": [-5, 5, -5, 6],
  "axes": true,
  "curves": [
    {"family": "reciprocal", "k": 6},
    {"family": "linear", "a": 1, "b": 1}
  ],
  "points": [{"xy": [2, 3], "label": "A", "offset": [15, 10]}],
  "segments": [{"a": [0, 0], "b": [2, 3], "dash": true}]
}
```

还支持 `quadratic`（`a,b,c`）、`circles`（`center,radius`）、`right_angles`（`vertex,u,v,size`）及独立 `labels`（`xy,text,offset`）。`offset` 是渲染画布的像素偏移；用于防止标签与线条重叠，不能改变点的位置。图形按 x、y 等比例坐标渲染，PNG 至少 1400 像素宽并标注 300 dpi。反比例函数在 x=0 处断开，禁止跨渐近线连成一条线。当前文字标注以英文字母、数字为主。

每题可设置 `figure_width_mm`，建议 60 至 90 毫米，并写 `figure_alt`。通过 `MATHS_FIGURE_FONT` 指定实际存在的字体文件；否则依次检测 macOS、Windows、Linux 的本地衬线字体。`figure:{"path":"relative-diagram.png"}` 可引用预先核验、重新绘制的 PNG，路径相对于输入 JSON；不得把学生手写截图当作错题总结的重绘配图。

绘图器不会自动证明几何关系。模型必须验证曲线参数、交点、长度、垂直或平行关系、切点和活动点范围；本技能禁止用生成式 AI 画图代替精确数学配图。

## 错题总结 JSON

可复用出卷 JSON 的 `sections`，也可用更小的顶层 `questions` 数组。错题总结不要求知道原题分数，不知道时省略 `points`，不能虚构分值。每题至少有唯一 `id`、`stem`、已核验 `solution`；有图时按上述规则提供。示例：

```json
{
  "title": "反比例函数错题总结",
  "topic": "反比例函数",
  "questions": [
    {"id": 1, "stem": ["这里放已核对的原题文字"], "solution": ["这里放完整正确解法"]}
  ],
  "mistake_records": [
    {
      "question_id": 1,
      "record_id": "实际的错题及作答记录标识",
      "topic": "实际知识点",
      "evidence": "实际作答记录标识、日期及能支持结论的步骤",
      "pitfalls": ["有证据支持的易错点"],
      "cause": ["错误发生的具体位置；推测须标待确认"],
      "improvement": ["对应的改进步骤与检查办法"]
    }
  ]
}
```

正文顺序为原题、易错点、出错原因、改善方法、规范解法。引用原始记录，但不嵌入手写过程截图。真实原因不明则明写证据不足；没有记录时不能输出虚构的个人总结。`mistakes_title`、`mistakes_notice` 可覆盖标题和开头说明。演示题必须说明没有真实学生作答，并保存在演示目录。脚本只根据引用题号生成该总结真正用到的配图。

## 渲染验收和字体

在 Codex 中先调用 `load_workspace_dependencies` 获取权威 Node、Python 路径，读取已安装 documents 技能。查找该技能实际目录中的 `container_tools/mark_artifact_operation_started.mjs` 和 `render_docx.py`；不要把开发机器的绝对路径写死进可移植流程。首次创建成品前按 documents 规范成功执行一次 mark；不是每次修订都重复标记。

用加载的 bundled Python 调用渲染器，使用其 bundled LibreOffice，不能因为失败而改用用户桌面 LibreOffice：

```sh
"<bundled-python>" "<documents-skill>/render_docx.py" "<output.docx>" --output_dir "<qa-folder>" --emit_pdf
```

默认中文字体按平台为 macOS 的 Songti SC、Windows 的 SimSun、Linux 的 Noto Serif CJK SC。可用 `MATHS_CJK_FONT` 设置当前机器已安装的中文字体族名。脚本会清除主题字体覆盖，标题和正文都是黑色，并去除模板默认的标题下边框。不把字体文件复制进分发包。

macOS 的 bundled headless LibreOffice 可能未扫描系统中文字体，症状是英文和公式正常、中文消失或成方框。这时用本次运行 QA 目录下的临时 `fonts.conf`，设置 `FONTCONFIG_FILE` 后重渲染。内容应指向当前机器真实存在的目录：

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/System/Library/Fonts</dir>
  <dir>/System/Library/Fonts/Supplemental</dir>
  <dir>本次依赖运行时的LibreOffice字体目录</dir>
  <cachedir>本次QA目录下的字体缓存目录</cachedir>
</fontconfig>
```

上述系统目录仅适用于 macOS；Windows 使用实际系统字体目录，Linux 使用实际 CJK 字体目录。目录值在写 XML 时须转义。`SAL_FONTPATH` 本身不能保证解决这类字体缺失。不要修改托管运行时或覆盖用户字体配置；用当前渲染进程的局部环境变量。

必须逐页打开最新生成的 PNG 检查：中文全可读、分式与根号正确、下标和负号无缺失、标题无彩线、所有图标签清楚、图与题干同页、作答空间足够、答案从题目之后新页开始、无孤立标题和空白尾页。有任何修订就重渲染并重新检查受影响的全部页面。Word 页图及 PDF 是内部 QA；用户交付 Word 和题目配图 PNG，除非另有要求不发 QA 中间文件。新机器和新字体均应重做这一验收，不能用 macOS 测试结果宣称 Windows 已经实测。

导出默认拒绝非空输出目录，以保护已生成的历史卷和配图。只有在明确重建同一次运行的 QA 成品时，才能加 `--overwrite`；正式下一次出卷必须换新的运行目录。`stem` 和 `solution` 若误传成字符串而非段落数组，会直接报错，不按字符拆分排版。

选项可设 `options_columns: 2` 或 `4`。数值和短公式通常排 4 列，较长文字或图形选项排 2 列；由渲染结果确认没有越过列宽。当前示例包含 5 张精确配图，覆盖等腰三角形、反比例函数、圆的切线、正方形综合和二次函数。示例第 17、18、25 题包含参数正根、距离与反比例关系、几何与面积方程的综合运用；难度是教师设计判断，不是经学生样本测量得到的难度系数。
