# 发布与历史导入

## 一篇文章，就是一个 Markdown 文件

公开正文唯一来源是 `docs/lessons/` 中的 Markdown 文件。推荐路径：

```text
docs/lessons/YYYY-MM-DD-concept-slug.md
```

元数据示例（正文仅为协议占位，不会作为历史文章发布）：

```yaml
---
id: softmax
title: Softmax：把分数变成概率
date: '2026-10-09'
category: training
order: 200
prerequisites: [relu]
next_concepts: []
source: manual
---
```

在 front matter 后放入同一篇完整正文，包括故事、解释和原始公式。`id` 是进度标识，发布后保持不变；日期和文件名共同形成永久链接，也应保持不变。`order` 是全站唯一正整数，可在已有顺序间插入新章节。`category` 对应 `cnn`、`training`、`statistics` 或 `probability`；新增领域时先扩展 `data/learning-plan.yml`。

前置与后续概念使用 ID 数组；可以指向学习计划中尚未补录的概念，网站会标注“待补录”，不会生成空文章链接。文章创建后，学习路径、分类、归档和搜索都会在构建时更新。目录文件不用手工维护。

历史记录没有可信时间戳时，使用 `date: null` 和 `docs/lessons/undated-concept-slug.md`，归入“日期不详”。不能用导入当天替代原始日期。

## 本地发布

```powershell
.\.venv\Scripts\python.exe scripts/publish.py .private/reviewed-article.md --reviewed
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\mkdocs.exe build --strict
git add docs/lessons/
git commit -m "Publish a new AI fable"
git push origin main
```

`--reviewed` 表示你已经检查隐私与无关内容。脚本还有高置信度隐私模式检查，但不能代替人工审核。相同文件重试不做改动；已有正文不同、重复 ID 或顺序冲突会停止，不会覆盖原文。

## ChatGPT 历史导入

支持官方导出的 `conversations.json` 或包含它的 ZIP，全部在本地读取。把文件放到 `.private/` 或仓库外；不要上传到公开 GitHub，也不要把整个导出交给 Actions。

1. 运行扫描，将有效对话分支中的纯文本助手消息提取到 `.private/candidates/`。用户消息、隐藏消息、工具消息和非文本附件不会自动发布。
2. 在本地逐篇阅读候选全文，挑出完整教学文章。确认无个人信息和无关对话后，创建 `.private/selection.json`。
3. 明确给出消息 ID、全文 SHA-256、标题、概念 ID、分类与顺序。工具不按关键词猜测哪一条应该公开。
4. 导入只读取明确选择的消息，保留完整正文和公式。日期来自该助手消息的时间戳（北京时间）；没有时间戳时保持未知。同一对话内的章节顺序必须与消息顺序一致。

```powershell
.\.venv\Scripts\python.exe scripts/import_chatgpt.py scan .private/export.zip
.\.venv\Scripts\python.exe scripts/import_chatgpt.py import .private/export.zip --selection .private/selection.json
```

筛选清单结构：

```json
{
  "articles": [
    {
      "conversation_id": "从本地 candidates.json 复制",
      "message_id": "从本地 candidates.json 复制",
      "sha256": "从本地 candidates.json 复制完整摘要",
      "privacy_reviewed": true,
      "id": "receptive-field",
      "title": "填写实际文章标题",
      "category": "cnn",
      "order": 10,
      "prerequisites": [],
      "next_concepts": ["pooling"]
    }
  ]
}
```

扫描结果和清单包含私人对话定位信息，仅保留在 `.private/`。导入不会把对话标题、对话 ID、用户消息或原始导出写入公开正文。不能完整提取的多模态内容需要人工补录；不得丢弃附件后声称导入完整。若原文夹带隐私，应先人工处理，并明确标注删改来源，再通过本地发布接口发布。

## ChatGPT 已连接 GitHub 应用

接口只需要向仓库 `hdy7031/ai-fable-notes` 写入一个新 Markdown 文件，不需要运行脚本或写目录索引。建议先创建分支或 PR，由构建检查确认元数据、链接和隐私模式检查通过，再合入 `main`。直接写入 `main` 也会触发构建；错误文章会阻止新部署。

现有定时任务应保留原来生成的完整正文，把同一正文附带上述 front matter 后写入新文件。不要重新概括，不要在同一天创建第二篇，也不要修改已存在的文章。

**待真实联调：** ChatGPT 定时任务能否在无人值守时调用 GitHub 文件写入、是否覆盖该仓库、是否具有分支/提交权限，以及交互授权是否必需，必须用实际定时任务验证。本项目没有把这条链路标记为成功，也没有新增 ChatGPT 定时任务。

## GitHub Actions + 模型 API 替代方案

备用 workflow 为 `.github/workflows/daily-api.yml`，默认关闭。历史缺失正文不会被它补造；它只消费 `data/daily-queue.yml` 中明确配置的**未来新文章**。

在仓库 **Settings → Secrets and variables → Actions** 配置：

- Secret `OPENAI_API_KEY`：有效的 OpenAI API Key，有独立 API 额度。
- Variable `OPENAI_MODEL`：你有权限使用且支持 Responses API 的模型 ID。
- Variable `DAILY_API_ENABLED`：设置为 `true` 才启用生成。
- 可选 Variable `OPENAI_MAX_OUTPUT_TOKENS`：长文输出上限，默认 `12000`；需符合所选模型限制。

先在队列添加一篇未来文章；示例：

```yaml
lessons:
  - id: softmax
    title: Softmax：把分数变成概率
    category: training
    order: 200
    prerequisites: [relu]
    next_concepts: []
    brief: 用一个完整寓言解释归一化指数函数，给出公式、数值稳定性、适用边界和自测。
```

调度为北京时间每天 08:20，GitHub 可能延迟，也可能暂停长期无活动仓库的定时运行。支持 Actions 页面手动运行。用仓库机器人 `GITHUB_TOKEN` 提交和部署；若仓库规则保护 `main`，需允许该机器人写入或改为人工 PR 流程。

生成前先提交 `.automation/YYYY-MM-DD.json` 的日期预留记录，预留 push 成功后才调用模型。当天已有文章或预留记录时跳过；并发任务串行；不存在自动网络重试。返回不完整、隐私模式检查失败或构建失败时停止，保留预留记录，不能覆盖已有正文。失败后的重新生成需要人工确认计费和内容状态，再处理预留记录，不能盲目删除记录重跑。

模型只返回新文章的 Markdown 正文，元数据由队列确定。API Key 只从 Actions Secret 注入请求，不写入代码、正文或日志；API 响应正文也不会打印。模型 API 使用 `store: false`。[Responses API 官方参考](https://developers.openai.com/api/reference/resources/responses/methods/create)。

未来正文的默认节奏按现有寓言设置：完整故事 → 概念出现的原因 → 前置概念 → 公式符号与完整手算 → AI/OCR 场景 → 隐喻映射和边界 → 5 个记忆点 → 下一步知识网络。发布已有 ChatGPT 正文时仍直接使用原文，不用这个生成接口重新写一遍。

机器人提交不会触发另一个 `push` workflow，因此备用 workflow 自己上传 Pages 构建产物并部署。当前没有配置 API Secret、模型和生成队列，**真实模型生成及自动提交链路尚未验证**。
