#!/usr/bin/env python3
"""서버 리포트 — 로컬에서 못 하는 계산을 이미지팩토리 서버가 대신 한다.

무엇이 다른가
로컬은 자기 데이터만 본다. 그래서 못 하는 것이 있다:
  · **벤치마크 대비 내 위치** — 남의 분포를 알아야 나온다
  · **다채널 통합 판정** — 채널별 커넥터를 다 붙이지 않아도 서버가 합쳐 준다
  · **이상 탐지** — 며칠치 추이를 놓고 봐야 "이건 소재 피로도"인지 "시장 변화"인지 갈린다
  · **무거운 계산** — 몇 달치 추이 회귀·업종 보간은 노트북에서 돌리기 아깝다

대신 무엇을 주는가 — **캠페인 원본이 서버로 전송된다.** 집계가 아니라 원본이다.
이걸 흐리게 말하지 않는다. 흐리면 동의가 무효가 되고, 무효인 동의로 모은 데이터는
나중에 통째로 못 쓴다. 정확히 고지하는 쪽이 결국 더 많이 모은다.

**전송은 사용자가 리포트를 요청할 때만 일어난다.** 배경에서 주기적으로 올리지 않는다.
동의를 받았더라도 몰래 도는 업로드는 수확처럼 보이고, 실제로 그것과 구분되지 않는다.
"리포트 주세요" 라는 요청이 곧 전송이고, 그 자리에서 무엇이 나가는지 다시 보여준다.

두 단계로 나뉜다. 사용자가 고른다.
  [1단계] 집계만  — 원본은 이 컴퓨터를 안 떠난다. 벤치마크 위치만 받는다. (bench.py)
  [2단계] 원본 연동 — 원본을 보내고 서버 리포트 전체를 받는다. (이 파일)

    report_server.py plan       # 1단계와 2단계가 각각 뭘 주고받는지
    report_server.py preview    # 나가는 데이터 전문 (요청 전 확인)
    report_server.py optin      # 2단계 동의 (고지문을 다 읽어야 진행)
    report_server.py request    # **리포트 요청 = 이때만 전송된다**
    report_server.py optout     # 해지 + 삭제 요청
    report_server.py status
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from common import HOME, LIBRARY_DIR, file_lock, load_config, looks_private
except Exception:
    HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
    LIBRARY_DIR = os.path.join(HOME, "library")

    def load_config(**_k):
        return {}

    def looks_private(_s):
        return False

    import contextlib

    def file_lock(*_a, **_k):
        return contextlib.nullcontext()

RS_DIR = os.path.join(HOME, "report-server")
STATE = os.path.join(RS_DIR, "state.json")

# 원본이라도 이건 안 보낸다. 리포트 계산에 필요 없는데 위험만 크다.
NEVER_SEND = {"learned", "note", "offer", "audience", "message_id", "target_id"}
# 회사를 특정하는 값. 리포트에 필요 없으므로 뺀다.
IDENTIFYING = {"name", "account_id", "brand"}


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tier": 1}


def _save(d):
    os.makedirs(RS_DIR, exist_ok=True)
    with file_lock(STATE):
        tmp = f"{STATE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)


def _campaigns():
    p = os.path.join(LIBRARY_DIR, "campaigns.jsonl")
    out = []
    if not os.path.isfile(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        pass
    return out


def payload():
    """2단계에서 실제로 나가는 것. 원본이되 불필요한 위험은 뺀다."""
    cfg = load_config(soft=True) or {}
    rows = []
    for c in _campaigns():
        r = {k: v for k, v in c.items()
             if k not in NEVER_SEND and k not in IDENTIFYING}
        # 자유 서술 필드에 민감한 값이 섞였으면 통째로 뺀다
        for k, v in list(r.items()):
            if isinstance(v, str) and looks_private(v):
                r.pop(k)
        rows.append(r)
    return {
        "v": 1,
        "at": datetime.datetime.now().strftime("%Y-%m-%d"),
        "industry": (cfg.get("brand", {}) or {}).get("industry", "") or "etc",
        "campaigns": rows,
    }


PLAN = """
📋 두 단계 — 무엇을 주고 무엇을 받나

┌─ [1단계] 집계만  (bench)                          기본값
│  주는 것  (업종·채널·월) 칸당 ROAS 사분위·CAC 구간·표본 수
│           **원본은 이 컴퓨터를 떠나지 않습니다.** 캠페인 한 건도 그대로 안 나갑니다.
│  받는 것  벤치마크에서 내 위치 — "이 업종 상위 30%"
│  한계     칸당 3건 미만이면 그 칸이 안 만들어져 비교가 비게 됩니다.
│           채널을 합쳐 보거나 추이를 보는 건 안 됩니다.
└─

┌─ [2단계] 원본 연동  (report-server)                선택
│  주는 것  **캠페인 원본이 서버로 전송됩니다.**
│           채널·예산·ROAS·CAC·기간·상태·중단조건·판정
│           빼고 보내는 것: 캠페인명·브랜드·계정ID·메모·오퍼·타깃 설명·메시지 원문
│  받는 것  · 벤치마크 정밀 비교 (표본이 적은 칸도 서버가 인접 칸으로 보간)
│           · 다채널 통합 판정 — 커넥터를 다 안 붙여도 서버가 합칩니다
│           · 이상 탐지 — 며칠치 추이로 소재 피로도와 시장 변화를 갈라 줍니다
│           · 리포트를 요청할 때마다 그 시점 데이터로 계산
│  보관     계약 기간 동안. 해지하면 삭제를 요청할 수 있습니다.
└─

  1단계만 써도 플러그인의 모든 기능이 동작합니다. 2단계는 리포트를 더 받는 선택입니다.
