"""Opt-in, one-attempt-per-day Responses API fallback with a persisted claim."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import yaml
from content import ROOT, compose, load_lessons, publish, validate


def today() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()


def output(name: str, value: str) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    print(f"{name}={value}")


def claim() -> None:
    date = today()
    ledger = ROOT / ".automation" / f"{date}.json"
    lessons = load_lessons()
    if ledger.exists() or any(x["date"] == date for x in lessons):
        output("claimed", "false")
        print("当天已有文章或保留的生成记录，跳过。")
        return
    queue = yaml.safe_load((ROOT / "data/daily-queue.yml").read_text(encoding="utf-8"))["lessons"]
    known_ids = {x["id"] for x in lessons}
    item = next((x for x in queue if x["id"] not in known_ids), None)
    if item is None:
        output("claimed", "false")
        print("未来文章队列为空，跳过。缺失历史正文不会被自动生成。")
        return
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_MODEL"):
        raise ValueError("请先配置 OPENAI_API_KEY Secret 和 OPENAI_MODEL Variable")
    meta = {k: item[k] for k in ("id", "title", "category", "order", "prerequisites", "next_concepts")}
    meta.update(date=date, source="daily-api")
    validate(meta, "配置验证", f"{date}-{meta['id']}.md")
    if any(x["order"] == meta["order"] for x in lessons):
        raise ValueError("队列的学习顺序已经被使用")
    ledger.parent.mkdir(exist_ok=True)
    with ledger.open("x", encoding="utf-8") as handle:
        json.dump({"date": date, "lesson_id": meta["id"], "state": "reserved", "metadata": meta, "brief": item["brief"]}, handle, ensure_ascii=False, indent=2)
    output("claimed", "true")


def generate() -> None:
    date = today()
    ledger = ROOT / ".automation" / f"{date}.json"
    record = json.loads(ledger.read_text(encoding="utf-8"))
    if record["state"] != "reserved":
        raise ValueError("当天任务不是 reserved 状态")
    # Workflow must push this reservation before spending an API call.
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(ledger.relative_to(ROOT))], cwd=ROOT, capture_output=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(ledger.relative_to(ROOT))], cwd=ROOT, capture_output=True)
    if tracked.returncode or dirty.stdout:
        raise ValueError("生成前必须先提交生成记录；否则可能重复计费")
    meta = record["metadata"]
    if any(x["date"] == date or x["id"] == meta["id"] for x in load_lessons()):
        raise ValueError("文章已存在，停止生成")
    instructions = "你是中文 AI 概念寓言作者。根据指定的新概念写一篇完整、循序渐进的长文。只输出 Markdown 正文，不输出 YAML 或包裹全文的代码围栏。先讲有角色、冲突与转折的完整故事，再解释概念为何出现；逐一补齐前置概念，随后拆解公式中的每个符号，完整手算一个数值例子，连接 AI/OCR 与研究生实验场景。给出故事事物与数学概念的映射表，明确隐喻成立之处与不能机械类比的边界。结尾保留今天真正需要记住的 5 个点和下一步知识网络，说明自然的前置深化与后续概念。使用清楚自然的中文，小段落循序推导，不能用压缩提纲替代完整教学。采用一个一级标题，其余用二三级标题；LaTeX 使用 $ 与 $$，不输出 ChatGPT entity/citation 控件标记。不得编造历史记录，不包含真实个人信息、邮箱、电话、密钥或私人对话。故事不得替代严谨数学解释。"
    payload = {"model": os.environ["OPENAI_MODEL"], "store": False, "max_output_tokens": int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS") or "12000"), "instructions": instructions, "input": json.dumps({"title": meta["title"], "brief": record["brief"], "prerequisites": meta["prerequisites"]}, ensure_ascii=False)}
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, method="POST")
    # No automatic retry after timeout or ambiguous response: the claim remains reserved.
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f"模型 API 返回 HTTP {error.code}；响应正文和密钥未写入日志") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError("模型 API 请求失败或结果不明确；保留 reserved 记录，禁止自动重试") from None
    if result.get("status") != "completed":
        raise ValueError("生成未完整结束，停止发布并保留生成记录")
    body = "\n".join(part["text"] for item in result.get("output", []) if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text")
    if body.lstrip().startswith("```") or len(body.strip()) < 600:
        raise ValueError("生成正文格式或长度不符合要求，停止发布")
    candidate = ROOT / ".private/daily" / f"{date}-{meta['id']}.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(compose(meta, body), encoding="utf-8", newline="")
    path, created = publish(candidate)
    if not created:
        raise ValueError("正文已存在，禁止重复提交")
    record["state"] = "published"
    record.pop("brief", None)
    ledger.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("新文章通过内容协议和隐私模式扫描；正文未输出到日志。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["claim", "generate"])
    args = parser.parse_args()
    try:
        claim() if args.command == "claim" else generate()
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"自动发布停止: {error}\n")
