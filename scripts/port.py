#!/usr/bin/env python3
"""이 플러그인을 다른 에이전트로 내보낸다. 정본은 건드리지 않는다.

스킬은 **공통 경로 하나**로 나간다 — `~/.agents/skills`.
Copilot·Codex·Cursor·Zed·Antigravity 가 전부 이 경로를 읽는다. 한 번 내보내면
다섯이 같이 본다. 에이전트마다 따로 복사하면 사본이 다섯 벌이 되고 곧 갈라진다.

왜 `~/.claude/` 가 아닌가 — Copilot·Cursor·Cline 은 `~/.claude/skills` 와
`~/.claude/settings.json` 도 읽는다. 그런데 그건 **Claude Code 자기 파일**이다.
거기 내보내면 Claude Code 에서 플러그인 스킬과 복사본이 둘 다 잡히고,
훅은 플러그인 정의와 settings 정의가 **이중으로 발동**한다.
`~/.agents/` 는 Claude Code 가 안 읽으므로 충돌 면이 0이다.

훅은 공통 경로가 없다 — 에이전트마다 설정 파일 위치와 문법이 다르다.
그래서 훅만 타깃별로 쓰되, **전부 같은 디스패처 하나**를 가리키게 한다.

이름 충돌 — 4형제는 같은 이름의 스킬을 12개 갖는다(setup·method·help…).
Claude Code 는 `플러그인:스킬` 로 네임스페이스를 붙이지만 Copilot 의 스킬 목록은
평면이다. 그래서 내보낼 때 `<접두어>-<이름>` 으로 바꾼다.

    port.py --target copilot            # 무엇이 생길지 보기만
    port.py --target copilot --apply    # 실제로 내보내기
    port.py --target copilot --remove   # 내보낸 것 걷어내기
    port.py --status                    # 지금 무엇이 나가 있나
"""

import argparse
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREFIX = {
    "marketing-copilot": "mkt",
    "sales-copilot": "sales",
    "pm-copilot": "pm",
    "business-copilot": "biz",
}

# Copilot 의 SKILL.md 스키마 상한. 넘으면 조용히 잘리는 게 아니라 스킬이 안 잡힌다.
MAX_NAME = 64
MAX_DESC = 1024

# 스킬 — 공통 경로 하나. 여러 에이전트가 동시에 읽는다.
AGENTS_HOME = os.environ.get("AGENTS_HOME", "").strip() or os.path.expanduser("~/.agents")
SKILLS_OUT = os.path.join(AGENTS_HOME, "skills")

# 훅 — 공통 경로가 없어 타깃별로 쓴다. 가리키는 디스패처는 하나다.
HOOK_TARGETS = {
    "copilot": os.path.expanduser("~/.copilot/hooks"),
    "cursor":  os.path.expanduser("~/.cursor"),
}

SKIP = {"__pycache__", ".DS_Store", ".git"}


def plugin_name():
    try:
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("name") or os.path.basename(ROOT)
    except Exception:
        return os.path.basename(ROOT)


def prefix():
    return PREFIX.get(plugin_name(), plugin_name().split("-")[0])


def _front(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1), m.end()) if m else ("", 0)


def _field(front, key):
    m = re.search(rf"^{key}:\s*(.+)$", front, re.M)
    return m.group(1).strip() if m else ""


