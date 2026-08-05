"""공통 유틸: 설정 로드, HTTP 요청, 브리핑 컨텍스트/저장소.

외부 라이브러리 없이 파이썬 표준 라이브러리만 사용한다(설치 없이 바로 실행).
"""
import contextlib
import datetime
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    import fcntl                      # POSIX 전용 — 없으면 잠금 없이 동작한다
except ImportError:                   # pragma: no cover
    fcntl = None

# ROOT = 설치된 패키지 폴더(스킬·스크립트·템플릿). 플러그인 업데이트 시 갈아끼워지므로 '읽기 전용' 취급.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# HOME = 사용자 설정·데이터를 두는 '안정적' 폴더. 플러그인을 업데이트/재설치해도 여기 값은 유지된다.
HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
DATA_DIR = os.path.join(HOME, "data")
BRIEFS_DIR = os.path.join(DATA_DIR, "briefs")
CONFIG_PATH = os.path.join(HOME, "config.json")
EXAMPLE_CONFIG = os.path.join(ROOT, "config.example.json")


@contextlib.contextmanager
def file_lock(path, timeout=10.0):
    """읽고-고치고-쓰는 구간을 프로세스 사이에서 직렬화한다.

    왜 필요한가 — 원장(JSONL)을 갱신할 때 read_all → 수정 → 전체 재작성을 한다.
    이 사이에 다른 프로세스가 쓰면 그 쓰기가 통째로 사라진다. 채번도 마찬가지로
    읽어서 다음 번호를 정하므로, 동시에 두 프로세스가 같은 id 를 붙인다.
    중복 id 는 조용히 퍼진다 — update() 가 첫 매치에서 멈추므로 이후 갱신이
    한쪽 레코드에만 가고, 성과 귀속이 어긋나도 아무 오류가 안 난다.

    아침 루틴과 대화 세션이 겹치기만 해도 재현된다. 호스트가 둘이면 더 잦다.

    fcntl 이 없는 환경(윈도우 등)에서는 잠금 없이 통과시킨다 — 기능을 막지는 않는다.
    """
    if fcntl is None:
        yield
        return
    lock_path = str(path) + ".lock"
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    except OSError:
        pass
    f = None
    try:
        f = open(lock_path, "w")
    except OSError:
        yield          # 잠금을 못 잡는다고 작업 자체를 막지는 않는다
        return

    deadline = time.time() + timeout
    got = False
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
            break
        except OSError:
            if time.time() >= deadline:
                break  # 기다릴 만큼 기다렸으면 진행한다(교착보다 낫다)
            time.sleep(0.05)
    try:
        yield
    finally:
        if got:
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            f.close()
        except OSError:
            pass
