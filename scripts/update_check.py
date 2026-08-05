#!/usr/bin/env python3
"""설치된 코파일럿이 배포본보다 뒤처졌는지 점검하고, 내 수정본을 지키면서 갱신한다.

왜 필요한가 — Claude Code 는 **공식 마켓플레이스만** 자동 갱신을 기본으로 켠다.
서드파티·로컬 마켓플레이스는 기본이 꺼짐이다. 코파일럿은 서드파티라서
아무도 갱신해 주지 않는다. 사용자는 몇 달 전 버전을 쓰면서 그 사실조차 모른다.

뒤처짐은 세 종류이고 원인도 처방도 다르다. 뭉뚱그리면 못 고친다:
  ① 카탈로그가 낡음 — 마켓플레이스 클론이 GitHub보다 뒤  → marketplace update
  ② 설치본이 낡음   — 카탈로그는 최신인데 설치본이 뒤     → plugin update
  ③ 배포가 안 됨    — 작성자가 version 을 안 올림          → 커밋을 밀어도 ①②로 안 넘어옴
③은 작성자만 고칠 수 있다. 개발 리포가 로컬에 있을 때만 그 진단을 켠다.

★ 내 수정본은 갱신에서 말없이 사라진다
플러그인은 버전마다 새 디렉터리에 설치된다(.../1.3.0/ → .../1.4.0/).
그래서 사용자가 설치본 안의 스킬을 고쳐 놨다면, 갱신하는 순간 그 파일은
새 디렉터리에 없고 옛 디렉터리에만 남는다 — 경고도 없이 원상복구된 것처럼 보인다.

이 스크립트는 갱신 전에 **내가 고친 파일을 먼저 찾아내고**, 위쪽 변경과 겹치는지
따져서 취사선택하게 한다. 고른 것은 `~/.<플러그인>/overrides/` 에 보관되어
이후 모든 갱신에 자동 재적용된다. 한 번 고르면 다시 고를 필요가 없다.

    python3 update_check.py                 # 점검만
    python3 update_check.py --custom        # 내가 고친 파일 찾기
    python3 update_check.py --keep <경로>   # 그 파일을 내 것으로 확정(계속 유지)
    python3 update_check.py --drop <경로>   # 내 수정을 버리고 배포본을 따름
    python3 update_check.py --apply         # 갱신(수정본이 있으면 먼저 물어본다)
    python3 update_check.py --apply --force # 미해결 수정본이 있어도 강행
    python3 update_check.py --install-cron  # 주 1회 자동 갱신 등록
"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from common import HOME, log_activity
except Exception:  # 커널이 없어도 점검은 돌아야 한다
    HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")

    def log_activity(*_a, **_k):
        pass

PLUGIN_DIR = os.path.expanduser("~/.claude/plugins")
INSTALLED = os.path.join(PLUGIN_DIR, "installed_plugins.json")
MARKETPLACES = os.path.join(PLUGIN_DIR, "known_marketplaces.json")

# 공식 마켓플레이스는 자동 갱신이 기본 켜짐이라 우리가 챙길 필요가 없다.
OFFICIAL = {"claude-plugins-official", "claude-community", "claude-code-plugins"}

OVERRIDES = os.path.join(HOME, "overrides")
LAUNCHER = os.path.join(HOME, "bin", "copilot-update.sh")
LOG = os.path.join(HOME, "data", "_activity", "update.log")
CRON_TAG = "# copilot-update"

# 비교에서 뺀다 — 실행 부산물이거나 내용이 매번 달라지는 것들.
# `.in_use` 는 Claude Code 가 캐시에 직접 쓰는 사용 중 표시(PID 파일)라 배포본에 없다.
# 빼지 않으면 "사용자가 추가한 파일" 수십 개로 잘못 잡힌다.
SKIP = {"__pycache__", ".git", ".DS_Store", "node_modules", ".in_use", ".pytest_cache"}


# ───────────────────────── 읽기 도우미 ─────────────────────────

def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _git(cwd, *args, binary=False):
    """git 을 조용히 돌리고 stdout 을 준다. 실패하면 None — 호출부가 판단한다."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args],
                           capture_output=True, text=not binary, timeout=20)
        if r.returncode != 0:
            return None
        return r.stdout if binary else r.stdout.strip()
    except Exception:
        return None


