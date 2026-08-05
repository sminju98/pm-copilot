#!/usr/bin/env python3
"""벤치마크 — 내 성과가 같은 업종에서 어디쯤인지 알기 위해, 집계만 주고받는다.

왜 필요한가
마케터는 "우리 ROAS 2.1이 좋은 건가"를 알 방법이 없다. 매체사는 자기 매체만,
대행사는 자기 고객만 본다. 여러 광고주의 실측이 모여야 답이 나오는데
국내에 그런 자리가 없다.

무엇을 주고받는가 — **집계만 오간다. 캠페인 한 건도 그대로 나가지 않는다.**
  보내는 것: (업종, 채널, 월) 칸마다 ROAS 사분위·CAC 구간·예산 구간·표본 수
  받는 것  : 같은 칸의 전체 분포. "당신은 상위 30%" 같은 판정

왜 원본을 안 보내는가 — 이해충돌 때문이다.
이 도구를 만든 이미지팩토리는 퍼포먼스 마케팅 대행을 한다. 원본을 받으면
**경쟁 광고주의 캠페인을 보게 된다.** "안 본다"는 약속으로는 부족하고
**볼 수 없는 구조**여야 한다. 그래서 원본은 이 컴퓨터를 떠나지 않고,
칸당 표본이 MIN_ROWS 미만이면 그 칸은 아예 만들지 않는다.

지우는 것 — 브랜드명·상품명·캠페인명·계정ID·메시지 원문·메모·오퍼·타깃 설명.
구간화 — 예산과 CAC 는 절대 금액 대신 구간으로. 금액은 회사 규모를 드러낸다.

    bench.py preview     # 보낼 내용을 **그대로** 본다 (기본값 — 아무것도 안 보낸다)
    bench.py optin       # 참여 켜기
    bench.py optout      # 참여 끄기 + 무엇이 삭제 요청되는지
    bench.py status      # 지금 상태
    bench.py send        # 실제 전송 (참여 중일 때만)
"""

import argparse
import collections
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from common import HOME, LIBRARY_DIR, file_lock, load_config
except Exception:
    HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
    LIBRARY_DIR = os.path.join(HOME, "library")

    def load_config(**_k):
        return {}

    import contextlib

    def file_lock(*_a, **_k):
        return contextlib.nullcontext()

BENCH_DIR = os.path.join(HOME, "bench")
STATE = os.path.join(BENCH_DIR, "state.json")
CAMPAIGNS = os.path.join(LIBRARY_DIR, "campaigns.jsonl")

# 한 칸(업종×채널×월)에 이만큼은 있어야 내보낸다. 적으면 개별 캠페인이 역산된다.
MIN_ROWS = 3
# 이 개수 미만이면 아예 참여 자체를 권하지 않는다 — 표본이 없으면 벤치마크가 아니라 거짓말이다.
MIN_TOTAL = 5

# 금액은 회사 규모를 드러낸다. 절대값 대신 구간으로.
BUDGET_BUCKETS = [(0, 100), (100, 500), (500, 2000), (2000, 10000), (10000, None)]   # 만원
CAC_BUCKETS = [(0, 1), (1, 3), (3, 10), (10, 30), (30, None)]                        # 만원

INDUSTRIES = [
    "ecommerce-fashion", "ecommerce-beauty", "ecommerce-food", "ecommerce-living",
    "ecommerce-etc", "education", "healthcare", "finance", "saas-b2b", "app-service",
    "local-service", "manufacturing", "content-media", "etc",
]


def _bucket(v, buckets, unit="만"):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    for lo, hi in buckets:
        if hi is None:
            return f"{lo}{unit}+"
        if lo <= v / 10000 < hi:
            return f"{lo}-{hi}{unit}"
    return ""


def _read_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"optin": False}


def _write_state(d):
    os.makedirs(BENCH_DIR, exist_ok=True)
    with file_lock(STATE):
        tmp = f"{STATE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)


