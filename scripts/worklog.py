#!/usr/bin/env python3
"""개인 업무일지(🔒 로컬 전용) — 오늘의 할 일/한 일을 쌓고 일·주·월로 본다.
전송·공유하지 않는다. ~/.pm-copilot/worklog/ 에 날짜별로 저장(git·저장소와 무관).

  python3 scripts/worklog.py --todo "슬랙 연동 설계 마무리"
  python3 scripts/worklog.py --done "이탈 퍼널 계측 스펙 초안"
  python3 scripts/worklog.py --show            # 오늘
  python3 scripts/worklog.py --show week        # 최근 7일
  python3 scripts/worklog.py --show month       # 이번 달
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME

WORKLOG_DIR = os.path.join(HOME, "worklog")
TODO_H = "## 오늘의 할 일"
DONE_H = "## 오늘 한 일"


def day_path(d):
    return os.path.join(WORKLOG_DIR, f"{d}.md")


def _ensure(d):
    os.makedirs(WORKLOG_DIR, exist_ok=True)
    p = day_path(d)
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 업무일지 {d} (🔒 나만 보기)\n\n{TODO_H}\n\n{DONE_H}\n")
    return p


def add(kind, text, d):
    p = _ensure(d)
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    header = TODO_H if kind == "todo" else DONE_H
    stamp = datetime.datetime.now().astimezone().strftime("%H:%M")
    entry = (f"- [ ] {text}\n" if kind == "todo" else f"- [{stamp}] {text}\n")
    idx = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if idx is None:
        lines += [f"\n{header}\n", entry]
    else:
        lines.insert(idx + 1, entry)
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[{'할 일' if kind == 'todo' else '한 일'} 기록] {text}  → {p}")


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def show(scope, d):
    if scope == "today":
        txt = _read(day_path(d.isoformat()))
        print(txt if txt else f"({d} 업무일지 없음 — '오늘 할 일 정리해줘'라고 해보세요)")
        return
    if scope == "week":
        days = [d - datetime.timedelta(days=i) for i in range(6, -1, -1)]
        title = f"주간 업무일지 ({days[0]} ~ {days[-1]})"
    else:  # month
        first = d.replace(day=1)
        days = [first + datetime.timedelta(days=i) for i in range((d - first).days + 1)]
        title = f"월간 업무일지 ({first} ~ {d})"
    print(f"# {title} 🔒 나만 보기\n")
    any_ = False
    for dd in days:
        txt = _read(day_path(dd.isoformat())).strip()
        if txt:
            any_ = True
            print(txt + "\n")
    if not any_:
        print("(해당 기간 기록 없음)")


def main():
    ap = argparse.ArgumentParser(description="개인 업무일지(로컬 전용)")
    ap.add_argument("--todo", help="오늘의 할 일 추가")
    ap.add_argument("--done", help="오늘 한 일 추가")
    ap.add_argument("--show", nargs="?", const="today", choices=["today", "week", "month"])
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
    a = ap.parse_args()
    d = datetime.date.fromisoformat(a.date) if a.date else datetime.date.today()
    if a.todo:
        add("todo", a.todo, d.isoformat())
    elif a.done:
        add("done", a.done, d.isoformat())
    elif a.show:
        show(a.show, d)
    else:
        ap.error("--todo / --done / --show 중 하나가 필요합니다.")


if __name__ == "__main__":
    main()
