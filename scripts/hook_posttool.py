#!/usr/bin/env python3
"""PostToolUse(Write|Edit) 훅 — PM 작업물을 저장할 때마다 사수가 즉석 검토를 제안한다.
PM 산출물이 아니면 조용히 종료. 짧은 시간 반복 저장은 throttle(소음 방지)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DOCLIKE = (
    "spec", "prd", "기획", "plan", "제안", "요구사항", "정책", "보고", "roadmap", "로드맵",
    "screen", "화면", "design", "디자인", "decision", "의사결정", "ir", "가이드", "guide",
    "manual", "설명서", "브리핑", "brief", "voc", "리서치", "research", "story", "스토리보드",
)


def is_pm_artifact(path):
    if not path:
        return False
    p = path.lower()
    if "/.pm-copilot/" in p:  # 플러그인이 다루는 데이터 폴더
        return True
    if not (p.endswith(".md") or p.endswith(".html")):
        return False
    base = os.path.basename(p)
    return any(k in base for k in DOCLIKE)


def throttled(path, minutes=15):
    p = os.path.join(common.DATA_DIR, "_review_seen.json")
    try:
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    except Exception:
        d = {}
    now = time.time()
    if now - d.get(path, 0) < minutes * 60:
        return True
    d[path] = now
    d = {k: v for k, v in d.items() if now - v < 24 * 3600}  # 오래된 것 정리
    try:
        os.makedirs(common.DATA_DIR, exist_ok=True)
        json.dump(d, open(p, "w", encoding="utf-8"))
    except Exception:
        pass
    return False


def main():
    p = common.proactive_cfg()
    if p is None or p.get("review_on_save", True) is False:
        return
    data = common.read_hook_input()
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ""
    if not is_pm_artifact(path):
        return

    common.log_activity("작업물 저장", path)
    try:  # 회고 대기 표식 → 다음 요청 때 회고 상기
        open(common.PENDING_RETRO, "w").close()
    except Exception:
        pass

    if throttled(path):
        return
    name = os.path.basename(path)
    common.emit_context(
        "PostToolUse",
        f"🧭 사수: 방금 **{name}** 저장됨. 넘어가기 전에 짧게 검토해 — "
        f"빠진 섹션/‘왜’가 약한 곳/블라인드스팟/지어낸 수치가 있으면 **먼저 짚고**, 없으면 통과. "
        f"더 깊게는 [[qa]]·[[ask-sunbae]].",
    )


if __name__ == "__main__":
    main()
