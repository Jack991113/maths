# maths 本地错题档案

本工具只保存经模型核对过的结构化记录，不做 OCR、判题或自动诊断。先实际读取原图，再把可确认内容传入 JSON；模糊题干保留疑问。图片中的手写过程作为证据长期保留。生成 Word 时使用整理后的题干、规范解法和另绘 PNG，**不得把含手写的 source_images / process_images 嵌入 Word**。

## 位置与命令

在技能目录运行 `python3 scripts/archive.py ...`（Windows 可用安装器选定的 Python 命令）。`--root PATH` 放在子命令前；省略时调用同目录 `paths.data_root()`：优先 `MATHS_DATA_DIR`，否则读取 Codex 目录下 `maths-runtime/data-location.json` 中安装器持久保存的 `data_dir`，缺少位置配置时退回 `CODEX_HOME/maths-data` 或 `~/.codex/maths-data`。

```text
archive.py [--root PATH] init
archive.py [--root PATH] add --file question.json
archive.py [--root PATH] revise --question q_ID --file question.json
archive.py [--root PATH] attempt --question q_ID --file attempt.json
archive.py [--root PATH] annotate --attempt a_ID --file annotation.json
archive.py [--root PATH] list [--topic 一元二次方程]
archive.py [--root PATH] show --question q_ID
archive.py [--root PATH] summary [--topic 一元二次方程]
archive.py [--root PATH] export [--out readable-archive.json]
archive.py [--root PATH] backup --out maths-data-backup.zip
archive.py [--root PATH] restore --from maths-data-backup.zip
archive.py [--root PATH] delete --question q_ID
archive.py [--root PATH] delete --all
```

成功输出 UTF-8 JSON、退出码 0；无效输入或文件错误输出 JSON 到 stderr、退出码 2。已有备份、导出和恢复目标不会被覆盖。`init` 幂等，完全不写 `profile.json`。先调用 `init`，其余读写需要已初始化数据库。新对话先定位数据根，再读取 `profile.json`、`summary` 和有关 `list/show`，不能只凭对话记忆。

数据根中保存：

- `archive.sqlite3`：题目 ID、版本、来源、全部实际作答、分析勘误及其关联。
- `assets/`：复制保存的原始图片，以内容 SHA-256 命名，数据库存相对路径和散列；原上传位置消失后仍可读取。
- `profile.json`：由技能的档案流程维护，本工具只在备份时带上已有文件。

图片不因出卷、修订、复测、关闭对话或重新初始化而删除。程序没有自动清空、过期淘汰或覆盖旧版本功能。

## 题目 JSON

下列是**字段格式示例**，不是用户的真实记录。`source_images` 中填当前机器实际存在的原始图片路径；建议使用绝对路径，不要把示例路径直接传给程序。

```json
{
  "stem": "经阅读原图后确认的完整题干；看不清处明确标注待确认",
  "topics": ["一元二次方程", "因式分解法"],
  "source_images": ["/实际路径/含手写的原图.png"],
  "source_item_key": "原图中第12题",
  "recognition": {
    "status": "needs_confirmation",
    "notes": "注明待确认的具体条件；全部核对后改为 confirmed"
  },
  "source": {
    "type": "user_upload",
    "citation": "用户上传；若真题年份与出处尚未核实，应明确写明"
  },
  "answer": {
    "text": "经独立解题得到的规范解法；尚未解出可留空",
    "verification_status": "unverified",
    "verification_notes": "实际核验步骤；没有核验就不填写已验证结论"
  },
  "notes": "可选备注"
}
```

必填：`stem`、非空 `topics`、`source.type`。有图时 `source_item_key` 必填；`user_upload` 必须提供原图。支持 PNG、JPEG、WEBP、GIF、HEIC/HEIF、TIFF、BMP 后缀；存储工具只验证文件存在且非空，图像能否读取和内容是否真实由读取图片的模型核对。

来源类型：`user_upload`（用户上传）、`original`（原创）、`verified_past_paper`（已核实真题）、`adapted`（变式）、`unverified_reference`（出处待核实）。已核实真题必须有 `citation`，写出年份、试卷标题、题号、可核验链接和实际核验范围。程序不会替模型联网核实此声明。