def _walk(root):
    """플러그인 트리의 상대경로 집합. 부산물은 뺀다."""
    out = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f in SKIP:
                continue
            out.add(os.path.relpath(os.path.join(base, f), root))
    return out


def _catalog_version(mp_dir, plugin_name):
    """마켓플레이스 클론이 광고하는 버전.

    선언이 두 군데다 — marketplace.json 의 항목과 플러그인 자신의 plugin.json.
    **설치 시점에는 plugin.json 이 이긴다**(claude plugin validate 가 경고하는 그 규칙).
    여기서도 plugin.json 을 우선하고, 어긋나면 둘 다 돌려준다.
    """
    entry_ver = src = None
    cat = _json(os.path.join(mp_dir, ".claude-plugin", "marketplace.json"))
    for e in cat.get("plugins", []) or []:
        if e.get("name") == plugin_name:
            entry_ver, src = e.get("version"), e.get("source") or "./"
            break
    if src is None:
        return None, None, "./"
    sub = src if isinstance(src, str) else "./"
    pj = _json(os.path.join(mp_dir, sub, ".claude-plugin", "plugin.json"))
    return (pj.get("version") or entry_ver), entry_ver, sub


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return None


def _is_behind(installed, catalog):
    """설치본이 카탈로그보다 낮은가. 판단이 안 서면 '다르면 뒤처짐'으로 본다."""
    if not catalog or not installed or installed == catalog:
        return False
    a, b = _ver_tuple(installed), _ver_tuple(catalog)
    return a < b if (a and b) else True


def _dev_repo(name):
    """작성자 진단용 — 같은 이름의 개발 리포가 로컬 홈에 있는가."""
    p = os.path.expanduser(f"~/{name}")
    return p if os.path.isdir(os.path.join(p, ".git")) else None


# ───────────────────── 내 수정본 찾기 (취사선택) ─────────────────────

def _sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _baseline_file(plugin, version):
    return os.path.join(OVERRIDES, ".baseline", f"{plugin}-{version}.json")


def _load_baseline(plugin, version):
    return _json(_baseline_file(plugin, version), {}) or {}


def _save_baseline(plugin, version, manifest):
    """설치 직후의 순정 상태를 지문으로 남긴다.

    왜 필요한가 — 마켓플레이스 클론은 **얕은 복제(depth=1)** 라서 커밋이 하나뿐이다.
    그래서 설치 기록에 남은 SHA 로 되짚으려 해도 그 커밋이 없다.
    기준선이 없으면 '내가 고친 것'과 '원래 그런 것'을 영영 구분할 수 없으므로,
    갱신할 때마다 순정 지문을 직접 남겨 다음 점검의 기준으로 쓴다.
    """
    p = _baseline_file(plugin, version)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=0, sort_keys=True)
    except Exception:
        pass


def _manifest(root):
    out = {}
    for rel in _walk(root):
        try:
            with open(os.path.join(root, rel), "rb") as f:
                out[rel] = _sha(f.read())
        except Exception:
            pass
    return out


