"""One-time backfill from a complete checkout; never run by Pages builds."""
import json
import subprocess

from content import ROOT, load_lessons


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, encoding='utf-8').strip()


if __name__ == '__main__':
    if git('rev-parse', '--is-shallow-repository') != 'false':
        raise SystemExit('需要完整 Git 历史才能恢复首次入库时间')
    path = ROOT / 'data/library-entries.json'
    payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(version=1, entries={})
    for lesson in load_lessons():
        if lesson['id'] in payload['entries']:
            continue
        history = git('log', '--follow', '--diff-filter=A', '--format=%H %cI', '--', 'docs/' + lesson['file'])
        if history:
            commit, timestamp = history.splitlines()[-1].split(' ', 1)
            payload['entries'][lesson['id']] = dict(file=lesson['file'], commit=commit, added_at=timestamp)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"已保留 {len(payload['entries'])} 篇文章的首次入库记录")
