#!/usr/bin/env python3
"""매일 자동 브리핑을 등록할 때 쓸 문구/크론식을 보여준다(등록 자체는 하지 않는다).

클로드 Code의 예약 실행(routines / `/schedule`)에 붙여넣을 프롬프트와, 참고용 크론식을 출력한다.

  python3 scripts/schedule_brief.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_config

DOW = {"0": "일", "1": "월", "2": "화", "3": "수", "4": "목", "5": "금", "6": "토", "7": "일"}


def human(cron):
    try:
        m, h, dom, mon, dow = cron.split()
    except ValueError:
        return cron
    when = f"{int(h):02d}:{int(m):02d}"
    if dow == "1-5":
        days = "평일(월~금)"
    elif dow == "*":
        days = "매일"
    else:
        days = ", ".join(DOW.get(d, d) for d in dow.split(",")) + "요일"
    return f"{days} {when}"


def main():
    cfg = load_config()
    cron = cfg.get("brief", {}).get("schedule", "0 9 * * 1-5")
    print("=== 매일 자동 브리핑 예약 안내 ===\n")
    print(f"원하는 시각: {human(cron)}   (크론식: {cron}, 최소 간격 1시간)\n")
    print("● 방법 A — 이 세션에서 바로:")
    print('   클로드에게 → "/schedule 평일 오전 9시에 기획 사수 데일리 브리핑 실행"\n')
    print("● 방법 B — claude.ai/code/routines 웹에서 New routine 생성 시, 아래 프롬프트를 넣으세요:")
    print("   (환경변수 PM_COPILOT_SCHEDULED=1 도 함께 설정하면 더 확실합니다)")
    print("   ┌" + "─" * 58)
    print("   │ [예약 실행] pm-copilot 의 daily-brief 스킬을 실행해 오늘자 기획")
    print("   │ 데일리 브리핑을 생성하고 '사용자 확인 없이' 바로 저장·전송해줘.")
    print("   │ 팀 공유본은 팀 채널로, 개인본(팀원 현황 포함)은 나만 보는 채널로.")
    print("   │ 근거 없는 수치는 지어내지 말고 '확인 필요'로 표시할 것.")
    print("   └" + "─" * 58)
    print("\n⚠️ 중요(예약 실행의 현실적 제약):")
    print("  · 클라우드에서 도는 예약은 이 로컬 폴더의 config.json/컨텍스트에 접근하지")
    print("    못할 수 있습니다. 안정적으로 쓰려면 (a) 로컬 파일에 접근 가능한 환경에서")
    print("    예약하거나, (b) 웹훅·컨텍스트를 그 환경에 넣어두세요.")
    print("  · 메일/노션 읽기는 claude.ai 계정 커넥터로 연결(로컬 CLI MCP는 예약에서 안 보임).")
    print("  · 웹 리서치가 필요하면 루틴의 네트워크 접근을 켜세요.")
    print("  · 전달은 슬랙 Incoming Webhook 이 OAuth 만료 걱정 없이 가장 안정적입니다.")
    print("  · 첫 예약 후에는 실제 슬랙 도착을 반드시 눈으로 확인하세요.")


if __name__ == "__main__":
    main()