def _pristine_source(row):
    """기준선을 어디서 얻을지 정한다. 정확한 순서대로 시도한다.

    ① 저장해 둔 지문      — 이전 갱신 때 남긴 것. 얕은 복제와 무관하게 정확하다.
    ② 클론 자체           — 설치본과 배포본 버전이 같으면 클론이 곧 순정이다.
    ③ git show <설치SHA>  — 전체 복제일 때만 된다.
    셋 다 안 되면 (None, "확인불가") — 추측으로 단정하지 않는다.
    """
    plugin, ver = row["plugin"], row.get("installed")
    saved = _load_baseline(plugin, ver)
    if saved:
        return ("manifest", saved)

    clone, sub = row.get("clone"), row.get("sub", "./")
    head_dir = os.path.join(clone, sub) if clone else None
    # 클론을 순정으로 쓰려면 **설치된 그 커밋 그대로**여야 한다.
    # 버전만 같은 것으로는 부족하다 — 작성자가 version 을 안 올린 채 커밋을 밀면
    # 클론은 앞서 나가 있고, 그걸 기준선으로 삼으면 위쪽 변경이 전부
    # "사용자가 고친 파일"로 둔갑한다(실제로 그렇게 오탐이 났다).
    if (head_dir and os.path.isdir(head_dir) and row.get("sha")
            and _git(clone, "rev-parse", "HEAD") == row["sha"]):
        m = _manifest(head_dir)
        _save_baseline(plugin, ver, m)  # 다음부터는 ①로 빠르게 간다
        return ("manifest", m)

    sha = row.get("sha")
    if sha and clone and _git(clone, "cat-file", "-t", sha) == "commit":
        return ("git", sha)

    return (None, None)


def scan_custom(row):
    """설치본에서 사용자가 손댄 파일을 찾아 네 갈래로 나눈다.

    added    — 사용자가 새로 넣은 파일. 위쪽과 겹칠 일이 없으니 항상 안전하다.
    safe     — 내가 고쳤고 위쪽은 그대로. 그대로 들고 가면 된다.
    conflict — 내가 고쳤는데 위쪽도 고쳤다. 여기서만 사람이 골라야 한다.
    unknown  — 기준선이 없어 판정 불가. 모르면 모른다고 한다(추측해서 덮지 않는다).
    """
    res = {"added": [], "safe": [], "conflict": [], "kept": [], "unknown": []}
    inst, clone, sub = row.get("install_path"), row.get("clone"), row.get("sub", "./")
    if not (inst and os.path.isdir(inst)):
        return res

    over = os.path.join(OVERRIDES, row["plugin"])
    kept = set(_walk(over)) if os.path.isdir(over) else set()
    res["kept"] = sorted(kept)

    kind, base_src = _pristine_source(row)
    head_dir = os.path.join(clone, sub) if clone else None

    def _base(rel):
        """설치 당시 순정 내용(또는 그 지문). 없으면 None."""
        if kind == "manifest":
            return base_src.get(rel)          # sha256 문자열
        if kind == "git":
            # normpath 가 이미 선행 "./" 를 없앤다. lstrip("./") 를 쓰면 안 된다 —
            # 문자 집합을 깎아서 ".gitignore" 를 "gitignore" 로 만들어 버린다.
            blob = _git(clone, "show", f"{base_src}:{os.path.normpath(os.path.join(sub, rel))}", binary=True)
            return _sha(blob) if blob is not None else None
        return None

    for rel in sorted(_walk(inst)):
        if rel in kept:
            continue  # 이미 내 것으로 확정된 파일 — 다시 묻지 않는다
        try:
            with open(os.path.join(inst, rel), "rb") as f:
                mine = _sha(f.read())
        except Exception:
            continue

        if kind is None:
            # 기준선이 없다. 배포본에 아예 없는 파일만 '추가'로 단정할 수 있다.
            up = os.path.join(head_dir, rel) if head_dir else None
            if up and not os.path.isfile(up):
                res["added"].append(rel)
            elif up:
                try:
                    with open(up, "rb") as f:
                        if _sha(f.read()) != mine:
                            res["unknown"].append(rel)
                except Exception:
                    pass
            continue

        b = _base(rel)
        if b is None:
            res["added"].append(rel)   # 설치 당시 순정에 없던 파일 = 사용자가 넣은 것
            continue
        if mine == b:
            continue                   # 안 건드렸다

        # 내가 고쳤다. 위쪽도 그 사이에 고쳤는지 본다.
        upstream_changed = True
        up = os.path.join(head_dir, rel) if head_dir else None
        if up and os.path.isfile(up):
            try:
                with open(up, "rb") as f:
                    upstream_changed = _sha(f.read()) != b
            except Exception:
                pass
        (res["conflict"] if upstream_changed else res["safe"]).append(rel)

    return res


