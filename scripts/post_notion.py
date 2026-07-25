#!/usr/bin/env python3
"""(선택·고급) 노션 페이지에 브리핑을 append 한다.

노션 '내부 통합(internal integration)' 토큰과 대상 페이지 ID가 필요하다. 토큰은 OAuth가
아니라 정적 값이라 예약(cron) 실행에서도 동작한다. 슬랙 웹훅이 더 간단하므로 노션은 선택.

준비:
  1) notion.so/my-integrations 에서 내부 통합 만들기 → 토큰 복사 → config.notion.token
  2) 브리핑을 쌓을 노션 페이지에서 '연결(Connections)'로 위 통합 추가
  3) 그 페이지 ID(URL 끝 32자리)를 config.delivery.<team|private>.notion_page_id 에 저장

사용:
  python3 scripts/post_notion.py --to private --file data/last_brief_private.md --title "2026-07-26 기획 브리핑" --dry-run

안전장치: --sensitive 를 주면 team 대상으로는 전송을 거부한다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, ROOT, http_request, load_config, looks_private

NOTION_VERSION = "2022-06-28"
MAX_LEN = 1900


def _rt(text):
    return [{"type": "text", "text": {"content": text[:MAX_LEN]}}]


def md_to_blocks(md):
    """아주 단순한 마크다운 → 노션 블록 변환(제목/불릿/일반 문단)."""
    blocks = []
    for line in md.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if s.startswith("### "):
            blocks.append({"type": "heading_3", "heading_3": {"rich_text": _rt(s[4:])}})
        elif s.startswith("## "):
            blocks.append({"type": "heading_2", "heading_2": {"rich_text": _rt(s[3:])}})
        elif s.startswith("# "):
            blocks.append({"type": "heading_1", "heading_1": {"rich_text": _rt(s[2:])}})
        elif s.lstrip().startswith(("- ", "* ")):
            blocks.append({"type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rt(s.lstrip()[2:])}})
        else:
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": _rt(s)}})
    return blocks


def main():
    ap = argparse.ArgumentParser(description="노션 페이지에 브리핑 append")
    ap.add_argument("--to", choices=["team", "private"], required=True)
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--title", default="")
    ap.add_argument("--sensitive", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.sensitive and args.to == "team":
        raise SystemExit("⛔ 거부: --sensitive 콘텐츠는 team 대상 노션으로 보낼 수 없습니다. --to private 로만.")

    cfg = load_config()
    token = cfg.get("notion", {}).get("token", "")
    dest = cfg.get("delivery", {}).get(args.to, {})
    page_id = dest.get("notion_page_id", "")
    if not dest.get("enabled", False):
        print(f"[건너뜀] delivery.{args.to}.enabled=false")
        return
    if not token or not page_id:
        raise SystemExit(f"[미설정] notion.token 또는 delivery.{args.to}.notion_page_id 가 없습니다.")

    if args.text is not None:
        md = args.text
    elif args.file:
        path = args.file if os.path.isabs(args.file) else os.path.join(DATA_DIR, args.file)
        with open(path, encoding="utf-8") as f:
            md = f.read()
    elif not sys.stdin.isatty():
        md = sys.stdin.read()
    else:
        raise SystemExit("보낼 내용이 없습니다(--text/--file/stdin).")

    # 내용 기반 백스톱: '나만 보기' 콘텐츠는 team 대상 노션으로도 차단
    if args.to == "team" and looks_private(md):
        raise SystemExit("⛔ 거부: 본문이 '나만 보기' 콘텐츠로 보입니다. team 노션으로 보낼 수 없습니다.")

    body_md = (f"## {args.title}\n{md}" if args.title else md)
    blocks = md_to_blocks(body_md)

    if args.dry_run:
        print(f"[DRY-RUN 노션 → {args.to}] page={page_id[:8]}… 블록 {len(blocks)}개 append 예정")
        return

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    # 노션은 요청당 최대 100블록 → 100개씩 나눠 여러 번 append(뒷부분 유실 방지)
    sent = 0
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        res = http_request(url, payload={"children": chunk}, headers=headers, method="PATCH")
        if res.get("error") or (res.get("status") or 0) >= 300:
            reason = res.get("error") or f"HTTP {res.get('status')}"
            raise SystemExit(f"[노션 append 실패] {reason} (블록 {i}부터) — 토큰/페이지 공유 설정을 확인하세요. 지금까지 {sent}블록 전송됨.")
        sent += len(chunk)
    print(f"[노션 append 성공] to={args.to} 블록 {sent}개")


if __name__ == "__main__":
    main()
