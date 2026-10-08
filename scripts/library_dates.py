"""Library timestamps, kept separate from original article metadata."""
import datetime as dt
import json
import re

from content import ROOT


def load_entry_index(root=ROOT):
    payload = json.loads((root / 'data/library-entries.json').read_text(encoding='utf-8'))
    if payload.get('version') != 1 or not isinstance(payload.get('entries'), dict):
        raise ValueError('入库索引格式无效')
    for entry in payload['entries'].values():
        if not re.fullmatch(r'[0-9a-f]{40}', entry['commit']):
            raise ValueError('入库索引缺少可核验的提交')
        timestamp = dt.datetime.fromisoformat(entry['added_at'])
        if timestamp.tzinfo is None or not entry['file'].startswith('lessons/'):
            raise ValueError('入库索引必须包含时区和文章路径')
    return payload['entries']


def library_dates(lessons, root=ROOT):
    entries = load_entry_index(root)
    dates = {}
    for lesson in lessons:
        entry = entries.get(lesson['id'])
        if entry:
            if entry['file'] != lesson['file']:
                raise ValueError(f"入库索引路径不匹配: {lesson['id']}")
            timestamp, label = entry['added_at'], '入库'
        elif lesson['date']:
            # Daily publishing supplies a real date; no Git history or manual index update needed.
            timestamp, label = lesson['date'] + 'T00:00:00+08:00', '发布'
        else:
            continue
        day = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        dates[lesson['id']] = dict(timestamp=timestamp, day=day.isoformat(), label=label)
    return dates