def keep(row, rels):
    """고른 파일을 overrides 로 옮겨 영구 보관한다 — 이후 갱신마다 자동 재적용된다."""
    dst_root = os.path.join(OVERRIDES, row["plugin"])
    done = []
    for rel in rels:
        src = os.path.join(row["install_path"], rel)
        if not os.path.isfile(src):
            print(f"  건너뜀 — 설치본에 없는 경로: {rel}")
            continue
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        done.append(rel)
    if done:
        log_activity("update", f"{row['plugin']} 사용자 수정본 확정: {', '.join(done)}")
        print(f"  {len(done)}개 파일을 내 것으로 확정했습니다 → {dst_root}")
        print("  이후 갱신에서 자동으로 다시 얹힙니다.")
    return done


def drop(row, rels):
    """확정을 취소한다 — 다음 갱신부터 배포본을 따른다."""
    dst_root = os.path.join(OVERRIDES, row["plugin"])
    n = 0
    for rel in rels:
        p = os.path.join(dst_root, rel)
        if os.path.isfile(p):
            os.remove(p)
            n += 1
    if n:
        print(f"  {n}개 파일의 확정을 취소했습니다 — 다음 갱신에서 배포본으로 돌아갑니다.")
    return n


def reapply(row):
    """overrides 를 현재 설치본에 다시 얹는다. 갱신 직후에 부른다."""
    src_root = os.path.join(OVERRIDES, row["plugin"])
    if not os.path.isdir(src_root):
        return []
    inst = row.get("install_path")
    if not (inst and os.path.isdir(inst)):
        return []
    done = []
    for rel in sorted(_walk(src_root)):
        src, dst = os.path.join(src_root, rel), os.path.join(inst, rel)
        if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        done.append(rel)
    if done:
        log_activity("update", f"{row['plugin']} 수정본 {len(done)}개 재적용")
    return done


def show_diff(row, rel):
    """내 것과 배포본의 차이를 보여준다 — 고르기 전에 눈으로 확인하라고."""
    inst, clone, sub = row["install_path"], row["clone"], row.get("sub", "./")
    mine, theirs = os.path.join(inst, rel), os.path.join(clone, sub, rel)
    if not os.path.isfile(theirs):
        print(f"  배포본에는 없는 파일입니다(내가 추가한 것): {rel}")
        return
    r = subprocess.run(["diff", "-u", "--label", f"배포본/{rel}", theirs,
                        "--label", f"내것/{rel}", mine],
                       capture_output=True, text=True, timeout=20)
    print(r.stdout or "  (차이 없음)")


# ───────────────────────── 점검 ─────────────────────────

