"""Publish a reviewed Markdown file without replacing any existing article."""
import argparse
from pathlib import Path

from content import publish

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--reviewed", action="store_true", required=True, help="确认已检查正文与元数据中的隐私和无关内容")
    args = parser.parse_args()
    try:
        path, created = publish(args.input)
        print(f"{'已发布' if created else '相同正文，跳过'}: {path.name}")
    except (ValueError, OSError) as error:
        parser.exit(1, f"发布失败: {error}\n")
