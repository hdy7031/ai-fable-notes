# OCR 完整教学补录

## 内容边界

课程入口为 [OCR 从零入门](../ocr/index.md)。章节计划在 `data/ocr-course.yml`；已审查的完整教学正文在 `docs/ocr/chapters/`，与每日寓言的 `docs/lessons/` 分开。前四章等待实际教学原文，DBNet、CRNN/CTC、PaddleOCR 实战、文档智能只列后续规划。已有寓言可以辅助理解，不能当作四章已经完整迁移的证据。

一次补录需要当前可访问的**完整消息原文**：优先官方 `conversations.json` 或包含它的 ZIP，可确定有效分支、消息 ID 与时间。只有摘要、分享链接占位、未提供正文的旧会话引用时，保持待补录。MD/TXT 可人工逐条审查后整理为课程 Markdown，但不伪造官方消息 ID；保留原始字节 SHA、来源时间或未知时间、具体消息/行号对应关系以及正式正文 SHA，来源记录留在私有区。

原始文件与附件继续保存在已有本地私有归档（`ChatExports` 的 inbox / processed / _staging / _state，或本站被忽略的 `.private/`）。不要将 ZIP、候选消息、会话标题、ID、选择清单或来源回执提交到公开仓库，也不放进 Obsidian 阅读 Vault。扫描器只读原件，不移动、不删除、不上传附件。ZIP 仅流式读取唯一 `conversations.json`，不代表图片已提取或已审查。

## 最短操作

从网页仓库根目录运行。下面的路径是示例，应替换为已有私有原件的实际路径；不创建公开导出文件。

```powershell
.\.venv\Scripts\python.exe scripts/import_chatgpt.py scan .private/export.zip --title-keywords "OCR,文字识别" --include-user --output .private/ocr/candidates.json
```

标题先过滤，再读取有效分支。`--include-user` 只对本地候选增加学习者追问；默认寓言扫描仍只选助手文本。逐条阅读 `.private/ocr/candidates/` 的实际内容，按章节边界选连续的可见问答。非文本内容/附件会保留 `supported: false` 标记，不能静默丢弃后声称完整；先人工核查原附件并脱敏，再用人工流程处理，不绕过标记。

创建 `.private/ocr/selection.json`，从扫描结果复制实际哈希与消息 ID。以下只是结构示例，不能原样执行；`privacy_reviewed: true` 只能在逐条审查后填写。

```json
{
  "export_sha256": "扫描结果中的完整原件 SHA-256",
  "chapters": [
    {
      "id": "ocr-pixels-rgb",
      "conversation_id": "实际会话 ID",
      "privacy_reviewed": true,
      "messages": [
        {"message_id": "实际问题 ID", "sha256": "该消息的 SHA-256"},
        {"message_id": "实际讲解 ID", "sha256": "该消息的 SHA-256"}
      ]
    }
  ]
}
```

```powershell
.\.venv\Scripts\python.exe scripts/import_chatgpt.py import-course .private/export.zip --selection .private/ocr/selection.json
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\mkdocs.exe build --strict
git status --short
git diff -- docs/ocr/
```

导入保留每条消息的全文、公式、代码、例子与追问，仅加问答分隔标题和空行；不会重写、缩写或自动补充教学。选中范围中间漏消息、分支不明、包含附件、哈希变化、隐私模式命中、同消息复用、顺序冲突、章节已存在都会停止；一批检查失败不留下半批正文。只有真实生成的非空正文才计入“已发布”。同一章分散在多段/多个会话时先在私有区人工核对章节边界与对应关系，当前自动命令只接受同一会话的连续问答，不能跳过关键追问拼成完整章。

日期取本章第一条助手教学消息的实际时间（北京时间），缺少则 `null`，不能填补录当天；每条原始时间、会话/消息 ID、消息 SHA、原件 SHA、正文 SHA 与目标路径保存在 `.private/ocr/receipts/<章节ID>.json`，该回执本身不公开。首版正文路径由日期和稳定 ID 构成，发布后保持不变。阅读进度使用既有 localStorage 键，OCR ID 与寓言 ID 不重叠，导入不会把章节标记为已读。

人工查看 `mkdocs serve`，检查公式、代码、链接、问答边界和前后章；确认全文无个人信息及无关聊天，再**只暂存本次审核后的章节 Markdown**，commit + 普通 push 到 main。原有 Pages workflow 自动部署；无需改定时任务、寓言计划或生成索引。需要新增课程位置时，仅扩展 `data/ocr-course.yml`。

## 脱敏与订正

自动导入要求消息全文与原始哈希一致，不能将改写文本冒充原文。正文含隐私时暂停自动导入：在私有区保存原始 SHA、审查后的版本及逐项删改说明，公开版使用明确的 `[隐私信息已移除]` 标记；人工审查正式文件后走同样的检查与提交流程。公开仓库不得包含敏感原文、原始对话标题/ID或私人路径。自动隐私模式只作辅助，不能代替逐条审核。

发现原文知识性错误时保留可安全发布的原句，紧邻增加 **“订正（日期）：原解释……应为……，理由/依据……”**，在私有记录保存订正说明和正式正文哈希。不无痕修改源消息、不用订正代替缺失正文。代码围栏及公式边界只在现有渲染层兼容处理，不批量改写旧寓言。

## Obsidian 的最小配合

个人知识库仍调用原有 `$knowledge-ingest`，读取同一份实际可访问的私有原件（不是本页示例），合并已有 OCR 主题，记录来源 SHA 与证据等级，核实推送后按原流程归档。只沉淀概念、误区、复习问题和网页章节链接，不复制完整教学。本站回执不能代替 knowledge-ingest 的来源捕获/归档状态；任一侧完成不代表另一侧完成。

## 当前验证边界

初次接入没有取得上述四章的完整教学导出，四章保持待补录，零历史正文迁移。隔离合成消息只用于检查哈希、连续问答、拒绝附件/隐私和不覆盖行为，不能算真实课程导入验收。真实源文件到位后，还需逐条隐私审查、完整章节导入及页面核验。