def scan():
    installed = _json(INSTALLED).get("plugins", {})
    markets = _json(MARKETPLACES)
    out = []

    for key, entries in installed.items():
        if "@" not in key or not entries:
            continue
        plugin, market = key.rsplit("@", 1)
        if market in OFFICIAL:
            continue

        e0 = entries[0]
        mp = markets.get(market) or {}
        clone = mp.get("installLocation") or os.path.join(PLUGIN_DIR, "marketplaces", market)
        cat_ver, entry_ver, sub = _catalog_version(clone, plugin)
        cur = e0.get("version")

        row = {
            "plugin": plugin,
            "marketplace": market,
            "installed": cur,
            "catalog": cat_ver,
            "install_path": e0.get("installPath"),
            "sha": e0.get("gitCommitSha"),
            "clone": clone,
            "sub": sub,
            # 명시 키가 없으면 서드파티는 꺼짐이 기본이다
            "auto_update": bool(mp.get("autoUpdate", market in OFFICIAL)),
            "behind": _is_behind(cur, cat_ver),
            "issues": [],
        }

        # ① 카탈로그 자체가 낡았는가 (클론이 origin 보다 뒤)
        if os.path.isdir(os.path.join(clone, ".git")):
            _git(clone, "fetch", "--quiet", "origin")
            head = _git(clone, "symbolic-ref", "--short", "HEAD") or "main"
            behind = _git(clone, "rev-list", "--count", f"HEAD..origin/{head}")
            if behind and behind.isdigit() and int(behind) > 0:
                row["issues"].append(("카탈로그", f"마켓플레이스가 원본보다 {behind}커밋 뒤처짐"))

        # ② 설치본이 카탈로그보다 낮은가
        if row["behind"]:
            row["issues"].append(("설치본", f"{cur} → {cat_ver} 로 올릴 수 있음"))

        # ③ 작성자 함정 — 개발 리포가 로컬에 있을 때만
        dev = _dev_repo(plugin)
        if dev:
            row["dev_repo"] = dev
            dev_pj = _json(os.path.join(dev, ".claude-plugin", "plugin.json")).get("version")
            dev_mj = None
            for e in _json(os.path.join(dev, ".claude-plugin", "marketplace.json")).get("plugins", []) or []:
                if e.get("name") == plugin:
                    dev_mj = e.get("version")
                    break

            if dev_pj and dev_mj and dev_pj != dev_mj:
                row["issues"].append(
                    ("작성자", f"버전 선언 불일치 — plugin.json {dev_pj} vs marketplace.json {dev_mj}"))

            _git(dev, "fetch", "--quiet", "origin")
            br = _git(dev, "symbolic-ref", "--short", "HEAD") or "main"
            ahead = _git(dev, "rev-list", "--count", f"origin/{br}..HEAD")
            if ahead and ahead.isdigit() and int(ahead) > 0:
                row["issues"].append(("작성자", f"미푸시 {ahead}커밋 — 밀지 않으면 아무에게도 안 간다"))

            dirty = _git(dev, "status", "--porcelain")
            if dirty:
                row["issues"].append(("작성자", f"미커밋 {len(dirty.splitlines())}개 파일"))

            # version 을 안 올린 채 커밋만 쌓였는가 — 사용자에게 영원히 안 간다
            if dev_pj and cat_ver and dev_pj == cat_ver == cur:
                last = _git(dev, "log", "-1", "--format=%h", "--", ".claude-plugin/plugin.json")
                head_sha = _git(dev, "rev-parse", "--short", "HEAD")
                if last and head_sha and last != head_sha:
                    n = _git(dev, "rev-list", "--count", f"{last}..HEAD")
                    if n and n.isdigit() and int(n) > 0:
                        row["issues"].append(
                            ("작성자", f"version({dev_pj}) 을 안 올린 채 {n}커밋 — 갱신이 사용자에게 안 간다"))

        out.append(row)

    return sorted(out, key=lambda r: (not r["issues"], r["plugin"]))


# ───────────────────────── 갱신 ─────────────────────────

def apply(rows, force=False, verbose=True):
    """실제 갱신. 미해결 수정본이 있으면 **멈춘다** — 말없이 덮어쓰지 않는다."""
    claude = shutil.which("claude")
    if not claude:
        if verbose:
            print("  claude 명령을 못 찾았습니다 — 갱신을 건너뜁니다.")
        return []

    targets = [r for r in rows if r["behind"] or any(k == "카탈로그" for k, _ in r["issues"])]
    if not targets:
        return []

    if not force:
        blocked = []
        for r in targets:
            c = scan_custom(r)
            pending = c["conflict"] + c["safe"] + c["added"] + c["unknown"]
            if pending:
                blocked.append((r, c))
        if blocked:
            print("  ⛔ 갱신을 멈췄습니다 — 아직 고르지 않은 수정본이 있습니다.\n")
            for r, c in blocked:
                _print_custom(r, c, indent="    ")
            print("    --keep 로 지킬 것을 고르거나, --drop 으로 버리거나, --force 로 강행하세요.")
            return []

    done = []
    for market in sorted({r["marketplace"] for r in targets}):
        subprocess.run([claude, "plugin", "marketplace", "update", market],
                       capture_output=True, text=True, timeout=180)

    for r in targets:
        p = subprocess.run([claude, "plugin", "update", f"{r['plugin']}@{r['marketplace']}"],
                           capture_output=True, text=True, timeout=180)
        lines = (p.stdout or p.stderr or "").strip().splitlines()
        msg = lines[-1] if lines else ""
        if "updated from" in msg:
            done.append((r["plugin"], msg))
            log_activity("update", f"{r['plugin']} 갱신: {msg}")
        if verbose and msg:
            print(f"  {msg}")

    # 갱신되면 설치 경로가 새 버전 디렉터리로 바뀐다.
    # 순서가 중요하다 — 내 수정본을 얹기 **전에** 순정 지문을 찍어야
    # 다음 점검이 '내가 고친 것'을 정확히 가려낼 수 있다.
    for r in scan():
        if r.get("install_path") and os.path.isdir(r["install_path"]):
            if not _load_baseline(r["plugin"], r.get("installed")):
                _save_baseline(r["plugin"], r.get("installed"), _manifest(r["install_path"]))
        back = reapply(r)
        if back and verbose:
            print(f"  {r['plugin']}: 내 수정본 {len(back)}개를 새 버전에 다시 얹었습니다.")

    return done


