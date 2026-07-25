#!/usr/bin/env python3
"""원커맨드 셋업 — 슬랙 웹훅만 주면 설정 생성·검증·테스트 발송까지 한 번에.

  python3 scripts/quicksetup.py --private "https://hooks.slack.com/services/..." \
      [--team "https://hooks.slack.com/services/..."] \
      [--name "홍길동"] [--product "우리서비스"] [--no-test]

설정은 ~/.pm-copilot/ 에 저장되어 플러그인을 업데이트/재설치해도 유지된다.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_PATH, DATA_DIR, EXAMPLE_CONFIG, ROOT, context_path, http_request

SLACK_PREFIX = "https://hooks.slack.com/"


def valid_webhook(url):
    return bool(url) and url.startswith(SLACK_PREFIX)


def send_test(url, label):
    res = http_request(url, payload={"text": f"✅ 기획 사수 연결 완료 — 이 채널은 *[{label}]* 입니다."})
    if res.get("error") or (res.get("status") or 0) >= 300:
        return False, res.get("error") or f"HTTP {res.get('status')}"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser(description="기획 사수 원커맨드 셋업")
    ap.add_argument("--private", required=True, help="나만 보기 슬랙 Incoming Webhook URL (필수)")
    ap.add_argument("--team", help="팀 공유 슬랙 웹훅 URL (선택)")
    ap.add_argument("--name", default="", help="내 이름")
    ap.add_argument("--product", default="", help="프로덕트 이름")
    ap.add_argument("--no-test", action="store_true", help="테스트 메시지 발송 생략")
    args = ap.parse_args()

    if not valid_webhook(args.private):
        raise SystemExit("⛔ --private 는 https://hooks.slack.com/ 로 시작하는 슬랙 웹훅이어야 합니다.")
    if args.team and not valid_webhook(args.team):
        raise SystemExit("⛔ --team 웹훅 형식이 올바르지 않습니다.")

    # 1) 안정적 폴더(~/.pm-copilot)에 설정 생성
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EXAMPLE_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["delivery"]["private"].update(enabled=True, slack_webhook=args.private)
    if args.team:
        cfg["delivery"]["team"].update(enabled=True, slack_webhook=args.team)
    if args.name:
        cfg["me"]["name"] = args.name
    if args.product:
        cfg["product"]["name"] = args.product
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[설정 저장] {CONFIG_PATH}")

    # 2) 컨텍스트 문서 준비(없으면 템플릿 복사)
    ctx = context_path(cfg)
    if not os.path.exists(ctx):
        shutil.copy(os.path.join(ROOT, "templates", "context.example.md"), ctx)
        print(f"[컨텍스트 템플릿] {ctx}  ← 여기에 현황/경쟁사/팀을 채우세요")

    # 3) 테스트 발송(웹훅 검증 + 팀/개인 뒤바뀜 확인)
    if not args.no_test:
        ok, msg = send_test(args.private, "나만 보기")
        print(f"[테스트→개인] {'✅ 전송 — 슬랙 확인' if ok else '⚠️ 실패: ' + msg}")
        if args.team:
            ok, msg = send_test(args.team, "팀 공유")
            print(f"[테스트→팀]  {'✅ 전송 — 슬랙 확인' if ok else '⚠️ 실패: ' + msg}")

    print("\n다음 할 일:")
    print("  1) 슬랙 두 채널에 라벨이 맞게 왔는지 확인(뒤바뀌었으면 --private/--team 값 바꿔 재실행)")
    print(f"  2) 컨텍스트 채우기: {ctx}  (또는 클로드에게 '컨텍스트 채우자')")
    print("  3) 매일 자동: python3 scripts/schedule_brief.py 로 루틴 등록 문구 확인")


if __name__ == "__main__":
    main()
