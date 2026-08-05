#!/usr/bin/env python3
"""쓰면서 배운다 — 전부 이 컴퓨터 안에서. 아무것도 밖으로 나가지 않는다.

왜 로컬인가
이 플러그인이 다루는 것은 고객 명단·마진율·예산 상한·미공개 캠페인이다.
`looks_private()` 로 팀 채널에도 안 내보내게 막아 둔 값들이다. 그걸 서버로
보내는 학습은 설계 위반이다. 그리고 자기 사용 패턴은 자기 컴퓨터에 있을 때
가장 정확하다 — 남의 평균과 섞을 이유가 없다.

무엇을 배우는가 — 새로 계측하지 않고 **이미 쌓이는 것에서 캐낸다.**
  ① 스킬 사용 분포   ← data/_activity/*.md      어떤 걸 쓰고 어떤 걸 안 쓰나
  ② 게이트 히트      ← gates/gate_log.jsonl     무엇에 자꾸 막히나
  ③ 재편집           ← data/_activity/*.md      산출물을 얼마나 다시 고치나
  ④ 승인·거절        ← 스킬이 직접 기록          무엇을 O 하고 무엇을 X 하나
①~③은 계측 부담이 0이고 **과거 로그에도 소급 적용된다.** ④만 스킬이 부른다.

배운 것은 짧은 프로필 한 장으로 접어 세션 시작에 실린다. 원장을 통째로
읽히는 게 아니다 — 컨텍스트는 비싸고, 요약되지 않은 로그는 잡음이다.

    learn.py profile          # 배운 것 한 장
    learn.py observe          # 로그를 다시 훑어 프로필 갱신
    learn.py record 승인 --about "광고 초안" --detail "그대로 승인"
    learn.py reset            # 전부 지운다
"""

import argparse
import collections
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from common import DATA_DIR, HOME, file_lock, looks_private
except Exception:  # 커널이 없어도 최소한 돈다
    HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
    DATA_DIR = os.path.join(HOME, "data")

    def looks_private(s):
        return False

    import contextlib

    def file_lock(*_a, **_k):
        return contextlib.nullcontext()

LEARN_DIR = os.path.join(HOME, "learn")
OBS = os.path.join(LEARN_DIR, "observations.jsonl")
PROFILE = os.path.join(LEARN_DIR, "profile.json")

ACTIVITY = os.path.join(DATA_DIR, "_activity")
GATE_LOG = os.path.join(HOME, "gates", "gate_log.jsonl")

WINDOW_DAYS = 30          # 최근 이만큼만 본다. 오래된 습관은 이미 바뀌었을 수 있다.
MIN_OBS = 5               # 이보다 적으면 프로필을 내지 않는다 — 표본 3개로 단정하면 틀린다
REEDIT_MINUTES = 20       # 같은 파일을 이 안에 다시 저장하면 '고쳤다'로 본다


def _now():
    return datetime.datetime.now()


def _safe(s, n=40):
    """민감 원문은 프로필에 넣지 않는다. 세션 컨텍스트로 흘러가는 값이다."""
    s = str(s or "").strip()
    if not s:
        return ""
    if looks_private(s):
        return "(비공개 항목)"
    return s if len(s) <= n else s[:n - 1] + "…"


# ───────────────────── 이미 쌓이는 것에서 캐내기 ─────────────────────

def _activity_lines():
    """활동 로그를 (시각, 본문) 으로. 최근 WINDOW_DAYS 만."""
    out = []
    cutoff = (_now() - datetime.timedelta(days=WINDOW_DAYS)).date()
    if not os.path.isdir(ACTIVITY):
        return out
    for fn in sorted(os.listdir(ACTIVITY)):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", fn)
        if not m:
            continue
        try:
            day = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if day < cutoff:
            continue
        try:
            with open(os.path.join(ACTIVITY, fn), encoding="utf-8") as f:
                for line in f:
                    lm = re.match(r"-\s*(\d{2}:\d{2})\s*·\s*(.+)$", line.strip())
                    if lm:
                        out.append((datetime.datetime.combine(
                            day, datetime.time.fromisoformat(lm.group(1))), lm.group(2)))
        except OSError:
            pass
    return out