# ───────────────────────── 자동 등록 ─────────────────────────

def install_cron():
    """주 1회 자동 갱신을 crontab 에 건다.

    크론이 캐시 경로를 직접 가리키면 안 된다 — 갱신될 때마다 버전 디렉터리가 바뀌어
    다음 주에 경로가 사라진다. 그래서 상태 디렉터리에 고정 런처를 두고 그걸 부른다.
    """
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    here = os.path.abspath(__file__)

    with open(LAUNCHER, "w", encoding="utf-8") as f:
        f.write(
            "#!/bin/sh\n"
            "# 코파일럿 자동 갱신 — Claude Code 는 서드파티 마켓플레이스를 자동 갱신하지 않는다.\n"
            "# 점검 스크립트가 살아 있으면 그쪽을 쓴다(내 수정본을 지켜 준다).\n"
            "# 갱신으로 경로가 바뀔 수 있으므로, 사라졌으면 claude CLI 로 폴백한다.\n"
            f'CHECK="{here}"\n'
            'if [ -f "$CHECK" ]; then\n'
            '  exec python3 "$CHECK" --apply --quiet\n'
            "fi\n"
            'CLAUDE="$(command -v claude)" || exit 0\n'
            '[ -n "$CLAUDE" ] || exit 0\n'
            '"$CLAUDE" plugin marketplace update 2>&1\n'
        )
    os.chmod(LAUNCHER, 0o755)

    line = f"30 9 * * 1 {LAUNCHER} >> {LOG} 2>&1  {CRON_TAG}"
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15)
        existing = cur.stdout if cur.returncode == 0 else ""
    except Exception:
        print("  crontab 을 읽지 못했습니다. 아래 줄을 직접 등록하세요:\n  " + line)
        return False

    if CRON_TAG in existing:
        print(f"  이미 등록돼 있습니다 → {LAUNCHER}")
        return True

    body = (existing.rstrip("\n") + "\n" if existing.strip() else "") + line + "\n"
    try:
        subprocess.run(["crontab", "-"], input=body, text=True, timeout=15, check=True)
    except Exception:
        print("  crontab 등록에 실패했습니다. 아래 줄을 직접 넣어 주세요:\n  " + line)
        return False

    print(f"  매주 월요일 09:30 자동 갱신 등록 완료 → 로그 {LOG}")
    log_activity("update", "주간 자동 갱신 크론 등록")
    return True


# ───────────────────────── 출력 ─────────────────────────

def _print_custom(row, c, indent="  "):
    if not any((c["conflict"], c["safe"], c["added"], c["kept"], c["unknown"])):
        return
    print(f"{indent}▸ {row['plugin']} — 내가 손댄 파일")
    for rel in c["conflict"]:
        print(f"{indent}    ⚠️  {rel}  (배포본도 바뀜 — 골라야 합니다)")
    for rel in c["unknown"]:
        print(f"{indent}    ?  {rel}  (기준선이 없어 판정 불가 — --diff 로 확인하세요)")
    for rel in c["safe"]:
        print(f"{indent}    ·  {rel}  (배포본은 그대로 — 유지해도 안전)")
    for rel in c["added"]:
        print(f"{indent}    +  {rel}  (내가 추가 — 유지 권장)")
    for rel in c["kept"]:
        print(f"{indent}    ✓  {rel}  (이미 내 것으로 확정됨)")
    print()