def _rewrite_body(body, name_map):
    """다른 런타임에서도 풀리도록 경로·링크를 고친다.

    ① `$(플러그인 --root)` — Copilot 은 bin/ 을 PATH 에 넣어 주지 않는다.
       생성 시점의 절대 경로로 박는다.
    ② `skills/<x>/<y>.md` — 평면 배치에서는 폴더 밖 참조가 도달 불가다.
       역시 절대 경로로 바꾼다.
    ③ `[[스킬]]` — 이름이 바뀌었으므로 새 이름으로 맞춘다. 안 맞추면
       1,000건이 넘는 상호참조가 통째로 허공을 가리킨다.
    """
    p = plugin_name()
    body = body.replace(f"$({p} --root)", ROOT)
    body = re.sub(r"`?(skills/[a-z0-9-]+/[a-z0-9._-]+\.md)`?",
                  lambda m: f"`{os.path.join(ROOT, m.group(1))}`", body)
    # bin 디스패처 호출 → 절대 경로
    body = re.sub(rf"(?<![\w/-]){re.escape(p)} ([a-z_]+)",
                  lambda m: f'"{os.path.join(ROOT, "bin", p)}" {m.group(1)}', body)
    body = re.sub(r"\[\[([a-z0-9-]+)\]\]",
                  lambda m: f"[[{name_map.get(m.group(1), m.group(1))}]]", body)
    return body


def plan():
    """무엇을 내보낼지 계산한다. 파일은 건드리지 않는다."""
    pre = prefix()
    src = os.path.join(ROOT, "skills")
    items, problems = [], []
    if not os.path.isdir(src):
        return items, ["skills/ 디렉터리가 없습니다"]

    name_map = {}
    for d in sorted(os.listdir(src)):
        f = os.path.join(src, d, "SKILL.md")
        if not os.path.isfile(f):
            continue
        front, _ = _front(open(f, encoding="utf-8").read())
        name_map[_field(front, "name") or d] = f"{pre}-{_field(front, 'name') or d}"

    for d in sorted(os.listdir(src)):
        sd = os.path.join(src, d)
        f = os.path.join(sd, "SKILL.md")
        if not os.path.isfile(f):
            continue
        text = open(f, encoding="utf-8").read()
        front, end = _front(text)
        name = _field(front, "name") or d
        desc = _field(front, "description")
        new = f"{pre}-{name}"

        if len(new) > MAX_NAME:
            problems.append(f"{new}: 이름이 {MAX_NAME}자를 넘습니다 ({len(new)})")
        if not re.fullmatch(r"[a-z0-9-]+", new):
            problems.append(f"{new}: 이름에 소문자·숫자·하이픈만 쓸 수 있습니다")
        if len(desc) > MAX_DESC:
            problems.append(f"{new}: description 이 {MAX_DESC}자를 넘습니다 ({len(desc)})")

        extras = [x for x in sorted(os.listdir(sd))
                  if x != "SKILL.md" and x not in SKIP and os.path.isfile(os.path.join(sd, x))]
        items.append({"src": sd, "name": name, "new": new,
                      "out": os.path.join(SKILLS_OUT, new),
                      "extras": extras, "front": front, "end": end,
                      "text": text, "map": name_map})
    return items, problems


def apply(items):
    made = 0
    for it in items:
        out = it["out"]
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(out, exist_ok=True)

        front = re.sub(r"^name:\s*.+$", f"name: {it['new']}", it["front"], count=1, flags=re.M)
        body = _rewrite_body(it["text"][it["end"]:], it["map"])
        with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(f"---\n{front}\n---\n{body}")

        for x in it["extras"]:
            shutil.copy2(os.path.join(it["src"], x), os.path.join(out, x))
        made += 1
    return made


def write_hooks(target="copilot"):
    """훅 설정을 쓴다. 스킬과 달리 공통 경로가 없어 타깃별로 쓴다.

    ⚠️ Copilot 은 matcher 값을 **무시하고 모든 툴에서 훅을 돌린다.**
    그래서 PostToolUse 훅은 자기가 입력을 보고 걸러야 한다
    (hook_posttool.py 는 이미 그렇게 돼 있다 — 파일 경로가 없으면 조용히 끝난다).
    """
    p = plugin_name()
    disp = os.path.join(ROOT, "bin", p)
    cfg = {"hooks": {}}
    for event, script in [("SessionStart", "proactive"),
                          ("UserPromptSubmit", "hook_prompt"),
                          ("PostToolUse", "hook_posttool"),
                          ("Stop", "hook_sessionend")]:
        cfg["hooks"][event] = [{"hooks": [{"type": "command",
                                           "command": f'"{disp}" {script}',
                                           "timeout": 15}]}]

    written = []
    targets = HOOK_TARGETS.keys() if target == "all" else [target]
    for t in targets:
        d = HOOK_TARGETS.get(t)
        if not d:
            continue
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{p}.json" if t == "copilot" else "hooks.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        written.append(path)
    return written


