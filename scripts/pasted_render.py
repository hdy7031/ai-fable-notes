"""Display pasted plain text as readable Markdown without changing its source."""
import re


def _heading(line):
    if re.match(r"^(?:每日概念寓言)?今日寓言：", line):
        return "# " + line.removeprefix("每日概念寓言")
    if re.match(r"^[一二三四五六七八九十百]+、", line) or line.startswith(("今天的概念：", "回到", "今天真正需要记住的", "下一步知识网络", "现在视觉知识链")):
        return "## " + line
    if re.match(r"^第[一二三四五六七八九十]+[：:]", line):
        return "### " + line
    return None


def _diagram_line(line):
    stripped = line.strip()
    return bool(
        re.fullmatch(r"[↑↓→←\s]+", line)
        or re.fullmatch(r"(?:x\d*|h\d+|g\d+)(?:\s+(?:x\d*|h\d+|g\d+))+", stripped)
        or re.match(r"^[hg]\d+\s*→\s*x", stripped)
        or stripped in {"原图", "ReLU", "Pooling", "Pool"}
        or re.fullmatch(r"[\d×x]+ Conv", stripped)
        or re.fullmatch(r"(?:Conv|Feature Map)[\w\s×,=().-]*", stripped)
    )


def render_pasted(text):
    lines = text.splitlines()
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.strip() in (r"\[", "$$"):
            end = r"\]" if line.strip() == r"\[" else "$$"
            math = [line]
            i += 1
            while i < len(lines):
                math.append(lines[i])
                i += 1
                if math[-1].strip() == end:
                    break
            blocks.append("\n".join(math))
            continue
        if "\t" in line:
            rows = []
            while i < len(lines) and "\t" in lines[i]:
                rows.append(lines[i].split("\t"))
                i += 1
            width = max(map(len, rows))
            table = ["| " + " | ".join(cell.replace("|", r"\|") for cell in row + [""] * (width - len(row))) + " |" for row in rows]
            table.insert(1, "| " + " | ".join(["---"] * width) + " |")
            blocks.append("\n".join(table))
            continue
        heading = _heading(line)
        if heading:
            blocks.append(heading)
            i += 1
            continue
        if _diagram_line(line):
            end = i
            while end < len(lines) and _diagram_line(lines[end]):
                end += 1
            diagram = lines[i:end]
            if len(diagram) > 1 and any(any(c in row for c in "↑↓→←") for row in diagram):
                blocks.append("```text\n" + "\n".join(diagram) + "\n```")
                i = end
                continue
        # Original one-line paragraphs become separate paragraphs; formulas stay intact.
        blocks.append(line)
        i += 1
    return "\n\n".join(blocks) + "\n"