def report(rows, quiet=False):
    stale = [r for r in rows if r["issues"]]
    if quiet and not stale:
        return 0

    if not stale:
        print("📦 설치된 코파일럿이 전부 최신입니다.")
        off = [r["plugin"] for r in rows if not r["auto_update"]]
        if off:
            print(f"   (자동 갱신 꺼짐: {', '.join(off)} — 주 1회 점검을 걸어두면 좋습니다)")
        return 0

    print("📦 갱신할 것이 있습니다.\n")
    for r in stale:
        head = f"  ▸ {r['plugin']}  설치본 {r['installed']}"
        if r["catalog"] and r["catalog"] != r["installed"]:
            head += f" · 배포본 {r['catalog']}"
        print(head)
        for kind, msg in r["issues"]:
            print(f"      [{kind}] {msg}")
        print()

    if any(k == "작성자" for r in stale for k, _ in r["issues"]):
        print("  ⚠️  [작성자] 항목은 사용자 쪽에서 아무리 갱신해도 안 옵니다 — 배포부터 고쳐야 합니다.\n")
    return 1


def _pick(rows, name):
    if name:
        for r in rows:
            if r["plugin"] == name:
                return r
        print(f"  설치 목록에 없습니다: {name}")
        return None
    if len(rows) == 1:
        return rows[0]
    print("  플러그인을 --plugin 으로 지정하세요: " + ", ".join(r["plugin"] for r in rows))
    return None


def main():
    ap = argparse.ArgumentParser(description="코파일럿 갱신 점검 — 내 수정본은 지킨다")
    ap.add_argument("--apply", action="store_true", help="실제로 갱신한다")
    ap.add_argument("--force", action="store_true", help="미해결 수정본이 있어도 강행")
    ap.add_argument("--quiet", action="store_true", help="뒤처진 게 있을 때만 출력(훅·크론용)")
    ap.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    ap.add_argument("--custom", action="store_true", help="내가 고친 파일을 찾는다")
    ap.add_argument("--keep", nargs="+", metavar="경로", help="그 파일을 내 것으로 확정")
    ap.add_argument("--drop", nargs="+", metavar="경로", help="확정을 취소하고 배포본을 따름")
    ap.add_argument("--diff", metavar="경로", help="내 것과 배포본의 차이를 본다")
    ap.add_argument("--plugin", metavar="이름", help="대상 플러그인(여러 개 설치했을 때)")
    ap.add_argument("--install-cron", action="store_true", help="주 1회 자동 갱신 등록")
    a = ap.parse_args()

    if a.install_cron:
        return 0 if install_cron() else 1

    rows = scan()
    if not rows:
        print("  서드파티 코파일럿이 설치돼 있지 않습니다.")
        return 0

    if a.json:
        for r in rows:
            r["custom"] = scan_custom(r)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if a.diff:
        r = _pick(rows, a.plugin)
        return 0 if (r and show_diff(r, a.diff) is None) else 1

    if a.keep or a.drop:
        r = _pick(rows, a.plugin)
        if not r:
            return 1
        if a.keep:
            keep(r, a.keep)
        if a.drop:
            drop(r, a.drop)
        return 0

    if a.custom:
        found = False
        for r in rows:
            c = scan_custom(r)
            if any((c["conflict"], c["safe"], c["added"], c["kept"], c["unknown"])):
                found = True
                _print_custom(r, c)
        if not found:
            print("  설치본을 손댄 흔적이 없습니다 — 그냥 갱신하셔도 됩니다.")
        else:
            print("  --keep <경로> 로 지킬 것을 고르고, --diff <경로> 로 차이를 볼 수 있습니다.")
        return 0

    code = report(rows, quiet=a.quiet)

    if a.apply:
        done = apply(rows, force=a.force, verbose=not a.quiet)
        if done:
            print("\n  갱신본은 다음 세션부터 적용됩니다 (지금 적용하려면 /reload-plugins).")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
