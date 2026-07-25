"""공통 유틸: 설정 로드, HTTP 요청, 브리핑 컨텍스트/저장소.

외부 라이브러리 없이 파이썬 표준 라이브러리만 사용한다(설치 없이 바로 실행).
"""
import datetime
import json
import os
import ssl
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
BRIEFS_DIR = os.path.join(DATA_DIR, "briefs")
CONFIG_PATH = os.path.join(ROOT, "config.json")


def load_config(path=CONFIG_PATH, soft=False):
    """config.json을 읽는다. soft=True면 파일이 없어도 빈 dict 반환(예약/클라우드 실행용)."""
    if not os.path.exists(path):
        if soft:
            return {}
        raise SystemExit(
            f"[설정 없음] {path} 가 없습니다.\n"
            "  클로드에게 '기획 사수 설정 시작하자'라고 말하면 대화로 만들어 줍니다.\n"
            "  (예약/클라우드 실행이면 환경변수 PM_COPILOT_SLACK_PRIVATE 등으로 대체 가능)"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def context_path(cfg=None):
    cfg = cfg or {}
    rel = cfg.get("context_file", "data/context.md")
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def load_context(cfg=None):
    """사용자가 관리하는 프로덕트/팀/로드맵 컨텍스트 문서를 읽는다. 없으면 빈 문자열."""
    p = context_path(cfg)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def http_request(url, payload=None, headers=None, method=None, timeout=20):
    """JSON POST/GET 공통. 성공/실패 모두 예외 없이 dict로 반환한다.
    반환: {"status": int|None, "body": obj|str|None, "error": str|None}
    무인(예약) 실행에서 원시 트레이스백으로 죽지 않게 하려는 목적.
    """
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    method = method or ("POST" if data is not None else "GET")
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = getattr(resp, "status", None)
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return {"status": e.code, "body": body, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"status": None, "body": None, "error": f"네트워크 오류: {e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"status": None, "body": None, "error": f"요청 실패: {e}"}
    try:
        return {"status": status, "body": json.loads(raw), "error": None}
    except (json.JSONDecodeError, ValueError):
        return {"status": status, "body": raw, "error": None}


# 나만 보기 전용 콘텐츠를 기계가 식별하는 표식 — 팀 채널 오전송을 내용 기반으로 막는 백스톱.
PRIVATE_SENTINEL = "PM-COPILOT:PRIVATE-ONLY"
_PRIVATE_MARKERS = (PRIVATE_SENTINEL, "팀원별", "팀원 현황", "팀 현황")


def looks_private(text):
    """본문이 '나만 보기' 전용으로 보이면 True. --sensitive 를 안 붙였어도 팀 오전송을 막는다."""
    t = text or ""
    return any(m in t for m in _PRIVATE_MARKERS)


def is_scheduled():
    """예약(무인) 실행이면 True. 루틴 환경이 PM_COPILOT_SCHEDULED=1 을 넣어준다."""
    return os.environ.get("PM_COPILOT_SCHEDULED", "").strip().lower() in ("1", "true", "yes", "on")


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def today_str(cfg=None):
    return datetime.date.today().isoformat()


def save_brief(text, date=None, kind="private"):
    """생성된 브리핑을 data/briefs/<날짜>-<kind>.md 로 저장하고, 최신본을 last_brief.md 로 갱신."""
    os.makedirs(BRIEFS_DIR, exist_ok=True)
    date = date or datetime.date.today().isoformat()
    path = os.path.join(BRIEFS_DIR, f"{date}-{kind}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    latest = os.path.join(DATA_DIR, f"last_brief_{kind}.md")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(text)
    return path