def plugin_option(key):
    """plugin.json 의 userConfig(활성화 시 물어보는 질문) 답변값.
    Claude Code가 CLAUDE_PLUGIN_OPTION_<KEY> 환경변수로 넘겨준다. 버전마다 대소문자
    규칙이 다를 수 있어 후보를 모두 확인한다. 없으면 ''."""
    for name in (f"CLAUDE_PLUGIN_OPTION_{key.upper()}", f"CLAUDE_PLUGIN_OPTION_{key}"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def config_from_options():
    """config.json 없이 userConfig 답변만으로 최소 설정을 구성한다.
    (설치 후 네이티브 질문에만 답한 사용자도 브리핑 전송이 되게 하는 연결고리.)"""
    cfg = {}
    name = plugin_option("me_name")
    if name:
        cfg["me"] = {"name": name}
    product = plugin_option("product_name")
    if product:
        cfg["product"] = {"name": product}
    delivery = {}
    for to, opt in (("team", "slack_team_webhook"), ("private", "slack_private_webhook")):
        wh = plugin_option(opt)
        if wh:
            delivery[to] = {"enabled": True, "slack_webhook": wh}
    if delivery:
        cfg["delivery"] = delivery
    pro = plugin_option("proactive_enabled")
    if pro:
        cfg["proactive"] = {"enabled": pro.lower() in ("1", "true", "yes", "on")}
    return cfg


def load_config(path=CONFIG_PATH, soft=False):
    """config.json을 읽는다. 파일이 없으면 plugin.json userConfig 답변으로 대체하고,
    그것도 없으면 soft=True일 때 빈 dict(예약/클라우드 실행용)."""
    if not os.path.exists(path):
        opt = config_from_options()
        if opt:
            return opt
        if soft:
            return {}
        raise SystemExit(
            f"[설정 없음] {path} 가 없습니다.\n"
            "  클로드에게 '기획 사수 설정 시작하자'라고 말하면 대화로 만들어 줍니다.\n"
            "  (또는 플러그인 활성화 시 뜨는 질문에 답하거나, 예약/클라우드면 환경변수 PM_COPILOT_SLACK_PRIVATE 등으로 대체)"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def context_path(cfg=None):
    cfg = cfg or {}
    rel = cfg.get("context_file", "data/context.md")
    return rel if os.path.isabs(rel) else os.path.join(HOME, rel)


def routine_ready(cfg=None):
    """무인 루틴을 돌려도 되는 상태인가. (가능여부, 못 하는 이유들) 로 답한다.

    설정이 덜 된 상태에서 루틴을 걸면 매일 빈 브리핑이나 "설정 없음" 오류가
    예약 시각마다 날아온다. 사용자는 그걸 보고 루틴을 꺼 버리고, 다시는 안 켠다.
    **아무것도 안 보내는 게 빈 걸 보내는 것보다 낫다.**

    그래서 두 곳에서 쓴다:
      · 등록 전 — 준비가 안 됐으면 루틴을 걸지 않고 무엇이 빠졌는지 알린다.
      · 실행 중 — 예약으로 깨어났는데 준비가 안 됐으면 조용히 종료한다(오류 아님).
    """
    why = []
    if cfg is None:
        if not os.path.exists(CONFIG_PATH):
            return False, ["설정 파일이 없습니다 — 먼저 설정을 마쳐야 합니다"]
        cfg = load_config(soft=True) or {}
    if not cfg:
        return False, ["설정이 비어 있습니다"]
    if cfg.get("setup", {}).get("completed") is not True:
        why.append("설정이 끝나지 않았습니다(setup.completed)")
    if not (cfg.get("brand", {}).get("name") or cfg.get("company", {}).get("name")):
        why.append("브랜드·회사 이름이 없습니다")
    return (not why), why


def routine_guard():
    """예약(무인) 실행인데 준비가 안 됐으면 **조용히** 끝낸다.

    스크립트 맨 앞에서 부른다. 오류를 내지 않는 것이 핵심이다 — 예약 로그에
    빨간 줄이 쌓이면 사용자는 원인을 못 찾고 루틴 자체를 의심하게 된다.
    """
    if not is_scheduled():
        return True
    ok, _ = routine_ready()
    if not ok:
        sys.exit(0)
    return True


def user_language(cfg=None):
    """사용자 언어 코드. 'auto' 면 클로드가 대화 언어를 보고 정한다.

    스킬 문서가 한국어인 것과 사용자가 쓰는 언어는 별개다 — 문서는 클로드에게 주는
    지시문이지 사용자에게 보여줄 글이 아니다. 그래서 기본값이 'auto' 다.
    """
    if cfg is None:
        cfg = load_config(soft=True) or {}
    v = cfg.get("language") or cfg.get("brief", {}).get("language") or "auto"
    v = str(v).strip().lower()
    return v if v else "auto"


def load_context(cfg=None):
    """사용자가 관리하는 프로덕트/팀/로드맵 컨텍스트 문서를 읽는다. 없으면 빈 문자열."""
    env = os.environ.get("PM_COPILOT_CONTEXT", "").strip()
    if env:
        return env
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
    # macOS python.org 파이썬은 기본 CA 저장소가 비어 SSL 검증이 실패하곤 한다.
    # certifi가 설치돼 있으면 그 CA 번들을 쓴다(없으면 시스템 기본 — 하드 의존성 아님).
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
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
_PRIVATE_MARKERS = (PRIVATE_SENTINEL, "팀원별", "팀원 현황", "팀 현황", "나만 보기", "로컬 전용", "공유 안 함")


def looks_private(text):
    """본문이 '나만 보기' 전용으로 보이면 True. --sensitive 를 안 붙였어도 팀 오전송을 막는다."""
    t = text or ""
    return any(m in t for m in _PRIVATE_MARKERS)


def is_scheduled():
    """예약(무인) 실행이면 True. 루틴 환경이 PM_COPILOT_SCHEDULED=1 을 넣어준다."""
    return os.environ.get("PM_COPILOT_SCHEDULED", "").strip().lower() in ("1", "true", "yes", "on")


ENV_WEBHOOK = {"team": "PM_COPILOT_SLACK_TEAM", "private": "PM_COPILOT_SLACK_PRIVATE"}


def env_webhook(to):
    """예약/클라우드 실행용 — 환경변수에 담긴 슬랙 웹훅을 반환(없으면 ''). 로컬 config 없이 동작."""
    return os.environ.get(ENV_WEBHOOK.get(to, ""), "").strip()


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


# ============================================================
# 훅(hook) 공용 유틸 — 선제적 사수 동작(세션시작·요청·저장·종료)에서 쓴다.
# ============================================================
ACTIVITY_DIR = os.path.join(DATA_DIR, "_activity")
PENDING_RETRO = os.path.join(DATA_DIR, "_pending_retrospect")


def read_hook_input(timeout=2):
    """훅 stdin(JSON)을 블로킹 없이 읽어 dict로. 데이터 없거나 오류면 {}.
    (일부 이벤트에서 stdin이 안 닫혀 무한 대기하는 것을 select로 방지.)"""
    raw = ""
    try:
        import select
        if select.select([sys.stdin], [], [], timeout)[0]:
            raw = sys.stdin.read()
    except Exception:
        try:
            raw = sys.stdin.read()
        except Exception:
            return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def emit_context(event, text):
    """훅 stdout으로 모델에 컨텍스트를 주입한다(UserPromptSubmit/PostToolUse/SessionStart 등)."""
    text = (text or "").strip()
    if not text:
        return
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
        ensure_ascii=False,
    ))


def proactive_cfg():
    """proactive 설정 반환. 전체 off면 None. 개별 토글은 호출부에서 기본 True로 처리."""
    p = load_config(soft=True).get("proactive", {})
    if p.get("enabled", True) is False:
        return None
    return p


def log_activity(kind, detail):
    """오늘 활동 원장에 한 줄 남긴다(세션 종료 시 업무일지 초안 등에 사용). 실패해도 조용히."""
    try:
        os.makedirs(ACTIVITY_DIR, exist_ok=True)
        path = os.path.join(ACTIVITY_DIR, datetime.date.today().isoformat() + ".md")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {datetime.datetime.now().strftime('%H:%M')} · {kind} · {detail}\n")
    except Exception:
        pass
