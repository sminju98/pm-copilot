#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 요청을 읽고 상황을 감지해 사수 관점을 선제적으로 주입한다.
관련 없으면 조용히 종료(아무 것도 출력 안 함). 같은 상황은 세션당 1회만(소음 방지)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# (트리거 키워드들, 주입할 사수 한마디)
SITUATIONS = [
    (("기획", "스펙", "prd", "요구사항", "기능 정의", "화면 설계", "정책"),
     "🧭 사수: 만들기 전에 — 이 기획의 **왜(목적·사용자 의도)**, **비목표**, **성공기준**부터 한 줄로 확정했나? 근거 없는 수치는 '확인 필요'."),
    (("배포", "출시", "릴리즈", "런칭", "론칭", "deploy", "launch"),
     "🧭 사수: 출시 게이트 — QA·롤백·핵심지표·법무/개인정보·접근성 확인했나? ([[launch-readiness]]·[[qa]])"),
    (("우선순위", "priority", "백로그", "뭐부터", "rice", "ice"),
     "🧭 사수: 우선순위엔 **근거(RICE 등)** + **무엇을 미루는지**를 함께. ([[prioritize]])"),
    (("지표", "metric", "데이터", "전환", "리텐션", "kpi", "퍼널", "코호트"),
     "🧭 사수: 지표는 상관≠인과, 계정≠기업 정의 혼동 주의. so-what(그래서 뭐)까지. ([[metrics-report]])"),
    (("팀원", "평가", "스탠드업", "팀 현황", "누가 뭐"),
     "🔒 사수: 팀원 현황은 **나만 보기 전용** — 팀 채널로 안 나가게, 낙인/인신공격 금지, 사실·근거만. ([[team-standup]])"),
    (("회의", "미팅", "회의록"),
     "🧭 사수: 회의는 목적·안건·결정·액션(담당·기한). 끝나면 스펙·프로젝트에 반영. ([[meeting]])"),
    (("ir", "투자", "피치", "데크", "덱", "투자자"),
     "🧭 사수: IR은 문제→해법→시장→트랙션→팀→요청. 수치는 출처·기준일, 없으면 '확인 필요'(지어내면 신뢰 붕괴)."),
    (("voc", "고객 문의", "리뷰 분석", "고객의 소리"),
     "🧭 사수: VOC는 목록이 아니라 **인사이트→기획**까지. 미응답엔 추천 답변 초안. ([[voc]])"),
]


def _throttle(session, key):
    """세션당 같은 상황은 1회만. 이미 봤으면 True."""
    p = os.path.join(common.DATA_DIR, "_nudge_seen.json")
    try:
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    except Exception:
        d = {}
    seen = set(d.get(session, []))
    if key in seen:
        return True
    seen.add(key)
    try:
        os.makedirs(common.DATA_DIR, exist_ok=True)
        json.dump({session: sorted(seen)}, open(p, "w", encoding="utf-8"))  # 현재 세션만 유지
    except Exception:
        pass
    return False


def main():
    p = common.proactive_cfg()
    if p is None or p.get("prompt_nudge", True) is False:
        return
    data = common.read_hook_input()
    prompt = (data.get("prompt") or "").lower()
    session = data.get("session_id") or "-"
    notes = []

    # 직전에 만든 작업물의 회고가 남아 있으면 먼저 상기(저장 후 다음 턴)
    if os.path.exists(common.PENDING_RETRO):
        try:
            os.remove(common.PENDING_RETRO)
        except Exception:
            pass
        notes.append(
            "🔁 사수(회고): 직전에 만든 작업물이 원래 '왜'를 충족했는지, "
            "다음 액션([[project]] 등록/[[gantt]] 갱신/공유)이 남았는지 먼저 점검해줘."
        )

    if prompt:
        for i, (keys, msg) in enumerate(SITUATIONS):
            if any(k in prompt for k in keys) and not _throttle(session, i):
                notes.append(msg)

    if not notes:
        return
    common.emit_context("UserPromptSubmit", "\n".join(notes[:3]))


if __name__ == "__main__":
    main()