def _skill_usage(lines):
    """어떤 스킬을 쓰고 어떤 걸 안 쓰나.

    안 쓰는 스킬이 많다는 것은 스킬이 나쁘다는 뜻이 아니라 **안 보인다**는 뜻일 때가 많다.
    그래서 이 숫자는 사용자를 탓하는 데 쓰지 않고, 먼저 꺼내 주는 데 쓴다.
    """
    used = collections.Counter()
    for _, body in lines:
        m = re.match(r"([a-z][a-z0-9_-]*)\s*·", body)
        if m:
            used[m.group(1)] += 1
    return used


def _reedits(lines):
    """같은 산출물을 짧은 시간 안에 다시 저장했는가 = 결과를 고쳤다.

    품질 신호 중 가장 정직하다. 사용자가 말로 불평하지 않아도 손이 말해 준다.
    """
    last, n, saves = {}, 0, 0
    for ts, body in lines:
        m = re.search(r"(?:작업물 저장|저장)\s*·\s*(\S+)", body)
        if not m:
            continue
        saves += 1
        path = m.group(1)
        prev = last.get(path)
        if prev and (ts - prev).total_seconds() <= REEDIT_MINUTES * 60:
            n += 1
        last[path] = ts
    # 분모는 **전체 저장 횟수**다. 고유 파일 수로 나누면 한 파일을 열 번 고쳤을 때
    # 900% 같은 값이 나온다(실제로 182% 가 나왔다).
    return n, saves, len(last)


