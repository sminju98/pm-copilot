#!/usr/bin/env python3
"""생성된 브리핑을 로컬(data/briefs/)에 저장한다.

사용:
  python3 scripts/save_brief.py --kind private --file draft.md
  echo "본문" | python3 scripts/save_brief.py --kind team
  python3 scripts/save_brief.py --kind private --date 2026-07-26 --file draft.md
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, save_brief


def main():
    ap = argparse.ArgumentParser(description="브리핑 로컬 저장")
    ap.add_argument("--kind", choices=["private", "team"], default="private")
    ap.add_argument("--file")
    ap.add_argument("--text")
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
    args = ap.parse_args()

    if args.text is not None:
        text = args.text
    elif args.file:
        path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
        with open(path, encoding="utf-8") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise SystemExit("저장할 내용이 없습니다(--text/--file/stdin).")

    path = save_brief(text, date=args.date, kind=args.kind)
    print(f"[저장됨] {path}")


if __name__ == "__main__":
    main()
