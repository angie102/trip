# -*- coding: utf-8 -*-
"""정본의 장소 이름 ↔ places.json 의 키. 그리고 그 파일을 쓰는 유일한 자리.

하는 일은 셋이다.

    ① 정본(master.json)을 훑어 자리마다 키(p_이름)를 박는다
    ② places.json 에 아직 없는 키를 빈 자리로 만든다 (source=unresolved)
    ③ 아무도 안 쓰는 키를 걷어낸다. 버리기 전에 좌표를 새 키로 옮긴다

②와 ③은 같은 일의 앞뒤다 — 시트에서 이름을 고치면 새 키가 생기고 옛 키가
남는다. 한때 268개 중 88개가 그런 것이었고 그중 58개는 좌표까지 갖고
있었다. 돈 주고 조회해 놓고 아무도 안 쓰는 셈이라, 지우기 전에 옮긴다.

좌표는 여기서 찾지 않는다. 출처는 둘뿐이다 —
구글 내보내기의 CID, 또는 사람이 지도 링크로 짚어 준 자리.
빈 자리는 check.py 가 「다리에 답이 비었다」로 물어본다.

places.json 을 쓰는 곳도 여기 하나다. 한때 여섯이 각자 읽고 고쳐 썼는데,
서식마저 갈렸다 — 어떤 도구는 indent=2, prune 만 indent=1 이라 누가 마지막에
썼느냐로 파일 전체가 뒤집혔다. build.py 의 「순서를 어기면 조용히 망가진다」가
그 값이다.

    python tools/places_keys.py            # 무엇이 어떻게 될지만 본다
    python tools/places_keys.py --apply    # 키를 박고, 빈 자리를 만들고, 걷어낸다
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MASTER = DATA / "master.json"
PLACES = DATA / "places.json"

# 제목에서 걷어낼 동사·수식어. 장소 이름만 남긴다.
STRIP_TAIL = re.compile(
    r"\s*(?:에서.*$|에\s*짐\s*맡기기$|짐맡기기$|체크인\s*$|체크아웃\s*$|예약\s*$|"
    r"구경(?:하기|하고.*)?$|관람$|산책(?:하거나.*)?$|먹기$|타기$|이용$|"
    r"석식$|조식$|점심$|저녁$|아침$|뷔페$|호텔$)"
)
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿️✈㊗㊙]+", re.UNICODE)

# 접두사·접미사가 붙은 옛 키와 새 키를 잇는 데 쓴다.
# '저녁 텐키아라타' 와 '텐키아라타' 는 같은 곳이다.
DROP = re.compile(
    r"(저녁|점심|아침|조식|석식|간식|카페|호텔|료칸|체크인|체크아웃|구경|"
    r"들리기|먹기|이동|근처|주변|가는\s*길에|들려볼\s*만한\s*곳)")


# ── places.json 을 읽고 쓰는 유일한 자리 ────────────────────
def load_places() -> dict:
    return json.loads(PLACES.read_text(encoding="utf-8")) if PLACES.exists() else {}


def save_places(places: dict, backup: bool = False) -> None:
    """서식은 여기서만 정한다. 백업은 걷어낼 때만 남긴다."""
    if backup and PLACES.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(PLACES, PLACES.with_name(f"places.backup-{stamp}.json"))
        # 백업은 셋만 남긴다 — 되돌릴 일은 바로 다음이지 한 달 뒤가 아니다
        for f in sorted(DATA.glob("places.backup-*.json"))[:-3]:
            f.unlink()
    DATA.mkdir(exist_ok=True)
    PLACES.write_text(json.dumps(places, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 저장 목록과 얼마나 어긋났나 ────────────────────────────
# 구글 내보내기의 좌표는 id 로 물어 받은 값이라 믿을 수 있다. places.json
# 쪽이 그것과 멀면 이쪽이 틀린 것이다 — 넷이 수백 km 씩 어긋나 있었고,
# 주소는 넷 다 맞아서 주소만 봐서는 안 보였다.
#
# 0.2km 은 같은 건물의 다른 출입구와 아예 다른 가게를 가르는 선이다.
# 재는 곳이 둘(조회·검사)이라 값도 식도 여기 한 번만 적는다.
STRAY_KM = 0.2


def km_between(a: dict, b: dict) -> float | None:
    """두 자리의 거리(km). 한쪽이라도 좌표가 없으면 None."""
    if a.get("lat") is None or b.get("lat") is None:
        return None
    return (((a["lat"] - b["lat"]) * 111) ** 2
            + ((a["lng"] - b["lng"]) * 88) ** 2) ** 0.5


# ── ① 이름 → 키 ────────────────────────────────────────────
def slug(name: str) -> str:
    n = unicodedata.normalize("NFKC", name).strip().lower()
    n = re.sub(r"[^\w가-힣ぁ-んァ-ン一-龥]+", "_", n)
    return "p_" + n.strip("_")[:48]


def clean(title: str) -> str:
    """항목 제목에서 장소 이름만 남긴다."""
    t = EMOJI.sub("", title).strip()
    t = re.sub(r"^\s*(차\s*타고|기차\s*타고)\s*", "", t)
    # 「시간 남으면 …」 처럼 조건을 적은 말은 이름 앞에 붙는다
    t = re.sub(r"^\s*(?:시간\s*남으면|날씨\s*좋으면|가능하면|여유\s*있으면)\s*",
               "", t)
    prev = None
    while prev != t:
        prev = t
        t = STRIP_TAIL.sub("", t).strip()
    t = t.strip(" ·,-")
    return t


def collect(trip: dict) -> dict[str, dict]:
    """정본을 훑어 {placeId: {name, kind}} 를 만들고, 정본에 키를 박는다."""
    found: dict[str, dict] = {}
    skipped: list[str] = []

    def add(name: str, kind: str) -> str | None:
        nm = clean(name)
        if not nm:
            skipped.append(name)
            return None
        pid = slug(nm)
        found.setdefault(pid, {"name": nm, "kind": kind})
        return pid

    for day in trip["days"]:
        stay = day.get("stay") or {}
        if stay.get("name"):
            stay["placeId"] = add(stay["name"], "stay")

        def walk(items):
            for it in items:
                # 장소는 '- ' 줄에서만 찾는다.
                #
                # 시각 옆 제목은 라벨이다 — 「무엇을 하는가」를 적은 말이지
                # 「그 자리가 어디인가」가 아니다. 갈 곳은 그 아래 '- ' 줄에
                # 적힌다. 후보가 하나뿐이면 파서가 그것을 detail 로 접어 두므로
                # (parse_trip 의 fold_solo), detail 도 후보다.
                #
                # 한때는 반대로 서 있었다 — 제목으로 조회하는 것이 기본이고
                # 「아래에 후보가 있으면」 「묶음이면」 「숙소면」 건너뛰었다.
                # 규칙이 「후보에서 찾는다」인데 코드가 「제목에서 찾되 이럴 땐
                # 빼고」라 적혀 있으니, 빼야 할 자리를 발견할 때마다 조건이
                # 하나씩 붙었다. 기본값을 뒤집으니 전부 필요 없다.
                it["placeId"] = None
                if it.get("detail"):
                    it["detail"]["placeId"] = add(it["detail"]["name"], "detail")
                for cd in it.get("candidates", []):
                    cd["placeId"] = add(cd["name"], "candidate")
                walk(it.get("subItems", []))

        walk(day["items"])
        # 이동에 딸린 '가는 길에 들를 곳' 도 장소다
        for lg in day.get("legs", []):
            walk(lg.get("subItems", []))

    if skipped:
        print(f"  좌표 생략 {len(skipped)}건 (후보 경계 상자로 대신): "
              + ", ".join(dict.fromkeys(skipped))[:150])
    return found


# ── ③ 아무도 안 쓰는 키 걷어내기 ────────────────────────────
def flat(s: str) -> str:
    """이름을 견주기 위한 납작한 꼴. 괄호 안은 표기 변형이라 버린다."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = DROP.sub("", s)
    return re.sub(r"[^\w가-힣ぁ-んァ-ン一-龥]+", "", s)


