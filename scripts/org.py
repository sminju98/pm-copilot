#!/usr/bin/env python3
"""코파일럿 조직 — 대표 1명, 직무임원 3명. 네 명이 동시에 떠드는 것을 막는다.

왜 필요한가
코파일럿 4종이 모두 SessionStart 훅을 건다. 훅은 병렬로 실행되고 순서가 보장되지
않으므로, 세션을 열면 영업·기획·사업·마케팅이 **각자 자기 브리핑을 쏟아낸다.**
사용자는 누구 말을 먼저 들어야 할지 모르고, 네 개가 서로를 밀어낸다.

"대표가 먼저 말하게 하라"는 순서 규칙으로는 못 푼다 — 순서를 정할 수가 없다.
그래서 발화와 수집을 분리한다:

  · 임원(마케팅·영업·기획)은 **말하지 않는다.** 자기 안건만 공용 버스에 올린다.
  · 대표(business-copilot)는 명부에 오른 임원들의 안건이 도착하기를 잠깐 기다렸다가,
    자기 것과 합쳐 **한 번만** 보고한다.
  · 대표가 없으면(미설치) 각자 예전처럼 말한다 — 조직이 없으면 지휘도 없다.

명부(roster)는 세션을 넘어 남는다. 그래야 대표가 "누구를 기다려야 하는지" 안다.
한동안 안 보이는 임원은 명부에서 내려, 없는 사람을 기다리다 늦어지지 않게 한다.

이 파일은 4형제에서 **바이트까지 같다.** 자기 이름은 매니페스트에서 읽는다.
"""

import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORG_DIR = os.environ.get("COPILOT_ORG_HOME", "").strip() or os.path.expanduser("~/.copilot-org")
ROSTER = os.path.join(ORG_DIR, "roster.json")
SESSIONS = os.path.join(ORG_DIR, "sessions")

CHAIR = "business-copilot"

# 직무. 대표가 안건을 묶어 보고할 때 이 순서·호칭을 쓴다.
ROLES = {
    "business-copilot":  ("대표",        0),
    "marketing-copilot": ("마케팅 임원", 1),
    "sales-copilot":     ("영업 임원",   2),
    "pm-copilot":        ("기획 임원",   3),
}

