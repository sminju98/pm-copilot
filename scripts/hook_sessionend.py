#!/usr/bin/env python3
"""SessionEnd 훅 — 오늘 활동 원장을 업무일지 초안으로 정리(로컬, 사람이 검토·보완). 표식 정리.
주입 없음(로컬 파일만 씀)."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    p = common.proactive_cfg()

    # 임시 표식 정리(항상)
    try:
        if os.path.exists(common.PENDING_RETRO):
            os.remove(common.PENDING_RETRO)
    except Exception:
        pass

    if p is None or p.get("worklog_on_end", True) is False:
        return

    today = datetime.date.today().isoformat()
    src = os.path.join(common.ACTIVITY_DIR, today + ".md")
    if not os.path.exists(src):
        return
    try:
        acts = open(src, encoding="utf-8").read().strip()
    except Exception:
        return
    if not acts:
        return

    outdir = os.path.join(common.DATA_DIR, "worklog")
    try:
        os.makedirs(outdir, exist_ok=True)
        out = os.path.join(outdir, f"{today}-draft.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(
                f"<!-- {common.PRIVATE_SENTINEL} -->\n"
                f"# 업무일지 초안 · {today}  (자동 수집 — 사람이 검토·보완)\n\n"
                f"## 오늘 만진 작업물/활동\n{acts}\n\n"
                f"> [claude ai] 자동 초안입니다. **무엇을·왜** 했는지, 배운 점/다음 할 일은 직접 채워 완성하세요. "
                f"(자세히 [[worklog]])\n"
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
