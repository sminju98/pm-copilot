#!/usr/bin/env python3
"""PM 전용 로컬 기록장 — 비공개 백로그·의사결정 로그를 data/ 아래에 쌓고 조회한다.
로컬 전용(전송·공유하지 않음). git 제외 폴더에 저장돼 팀엔 보이지 않는다.

사용:
  python3 scripts/journal.py --log backlog  --add "온보딩에 진행바 아이디어"
  python3 scripts/journal.py --log decision --add "결제모듈 A안 채택 (왜: 개발비 절반 / 가정: 트래픽 유지 / 재검토: 9월)"
  python3 scripts/journal.py --log backlog  --list
  python3 scripts/journal.py --log decision --list --since 30
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR

LOGS = {"backlog": "backlog.md", "decision": "decisions.md"}
TITLES = {"backlog": "PM 전용 비공개 백로그", "decision": "의사결정 로그"}


def path_for(log):
    return os.path.join(DATA_DIR, LOGS[log])


def add(log, text):
    os.makedirs(DATA_DIR, exist_ok=True)
    p = path_for(log)
    new = not os.path.exists(p)
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    with open(p, "a", encoding="utf-8") as f:
        if new:
            f.write(f"# {TITLES[log]} (로컬 전용 · 공유 안 함)\n\n")
        f.write(f"- [{stamp}] {text}\n")
    print(f"[기록됨] {log}: {text}")


def list_(log, since):
    p = path_for(log)
    if not os.path.exists(p):
        print(f"({TITLES[log]} 비어 있음)")
        return
    with open(p, encoding="utf-8") as f:
        lines = [ln.rstrip() for ln in f if ln.startswith("- [")]
    if since:
        cutoff = (datetime.date.today() - datetime.timedelta(days=since)).isoformat()
        lines = [ln for ln in lines if ln[3:13] >= cutoff]
    print(f"=== {TITLES[log]} ({len(lines)}건) ===")
    print("\n".join(lines) if lines else "(해당 기간 항목 없음)")


def main():
    ap = argparse.ArgumentParser(description="PM 전용 로컬 기록장")
    ap.add_argument("--log", choices=list(LOGS), required=True)
    ap.add_argument("--add", help="기록할 내용")
    ap.add_argument("--list", action="store_true", help="목록 보기")
    ap.add_argument("--since", type=int, help="최근 N일만")
    a = ap.parse_args()
    if a.add:
        add(a.log, a.add)
    elif a.list:
        list_(a.log, a.since)
    else:
        ap.error("--add 또는 --list 중 하나가 필요합니다.")


if __name__ == "__main__":
    main()