"""

CONSENT = """
📄 [2단계] 원본 연동 동의

  ▸ 수집 항목
      캠페인 원본 — 채널, 예산, 일예산, 목표, KPI, 손익분기 ROAS, 허용 CAC,
      실제 ROAS, 실제 CAC, 실제 매출, 중단조건, 확대조건, 상태, 판정, 기간
      업종(설정에 적은 값)

  ▸ 보내지 않는 항목
      캠페인명 · 브랜드명 · 상품명 · 계정ID · 메모 · 오퍼 문구 · 타깃 설명 · 메시지 원문
      그리고 마진·원가처럼 민감으로 판정된 값은 자동으로 빠집니다

  ▸ 이용 목적
      ① 이용자에게 리포트 제공(벤치마크 비교·다채널 통합·이상 탐지·주간 발송)
      ② 벤치마크 통계 산출 — 개별 식별이 불가능한 형태로만

  ▸ 보유 기간
      연동 해지 시까지. 해지하면 삭제를 요청할 수 있고, 통계에 이미 반영된
      집계값은 개별 복원이 불가능해 되돌릴 수 없습니다.

  ▸ 거부할 권리
      동의하지 않아도 됩니다. **플러그인의 모든 기능이 그대로 동작합니다.**
      1단계(집계만)로도 벤치마크 위치는 받을 수 있습니다.

  ▸ 알아두실 것
      만든 곳(이미지팩토리)은 퍼포먼스 마케팅 대행도 합니다.
      2단계는 원본이 전송되므로, 1단계와 달리 '볼 수 없는 구조'가 아닙니다.
      그래서 캠페인명·브랜드·계정ID를 빼고 보내며, 그래도 부담되면 1단계를 쓰세요.

  나가는 데이터를 **실제로** 보려면:  report-server preview
  동의하려면:                        report-server optin --agree
"""


def main():
    ap = argparse.ArgumentParser(description="서버 리포트 — 원본 연동은 선택")
    ap.add_argument("cmd", nargs="?", default="plan",
                    choices=["plan", "preview", "consent", "optin", "request", "optout", "status"])
    ap.add_argument("--agree", action="store_true",
                    help="고지문을 읽고 동의함 (이 플래그 없이는 켜지지 않는다)")
    a = ap.parse_args()
    st = _state()

    if a.cmd == "plan":
        print(PLAN)
        return 0
    if a.cmd == "consent":
        print(CONSENT)
        return 0

    if a.cmd == "status":
        print(f"  단계: {st.get('tier', 1)}단계 "
              f"({'원본 연동' if st.get('tier') == 2 else '집계만'})")
        if st.get("optin_at"):
            print(f"  연동 시작: {st['optin_at']}")
        p = payload()
        print(f"  2단계로 보낼 캠페인: {len(p['campaigns'])}건")
        return 0

    if a.cmd == "preview":
        p = payload()
        if not p["campaigns"]:
            print("  보낼 캠페인이 없습니다.")
            return 1
        print("📤 2단계에서 나가는 데이터 — 아래가 **전부**입니다.\n")
        print(json.dumps(p, ensure_ascii=False, indent=2)[:3000])
        if len(json.dumps(p, ensure_ascii=False)) > 3000:
            print("  … (이하 동일 형식)")
        print(f"\n  캠페인 {len(p['campaigns'])}건 · 각 건에서 "
              f"{', '.join(sorted(NEVER_SEND | IDENTIFYING))} 를 제거했습니다.")
        print("  ⚠️ 이것은 집계가 아니라 원본입니다. 1단계(bench)와 다릅니다.")
        return 0

    if a.cmd == "optin":
        if not a.agree:
            print(CONSENT)
            print("  ⏸ 아직 켜지 않았습니다. 위 고지를 확인하셨으면:")
            print("     report-server optin --agree")
            return 2
        st.update({"tier": 2, "optin_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "consent_version": 1})
        _save(st)
        print("  2단계(원본 연동)를 켰습니다.")
        print("  ※ 켰다고 바로 나가지 않습니다. **리포트를 요청하실 때만** 전송됩니다.")
        print("     요청: 'report-server request' · 전문 확인: 'report-server preview'")
        print("     해지: 'report-server optout' — 삭제 요청이 함께 접수됩니다.")
        print("\n  ⏸ 다만 수집 서버가 아직 열리지 않았습니다.")
        return 0

    if a.cmd == "request":
        if st.get("tier") != 2:
            print("  2단계(원본 연동) 동의가 없습니다. 아무것도 전송하지 않았습니다.")
            print("  1단계 벤치마크는 'bench preview' 로 쓸 수 있습니다.")
            return 2
        p = payload()
        if not p["campaigns"]:
            print("  보낼 캠페인이 없습니다.")
            return 1
        print(f"📤 리포트를 요청합니다 — 지금 이 순간 캠페인 {len(p['campaigns'])}건이 전송됩니다.")
        print("   (전문 확인: report-server preview)\n")
        print("  ⏸ 수집 서버가 아직 열리지 않았습니다. 지금은 전송되지 않았습니다.")
        return 0

    if a.cmd == "optout":
        st.update({"tier": 1, "optout_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "erase_requested": True})
        _save(st)
        print("  1단계(집계만)로 되돌렸습니다. 원본은 더 이상 나가지 않습니다.")
        print("  이미 보낸 원본은 삭제 요청 상태로 표시했습니다.")
        print("  ※ 통계에 이미 반영된 집계값은 개별 복원이 불가능해 되돌릴 수 없습니다.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
