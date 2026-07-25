#!/usr/bin/env python3
"""프로젝트 태스크·마일스톤 로컬 트래커 (Jira 없이도 동작). data/project.md 에 저장.
Jira/Linear가 커넥터로 연결돼 있으면 그쪽을 우선 쓰되, 미연결 환경을 위한 로컬 백본.

  project.py --add "슬랙 연동 개발" --owner 이개발 --due 2026-08-05 --deps "설계확정"
  project.py --list
  project.py --status                       # 지연/임박/블로커 경보
  project.py --done "슬랙 연동"              # 부분일치로 완료 처리
  project.py --block "슬랙 연동" --reason "API 정책 확인 대기"
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR

PROJECT_PATH = os.path.join(DATA_DIR, "project.md")
HEADER = "# 프로젝트 태스크·마일스톤\n\n"
DUE_RE = re.compile(r"마감:(\d{4}-\d{2}-\d{2})")


def _read():
    try:
        with open(PROJECT_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _write(text):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROJECT_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def _task_lines(text):
    return [l for l in text.splitlines() if l.strip().startswith("- [")]


def add(task, owner, due, deps):
    text = _read() or HEADER
    parts = [f"- [ ] {task}"]
    if owner:
        parts.append(f"담당:{owner}")
    if due:
        parts.append(f"마감:{due}")
    if deps:
        parts.append(f"의존:{deps}")
    _write(text.rstrip("\n") + "\n" + " · ".join(parts) + "\n")
    print(f"[추가] {task}")


def _update_first(sub, transform):
    text = _read()
    if not text:
        raise SystemExit("프로젝트 파일이 없습니다. 먼저 --add 하세요.")
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.strip().startswith("- [") and sub in l:
            lines[i] = transform(l)
            _write("\n".join(lines) + "\n")
            print(f"[갱신] {lines[i].strip()}")
            return
    raise SystemExit(f"'{sub}' 를 포함한 태스크를 못 찾았습니다.")


def done(sub):
    _update_first(sub, lambda l: l.replace("- [ ]", "- [x]", 1))


def block(sub, reason):
    _update_first(sub, lambda l: l + f" · ⛔블로커:{reason}")


def status():
    text = _read()
    if not text:
        print("(프로젝트 태스크 없음 — '프로젝트에 태스크 추가해줘')")
        return
    today = datetime.date.today()
    soon = today + datetime.timedelta(days=3)
    overdue, upcoming, blocked = [], [], []
    for l in _task_lines(text):
        if l.strip().startswith("- [x]"):
            continue
        if "⛔블로커" in l:
            blocked.append(l.strip())
        m = DUE_RE.search(l)
        if m:
            d = datetime.date.fromisoformat(m.group(1))
            if d < today:
                overdue.append(l.strip())
            elif d <= soon:
                upcoming.append(l.strip())
    print("=== 프로젝트 상태 ===")
    print(f"⛔ 지연(마감 지남) {len(overdue)}건" + (":\n  " + "\n  ".join(overdue) if overdue else ""))
    print(f"⏰ 임박(3일 내) {len(upcoming)}건" + (":\n  " + "\n  ".join(upcoming) if upcoming else ""))
    print(f"🚧 블로커 {len(blocked)}건" + (":\n  " + "\n  ".join(blocked) if blocked else ""))
    if not (overdue or upcoming or blocked):
        print("특이사항 없음(지연·임박·블로커 없음).")


def main():
    ap = argparse.ArgumentParser(description="프로젝트 태스크·마일스톤 트래커")
    ap.add_argument("--add")
    ap.add_argument("--owner", default="")
    ap.add_argument("--due", help="YYYY-MM-DD")
    ap.add_argument("--deps", default="")
    ap.add_argument("--done")
    ap.add_argument("--block")
    ap.add_argument("--reason", default="확인 필요")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.add:
        add(a.add, a.owner, a.due, a.deps)
    elif a.done:
        done(a.done)
    elif a.block:
        block(a.block, a.reason)
    elif a.list:
        print(_read() or "(프로젝트 태스크 없음)")
    elif a.status:
        status()
    else:
        ap.error("--add / --done / --block / --list / --status 중 하나가 필요합니다.")


if __name__ == "__main__":
    main()