def _gate_hits():
    """무엇에 자꾸 막히나. 자주 걸리는 항목은 초안 단계에서 미리 피할 수 있다."""
    hits = collections.Counter()
    if not os.path.isfile(GATE_LOG):
        return hits
    cutoff = _now() - datetime.timedelta(days=WINDOW_DAYS)
    try:
        with open(GATE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("verdict") != "BLOCK":
                    continue
                at = d.get("at", "")
                try:
                    if datetime.datetime.fromisoformat(at).replace(tzinfo=None) < cutoff:
                        continue
                except Exception:
                    pass
                blob = json.dumps(d, ensure_ascii=False)
                if "__selftest__" in blob or "selftest" in str(d.get("action", "")):
                    continue          # 자기시험은 학습 대상이 아니다 — 실사용이 아니다
                hits[d.get("action") or "unknown"] += 1
    except OSError:
        pass
    return hits


# ───────────────────── 스킬이 직접 남기는 것 ─────────────────────

def record(kind, about="", detail=""):
    """승인·거절처럼 로그에서 캐낼 수 없는 것만 스킬이 직접 남긴다."""
    os.makedirs(LEARN_DIR, exist_ok=True)
    rec = {"at": _now().isoformat(timespec="seconds"), "kind": kind,
           "about": _safe(about, 60), "detail": _safe(detail, 80)}
    with file_lock(OBS):
        with open(OBS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _recorded():
    out = []
    if not os.path.isfile(OBS):
        return out
    cutoff = _now() - datetime.timedelta(days=WINDOW_DAYS)
    try:
        with open(OBS, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if datetime.datetime.fromisoformat(d["at"]) >= cutoff:
                        out.append(d)
                except Exception:
                    continue
    except OSError:
        pass
    return out


# ───────────────────── 접기 ─────────────────────

def observe():
    """로그를 훑어 프로필을 다시 만든다. 원본은 건드리지 않는다."""
    lines = _activity_lines()
    used = _skill_usage(lines)
    reedit, saves, files = _reedits(lines)
    gates = _gate_hits()
    recs = _recorded()

    kinds = collections.Counter(r["kind"] for r in recs)
    total = sum(used.values()) + sum(gates.values()) + len(recs)

    prof = {
        "at": _now().isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "total_observations": total,
        "skills_used": used.most_common(8),
        "skills_used_count": len(used),
        "saved_outputs": saves,
        "saved_files": files,
        "reedits": reedit,
        "gate_blocks": gates.most_common(5),
        "recorded": kinds.most_common(6),
        "recent": [(r["kind"], r["about"]) for r in recs[-5:]],
    }
    os.makedirs(LEARN_DIR, exist_ok=True)
    with file_lock(PROFILE):
        tmp = f"{PROFILE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prof, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PROFILE)
    return prof


def profile(refresh=True):
    if refresh or not os.path.isfile(PROFILE):
        return observe()
    try:
        with open(PROFILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return observe()


def summary(prof=None, total_skills=0):
    """세션에 실을 한 장. **짧아야 한다** — 요약되지 않은 로그는 잡음이다."""
    p = prof or profile()
    if p["total_observations"] < MIN_OBS:
        return ""          # 표본이 적으면 아무 말도 하지 않는다. 단정이 오히려 해롭다

    L = [f"🧠 이 사용자에 대해 배운 것 (최근 {p['window_days']}일 · 관측 {p['total_observations']}건)"]

    if p["skills_used"]:
        top = " ".join(f"{k}({v})" for k, v in p["skills_used"][:5])
        L.append(f"  · 자주 쓰는 것: {top}")
        if total_skills and p["skills_used_count"] < total_skills:
            never = total_skills - p["skills_used_count"]
            L.append(f"  · 한 번도 안 쓴 스킬 {never}개 — 안 좋아서가 아니라 몰라서일 수 있다. "
                     "맥락이 맞으면 먼저 꺼내 준다")

    if p.get("saved_outputs"):
        rate = min(100, round(p["reedits"] * 100 / max(p["saved_outputs"], 1)))
        if rate >= 30:
            L.append(f"  · 산출물 재편집률 {rate}% — 초안이 바로 안 맞는다는 뜻이다. "
                     "먼저 톤·길이·형식을 확인하고 쓴다")
        elif p["reedits"]:
            L.append(f"  · 산출물 재편집률 {rate}%")

    if p["gate_blocks"]:
        g = " ".join(f"{k}({v})" for k, v in p["gate_blocks"][:3])
        L.append(f"  · 게이트에 자주 걸리는 것: {g} — 초안 단계에서 미리 피한다")

    if p["recorded"]:
        r = " ".join(f"{k}({v})" for k, v in p["recorded"][:4])
        L.append(f"  · 승인 이력: {r}")

    L.append("  (근거는 이 컴퓨터의 로그뿐이다. 밖으로 나가지 않는다. 추측을 사실처럼 말하지 말 것)")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="로컬 학습 — 배운 것은 이 컴퓨터를 벗어나지 않는다")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("profile", help="배운 것 한 장")
    sub.add_parser("observe", help="로그를 다시 훑어 갱신")
    sub.add_parser("json", help="기계용 원본")
    sub.add_parser("reset", help="배운 것을 전부 지운다")

    r = sub.add_parser("record", help="승인·거절처럼 로그에 안 남는 것을 기록")
    r.add_argument("kind", help="승인 / 거절 / 수정후승인 / 보류 등")
    r.add_argument("--about", default="", help="무엇에 대한 것인지")
    r.add_argument("--detail", default="", help="한 줄 사유")

    a = ap.parse_args()
    cmd = a.cmd or "profile"

    if cmd == "record":
        rec = record(a.kind, a.about, a.detail)
        print(f"  기록: {rec['kind']} · {rec['about'] or '(대상 없음)'}")
        return 0

    if cmd == "reset":
        n = 0
        for p in (OBS, PROFILE):
            if os.path.isfile(p):
                os.remove(p)
                n += 1
        print(f"  {n}개 파일을 지웠습니다. 활동 로그·게이트 로그는 그대로입니다"
              " (그건 학습용이 아니라 원래 있던 기록입니다).")
        return 0

    p = observe()
    if cmd == "json":
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0

    total = 0
    sk = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    if os.path.isdir(sk):
        total = sum(1 for d in os.listdir(sk) if os.path.isfile(os.path.join(sk, d, "SKILL.md")))

    s = summary(p, total)
    if s:
        print(s)
    else:
        print(f"  아직 배운 게 없습니다 (관측 {p['total_observations']}건 / 최소 {MIN_OBS}건 필요).")
        print("  표본이 적을 때 단정하면 틀린 습관을 학습합니다 — 조금 더 쓰고 다시 보세요.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
