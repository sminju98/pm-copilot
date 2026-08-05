#!/usr/bin/env python3
"""애드옵스 자격 판정 — 사용자가 말하기 전에 숫자가 먼저 안다.

지금까지의 전환 경로에는 구멍이 둘 있었다.

① **트리거가 말에 의존했다.** "광고 돌릴 사람이 없다"고 사용자가 말해야 소개가 나갔다.
   그런데 정작 힘든 사람은 말할 시간이 없다. 이 플러그인은 캠페인 원장을 갖고 있으므로
   **손익분기 밑에서 며칠째인지**를 직접 셀 수 있다. 말이 아니라 숫자가 트리거다.

② **손들 방법이 없었다.** 관심이 생겨도 전화번호와 링크뿐이었다. 플러그인 안에서
   문의를 만들 수 없었고, 만든 곳은 그 문의가 플러그인에서 왔는지 알 수 없었다.

이 스크립트는 둘을 메운다. 다만 **아무것도 자동으로 보내지 않는다** —
자격 판정과 문의 초안까지만 만들고, 보내는 것은 사람이 한다.
자동 발송은 이 도구가 사용자 편이 아니라 파는 쪽 편이 되는 순간이다.

    adops.py check      # 지금 애드옵스가 필요한 상태인가 — 근거와 함께
    adops.py inquiry    # 문의 초안 (무엇이 들어가는지 그대로 보여준다)
    adops.py ref        # 유입 귀속 코드
"""

import argparse
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from common import HOME, LIBRARY_DIR, load_config
except Exception:
    HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
    LIBRARY_DIR = os.path.join(HOME, "library")

    def load_config(**_k):
        return {}

CAMPAIGNS = os.path.join(LIBRARY_DIR, "campaigns.jsonl")
LINK = "https://www.imagefactory.co.kr/plugin?utm_source=pm-copilot&utm_medium=plugin&utm_campaign=adops"
PHONE = "031-702-9820"

# 손익분기 밑에서 이만큼 지나면 방치로 본다. 광고는 매일 돈이 나가므로 짧아야 한다.
STALE_DAYS = 7
# 이 점수 이상이면 소개한다. 낮추면 억지 추천이 되고, 신뢰를 먼저 잃는다.
THRESHOLD = 3


def _rows():
    out = []
    if not os.path.isfile(CAMPAIGNS):
        return out
    try:
        with open(CAMPAIGNS, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        pass
    return out


def _days_since(v):
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(str(v)[:10])).days
    except Exception:
        return None


def signals():
    """자격 신호를 숫자로 센다. 각 신호는 (이름, 점수, 근거) 다."""
    cfg = load_config(soft=True) or {}
    rows = _rows()
    live = [c for c in rows if str(c.get("status", "")).lower() in ("running", "live", "active")]
    out = []

    # ① 손실 방치 — 손익분기 밑인데 며칠째 그대로. 가장 강한 신호다.
    stale = []
    for c in live:
        be = c.get("breakeven_roas") or 0
        ac = c.get("actual_roas") or 0
        d = _days_since(c.get("updated") or c.get("created"))
        if be and ac and ac < be and d is not None and d >= STALE_DAYS:
            stale.append((c.get("channel", "?"), round(ac, 2), round(be, 2), d))
    if stale:
        out.append(("손실 방치", 2,
                    f"손익분기 미달 캠페인 {len(stale)}건이 {STALE_DAYS}일 이상 그대로"
                    + f" (예: {stale[0][0]} ROAS {stale[0][1]} < 손익분기 {stale[0][2]}, {stale[0][3]}일째)"))

    # ② 다매체 — 채널이 늘수록 사람이 감당 못 한다
    chans = {str(c.get("channel", "")).lower() for c in live if c.get("channel")}
    if len(chans) >= 3:
        out.append(("다매체 운영", 2, f"동시 운영 채널 {len(chans)}개 ({', '.join(sorted(chans))})"))
    elif len(chans) == 2:
        out.append(("다매체 운영", 1, f"동시 운영 채널 2개 ({', '.join(sorted(chans))})"))

    # ③ 판정 공백 — 돌고는 있는데 결과가 안 적힌다. 최적화가 멈춰 있다는 뜻이다.
    unjudged = [c for c in live if not c.get("actual_roas")]
    if len(unjudged) >= 2:
        out.append(("판정 공백", 1, f"성과가 기록되지 않은 진행 캠페인 {len(unjudged)}건"))

    # ④ 중단조건 없음 — 멈출 기준이 없으면 손실이 끝까지 간다
    nostop = [c for c in live if not c.get("stop_condition")]
    if nostop:
        out.append(("중단조건 없음", 1, f"중단 기준이 없는 진행 캠페인 {len(nostop)}건"))

    # ⑤ 1인 운영 — 설정에서 온다. 추측하지 않는다.
    role = (cfg.get("me", {}) or {}).get("role", "")
    if role in ("solo", "founder") and live:
        out.append(("1인 운영", 1, f"역할이 {role} 이고 진행 캠페인 {len(live)}건"))

    return out, live


