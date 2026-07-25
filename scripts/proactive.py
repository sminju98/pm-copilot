#!/usr/bin/env python3
"""SessionStart 훅 — 시키지 않아도 먼저 눈치껏 챙기고 제안한다(단, 실행은 '물어보고').
stdout이 세션 컨텍스트로 주입되어 클로드가 먼저 언급/제안한다.
원칙: 개인정보 원문은 노출하지 않는다(개수/일반 안내만). user-scope라 모든 프로젝트에서 뜨므로
proactive.enabled=false 로 끌 수 있다.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 훅이 stdin으로 JSON을 넘기지만 여기선 쓰지 않는다. read()하면 입력이 없을 때 블로킹되므로
# 아예 읽지 않는다(프로세스 종료 시 파이프는 알아서 닫힘).

from common import CONFIG_PATH, DATA_DIR, HOME, load_config

WORKLOG_DIR = os.path.join(HOME, "worklog")


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _nudges(cfg):
    today = datetime.date.today()
    out = []
    if today.weekday() < 5:  # 평일 아침 선제 제안(일반 안내, 개인정보 없음)
        out.append("오늘 브리핑/할 일부터 챙길까요? ('오늘 브리핑' · '오늘 할 일')")
    todos_open = [l for l in _read(os.path.join(WORKLOG_DIR, f"{today.isoformat()}.md")).splitlines()
                  if l.strip().startswith("- [ ]")]
    if todos_open:
        out.append(f"오늘 남은 할 일 {len(todos_open)}개 — '오늘 할 일 보여줘'")
    if any(l.strip().startswith("확인 필요")
           for l in _read(os.path.join(DATA_DIR, "last_brief_private.md")).splitlines()):
        out.append("지난 브리핑에 미결 항목이 있어요 — '브리핑 다시 보여줘'")
    bl = [l for l in _read(os.path.join(DATA_DIR, "backlog.md")).splitlines() if l.startswith("- [")]
    cutoff = (today - datetime.timedelta(days=7)).isoformat()
    stale = [l for l in bl if l[3:13] < cutoff]
    if stale:
        out.append(f"묵힌 백로그 {len(stale)}개(7일+) — '백로그 보여줘'")
    if not cfg.get("brief", {}).get("routine_enabled", False):
        out.append("아직 매일 자동 예약(루틴)을 안 거셨어요 — 걸어드릴까요? ('매일 브리핑 예약')")
    return out[:5]


def main():
    # 첫 설치(설정 전) → 선제 온보딩: 클로드가 먼저 설정을 제안하게 한다
    if not os.path.exists(CONFIG_PATH):
        print("🧭 [기획 사수] 아직 설정 전이에요. 방금 설치하셨다면 먼저 반갑게 인사하고 "
              "'지금 3분 설정을 도와드릴까요?'라고 물어보세요. 원하면 setup 스킬로 슬랙 웹훅·컨텍스트·"
              "매일 예약까지 쫙쫙 안내하고, 원치 않으면 존중하세요.")
        return
    cfg = load_config(soft=True)
    if cfg.get("proactive", {}).get("enabled", True) is False:
        return
    items = _nudges(cfg)
    if not items:
        return
    print("🧭 [기획 사수가 먼저 챙긴 것] — 실행은 물어보고 진행하세요")
    for it in items:
        print(f"  · {it}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 훅은 어떤 경우에도 세션을 방해하지 않는다
    sys.exit(0)
