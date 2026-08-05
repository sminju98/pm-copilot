#!/usr/bin/env python3
"""확산량 — 이 플러그인이 얼마나 퍼졌나. GitHub 지표를 매일 떠서 영구 보관한다.

텔레메트리를 넣지 않는 이유는 이걸로 충분하기 때문이다. 사용자 컴퓨터에서
아무것도 받아오지 않아도 **클론 수·고유 방문자**로 확산은 다 보인다.
사용자에게 아무것도 묻지 않고, 아무것도 보내게 하지 않는다.

왜 필요한가:
  GitHub 트래픽 API는 **최근 14일치만** 준다. 스냅샷을 안 뜨면 그 이전은 영원히 사라진다.
  또 조회·클론은 UTC 일 단위 집계라 활동 시점 기준 **약 이틀 뒤**에야 보인다
  (실측: 버킷 마감 후 13~25시간). 반면 별·포크는 실시간이다.
  그래서 매일 한 번씩 떠서 쌓아두면, 지연과 무관하게 나중에 전체 시계열을 볼 수 있다.

무엇을 저장하나:
  data/github-traffic/daily.jsonl   — 하루 한 줄, 레포별 지표 스냅샷
  data/github-traffic/events.jsonl  — 별·포크 이벤트(취소분까지 이력에 남음, 중복 제거)

  ⚠️ 이벤트 API는 최근 300건·약 90일까지만 보관하므로, 이것도 스냅샷이 있어야 영구 기록이 된다.

사용:
  reach.py                 # 스냅샷 1회
  reach.py --show          # 쌓인 시계열 요약 출력
  reach.py --repos a,b,c   # 대상 지정

전제: gh CLI 로그인 (`gh auth status`). 트래픽 API는 레포 push 권한이 필요하다.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

HOME = os.environ.get("PM_COPILOT_HOME", "").strip() or os.path.expanduser("~/.pm-copilot")
OUT_DIR = os.path.join(HOME, "data", "github-traffic")
DAILY = os.path.join(OUT_DIR, "daily.jsonl")
EVENTS = os.path.join(OUT_DIR, "events.jsonl")

OWNER = "sminju98"
REPOS = [
    "pm-copilot",
    "marketing-copilot",
    "sales-copilot",
    "business-copilot",
    "myeongham-sales-plugin",
]


def gh(path, jq=None, accept=None):
    """gh api 호출. 실패해도 죽지 않고 None 반환(무인 실행용)."""
    cmd = ["gh", "api", path]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    if jq:
        cmd += ["--jq", jq]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] {path}: {e}", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"  [경고] {path}: {r.stderr.strip()[:120]}", file=sys.stderr)
        return None
    out = r.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def snapshot_repo(repo):
    """레포 하나의 현재 지표. 트래픽은 지연되므로 '일자별 원본'을 통째로 보관한다."""
    full = f"repos/{OWNER}/{repo}"
    meta = gh(full) or {}
    clones = gh(f"{full}/traffic/clones") or {}
    views = gh(f"{full}/traffic/views") or {}
    refs = gh(f"{full}/traffic/popular/referrers") or []
    return {
        "repo": repo,
        # 실시간 지표
        "stars": meta.get("stargazers_count"),
        "forks": meta.get("forks_count"),
        "watchers": meta.get("subscribers_count"),
        "open_issues": meta.get("open_issues_count"),
        "created_at": meta.get("created_at"),
        # 지연 지표 — 일자별 원본을 그대로 남긴다(나중에 재계산·보정 확인 가능)
        "clones_total": clones.get("count"),
        "clones_uniques": clones.get("uniques"),
        "clones_daily": clones.get("clones", []),
        "views_total": views.get("count"),
        "views_uniques": views.get("uniques"),
        "views_daily": views.get("views", []),
        "referrers": refs,
        "traffic_last_day": (clones.get("clones") or [{}])[-1].get("timestamp", "")[:10] or None,
    }


def snapshot_events(repo, seen):
    """별·포크 이벤트. 카운트에는 안 남는 '취소분'까지 이력에 잡힌다."""
    rows = gh(f"repos/{OWNER}/{repo}/events") or []
    if not isinstance(rows, list):
        return []
    out = []
    for e in rows:
        if e.get("type") not in ("WatchEvent", "ForkEvent"):
            continue
        key = (repo, e.get("id"))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "repo": repo,
            "event_id": e.get("id"),
            "type": e.get("type"),
            "actor": (e.get("actor") or {}).get("login"),
            "created_at": e.get("created_at"),
        })
    return out


def load_seen_events():
    seen = set()
    if not os.path.exists(EVENTS):
        return seen
    with open(EVENTS, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add((r.get("repo"), r.get("event_id")))
    return seen


def append(path, rows):
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def cmd_snapshot(repos):
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    seen = load_seen_events()
    snaps, evs = [], []
    for r in repos:
        s = snapshot_repo(r)
        s["snapshot_at"] = now
        snaps.append(s)
        evs += snapshot_events(r, seen)
    n1 = append(DAILY, snaps)
    n2 = append(EVENTS, evs)

    print(f"📸 스냅샷 {now}")
    print(f"  저장: {DAILY} (+{n1}행) · {EVENTS} (+{n2}행 — 신규 별·포크 이벤트)")
    print()
    print(f"  {'레포':<24} {'⭐':>3} {'🍴':>3} {'클론(순)':>12} {'조회(순)':>12}  트래픽 마지막")
    for s in snaps:
        cl = f"{s['clones_total']}({s['clones_uniques']})" if s["clones_total"] is not None else "-"
        vw = f"{s['views_total']}({s['views_uniques']})" if s["views_total"] is not None else "-"
        print(f"  {s['repo']:<24} {str(s['stars']):>3} {str(s['forks']):>3} {cl:>12} {vw:>12}  {s['traffic_last_day'] or '-'}")
    if evs:
        print("\n  🆕 새 별·포크:")
        for e in evs:
            print(f"     {e['created_at']}  {e['type']}  {e['actor']}  ({e['repo']})")
    print("\n  ⚠️ 조회·클론은 활동 시점 기준 약 이틀 뒤에 반영된다(별·포크는 실시간).")


def cmd_show():
    if not os.path.exists(DAILY):
        raise SystemExit(f"[없음] {DAILY} — 먼저 스냅샷을 한 번 뜨세요: python3 {os.path.basename(__file__)}")
    rows = []
    with open(DAILY, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not rows:
        raise SystemExit("[비어 있음]")

    # 레포별로 '일자별 원본'을 합쳐 중복 제거 — 스냅샷을 여러 번 떠도 날짜당 최신값만 남는다.
    per = {}
    for r in rows:
        d = per.setdefault(r["repo"], {"clones": {}, "views": {}, "stars": None, "forks": None})
        for c in r.get("clones_daily") or []:
            d["clones"][c["timestamp"][:10]] = (c.get("count"), c.get("uniques"))
        for v in r.get("views_daily") or []:
            d["views"][v["timestamp"][:10]] = (v.get("count"), v.get("uniques"))
        d["stars"], d["forks"] = r.get("stars"), r.get("forks")

    print(f"📈 누적 시계열 (스냅샷 {len(rows)}행 · {DAILY})\n")
    for repo, d in per.items():
        days = sorted(set(d["clones"]) | set(d["views"]))
        days = [x for x in days if (d["clones"].get(x, (0, 0))[0] or d["views"].get(x, (0, 0))[0])]
        if not days:
            continue
        print(f"  ── {repo}  (⭐{d['stars']} 🍴{d['forks']})")
        for day in days:
            c, cu = d["clones"].get(day, (0, 0))
            v, vu = d["views"].get(day, (0, 0))
            print(f"     {day}  클론 {c:>4}/순{cu:<4} 조회 {v:>4}/순{vu:<4}")
        print()
    print("  ※ 사람 수를 보려면 '조회'를 보세요 — 클론은 신규 공개 레포를 훑는 크롤러가 섞입니다.")


def main():
    p = argparse.ArgumentParser(description="GitHub 레포 지표 스냅샷(14일 만료 대비 영구 보관)")
    p.add_argument("--show", action="store_true", help="쌓인 시계열 요약 출력")
    p.add_argument("--repos", help="대상 레포 쉼표 구분(기본: 플러그인 5종)")
    a = p.parse_args()
    if a.show:
        cmd_show()
        return
    repos = [x.strip() for x in a.repos.split(",")] if a.repos else REPOS
    cmd_snapshot(repos)


if __name__ == "__main__":
    main()