识别状态：`confirmed` / `needs_confirmation`，默认待确认。答案状态：`unverified` / `verified` / `needs_review`，默认未验证；填 `verified` 必须同时填写答案和实际核验说明。这只是保存核验元数据，不代表数据库本身证明答案正确。

`add` 返回稳定的 `q_...` ID。原图 SHA-256 集合与 `source_item_key` 共同识别一次原题导入：

- 同图同题号再次 `add` 返回 `status: existing`，不改题干、不增版本、不增作答。即使新 JSON 写了不同内容，也保留原记录并提醒使用 `revise`。
- 一张图中的不同题必须用不同且稳定的 `source_item_key`，例如“第12题”“第13题”。不能全写“整页”。不能仅凭图片相同或题干相似合并。
- 同题重新拍照、裁切或换格式可能改变散列。先查找已有记录并确认题目身份，再使用已有 ID `revise`；不能声称能自动识别所有视觉重复。无法确认时保留独立记录并注明疑似重复。
- 无图原创题没有自动去重键；先检索，再新增。生成试卷中的每道题也不必自动混入“学生真实错题”库。

`revise` 接收与 `add` 相同的**完整题目 JSON**，在同一 ID 下追加版本。旧题干、来源、原图仍在历史版本中。读取 `show` 后要修订，可从当前 `question` 取字段，将其 `source_images` 对象数组转换为“数据根 / path”的实际路径数组；不要直接把导出对象作为输入。`show` 返回当前 `question`、全部 `revisions` 和 `attempts`。

## 作答 JSON

**题目导入与实际作答是两次独立操作。** 只有用户图片、过程文字或明确报告证明发生过作答，才调用 `attempt`。上传原题本身不是一次作答。重复上传返回 `existing` 时，先读取已有作答，默认不再调用 `attempt`；只有用户明确表示实际重做，或证据能确认是不同一次作答时才追加。工具每次 `attempt` 都追加事件，不把相同分数当作重复或自动跳过实际复测。

```json
{
  "occurred_at": null,
  "kind": "initial",
  "process_text": "准确转录或概括这次实际作答；学生口头报告也注明来源",
  "process_images": ["/实际路径/本次含手写的原图.png"],
  "result": "unknown",
  "score": null,
  "max_score": null,
  "assistance": "unknown",
  "error_analysis": {
    "status": "unknown",
    "causes": [],
    "evidence": ""
  },
  "linked_attempt_id": null,
  "notes": "可选备注"
}
```

- `process_text` 或 `process_images` 至少一个非空。可以引用与题目同一张原图，内容相同的文件共享存储。
- `occurred_at` 为实际作答时间，例如 `2026-09-12T20:00:00+09:00`；不知道则 `null`。`recorded_at` 由程序单独记录入库时间，不把上传时间冒充考试日期。
- `kind`：`initial` / `correction` / `retest`；`result`：`correct` / `incorrect` / `partial` / `unknown`。
- `score` 与 `max_score` 同时提供或同时留空，须满足 0 ≤ 得分 ≤ 满分，满分 > 0。不知道分值不能补造。满分与 `incorrect/partial`、非满分与 `correct` 会被拒绝。
- `assistance`：`none` / `hint` / `answer_seen` / `unknown`。不知道就保留 `unknown`，不默认独立完成。
- 错因状态：`unknown` / `hypothesis` / `confirmed`。有 `causes` 必须提供 `evidence`；猜测保留 `hypothesis`，不能因只看到题目而声称学生用了某种错解。
- `linked_attempt_id` 可指向本题先前的作答，订正/复测尽可能关联。外题事件或不存在的 ID 会被拒绝；不知道关联对象时留空并说明。
- 默认绑定当前题目版本；补录历史作答时可加 `question_version: 1` 等已有版本号。原作答不会因后来修订题干而改绑版本。

返回稳定的 `a_...` ID。作答事件不能原地覆写；学生实际订正或复测才追加关联作答。若仅补充或更正已发生作答的分析，使用 `annotate --attempt a_ID --file annotation.json`，不会新增实际作答次数，也不改动原始记录。例如首次只能假设错因，核对图片后再确认：

