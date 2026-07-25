#!/usr/bin/env python3
"""슬랙 Incoming Webhook 으로 브리핑을 보낸다.

Incoming Webhook 은 OAuth 없이 URL 하나로 동작하므로, 예약(cron) 실행에서도 안정적이다.

사용:
  python3 scripts/post_slack.py --to private --file data/last_brief_private.md --title "오늘의 기획 브리핑"
  python3 scripts/post_slack.py --to team --text "..." --title "팀 현황 공유"
  echo "본문" | python3 scripts/post_slack.py --to private --title "..." --dry-run

--to team    : config.delivery.team.slack_webhook 로 (팀 공유용)
--to private : config.delivery.private.slack_webhook 로 (나만 보기용)

안전장치:
  --sensitive 를 주면 '팀(team)' 채널로는 절대 보내지 않는다(에러). 팀원 현황 같은
  '나만 보기' 콘텐츠는 이 플래그로 실수 전송을 막는다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, http_request, load_config, looks_private, env_webhook, ENV_WEBHOOK


def to_mrkdwn(md):
    """마크다운을 슬랙 mrkdwn 로 최소 변환한다.
    슬랙은 '## 제목'·'**굵게**'를 렌더링하지 않으므로 기호가 문자 그대로 보이는 걸 막는다.
    """
    import re
    out = []
    for line in md.splitlines():
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", line)
        if m:
            out.append(f"*{m.group(2).strip()}*")           # 제목 → 굵게
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)          # **굵게** → *굵게*
        s = re.sub(r"^(\s*)[-*]\s+", r"\1• ", s)             # 불릿 → •
        out.append(s)
    return "\n".join(out)


def _read_body(args):
    if args.text is not None:
        return args.text
    if args.file:
        path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
        with open(path, encoding="utf-8") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("보낼 내용이 없습니다. --text, --file, 또는 표준입력(stdin) 중 하나를 주세요.")


def main():
    ap = argparse.ArgumentParser(description="슬랙 Incoming Webhook 전송")
    ap.add_argument("--to", choices=["team", "private"], required=True)
    ap.add_argument("--text", help="보낼 본문 문자열")
    ap.add_argument("--file", help="본문을 읽어올 파일 경로")
    ap.add_argument("--title", default="", help="상단에 굵게 표시할 제목")
    ap.add_argument("--sensitive", action="store_true",
                    help="민감 콘텐츠 표시. 켜면 팀 채널 전송을 거부한다.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.sensitive and args.to == "team":
        raise SystemExit("⛔ 거부: --sensitive 콘텐츠는 팀(team) 채널로 보낼 수 없습니다. --to private 로만 보내세요.")

    # 예약/클라우드 실행: 환경변수 웹훅을 우선 사용(로컬 config.json 없이도 동작)
    webhook = env_webhook(args.to)
    if not webhook:
        cfg = load_config(soft=True)
        dest = cfg.get("delivery", {}).get(args.to, {})
        if not dest.get("enabled", False):
            print(f"[건너뜀] delivery.{args.to} 비활성 & 환경변수({ENV_WEBHOOK[args.to]}) 없음 — 이 채널로 안 보냄.")
            return
        webhook = dest.get("slack_webhook", "")
    if not webhook or not webhook.startswith("https://hooks.slack.com/"):
        raise SystemExit(f"[미설정] {args.to} 슬랙 웹훅이 없습니다. config 또는 환경변수 {ENV_WEBHOOK[args.to]} 로 넣어주세요.")

    body = _read_body(args)

    # 내용 기반 백스톱: '나만 보기' 콘텐츠(팀원 현황 등)는 --sensitive 여부와 무관하게 팀 채널 차단
    if args.to == "team" and looks_private(body):
        raise SystemExit("⛔ 거부: 본문이 '나만 보기(팀원 현황 등)' 콘텐츠로 보입니다. 팀 채널로 보낼 수 없습니다. --to private 로만 보내세요.")

    text = (f"*{args.title}*\n" if args.title else "") + to_mrkdwn(body)

    if args.dry_run:
        who = "팀 채널" if args.to == "team" else "나만 보는 채널"
        print(f"[DRY-RUN 슬랙 → {who}]\n{'-'*40}\n{text[:1500]}\n{'-'*40}")
        return

    res = http_request(webhook, payload={"text": text})
    if res.get("error") or (res.get("status") or 0) >= 300:
        reason = res.get("error") or f"HTTP {res.get('status')}"
        raise SystemExit(f"[슬랙 전송 실패] {reason} — 웹훅이 만료·삭제됐을 수 있어요. 새 웹훅을 발급해 저장하세요.")
    print(f"[슬랙 전송 성공] to={args.to}")


if __name__ == "__main__":
    main()