def used_ids(master: dict) -> set[str]:
    """정본이 실제로 가리키는 placeId 만 모은다."""
    out: set[str] = set()

    def walk(o) -> None:
        if isinstance(o, dict):
            if o.get("placeId"):
                out.add(o["placeId"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(master)
    return out


def prune(master: dict, places: dict) -> tuple[dict, list, list]:
    """버려진 키의 좌표를 살아 있는 키로 옮기고, 버려진 것을 뺀 사전을 돌려준다."""
    used = used_ids(master)
    orphan = [k for k in places if k not in used]
    if not orphan:
        return places, [], []

    # 살아 있는데 좌표가 없는 것 ← 버려진 것에서 옮겨올 자리
    need = {k: v for k, v in places.items() if k in used and v.get("lat") is None}
    donor = {k: places[k] for k in orphan if places[k].get("lat") is not None}

    moved = []
    for v in need.values():
        f = flat(v.get("name", ""))
        if len(f) < 2:
            continue
        for dv in donor.values():
            df = flat(dv.get("name", ""))
            if len(df) < 2:
                continue
            if f == df or (len(f) >= 4 and (f in df or df in f)):
                # searchAs 도 함께 옮긴다. 그것이 이 장소를 가리키는 일본어
                # 이름이라, 두고 오면 화면에서 원어가 사라진다 —
                # 「ニッポンレンタカー新潟駅北口営業所」가 그렇게 없어졌다.
                for fld in ("lat", "lng", "address", "gid", "placeId", "googleName",
                            "searchAs",
                            "hours", "closedDays", "hoursText", "status", "always"):
                    if fld in dv and fld not in v:
                        v[fld] = dv[fld]
                v["source"] = dv.get("source", "places")
                moved.append((v.get("name"), dv.get("name")))
                break

    kept = {k: v for k, v in places.items() if k in used}
    return kept, moved, orphan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다")
    args = ap.parse_args()

    if not MASTER.exists():
        sys.exit("먼저 python tools/parse_trip.py --all 로 정본을 만드세요.")
    trip = json.loads(MASTER.read_text(encoding="utf-8"))
    places = load_places()

    # ① · ② 키를 박고 없는 자리를 만든다
    wanted = collect(trip)
    new = [pid for pid in wanted if pid not in places]
    for pid in new:
        info = wanted[pid]
        places[pid] = {"name": info["name"], "kind": info["kind"],
                       "source": "unresolved"}

    # ③ 아무도 안 쓰는 키를 걷어낸다
    kept, moved, orphan = prune(trip, places)

    print(f"장소 {len(wanted)}개 / 캐시 {len(kept)}개"
          f" / 새 자리 {len(new)}개 / 버릴 것 {len(orphan)}개")
    for pid in new:
        print(f"  + {wanted[pid]['name'][:52]}")
    if moved:
        print(f"  좌표를 옮겨 살린 것 {len(moved)}건")
        for a, b in moved[:8]:
            print(f"    {b[:30]:<32} → {a[:30]}")
        if len(moved) > 8:
            print(f"    … 외 {len(moved) - 8}건")

    # ── 저장 목록이 이미 아는 것은 다시 묻지 않는다 ──────────────
    #
    # 구글 내보내기(saved_places.json)에는 CID 마다 primaryType 이 딸려 온다.
    # 그런데 그 값을 아무도 places.json 으로 옮기지 않아, 업종이 빈 자리를
    # places_lookup --kinds 로 다시 물어야 했다 — 손에 든 답을 두고 돈을 내는 셈이다.
    #
    # 좌표를 내보내기의 CID 에서 받는 것과 같은 출처다. 이름으로 찾은 것이
    # 아니라 id 로 받은 값이라 샐 데가 없다.
    filled = []
    sf = DATA / "saved_places.json"
    if sf.exists():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from saved_lists import cid_of, place_id_of
        saved = json.loads(sf.read_text(encoding="utf-8"))

        # 다리가 짚어 준 자리는 여기서 id 를 박는다.
        #
        # 다리(place_map.json)는 여태 places_lookup 만 보았다. 그래서 CID 를
        # 적어 넣어도 유료 조회를 돌리기 전에는 좌표가 비어 있었다 —
        # 「다테하나 항구 아침 시장」이 그랬다. 답은 저장 목록에 이미 있었고
        # 다리에도 적혀 있었는데, 둘을 잇는 사람만 없었던 셈이다.
        bf = DATA / "place_map.json"
        bridge = ((json.loads(bf.read_text(encoding="utf-8")).get("다리") or {})
                  if bf.exists() else {})
        for v in kept.values():
            if v.get("placeId"):
                continue
            cid = bridge.get(v.get("name") or "")
            if cid and ":" in str(cid):
                v["placeId"] = place_id_of(cid)

        # 좌표도 업종과 같은 출처다. 업종만 옮기던 탓에 id 를 박고도
        # 자리가 비었다 — 지도에 점이 안 찍히는데 경고는 안 났다.
        FIELDS = ("lat", "lng", "address", "primaryType", "typeLabel")
        for k, v in kept.items():
            if not v.get("placeId"):
                continue
            s_ = saved.get(cid_of(v["placeId"]) or "")
            if not s_:
                continue
            got = [f for f in FIELDS
                   if v.get(f) is None and s_.get(f) is not None]
            if not got:
                continue
            for f in got:
                v[f] = s_[f]
            if "lat" in got:
                v.setdefault("googleName", s_.get("found") or s_.get("title"))
                if v.get("source") == "unresolved":
                    v["source"] = "saved-list"
            filled.append((k, " ".join(got)))
    if filled:
        print(f"  저장 목록에서 채운 것 {len(filled)}건 (조회 0회)")
        for k, t in filled[:8]:
            print(f"    {k[:38]:<40} {t}")

    if not args.apply:
        print("  (dry-run — 바꾸려면 --apply)")
        return 0

    save_places(kept, backup=bool(orphan))
    MASTER.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")

    resolved = sum(1 for v in kept.values() if v.get("lat") is not None)
    print(f"  좌표 있음 {resolved}/{len(kept)}"
          f" ({resolved * 100 // max(len(kept), 1)}%)")
    print(f"  → {PLACES}")
    if new:
        print("  좌표를 넣으려면: 구글 지도 링크를 주거나"
              " python tools/places_lookup.py (유료)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
