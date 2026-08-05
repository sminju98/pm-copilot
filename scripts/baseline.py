#!/usr/bin/env python3
"""기준선 비교 — 내 성과가 어느 수준인지, 지금 있는 근거로 답한다.

왜 이게 먼저인가
집계 벤치마크는 표본이 쌓여야 나온다. 그때까지 사용자는 아무것도 못 받는데,
받는 게 없는 교환은 교환이 아니다. 그래서 **공개된 리서치 수치**를 먼저 기준선으로 쓴다.

이 파일이 지키는 것 — 여기서 어기면 자료 전체가 못 쓰게 된다.
  ① **출처 없는 수치는 없다.** 모든 행에 출처·발표시점·시장이 붙는다.
  ② **미국 수치를 한국 것처럼 말하지 않는다.** 시장이 다르면 다르다고 표시한다.
  ③ **평균과 중앙값을 섞지 않는다.** 평균만 있는 자료로 분위 판정을 하면 틀린다.
  ④ **플랫폼 보고 ROAS 는 부풀려져 있다**는 것이 반복된 학술 발견이다. 함께 알린다.
  ⑤ **없는 칸은 비운다.** 채우려고 지어내지 않는다.

    baseline.py show                     # 기준선 표
    baseline.py compare --channel meta --metric roas --value 2.1
    baseline.py sources                  # 출처 목록
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "baseline.json")

try:
    from common import load_config
except Exception:
    def load_config(**_k):
        return {}


def load():
    try:
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 0, "sources": [], "rows": [], "caveats": []}


def _src(d, sid):
    for s in d.get("sources", []):
        if s.get("id") == sid:
            return s
    return {}


def show(d=None, channel=None, industry=None):
    d = d or load()
    rows = d.get("rows", [])
    if channel:
        rows = [r for r in rows if r.get("channel") == channel]
    if industry:
        rows = [r for r in rows if r.get("industry") in (industry, "", None)]

    if not rows:
        print("  기준선 데이터가 아직 없습니다.")
        print("  (조사가 끝나면 data/baseline.json 에 출처와 함께 채워집니다)")
        return 1

    print(f"📐 기준선 — 공개 자료 인용 {len(rows)}행 · 출처 {len(d.get('sources', []))}곳")
    print("   ⚠️ 이 도구 사용자의 실측이 아니라 **공개된 리서치 수치**입니다.\n")
    def w(t, n):
        """한글은 폭이 2다. 그걸 안 세면 표가 어긋난다."""
        t = str(t)
        cur = sum(2 if ord(c) > 0x1100 else 1 for c in t)
        while cur > n:
            t = t[:-1]
            cur = sum(2 if ord(c) > 0x1100 else 1 for c in t)
        return t + " " * (n - cur)

    print(f"  {w('채널',13)}{w('업종',24)}{w('지표',6)}{w('값',9)}{w('종류',9)}"
          f"{w('시장',13)}{w('신뢰',5)}출처")
    print("  " + "─" * 96)
    for r in sorted(rows, key=lambda x: (x.get("channel", ""), x.get("industry", ""), x.get("metric", ""))):
        src = _src(d, r.get("source"))
        val = f"{r.get('value','')}{r.get('unit','')}"
        print(f"  {w(r.get('channel',''),13)}{w(r.get('industry',''),24)}{w(r.get('metric',''),6)}"
              f"{w(val,9)}{w(r.get('kind',''),9)}{w(r.get('market',''),13)}"
              f"{w(r.get('confidence',''),5)}{src.get('name','')[:24]}")

    for c in d.get("caveats", []):
        print(f"\n  ⚠️ {c}")
    return 0


def compare(channel, metric, value, industry=None):
    """내 값이 기준선 대비 어디쯤인지. **말할 수 있는 것까지만 말한다.**"""
    d = load()
    cand = [r for r in d.get("rows", [])
            if r.get("channel") == channel and r.get("metric") == metric]
    if industry:
        exact = [r for r in cand if r.get("industry") == industry]
        cand = exact or cand

    if not cand:
        print(f"  {channel}/{metric} 기준선이 없습니다. 비교할 근거가 없어 판정하지 않습니다.")
        return 1

    cfg = load_config(soft=True) or {}
    my_market = "KR"
    print(f"📊 내 값 {value} ({channel} · {metric})\n")

    # 업종을 안 주면 '전체' 행을 먼저 보여준다. 업종 15개를 라벨 없이 쏟으면
    # 사용자가 어느 기준과 비교하는지 몰라 오히려 오도된다.
    def is_all(r):
        i = str(r.get("industry", "")).lower()
        return "all" in i or "overall" in i or "전체" in i

    if not industry:
        overall = [r for r in cand if is_all(r)]
        rest = [r for r in cand if not is_all(r)]
        cand = overall or rest
        extra = len(rest) if overall else 0
    else:
        extra = 0

    for r in sorted(cand, key=lambda x: (x.get("confidence") != "high",))[:6]:
        s = _src(d, r.get("source"))
        base = r.get("value")
        try:
            diff = (float(value) - float(base)) / float(base) * 100
            rel = f"{'+' if diff >= 0 else ''}{diff:.0f}%"
        except (TypeError, ValueError, ZeroDivisionError):
            rel = "-"
        mark = "" if r.get("market") == my_market else "  ← 다른 시장 수치"
        ind = r.get("industry", "") or "(전체)"
        print(f"  · [{ind}] 기준 {base} ({r.get('kind','')}, {r.get('market','')}) 대비 {rel}{mark}")
        print(f"    출처 {s.get('name','?')} · {s.get('published','?')} · 표본 {s.get('sample','미공개')}")

    if extra:
        print(f"\n  · 업종별 기준 {extra}개가 더 있습니다 — --industry 로 지정하면 그 업종과 비교합니다.")

    # 다른 채널의 같은 지표가 크게 다르면 반드시 알린다.
    others = {}
    for r in d.get("rows", []):
        if r.get("metric") == metric and r.get("channel") != channel and is_all(r):
            others.setdefault(r["channel"], r.get("value"))
    if others:
        line = " · ".join(f"{k} {v}" for k, v in sorted(others.items()))
        print(f"\n  ⚠️ 채널이 다르면 기준이 다릅니다 — {line}")
        print("     같은 숫자도 채널에 따라 상위·하위가 뒤바뀝니다. 채널을 밝히지 않은 비교는 하지 마세요.")

    # 여기서 멈춘다. 평균만 있는 자료로 분위를 말하면 틀린다.
    kinds = {r.get("kind") for r in cand}
    if not kinds & {"median", "quartile", "distribution"}:
        print("\n  ⚠️ 이 기준선에는 분포(중앙값·사분위)가 없고 평균뿐입니다.")
        print("     그래서 '상위 몇 %' 같은 판정은 하지 않습니다 — 평균만으로는 계산이 안 됩니다.")
        print("     말할 수 있는 것은 '평균 대비 얼마' 까지입니다.")

    for c in d.get("caveats", []):
        print(f"\n  ⚠️ {c}")
    return 0


def sources():
    d = load()
    ss = d.get("sources", [])
    if not ss:
        print("  출처가 아직 없습니다.")
        return 1
    print(f"📚 출처 {len(ss)}곳\n")
    for s in ss:
        print(f"  · {s.get('name','?')} ({s.get('market','?')}, {s.get('published','?')})")
        print(f"    표본 {s.get('sample','미공개')} · {s.get('url','')}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="기준선 — 공개 리서치 수치와의 비교")
    sub = ap.add_subparsers(dest="cmd")
    sh = sub.add_parser("show")
    sh.add_argument("--channel")
    sh.add_argument("--industry")
    cp = sub.add_parser("compare")
    cp.add_argument("--channel", required=True)
    cp.add_argument("--metric", required=True)
    cp.add_argument("--value", required=True)
    cp.add_argument("--industry")
    sub.add_parser("sources")
    a = ap.parse_args()

    if a.cmd == "compare":
        return compare(a.channel, a.metric, a.value, a.industry)
    if a.cmd == "sources":
        return sources()
    return show(channel=getattr(a, "channel", None), industry=getattr(a, "industry", None))


if __name__ == "__main__":
    sys.exit(main())
