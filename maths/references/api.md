# 硅基流动 API

本入口只调用给定文本，不包含网页产品或完整代理系统。Codex 负责原图理解、档案管理、数学核查和文档交付，API 可用于拟题或给出第二份解答草稿。

## 配置

使用已定位 Python 执行 `scripts/run.py api_client configure`，在本机终端隐藏输入密钥；可加 `--model` 和 `--base-url`。密钥存到数据目录的 `.siliconflow-key`，非密钥配置存 `api.json`。也可设置环境变量 `SILICONFLOW_API_KEY`；不要把真实密钥放入提示词、命令行参数、技能文件或安装包。复制档案备份不自动携带密钥。

默认 Base URL 为 `https://api.siliconflow.cn/v1`，请求路径为 `/chat/completions`。默认模型采用核验日官方接口文档示例 `deepseek-ai/DeepSeek-V4-Flash`；模型名称可随平台变动，请以账户可用模型的完整 ID 为准，用 `--model` 或 `SILICONFLOW_MODEL` 覆盖。不能用 DeepSeek 官方平台的简称直接冒充硅基流动 ID。

## 调用

准备 UTF-8 提示文本，只放本次需要的题干和已确认条件。命令中路径均为本机实际路径：

```text
python scripts/run.py api_client call --prompt-file request.txt --out answer.txt
python scripts/run.py api_client call --prompt-file request.txt --out answer.json --json
python scripts/run.py api_client call --prompt-file request.txt --dry-run
```

`--dry-run` 不联网，只检查本地请求配置。实际请求用 Bearer 鉴权、非流式返回；输出不存在时才写文件，同时产生不含密钥的 `.meta.json` 记录模型及 usage。JSON 模式只校验结果是 JSON 对象，不代表数学正确或符合试卷完整结构；调用文档工具前必须进一步核对字段、题目和评分。

26题及全部详解的结构化内容可能超过一次输出长度。可以按题组分别调用后合并，保持全局题号唯一，再核对总题数、总分与交叉引用；`--max-tokens` 依实际模型限制调整，不把被截断的JSON补猜成完整试卷。

遇到401/403检查密钥和权限，404检查模型或地址，429检查额度或限流。超时不自动重试，避免一次意图产生重复请求；输出截断或没有正文会失败，不交付残缺试卷。模型答案始终标为待数学核查。

当前安装包的接口测试使用模拟响应，不需要或包含真实密钥；真实账户联网调用必须在本机配置后验证。

## 官方依据

核验日期：2026-09-12。

- [硅基流动快速上手](https://docs.siliconflow.cn/docs/userguide/quickstart)：Base URL 与 API Key 接入。
- [创建对话请求](https://docs.siliconflow.cn/docs/api/chat-completions-post)：请求端点、鉴权、model/messages、非流式响应及官方示例模型。
- [JSON 模式](https://docs.siliconflow.cn/docs/userguide/guides/json-mode)：JSON 输出参数及不完整输出处理要求。
