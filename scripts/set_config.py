#!/usr/bin/env python3
"""config.json 값을 대화로 채우기 위한 헬퍼.

사용자가 JSON을 직접 편집하지 않도록, 클로드가 채팅에서 받은 값을 이 스크립트로 저장한다.
점(.)으로 중첩 경로를 지정한다. config.json이 없으면 config.example.json에서 복제한다.

예:
  python3 scripts/set_config.py me.name="홍길동" product.name="우리서비스"
  python3 scripts/set_config.py delivery.private.slack_webhook="https://hooks.slack.com/..."
  python3 scripts/set_config.py sources.use_email=true brief.schedule="0 9 * * 1-5"
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_PATH, EXAMPLE_CONFIG, HOME, file_lock

EXAMPLE = EXAMPLE_CONFIG


def parse_value(s):
    low = s.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return ""
    body = s[1:] if s.startswith("-") else s
    if body.isdigit():
        return int(s)
    # 소수 — 비율·배수 같은 값이 문자열로 저장되면 계산이 조용히 깨진다.
    # "30%" 도 받아 0.3 으로 바꾼다(비율을 퍼센트로 적는 실수가 잦다).
    if body.endswith("%"):
        try:
            return float(body[:-1]) / 100
        except ValueError:
            return s
    try:
        return float(s)
    except ValueError:
        return s


def set_path(cfg, path, value):
    """점 경로로 값을 넣는다. 숫자 조각은 리스트 인덱스로 취급한다.

    배열 항목(예: offerings.0.margin_rate)을 dict 전용으로 두면 AttributeError 로
    죽는다. 설정 경로가 막히면 그 기능 전체가 잠기므로 배열을 함께 지원한다."""
    keys = path.split(".")
    node = cfg
    for i, k in enumerate(keys[:-1]):
        nxt = keys[i + 1]
        if isinstance(node, list):
            node = node[_as_index(k, node, path)]
            continue
        if k not in node or not isinstance(node[k], (dict, list)):
            node[k] = [] if nxt.isdigit() else {}
        node = node[k]

    last = keys[-1]
    if isinstance(node, list):
        node[_as_index(last, node, path)] = value
    else:
        node[last] = value


def _as_index(k, seq, path):
    if not k.isdigit():
        raise SystemExit(f"[에러] '{path}' — '{k}' 위치는 배열이라 숫자 인덱스가 필요합니다(0부터). 아무것도 저장하지 않았습니다.")
    idx = int(k)
    if idx >= len(seq):
        raise SystemExit(
            f"[에러] '{path}' — 인덱스 {idx} 가 범위를 벗어났습니다(현재 {len(seq)}개). "
            "아무것도 저장하지 않았습니다."
        )
    return idx


def _redact(path, value):
    if any(w in path for w in ("password", "secret", "token", "webhook", "api_key")):
        return "••••••(저장됨)"
    return repr(value)


def main():
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(HOME, exist_ok=True)
        shutil.copy(EXAMPLE, CONFIG_PATH)
        print(f"[config.json 생성됨] {CONFIG_PATH}")

    # 읽고-고치고-쓰기다. 잠그지 않으면 설정 두 건을 동시에 바꿀 때
    # 나중에 저장한 쪽이 앞의 변경을 통째로 지운다(설정은 통짜 재작성이라 부분 병합이 없다).
    # 게다가 여기서 유실되는 건 승인 모드·예산 상한 같은 게이트 값이다.
    with file_lock(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)

        args = sys.argv[1:]
        if not args:
            print("사용: set_config.py path=value [path=value ...]")
            return

        for arg in args:
            if "=" not in arg:
                print(f"[무시] '{arg}' — path=value 형식이 필요합니다.")
                continue
            path, _, raw = arg.partition("=")
            path = path.strip()
            value = parse_value(raw)
            set_path(cfg, path, value)
            print(f"  ✓ {path} = {_redact(path, value)}")

        # 임시 파일에 쓰고 원자적으로 갈아끼운다 — 중간에 끊겨도 설정이 반쪽으로 남지 않는다.
        tmp = f"{CONFIG_PATH}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_PATH)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    print("[저장 완료]")


if __name__ == "__main__":
    main()