# 명부에서 내리는 기준. 이만큼 안 보이면 설치가 빠졌다고 본다.
STALE_SECONDS = 14 * 24 * 3600
# 대표가 임원 안건을 기다리는 시간. 훅 타임아웃(15초)보다 훨씬 짧아야 한다.
WAIT_SECONDS = float(os.environ.get("COPILOT_ORG_WAIT", "2.5"))


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data):
    """원자적으로 쓴다. 훅 4개가 동시에 이 파일을 건드린다."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def me():
    """내 플러그인 이름. 매니페스트에서 읽어 4형제가 같은 파일을 쓸 수 있게 한다."""
    d = _read(os.path.join(ROOT, ".claude-plugin", "plugin.json"), {})
    return d.get("name") or os.path.basename(ROOT)


def role_of(name):
    return ROLES.get(name, ("협력 모듈", 9))[0]


def acting_chair(r=None):
    """실제로 지휘할 사람. 대표가 설치돼 있으면 대표, 없으면 직무 순서가 가장 앞선 임원.

    대표가 없다고 전원이 각자 발화하면 조율이 통째로 무너진다 —
    반드시 한 명만 말하게 한다.
    """
    r = roster() if r is None else r
    names = set(r.keys()) or {me()}
    if CHAIR in names:
        return CHAIR
    return sorted(names, key=lambda n: ROLES.get(n, ("", 9))[1])[0]


def is_chair(name=None):
    """내가 이번 세션의 발화자인가."""
    return (name or me()) == acting_chair()


def _lock(path):
    """공용 파일을 고칠 때만 잠근다. fcntl 이 없으면 그냥 진행한다."""
    try:
        import fcntl
    except ImportError:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f = open(path + ".lock", "w")
        fcntl.flock(f, fcntl.LOCK_EX)
        return f
    except Exception:
        return None


def _unlock(f):
    if f is None:
        return
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        f.close()
    except Exception:
        pass


def register(name=None):
    """명부에 나를 올린다. 대표가 누구를 기다릴지 정하는 근거가 된다."""
    name = name or me()
    lk = _lock(ROSTER)
    try:
        r = _read(ROSTER, {})
        r[name] = {"role": role_of(name), "home": ROOT, "last_seen": time.time()}
        # 오래 안 보인 임원은 내린다 — 없는 사람을 기다리면 매 세션이 느려진다.
        now = time.time()
        r = {k: v for k, v in r.items()
             if now - float(v.get("last_seen", 0) or 0) < STALE_SECONDS}
        _write(ROSTER, r)
        return r
    finally:
        _unlock(lk)


def roster():
    return _read(ROSTER, {})


def _session_file(session_id):
    safe = "".join(c for c in str(session_id or "nosession") if c.isalnum() or c in "-_")[:64]
    return os.path.join(SESSIONS, f"{safe or 'nosession'}.json")


def post(session_id, items, name=None):
    """내 안건을 버스에 올린다. 임원은 여기까지만 하고 발화하지 않는다."""
    name = name or me()
    if not items:
        items = []
    p = _session_file(session_id)
    lk = _lock(p)
    try:
        d = _read(p, {})
        d[name] = {"role": role_of(name), "items": list(items), "ts": time.time()}
        _write(p, d)
        return d
    finally:
        _unlock(lk)


def collect(session_id, wait=None):
    """대표 전용 — 명부에 오른 임원들의 안건이 도착하기를 잠깐 기다렸다가 모은다.

    전원이 도착하면 즉시 끝낸다. 안 오는 임원이 있어도 시간이 되면 있는 것만 쓴다
    (훅이 세션을 붙잡고 있으면 안 된다).
    """
    wait = WAIT_SECONDS if wait is None else wait
    expected = set(roster().keys()) or {me()}
    p = _session_file(session_id)
    deadline = time.time() + max(0.0, wait)

    while True:
        d = _read(p, {})
        if expected.issubset(set(d.keys())) or time.time() >= deadline:
            return d
        time.sleep(0.1)


def render(collected, chair_name=None):
    """모인 안건을 하나의 보고로. 대표 것이 먼저, 임원은 직무 순서대로."""
    chair_name = chair_name or acting_chair()
    rows = sorted(collected.items(), key=lambda kv: ROLES.get(kv[0], ("", 9))[1])
    lines = []
    for name, blob in rows:
        items = [i for i in (blob.get("items") or []) if str(i).strip()]
        if not items:
            continue
        label = "대표" if name == chair_name else role_of(name)
        lines.append(f"■ {label}")
        lines += [f"  · {it}" for it in items]
    return "\n".join(lines)


def sweep(keep=40):
    """세션 파일이 무한정 쌓이지 않게 한다. 최근 것만 남긴다."""
    try:
        fs = sorted((os.path.join(SESSIONS, f) for f in os.listdir(SESSIONS)),
                    key=os.path.getmtime, reverse=True)
    except OSError:
        return
    for f in fs[keep:]:
        try:
            os.remove(f)
        except OSError:
            pass


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(f"나: {me()} ({role_of(me())}) · 대표 여부: {'예' if is_chair() else '아니오'}")
        print(f"조직 디렉터리: {ORG_DIR}")
        r = roster()
        if not r:
            print("명부: 비어 있음 (아직 아무도 등록 안 됨)")
        else:
            print(f"명부 {len(r)}명:")
            for k, v in sorted(r.items(), key=lambda kv: ROLES.get(kv[0], ("", 9))[1]):
                age = int((time.time() - float(v.get("last_seen", 0) or 0)) / 60)
                print(f"  · {v.get('role','?'):10} {k:20} {age}분 전")
    elif cmd == "register":
        print(json.dumps(register(), ensure_ascii=False, indent=2))
    elif cmd == "sweep":
        sweep()
        print("오래된 세션 파일 정리 완료")
    else:
        print("사용: org.py [status|register|sweep]")