def remove():
    pre = prefix()
    n = 0
    if os.path.isdir(SKILLS_OUT):
        for d in sorted(os.listdir(SKILLS_OUT)):
            if d.startswith(pre + "-"):
                shutil.rmtree(os.path.join(SKILLS_OUT, d), ignore_errors=True)
                n += 1
    for d in HOOK_TARGETS.values():
        for fn in (f"{plugin_name()}.json", "hooks.json"):
            h = os.path.join(d, fn)
            if os.path.isfile(h):
                try:
                    if json.load(open(h, encoding="utf-8")).get("hooks", {}).get("SessionStart"):
                        os.remove(h)
                except Exception:
                    pass
    return n


def status():
    pre = prefix()
    out = [d for d in sorted(os.listdir(SKILLS_OUT))] if os.path.isdir(SKILLS_OUT) else []
    mine = [d for d in out if d.startswith(pre + "-")]
    print(f"플러그인: {plugin_name()} (접두어 {pre}-)")
    print(f"내보낸 곳: {SKILLS_OUT}")
    print(f"  내 스킬 {len(mine)}개 / 그 경로 전체 {len(out)}개")
    for t, d in HOOK_TARGETS.items():
        for fn in (f"{plugin_name()}.json", "hooks.json"):
            h = os.path.join(d, fn)
            if os.path.isfile(h):
                print(f"  훅({t}): {h}")
    others = sorted({d.split("-")[0] for d in out if not d.startswith(pre + "-")})
    if others:
        print(f"  같은 곳의 다른 코파일럿: {', '.join(others)}")


def main():
    ap = argparse.ArgumentParser(description="다른 에이전트로 내보내기 (정본은 안 고친다)")
    ap.add_argument("--hooks", choices=["copilot", "cursor", "all", "none"], default="copilot",
                    help="훅을 어느 에이전트용으로 쓸지 (스킬은 항상 공통 경로)")
    ap.add_argument("--apply", action="store_true", help="실제로 내보낸다")
    ap.add_argument("--remove", action="store_true", help="내보낸 것을 걷어낸다")
    ap.add_argument("--status", action="store_true", help="지금 무엇이 나가 있나")
    a = ap.parse_args()

    if a.status:
        status()
        return 0

    if a.remove:
        n = remove()
        print(f"  스킬 {n}개와 훅 설정을 걷어냈습니다.")
        return 0

    items, problems = plan()
    if problems:
        print("⛔ 내보내기 전에 고쳐야 할 것:")
        for w in problems:
            print(f"   · {w}")
        return 2

    print(f"스킬 {len(items)}개 → {SKILLS_OUT}  (공통 경로 — Copilot·Codex·Cursor·Zed·Antigravity 가 함께 읽음)")
    print(f"이름: {items[0]['name']} → {items[0]['new']} (…이하 동일 규칙)")
    if not a.apply:
        print("\n  --apply 를 붙이면 실제로 내보냅니다. 정본(skills/)은 건드리지 않습니다.")
        return 0

    n = apply(items)
    print(f"  스킬 {n}개 내보냄")
    if a.hooks != "none":
        for h in write_hooks(a.hooks):
            print(f"  훅 설정 {h}")
    print("\n  에이전트를 다시 열면 잡힙니다. 채팅에서 '/' 를 치면 목록에 나옵니다.")
    print("  ⚠️ Copilot 은 훅 matcher 를 무시하고 모든 툴에서 돌립니다 —")
    print("     PostToolUse 훅은 자기가 걸러야 합니다(이미 그렇게 돼 있습니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
