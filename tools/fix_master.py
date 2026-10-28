# -*- coding: utf-8 -*-
"""정본(master.json)에 확정된 수정을 적용한다.

엑셀은 건드리지 않는다. 여기 적힌 수정은 되돌릴 수 있게 근거와 함께 남고,
다시 실행해도 같은 결과가 나온다 (멱등).

  python tools/fix_master.py            # 미리보기
  python tools/fix_master.py --apply    # 적용
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_trip as P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "master.json"
LOG = ROOT / "data" / "master_fixes.json"

# ── 예외는 코드가 아니라 파일에 있다 ────────────────────────
# data/exceptions.json 한 곳이다.
#
# 상수로 코드에 두던 때는 「지금 어떤 손질이 걸려 있나」를 알려면 이 파일을
# 읽어야 했다. 그러다 結城堂 瀬波店 이 기록도 없이 사라졌고, 시트에 적어
# 넣은 영업시간이 이름표만 보고 지워졌다. 둘 다 코드에 숨은 판단이었다.
EXCEPTIONS: dict = json.loads(
    (ROOT / "data" / "exceptions.json").read_text(encoding="utf-8"))
REGIONS: dict = EXCEPTIONS.get("지역") or {}
LEG_FIXES: list = EXCEPTIONS.get("구간") or []
ITEM_FIXES: list = EXCEPTIONS.get("항목") or []


def hhmm_to_min(s):
    h, m = map(int, s.split(":"))
    return h * 60 + m


def walk(items):
    for it in items:
        yield it
        yield from walk(it.get("subItems", []))


def key_of(f: dict) -> str:
    """수정 하나를 가리키는 이름. 죽었는지 셀 때 쓴다."""
    return f.get("id") or f"{f.get('date', '')} {f.get('match_title', '')}"


def apply(trip: dict) -> tuple[list[dict], list[str]]:
    """수정을 적용하고 (기록, 대상이 사라진 수정) 을 돌려준다.

    시트는 바뀐다. 그러면 여기 적어 둔 수정도 걸릴 자리를 잃는데, 잃은 채로
    남아 있으면 「아직 이런 손질이 필요하구나」로 읽혀 규칙이 실제보다
    복잡해 보인다. 실제로 다섯 개가 그렇게 죽어 있었다.
    """
    log: list[dict] = []
    seen: set[str] = set()      # 대상을 찾은 수정

    for day in trip["days"]:
        # 1) 지역명
        # 엑셀에 지역명이 들어오면 그쪽이 정본이다. 비어 있을 때만 메운다.
        want = REGIONS.get(day["date"])
        if want and not day.get("region"):
            log.append({"target": day["date"], "field": "region",
                        "from": day.get("region"), "to": want,
                        "why": "엑셀에 비어 있던 지역명"})
            day["region"] = want

        # 2) 구간: 시각 범위가 있으면 소요시간을 계산해 채운다
        for lg in day["legs"]:
            t = lg.get("time") or {}
            if not lg.get("durationMin") and t.get("start") and t.get("end"):
                d = hhmm_to_min(t["end"]) - hhmm_to_min(t["start"])
                if d < 0:
                    d += 1440
                log.append({"target": lg["id"], "field": "durationMin",
                            "from": None, "to": d,
                            "why": f"{t['start']}~{t['end']} 에서 계산"})
                lg["durationMin"] = d

        # 3) 지목된 구간 수정 — id 로도, 날짜+제목으로도 건다.
        #
        # id 는 행 순서에서 나오므로 시트에 줄 하나가 끼면 그 뒤가 전부
        # 밀려 지목이 어긋난다. 실제로 「귀국편이라 도착지가 문장에
        # 없음」 이 l05 에서 l06 으로 밀려 대상을 잃었다. 제목으로 걸면
        # 흔들리지 않는다 — 항목 수정이 이미 그렇게 하고 있다.
        for lg in day["legs"]:
            for f in LEG_FIXES:
                if f.get("id") and lg["id"] != f["id"]:
                    continue
                if f.get("date") and day["date"] != f["date"]:
                    continue
                if f.get("match_title") and f["match_title"] not in lg["title"]:
                    continue
                if not f.get("id") and not f.get("match_title"):
                    continue
                seen.add(key_of(f))
                for k, v in (f.get("set") or {}).items():
                    if k == "time":
                        cur = lg.get("time") or {}
                        v = {**cur, **v}
                    if lg.get(k) != v:
                        log.append({"target": lg["id"], "field": k,
                                    "from": lg.get(k), "to": v, "why": f["why"]})
                        lg[k] = v
                notes = lg.setdefault("notes", [])
                if f.get("drop_note") and f["drop_note"] in notes:
                    notes.remove(f["drop_note"])
                    log.append({"target": lg["id"], "field": "notes-",
                                "from": f["drop_note"], "to": None, "why": f["why"]})
                if f.get("note") and f["note"] not in notes:
                    notes.insert(0, f["note"])
                    log.append({"target": lg["id"], "field": "notes+",
                                "from": None, "to": f["note"], "why": f["why"]})

        # 4) 지목된 항목 수정
        for it in day["items"]:
            for f in ITEM_FIXES:
                if f.get("date") and day["date"] != f["date"]:
                    continue
                if f.get("id") and it["id"] != f["id"]:
                    continue
                if f.get("match_title") and f["match_title"] not in it["title"]:
                    continue
                if any(w not in it["title"] for w in f.get("match_all", [])):
                    continue
                seen.add(f.get("id") or f"{f['date']} {f.get('match_title','')}")
                for k, v in (f.get("set") or {}).items():
                    if k == "time":
                        v = {**(it.get("time") or {}), **v}
                    if it.get(k) != v:
                        log.append({"target": it["id"], "field": k,
                                    "from": it.get(k), "to": v, "why": f["why"]})
                        it[k] = v

    dead = [key_of(f) for f in LEG_FIXES if key_of(f) not in seen]
    dead += [f"{f['date']} {f.get('match_title', '')}" for f in ITEM_FIXES
             if (f.get("id") or f"{f['date']} {f.get('match_title','')}") not in seen]
    return log, dead


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not MASTER.exists():
        sys.exit("data/master.json 이 없습니다.")
    trip = json.loads(MASTER.read_text(encoding="utf-8"))
    log, dead = apply(trip)

    print(f"수정 {len(log)}건\n")
    if dead:
        # 시트가 바뀌어 걸릴 자리가 없어진 수정이다.
        # 남겨 두면 규칙이 실제보다 복잡해 보인다.
        print(f"  ! 대상이 없는 수정 {len(dead)}건 — 지운다: "
              + " · ".join(dead))
        print()
    for e in log:
        frm = json.dumps(e["from"], ensure_ascii=False) if e["from"] is not None else "—"
        to = json.dumps(e["to"], ensure_ascii=False)
        print(f"  {e['target']:<18} {e['field']:<12} {frm[:34]:<34} → {to[:44]}")
        print(f"      {e['why']}")

    if not args.apply:
        print("\n  미리보기입니다. --apply 로 적용하세요.")
        return 0

    MASTER.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  -> {MASTER}")
    print(f"  -> {LOG}   (되돌릴 근거)")
    print("  다음: python tools/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