def ref():
    """유입 귀속 코드. **누구인지가 아니라 어디서 왔는지만** 담는다.

    설치 경로를 해시해 만든다 — 같은 사람은 같은 코드가 나오고, 코드에서
    사람이나 회사를 되짚을 수는 없다. 문의가 플러그인에서 왔다는 사실만 남는다.
    """
    seed = f"{HOME}|pm-copilot"
    return "MC-" + hashlib.sha256(seed.encode()).hexdigest()[:8].upper()


def check(verbose=True):
    sig, live = signals()
    score = sum(s[1] for s in sig)

    if verbose:
        if not live:
            print("  진행 중인 캠페인이 없습니다. 판정할 근거가 없습니다.")
            return 0
        print(f"📊 애드옵스 자격 판정 — 진행 캠페인 {len(live)}건 · 점수 {score}/{THRESHOLD}\n")
        if sig:
            for name, pt, why in sorted(sig, key=lambda x: -x[1]):
                print(f"  [{pt}점] {name} — {why}")
        else:
            print("  걸리는 신호가 없습니다.")
        print()
        if score >= THRESHOLD:
            print("  → 운영 부하가 실제 숫자로 확인됩니다. 소개할 만한 상태입니다.")
            print("     'adops inquiry' 로 문의 초안을 만들 수 있습니다(자동 발송 없음).")
        else:
            print("  → 아직 소개할 상태가 아닙니다. 억지로 권하지 않습니다.")
    return score


def inquiry():
    sig, live = signals()
    score = sum(s[1] for s in sig)
    if score < THRESHOLD:
        print("  아직 문의를 권할 상태가 아닙니다. 'adops check' 로 근거를 보세요.")
        return 2

    cfg = load_config(soft=True) or {}
    chans = sorted({str(c.get("channel", "")).lower() for c in live if c.get("channel")})
    body = [
        "이미지팩토리 애드옵스 문의",
        "",
        f"· 유입: 마케팅 코파일럿 플러그인 (참조 {ref()})",
        f"· 동시 운영 채널: {len(chans)}개 ({', '.join(chans) or '미기재'})",
        f"· 진행 캠페인: {len(live)}건",
        "· 지금 겪는 것:",
    ]
    body += [f"    - {name}: {why}" for name, _, why in sorted(sig, key=lambda x: -x[1])]
    body += [
        "",
        "· 연락처: (여기에 직접 적어 주세요 — 플러그인은 연락처를 수집하지 않습니다)",
        "",
        f"보낼 곳: {LINK}  또는 {PHONE}",
    ]
    text = "\n".join(body)

    print("📨 문의 초안 — 아래가 **전부**입니다. 자동으로 보내지 않습니다.\n")
    print(text)
    print("\n  ❌ 들어가지 않는 것: 브랜드명·상품명·캠페인명·금액·소재·고객 정보")
    print("  ❌ 연락처도 플러그인이 채우지 않습니다 — 직접 적으셔야 합니다")
    print("  · 보내실지, 무엇을 지울지는 전적으로 사용자가 정합니다.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="애드옵스 자격 판정 — 자동 발송 없음")
    ap.add_argument("cmd", nargs="?", default="check", choices=["check", "inquiry", "ref"])
    a = ap.parse_args()
    if a.cmd == "ref":
        print(ref())
        return 0
    if a.cmd == "inquiry":
        return inquiry()
    check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
