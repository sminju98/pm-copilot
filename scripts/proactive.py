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
    out = []
    # 원칙: 원문(할일·미결 텍스트) 노출 금지 — 개수/일반 안내만. 실제로 '있는' 것만 알림
    # (없는 걸 조르지 않음 → 무관한 프로젝트 세션에선 조용). user-scope 훅이라 어디서든 뜨므로.

    # 오늘 업무일지의 '남은 할 일' (개수만)
    wl = _read(os.path.join(WORKLOG_DIR, f"{today.isoformat()}.md"))
    todos_open = [l for l in wl.splitlines() if l.strip().startswith("- [ ]")]
    if todos_open:
        out.append(f"오늘 남은 할 일 {len(todos_open)}개 — '오늘 할 일 보여줘'")

    # 지난 브리핑 미결 (개수만, 본문 노출 안 함)
    opens = [l for l in _read(os.path.join(DATA_DIR, "last_brief_private.md")).splitlines()
             if l.strip().startswith("확인 필요")]
    if opens:
        out.append("지난 브리핑에 미결 항목이 있어요 — '브리핑 다시 보여줘'")

    # 묵힌 백로그(7일+, 개수만)
    bl = [l for l in _read(os.path.join(DATA_DIR, "backlog.md")).splitlines() if l.startswith("- [")]
    cutoff = (today - datetime.timedelta(days=7)).isoformat()
    stale = [l for l in bl if l[3:13] < cutoff]
    if stale:
        out.append(f"묵힌 백로그 {len(stale)}개(7일+) — '백로그 보여줘'")

    return out[:3]


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
