# AI 寓言笔记

MkDocs + Material 中文学习站点。Markdown 是唯一正文来源，没有后端或数据库。

- 网站：https://hdy7031.github.io/ai-fable-notes/
- 仓库：https://github.com/hdy7031/ai-fable-notes
- 已归档历史正文：**7 篇**。用户提供的粘贴文本补回感受野、池化、参数量与计算量；此前对话补回统计功效、条件概率、贝叶斯定理和全概率公式。完整生成日期未能确认，标为“日期不详”，保留原始月日标签；其余 **12** 个已知概念待补录。
- 从视觉基础开始：https://hdy7031.github.io/ai-fable-notes/lessons/undated-receptive-field/

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\mkdocs.exe serve
```

验收：

```powershell
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\mkdocs.exe build --strict
```

## 内容与发布

新文章写入 `docs/lessons/YYYY-MM-DD-concept-slug.md`，提交到 `main` 后 GitHub Actions 校验、构建和部署。元数据要求和本地历史导入步骤见 [发布协议](docs/guide/publishing.md)。

`scripts/site_hook.py` 从文章元数据自动生成三种索引、导航、待补录清单和前后篇链接。生成文件不提交 Git。每篇文章有稳定 ID；新增文章不会清除原有阅读状态。

完成状态、最近阅读和滚动位置仅存于当前浏览器的 localStorage。使用说明支持手动导出、合并导入进度。不能声称它具备跨设备自动同步。

`.private/`、`exports/`、`imports/`、`conversations.json` 和 ZIP 都被忽略。原始聊天仅供本地读取，公开仓库只应包含审核过的教学 Markdown。不要使用 `git add -f` 绕过隐私目录保护。

## OCR 从零入门

独立课程入口：https://hdy7031.github.io/ai-fable-notes/ocr/ 。课程计划在 `data/ocr-course.yml`，审核后的完整正文在 `docs/ocr/chapters/`。前四章等待完整教学原文，后四章仅列未来规划；状态由实际正文存在与否决定，不能手动假报已发布。

OCR 共享 Markdown、公式、搜索与浏览器进度，使用 `ocr-` 开头的稳定 ID，课程路线与寓言路线分别展示。原有文章组织、URL、学习计划和每日任务不变。多轮导入复用 `scripts/import_chatgpt.py`，见 [OCR 导入说明](docs/guide/ocr-import.md)。私有来源、哈希和选择清单保留在 `.private/ocr/`；不把完整对话提交到公开仓库或 Obsidian。

## 每日自动化状态

- 新 Markdown 提交 → 校验 → 目录更新 → Pages 部署：由 `pages.yml` 负责。
- ChatGPT 定时任务 → 已连接 GitHub 应用写入：接口兼容，但无人值守授权和实际运行待联调。
- GitHub Actions → Responses API → 新文章提交 → Pages：备用方案已实现，默认关闭，需 API Secret、模型变量、未来文章队列和显式启用后真实联调。

Pages 使用 **Settings → Pages → Build and deployment → Source → GitHub Actions**。具体部署状态以 Actions 运行和在线页面为准。