def _campaigns():
    rows = []
    if not os.path.isfile(CAMPAIGNS):
        return rows
    try:
        with open(CAMPAIGNS, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        pass
    return rows


def _quartiles(xs):
    """사분위. 평균 대신 쓰는 이유는 이상치 하나가 칸 전체를 왜곡하기 때문이다."""
    s = sorted(xs)
    n = len(s)
    if not n:
        return None

    def q(p):
        i = (n - 1) * p
        lo, hi = int(i), min(int(i) + 1, n - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (i - lo), 2)
    return {"p25": q(0.25), "p50": q(0.5), "p75": q(0.75)}


def build():
    """보낼 내용을 만든다. **집계만 남기고 원본은 버린다.**"""
    cfg = load_config(soft=True) or {}
    industry = (cfg.get("brand", {}) or {}).get("industry", "") or "etc"
    if industry not in INDUSTRIES:
        industry = "etc"

    buckets = collections.defaultdict(lambda: {"roas": [], "cac": [], "budget": []})
    used = 0
    for c in _campaigns():
        roas = c.get("actual_roas")
        if not roas:
            continue                     # 성과가 기록되지 않은 캠페인은 벤치마크에 못 쓴다
        ch = (c.get("channel") or "").strip().lower()
        if not ch:
            continue
        month = str(c.get("created") or c.get("updated") or "")[:7]
        if len(month) != 7:
            continue
        k = (industry, ch, month)
        buckets[k]["roas"].append(float(roas))
        if c.get("actual_cac"):
            buckets[k]["cac"].append(float(c["actual_cac"]))
        if c.get("budget"):
            buckets[k]["budget"].append(float(c["budget"]))
        used += 1

    rows, dropped = [], 0
    for (ind, ch, month), v in sorted(buckets.items()):
        n = len(v["roas"])
        if n < MIN_ROWS:
            dropped += n            # 표본이 적은 칸은 통째로 버린다 — 역산 방지
            continue
        row = {"industry": ind, "channel": ch, "month": month, "n": n,
               "roas": _quartiles(v["roas"])}
        if v["cac"]:
            row["cac_bucket"] = _bucket(sum(v["cac"]) / len(v["cac"]), CAC_BUCKETS)
        if v["budget"]:
            row["budget_bucket"] = _bucket(sum(v["budget"]) / len(v["budget"]), BUDGET_BUCKETS)
        rows.append(row)

    return {
        "v": 1,
        "at": datetime.datetime.now().strftime("%Y-%m-%d"),
        "rows": rows,
        "_local": {"campaigns_with_result": used, "dropped_low_sample": dropped},
    }


def preview():
    p = build()
    rows, loc = p["rows"], p["_local"]

    print("📤 보낼 내용 — 아래가 **전부**입니다. 이 밖의 것은 나가지 않습니다.\n")
    if not rows:
        print("  (보낼 것이 없습니다)")
        print(f"  · 성과가 기록된 캠페인: {loc['campaigns_with_result']}건")
        if loc["dropped_low_sample"]:
            print(f"  · 표본 부족으로 제외: {loc['dropped_low_sample']}건 "
                  f"(한 칸에 {MIN_ROWS}건 미만이면 개별 캠페인이 역산되므로 통째로 뺍니다)")
        print("\n  캠페인 성과를 더 기록하면 그때 보낼 것이 생깁니다. 지금은 참여해도 줄 게 없습니다.")
        return 1

    payload = {k: v for k, v in p.items() if not k.startswith("_")}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n  집계 {len(rows)}칸 · 캠페인 {loc['campaigns_with_result']}건에서 뽑음")
    if loc["dropped_low_sample"]:
        print(f"  표본 부족으로 제외한 캠페인 {loc['dropped_low_sample']}건")

    print("\n  ❌ 나가지 않는 것: 브랜드명·상품명·캠페인명·계정ID·메시지 원문·메모·오퍼·타깃 설명")
    print("  ❌ 금액 절대값도 나가지 않습니다 — 구간으로만(회사 규모가 드러나므로)")
    print("  ❌ 캠페인 한 건도 그대로 나가지 않습니다 — 칸당 집계뿐")
    return 0


CONSENT = """
📊 벤치마크에 참여하시겠습니까?

  주는 것 — (업종, 채널, 월) 칸마다 **집계 수치만**:
      ROAS 사분위(25/50/75) · CAC 구간 · 예산 구간 · 표본 수
      캠페인 한 건도 그대로 나가지 않습니다. 한 칸에 3건 미만이면 그 칸은 아예 안 만듭니다.

  받는 것 — 같은 칸의 전체 분포. "당신의 ROAS 2.1은 이 업종 상위 30%" 같은 판정.
      지금은 이걸 알 방법이 없습니다. 매체사는 자기 매체만, 대행사는 자기 고객만 봅니다.

  안 나가는 것 — 브랜드명·상품명·캠페인명·계정ID·메시지 원문·메모·금액 절대값

  보관 — 집계만 보관합니다. 원본은 애초에 받지 않습니다.
  철회 — 언제든 'bench optout'. 그때까지 보낸 집계의 삭제도 함께 요청됩니다.
  거부해도 — 플러그인의 모든 기능이 그대로 동작합니다. 아무것도 잠기지 않습니다.

  ⚠️ 만든 곳(이미지팩토리)은 퍼포먼스 마케팅 대행도 합니다.
     그래서 원본을 받지 않고 집계만 받습니다 — '안 본다'가 아니라 '볼 수 없는 구조'입니다.

  참여하려면: bench optin   /   먼저 볼 내용을 확인하려면: bench preview
"""


def main():
    ap = argparse.ArgumentParser(description="벤치마크 — 집계만 주고받는다")
    ap.add_argument("cmd", nargs="?", default="preview",
                    choices=["preview", "optin", "optout", "status", "consent", "send"])
    a = ap.parse_args()
    st = _read_state()

    if a.cmd == "consent":
        print(CONSENT)
        return 0

    if a.cmd == "status":
        print(f"  참여: {'예' if st.get('optin') else '아니오'}")
        if st.get("optin_at"):
            print(f"  참여 시작: {st['optin_at']}")
        if st.get("last_sent"):
            print(f"  마지막 전송: {st['last_sent']}")
        p = build()
        print(f"  지금 보낼 수 있는 집계: {len(p['rows'])}칸")
        return 0

    if a.cmd == "optin":
        p = build()
        if p["_local"]["campaigns_with_result"] < MIN_TOTAL:
            print(f"  ⏸ 아직 참여를 권하지 않습니다.")
            print(f"     성과가 기록된 캠페인이 {p['_local']['campaigns_with_result']}건뿐입니다"
                  f"(최소 {MIN_TOTAL}건).")
            print("     줄 것도 없고 받을 것도 정확하지 않습니다. 나중에 다시 오세요.")
            return 2
        st.update({"optin": True,
                   "optin_at": datetime.datetime.now().isoformat(timespec="seconds")})
        _write_state(st)
        print("  참여를 켰습니다. 무엇이 나가는지는 언제든 'bench preview' 로 확인하세요.")
        print("  끄려면 'bench optout' — 그때까지 보낸 집계의 삭제도 함께 요청됩니다.")
        return 0

    if a.cmd == "optout":
        st.update({"optin": False,
                   "optout_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "erase_requested": True})
        _write_state(st)
        print("  참여를 껐습니다. 더 이상 아무것도 나가지 않습니다.")
        print("  이미 보낸 집계는 삭제 요청 상태로 표시했습니다.")
        return 0

    if a.cmd == "send":
        if not st.get("optin"):
            print("  참여 중이 아닙니다. 아무것도 보내지 않았습니다. ('bench consent' 로 내용 확인)")
            return 2
        # 수집 서버는 아직 없다. 있는 척하지 않는다 — 보낸다고 말하고 안 보내면 그게 최악이다.
        print("  ⏸ 수집 서버가 아직 없습니다. 지금은 아무것도 전송되지 않습니다.")
        print("     참여 의사만 기록해 두었고, 서버가 열리면 그때 'bench preview' 로")
        print("     무엇이 나갈지 다시 확인한 뒤 보내게 됩니다.")
        return 0

    return preview()


if __name__ == "__main__":
    sys.exit(main())
