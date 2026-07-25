#!/usr/bin/env python3
"""설정 점검: 데일리 브리핑을 돌리기 위해 아직 채워야 할 값을 보여준다.
사용자가 켠 항목만 점검한다(sources.use_*, delivery.*.enabled, brief.sections.*).

  python3 scripts/doctor.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_PATH, context_path, load_context

PLACEHOLDERS = [
    "홍길동", "우리 서비스", "우리서비스", "무엇을, 누구에게",
    "핵심 성공지표", "example.com", "여기에", "바꾸기", "XXXX",
]


def missing(v):
    if v in (None, "", 0, [], {}):
        return True
    return any(p in str(v) for p in PLACEHOLDERS)


def main():
    if not os.path.exists(CONFIG_PATH):
        print("⚠️  아직 설정 전입니다. 클로드에게 '기획 사수 설정 시작하자'라고 말해보세요.")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    me = cfg.get("me", {})
    product = cfg.get("product", {})
    delivery = cfg.get("delivery", {})
    sources = cfg.get("sources", {})
    sections = cfg.get("brief", {}).get("sections", {})

    print("=== 기획 사수(PM Copilot) 설정 점검 ===\n")
    ready = True

    # 1) 내 정보 + 프로덕트
    left = [k for k in ("name",) if missing(me.get(k))]
    left += [f"product.{k}" for k in ("name", "one_liner") if missing(product.get(k))]
    if left:
        ready = False
        print(f"  ⚠️  내 정보/프로덕트: 채울 값 → {', '.join(left)}")
    else:
        print("  ✅ 내 정보/프로덕트: 준비 완료")

    # 2) 컨텍스트 문서 (현황·경쟁사·로드맵·팀을 적어두는 곳)
    ctx = load_context(cfg)
    TEMPLATE_HINTS = ["(한 줄 소개)", "(핵심 사용자)", "(진행 중 과제", "예) 김OO", "예) 이OO", "(업계 키워드"]
    leftover = [h for h in TEMPLATE_HINTS if h in ctx]
    if len(ctx.strip()) < 40:
        ready = False
        print(f"  ⚠️  컨텍스트 문서({context_path(cfg)}): 비어 있음 — 현황/경쟁사/팀을 적어두면 브리핑 품질이 확 오릅니다.")
    elif leftover:
        ready = False
        print(f"  ⚠️  컨텍스트 문서: 아직 템플릿 상태({len(leftover)}곳 미작성) — 예시 문구를 실제 내용으로 바꿔야 알맹이 있는 브리핑이 나옵니다.")
    else:
        print(f"  ✅ 컨텍스트 문서: {len(ctx.splitlines())}줄 작성됨")

    # 3) 전달 채널 (팀 공유 / 나만 보기 중 최소 하나)
    def dest_ok(d):
        return bool(d.get("slack_webhook") or d.get("notion_page_id"))

    team = delivery.get("team", {})
    priv = delivery.get("private", {})
    dests = []
    if team.get("enabled"):
        dests.append(("팀 공유", dest_ok(team)))
    if priv.get("enabled"):
        dests.append(("나만 보기", dest_ok(priv)))
    if not dests:
        ready = False
        print("  ⚠️  전달 채널: 팀/개인 중 최소 하나를 켜세요.")
    else:
        for label, ok in dests:
            if ok:
                print(f"  ✅ 전달 채널({label}): 준비 완료")
            else:
                ready = False
                print(f"  ⚠️  전달 채널({label}): 슬랙 웹훅 또는 노션 페이지가 필요합니다.")

    # 4) 팀원 현황(감시) 섹션은 반드시 '나만 보기'로만
    if sections.get("team_standup"):
        if team.get("enabled") and not priv.get("enabled"):
            ready = False
            print("  ⛔ 팀원 현황 섹션이 켜져 있는데 '나만 보기' 채널이 꺼져 있습니다. 이 섹션은 개인 채널로만 전송됩니다 — 개인 채널을 켜세요.")
        else:
            print("  🔒 팀원 현황 섹션: '나만 보기' 채널로만 전송됩니다 (팀 채널로 안 나감).")

    # 5) 리서치/읽기 소스 (참고용 안내)
    on = [k.replace("use_", "") for k, v in sources.items() if v]
    print(f"\n  ℹ️  사용 소스: {', '.join(on) if on else '없음'} "
          "(email/notion/task_tracker는 커넥터 연결이 필요합니다. 미연결 시 웹 리서치+컨텍스트 문서로만 동작)")

    print()
    if ready:
        print("설정 완료! '오늘 브리핑 돌려줘' 또는 '/schedule 로 매일 자동 실행'을 등록하세요.")
    else:
        print("아직 남은 항목이 있어요. 클로드에게 '기획 사수 설정 계속하자'라고 하면 이어서 안내합니다.")


if __name__ == "__main__":
    main()