```json
{
  "reason": "重新核对原始作答图片后，确认具体错误位置",
  "changes": {
    "error_analysis": {
      "status": "confirmed",
      "causes": ["漏根"],
      "evidence": "此处填写真实核对结果和可定位的作答依据"
    }
  }
}
```

`reason` 必填。`changes` 只支持 `result`、`score`、`max_score`、`assistance`、`error_analysis`；其中 `error_analysis` 需给出完整对象。合并后的分数和结果仍须一致，不能把 `correct` 与非满分同时保存。每次勘误单独保存 `n_...` ID、时间、依据和字段改动，后续勘误按追加顺序生效。

`show` 的每条作答包括 `attempt`（未覆写的原始记录）、`annotations`（全部勘误）和 `effective_attempt`（合并后有效分析）。分析和出卷以 `effective_attempt` 为准，需要解释变化时回看原始记录与勘误证据。`summary` 按有效正误、提示状态和错因计数，`attempt_count` 不因 `annotate` 增加。作答过程图、原始过程文字、实际发生时间与关联题目版本不通过勘误改写；它们用于追溯原始证据。

## 查询和分析边界

`list --topic` 和 `summary --topic` 精确匹配当前题目的任一 `topics` 标签。入库时使用一致的单元标签，并可另加具体考点标签。`show` 是最终分析依据，可以追溯题目版本、作答、时间和证据。

`summary` 只输出题目数、待确认数、未验证答案数、实际作答事件数、有效正误数量、辅助情况和两类错因事件计数。不输出总体正确率、掌握率或默认能力评分；同题复测是不同事件，分析勘误不是新作答，错因事件计数也不等同于不同错题数。看答案后的订正和独立做对必须分开解释。学生“理解约90%”等自评保留在档案中，不升级为测量值。

## 导出、迁移和删除

`export` 输出可读 JSON；`--out` 保存到一个尚不存在的文件。JSON 包含全部版本和作答，但不嵌入图片二进制。只复制 JSON 不构成完整迁移。

完整迁移：

1. 旧电脑运行 `backup --out ...zip`。工具用 SQLite 一致性快照打包数据库、所有仍被引用的图片、已有 `profile.json`；校验图片 SHA-256。导出的 Word、独立输出文件和 API 密钥不在本备份范围内。
2. 把 ZIP 自行传到另一台电脑，安装同版本技能。选择一个**空的数据目录**，运行 `--root /新目录 restore --from ...zip`。
3. 恢复会检查安全路径、数据库关联和图片散列，全部通过才放入目标目录。非空目录一律拒绝，因此不会覆盖安装器已有的 `profile.json`；必要时恢复到另一新目录，再把 `MATHS_DATA_DIR` 指向它。
4. 在新电脑运行 `--root /新目录 summary` 和 `show --question q_...`，确认题目和原图可读。ID、版本和作答关联保持不变。迁移后使用新目录，无需保留原机器的绝对路径。

备份不是云同步，也不自动持续运行。备份可能包含学生原始手写图片和个人档案，应由用户自行保管。数据库结构版本不兼容时工具报错，不尝试覆盖或悄悄升级。

**只有用户明确要求删除对应题目或清空错题库时，才能调用 `delete`。** 按用户已给出的删除范围执行，不新增不必要确认。`delete --question` 删除该题及其所有版本、作答、分析勘误；共享原图仍被其他题或其作答引用时保留。`delete --all` 清空当前题库及所引用原图，保留 `profile.json`。数据库启用 `secure_delete` 并整理空闲页，但不承诺覆盖 SSD、系统快照或外部文件系统备份。

删除只作用于当前数据根，已另存的 ZIP、JSON、Word 和其他电脑副本不会自动改变。用户要求连备份一起删除时，还须在明确范围内删除那些已知文件，不能把只清空当前数据库说成所有副本均已删除。

## 验证

项目根运行 `python3 -m unittest discover -s tests -p test_archive.py -v`。测试在临时目录覆盖原图持久化、同图同题重复、多题不误合并、历史版本和关联作答、分析从假设改为确认但不增作答、非法输入无损、共享图删除、幂等初始化、可读导出、备份迁移、损坏包和路径穿越拒绝。测试数据不会写入学生真实档案。
