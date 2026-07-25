#!/usr/bin/env python3
"""SessionStart 훅 — 시키지 않아도 먼저 상태를 보고 챙긴다.
stdout이 세션 컨텍스트로 주입되어 클로드가 먼저 언급한다. 할 말 없으면 조용히(무출력).
user-scope로 모든 프로젝트에서 뜨므로, '설정됨 + 실제로 챙길 것 있음'일 때만 말한다(비침습).
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdin.read()  # 훅이 넘기는 JSON 입력을 소비(사용은 안 함)
except Exception:
    pass

from common import BRIEFS_DIR, CONFIG_PATH, DATA_DIR, HOME, load_config

WORKLOG_DIR = os.path.join(HOME, "worklog")


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def build():
    if not os.path.exists(CONFIG_PATH):
        return []  # 미설정이면 조용히(온보딩은 README가 담당)
    cfg = load_config(soft=True)
    if cfg.get("proactive", {}).get("enabled", True) is False:
        return []
    today = datetime.date.today()
    weekday = today.weekday()
    out = []

    # 오늘 업무일지
    wl = _read(os.path.join(WORKLOG_DIR, f"{today.isoformat()}.md"))
    todos_open = [l for l in wl.splitlines() if l.strip().startswith("- [ ]")]
    dones = [l for l in wl.splitlines()
             if l.strip().startswith("- [") and not l.strip().startswith("- [ ]")]
    if not wl and weekday < 5:
        out.append("오늘 업무일지가 아직 없어요. '오늘 할 일 정리해줘'로 시작할까요?")
    else:
        if todos_open:
            first = todos_open[0].split("]", 1)[-1].strip()
            out.append(f"오늘 남은 할 일 {len(todos_open)}개 (예: {first})")
        if dones:
            out.append(f"오늘 한 일 {len(dones)}건 기록됨 — 마감 때 요약·검토해드릴까요?")

    # 오늘 브리핑 여부(평일)
    if weekday < 5 and not os.path.exists(os.path.join(BRIEFS_DIR, f"{today.isoformat()}-private.md")):
        out.append("오늘 데일리 브리핑을 아직 안 돌렸어요 — '오늘 브리핑 돌려줘'.")

    # 지난 브리핑에서 아직 열린 것
    opens = [l.strip("*# -") for l in _read(os.path.join(DATA_DIR, "last_brief_private.md")).splitlines()
             if l.strip().startswith("확인 필요")]
    if opens:
        out.append("지난 브리핑 미결: " + opens[0][:80])

    # 묵힌 백로그(7일+)
    bl = [l for l in _read(os.path.join(DATA_DIR, "backlog.md")).splitlines() if l.startswith("- [")]
    cutoff = (today - datetime.timedelta(days=7)).isoformat()
    stale = [l for l in bl if l[3:13] < cutoff]
    if stale:
        out.append(f"묵힌 백로그 {len(stale)}개(7일+) — 볼까요? '백로그 보여줘'")

    return out[:4]


def main():
    items = build()
    if not items:
        return
    print("🧭 [기획 사수가 먼저 챙긴 것]")
    for it in items:
        print(f"  · {it}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 훅은 어떤 경우에도 세션을 방해하지 않는다
    sys.exit(0)
