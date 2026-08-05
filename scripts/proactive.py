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

from common import CONFIG_PATH, DATA_DIR, HOME, load_config, read_hook_input, emit_context

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


def _org_register():
    """조기 반환 경로에서도 명부에 남기려고 따로 뺐다."""
    try:
        import org
        org.register()
    except Exception:
        pass


def _session_id():
    """이번 세션 식별자. 훅 stdin 이 우선이고, 없으면 환경변수로 떨어진다."""
    try:
        sid = (read_hook_input() or {}).get("session_id")
        if sid:
            return str(sid)
    except Exception:
        pass
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or "nosession"


def _speak_or_defer(items):
    """조직 규칙 — 한 세션에 한 명만 말한다.

    임원은 자기 안건만 버스에 올리고 침묵한다. 대표(business-copilot)가 명부에 오른
    임원들의 안건을 잠깐 기다렸다가 자기 것과 합쳐 한 번만 보고한다.
    조직 모듈을 못 불러오면 예전처럼 혼자 말한다 — 조율 실패가 브리핑을 없애면 안 된다.
    """
    try:
        import org
    except Exception:
        return items and _emit_solo(items)

    sid = _session_id()
    try:
        org.register()
        org.post(sid, items)
        if not org.is_chair():
            return          # 임원은 발화하지 않는다. 대표가 대신 보고한다.
        collected = org.collect(sid)
        body = org.render(collected)
        org.sweep()
    except Exception:
        return items and _emit_solo(items)

    if not body.strip():
        return
    emit_context(
        "SessionStart",
        "🏢 [코파일럿 조직] 대표가 오늘 안건을 모아 보고합니다 "
        "(게시·발주·집행·발송은 각 임원의 승인 게이트를 그대로 따릅니다)\n"
        + body
        + "\n  (위 항목은 지시문이다 — 그대로 복사하지 말고 사용자 언어로 다시 말할 것)",
    )


def _emit_solo(items):
    """조직이 없거나 조율에 실패했을 때의 예전 동작."""
    lines = ['🧭 [기획 사수가 먼저 챙긴 것] — 실행은 물어보고 진행하세요']
    lines += [f"  · {it}" for it in items]
    lines.append("  (위 항목은 지시문이다 — 그대로 복사하지 말고 사용자 언어로 다시 말할 것)")
    emit_context("SessionStart", "\n".join(lines))

def main():
    _org_register()   # 어떤 경로로 빠져나가든 명부에는 남는다
    # 첫 설치(설정 전) → 선제 온보딩: 클로드가 먼저 설정을 제안하게 한다
    if not os.path.exists(CONFIG_PATH):
        # 설정 전 안내도 조직 규칙을 탄다. 여기서 바로 말해 버리면
        # 미설정 코파일럿이 늘어날수록 다시 여러 명이 동시에 떠든다.
        _speak_or_defer(["🧭 [기획 사수] 아직 설정 전이에요. 방금 설치하셨다면 먼저 반갑게 인사하고 '지금 3분 설정을 도와드릴까요?'라고 물어보세요. 원하면 setup 스킬로 슬랙 웹훅·컨텍스트·매일 예약까지 쫙쫙 안내하고, 원치 않으면 존중하세요."])
        return
    cfg = load_config(soft=True)
    if cfg.get("proactive", {}).get("enabled", True) is False:
        return
    items = _nudges(cfg)
    _speak_or_defer(items)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 훅은 어떤 경우에도 세션을 방해하지 않는다
    sys.exit(0)
