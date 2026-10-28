# -*- coding: utf-8 -*-
"""구글 Places API 로 places.json 을 채운다. 묻는 길은 id 하나뿐이다.

이름으로 찾는 길은 걷어냈다. 맞을 때도 틀릴 때도 화면에는 점 하나로
보여 가려낼 수가 없었다 — 「Shop KASAI」가 48km 떨어진 슈퍼로,
「Solano Terrace」가 캐나다로, 「Yu-Sa Market」이 이마트 영등포점으로 왔다.

id 는 두 곳에서만 온다.
    구글 내보내기의 CID   data/place_map.json 의 다리를 거쳐 온다
    사람이 짚은 지도 링크  그 링크에서 뽑아 places.json 에 박아 둔다

id 가 없는 자리는 묻지 않고 이름을 알려 준다. 빈 좌표는 검사가 물어보지만,
틀린 좌표는 아무도 묻지 않는다.

갈래 넷 — 무엇을 받아 오느냐만 다르고 묻는 방법은 같다.
    (없음)     좌표·요일별 영업시간
    --kinds    업종(마커 종류의 바탕)
    --names    언어별 이름 (--lang ja|en)
    --saved    구글 저장 목록의 CID 로 그 자리

다시 묻는 때 — 좌표·시간이 비었거나, 다리가 다른 답을 갖고 있거나,
저장 목록과 좌표가 어긋났을 때뿐이다. 그 밖에는 손대지 않는다.

사용:
    python tools/places_lookup.py --dry-run     # 대상만 확인
    python tools/places_lookup.py               # 좌표·영업시간
    python tools/places_lookup.py --only 낱말   # 한 곳만 id 로 다시
    python tools/places_lookup.py --refresh     # 전부 다시 (되도록 쓰지 않는다)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from places_keys import STRAY_KM, km_between, save_places   # noqa: E402  places.json 을 쓰는 유일한 자리

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLACES = DATA / "places.json"
ENV = ROOT / ".env"      # 열쇠는 이 프로젝트 안에 둔다

DETAILS = "https://places.googleapis.com/v1/places/"

# 웹 키는 HTTP 리퍼러로 묶여 있어 파이썬에서 부르면 리퍼러가 비어 403 이 난다.
# 제한 없는 키를 따로 두는 것이 옳지만, 없을 때는 허용된 주소를 실어 보낸다 —
# 내 프로젝트의 내 키로 내 데이터를 부르는 것이라 우회가 아니라 밝히는 쪽이다.
REFERER = "https://tohoku-2026-9pf.pages.dev/"
# 분류(types 계열)는 Pro 등급이고 영업시간은 그보다 위인 Enterprise 등급이라,
# 이미 영업시간을 받고 있는 이 호출에 분류를 더해도 요금은 오르지 않는다.
# 처음부터 넣었어야 했다 — 그 자리가 무엇인지는 그 자리가 안다.
FIELDS = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "regularOpeningHours.periods",
    "regularOpeningHours.weekdayDescriptions",
    "businessStatus",
    "primaryType",                 # 'ice_cream_shop'
    "primaryTypeDisplayName",      # '아이스크림 가게'
    "types",                       # 겹치는 분류 전부
])
DOW = "월화수목금토일"          # 우리 표기 (월=0)



def key() -> str:
    """서버용 키를 먼저 찾고, 없으면 지도용 키로 돌아간다.

    지도를 그리는 키와 장소를 조회하는 키는 쓰임이 다르다 —
    웹 키는 HTTP 리퍼러로 묶여 있어 파이썬에서 부르면 리퍼러가 비어
    403 으로 막힌다. 서버용 키는 콘솔에서 「애플리케이션 제한: 없음」,
    「API 제한: Places API (New)」 로 따로 만들어 아래 이름으로 넣는다.

        GOOGLE_PLACES_API_KEY=...
    """
    env = ENV.read_text(encoding="utf-8")
    # 줄머리에 앵커를 건다. 앵커가 없으면 GOOGLE_MAPS_API_KEY 가
    # NEXT_PUBLIC_GOOGLE_MAPS_API_KEY 안에서도 매칭되어, 리퍼러로 묶인
    # 웹 키를 집어 오고 또 403 이 난다.
    for name in ("SELECT_GOOGLE_MAPS_API_KEY", "GOOGLE_PLACES_API_KEY",
                 "GOOGLE_MAPS_API_KEY", "NEXT_PUBLIC_GOOGLE_MAPS_API_KEY"):
        m = re.search(r"^" + name + r"=(\S+)", env, re.M)
        if m:
            return m.group(1)
    sys.exit("API 키를 찾을 수 없습니다: " + str(ENV))






def details(place_id: str, api_key: str) -> dict | None:
    """placeId 로 그 자리 하나를 묻는다.

    이름 검색과 다른 점이 하나 있고, 그것이 전부다 — 샐 데가 없다.
    「Shop KASAI」를 이름으로 찾으면 48km 떨어진 슈퍼가 나오지만,
    id 로 물으면 그 id 의 자리가 온다. 그래서 사람이 짚어 준 자리도
    id 만 있으면 얼마든지 다시 물어도 된다.
    """
    req = urllib.request.Request(DETAILS + place_id, headers={
        "X-Goog-Api-Key": api_key,
        "Referer": REFERER,
        "X-Goog-FieldMask": FIELDS,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"      HTTP {e.code}: {e.read(200).decode('utf-8', 'replace')[:120]}")
    except Exception as e:
        print(f"      {e}")
    return None


def to_hours(oh: dict | None) -> tuple[dict, list[str], list[str]]:
    """Places 의 periods → 요일별 구간 + 휴무 요일.

    periods 의 day 는 0=일요일. 우리 표기는 월=0 이라 옮긴다.
    한 요일에 구간이 둘이면 브레이크 타임이다.
    """
    if not oh:
        return {}, [], []
    per = oh.get("periods", [])
    # 24시간 영업은 close 없는 period 하나로 온다 (open: 일요일 0시).
    # 이것을 '일요일만 영업' 으로 읽으면 나머지 엿새가 휴무가 돼버린다.
    if len(per) == 1 and not per[0].get("close"):
        o = per[0].get("open") or {}
        if o.get("hour", 0) == 0 and o.get("minute", 0) == 0:
            allday = {d: [{"open": "00:00", "close": "24:00"}] for d in DOW}
            return allday, [], oh.get("weekdayDescriptions", [])
    by_day: dict[str, list[dict]] = {}
    for p in per:
        o, c = p.get("open"), p.get("close")
        if not o:
            continue
        gd = o.get("day", 0)                      # 0=일
        ours = DOW[(gd + 6) % 7]                  # 월=0 으로
        rng = {"open": f"{o.get('hour', 0):02d}:{o.get('minute', 0):02d}",
               "close": (f"{c.get('hour', 0):02d}:{c.get('minute', 0):02d}"
                         if c else "24:00")}
        by_day.setdefault(ours, []).append(rng)
    for v in by_day.values():
        v.sort(key=lambda x: x["open"])
    closed = [d for d in DOW if d not in by_day]
    return by_day, closed, oh.get("weekdayDescriptions", [])


def run_hours(args) -> int:
    """좌표와 요일별 영업시간 — 갈래를 안 고르면 이것이다."""
    if not PLACES.exists():
        sys.exit("places.json 이 없습니다. places_keys.py 를 먼저 한 번 돌리세요.")
    places = json.loads(PLACES.read_text(encoding="utf-8"))

    # 두 정본 사이의 다리 — 엑셀 이름 → 내보내기 CID.
    #
    # 짚어 둔 자리도 id 로는 얼마든지 다시 묻는다. 울타리를 장소에
    # 치던 때는 「사람이 짚었으니 건드리지 말자」였는데, 위험한 것은
    # 그 장소가 아니라 이름으로 묻는 일이었다. 그 길이 없어졌으므로
    # 울타리도 필요 없다 — id 로 묻는 것은 샐 데가 없다.
    from saved_lists import cid_of, place_id_of
    bridge = {}
    f = DATA / "place_map.json"
    if f.exists():
        bridge = json.loads(f.read_text(encoding="utf-8")).get("다리") or {}

    # 저장 목록과 좌표가 어긋나면 그 자리는 다시 받아야 한다
    saved = {}
    f = DATA / "saved_places.json"
    if f.exists():
        s = json.loads(f.read_text(encoding="utf-8"))
        saved = {k: v for k, v in s.items()}

    def strayed(v: dict) -> bool:
        gid = v.get("placeId")
        s = saved.get(cid_of(gid) or "") if (gid and saved) else None
        km = km_between(v, s) if s else None
        return km is not None and km > STRAY_KM

    todo, byhand = [], []
    for pid, v in places.items():
        if args.only:
            # 한 곳만 콕 집어 다시 묻는다. id 로 묻는 것이라 샐 데가 없다 —
            # 「Yoshidaya」가 주소는 니가타인데 좌표만 나가사키였다.
            if args.only in (v.get("name", "") + (v.get("googleName") or "")):
                todo.append(pid)
            continue
        # 다리가 답을 갖고 있으면 그것이 이긴다.
        #
        # 사람이 지도에서 짚어 준 자리라 무엇보다 세다. 한때는 id 가
        # 아예 없을 때만 다리를 봤는데, 그러면 틀린 id 가 이미 박혀 있는
        # 자리를 고칠 수가 없었다 — 「DEL’IMMO TOKYO CAFE」가 그랬다.
        # 지점이 여럿이라 다른 지점이 들어와 있었고, 2~3km 떨어진
        # 자리인데 이름도 주소도 그럴듯해 눈으로는 가려낼 수 없었다.
        cid = next((c for k, c in bridge.items()
                    if c and ":" in str(c) and (k in v["name"] or v["name"] in k)),
                   None)
        if cid and v.get("placeId") != place_id_of(cid):
            v["placeId"] = place_id_of(cid)
            # 다른 자리의 값이 붙어 있다. 전부 걷어내고 id 로 다시 받는다.
            for fld in ("lat", "lng", "address", "googleName", "status",
                        "hours", "closedDays", "hoursText", "hoursNone",
                        "always", "primaryType", "typeLabel", "types"):
                v.pop(fld, None)

        want = args.refresh or "lat" not in v or strayed(v) or not (
            v.get("hours") or v.get("always") or v.get("hoursNone"))
        if not want:
            continue
        # id 로만 묻는다.
        #
        # 이름으로 찾는 길은 걷어냈다. 좌표의 출처는 둘뿐이다 —
        # 구글 내보내기의 CID, 또는 사람이 구글 지도 링크로 짚어 준 자리.
        # 이름 조회는 맞을 때도 틀릴 때도 화면에 점 하나로 보여
        # 가려낼 수가 없었다 (Shop KASAI 48km · Solano Terrace 캐나다).
        if v.get("placeId"):
            todo.append(pid)
        else:
            byhand.append(pid)

    print(f"장소 {len(places)}개 / 조회 대상 {len(todo)}개  [id 로만 묻는다]")
    if byhand:
        print(f"  ! id 가 없어 못 묻는 자리 {len(byhand)}곳 — 지도 링크로 짚어야 한다")
        for pid in byhand[:10]:
            print(f"      {places[pid]['name'][:48]}")
    if args.dry_run:
        for pid in todo[:30]:
            print(f"   {places[pid]['name'][:52]}")
        if len(todo) > 30:
            print(f"   … 외 {len(todo) - 30}개")
        return 0
    if args.limit:
        todo = todo[:args.limit]

    api_key = key()
    ok = fail = with_hours = 0
    for i, pid in enumerate(todo, 1):
        v = places[pid]
        name = v["name"]
        got = details(v["placeId"], api_key)
        time.sleep(0.12)
        if not got:
            # id 로 물었는데 답이 없으면 그것은 「못 찾은 자리」가 아니라
            # 그 요청이 실패한 것이다. 알아낸 방법을 지우지 않는다.
            fail += 1
            print(f"  [{i:>3}/{len(todo)}] --  {name[:46]}")
            continue
        # 다리는 위에서 이미 건넜다 — id 를 고르는 자리가 거기 하나뿐이라,
        # 조회한 뒤에 다시 갈아 끼울 일이 없다.
        loc = got.get("location") or {}
        by_day, closed, desc = to_hours(got.get("regularOpeningHours"))
        v.update({
            "lat": round(loc.get("latitude", 0), 6),
            "lng": round(loc.get("longitude", 0), 6),
            "address": got.get("formattedAddress", "")[:120],
            "googleName": (got.get("displayName") or {}).get("text", ""),
            "placeId": got.get("id"),
            "status": got.get("businessStatus"),
        })
        # source 는 「이 자리를 무엇으로 알아냈나」다. id 로 다시 물은 것은
        # 알아낸 방법이 바뀐 것이 아니므로 그대로 둔다.
        if by_day:
            v["hours"] = by_day
            v["closedDays"] = closed
            v["hoursText"] = desc
            v.pop("hoursNone", None)
            with_hours += 1
        else:
            # 구글에도 영업시간이 없는 곳이 있다 — 료칸과 호텔이 그렇다.
            # 없다는 사실도 적어 둔다. 다음에 또 묻지 않게.
            v["hoursNone"] = True
        ok += 1
        h = f"  영업 {len(by_day)}일" if by_day else ""
        st = "" if got.get("businessStatus") in (None, "OPERATIONAL") else f"  [{got['businessStatus']}]"
        print(f"  [{i:>3}/{len(todo)}] OK  {name[:40]:<40} → {v['googleName'][:26]}{h}{st}")

    save_places(places)
    res = sum(1 for x in places.values() if isinstance(x.get("lat"), (int, float)))
    hrs = sum(1 for x in places.values() if x.get("hours"))
    print(f"\n  성공 {ok} / 못 찾음 {fail}")
    print(f"  좌표 {res}/{len(places)} · 영업시간 {hrs}/{len(places)}")
    print(f"  → {PLACES}")
    print("  다음: python tools/export_web.py")
    return 0


# ── 갈래: 분류 ─────────────────────────────────────────────
# 그 자리가 무엇인지는 그 자리가 안다. 이름으로 추측하지 않는다.
# 마커로 묶는 표(MARKER)는 place_kinds.py 에 있다 — 그쪽은 조회를 하지 않는
# 순수한 표라 화면 쪽(export_web)이 그대로 import 한다.
KIND_FIELDS = "id,primaryType,primaryTypeDisplayName,types"


def fetch_kind(pid: str, api_key: str) -> dict | None:
    req = urllib.request.Request(
        f"{DETAILS}{pid}?languageCode=ko",
        headers={"X-Goog-Api-Key": api_key, "Referer": REFERER,
                 "X-Goog-FieldMask": KIND_FIELDS})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            d = json.loads(body)["error"]
            rs = next((x.get("reason") for x in d.get("details", []) if x.get("reason")), "-")
            print(f"      HTTP {e.code} {rs}")
        except Exception:
            print(f"      HTTP {e.code} {body[:100]}")
        return None
    except Exception as e:
        print(f"      {e}")
        return None


def run_kinds(args) -> int:
    from collections import Counter
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    todo = [pid for pid, v in places.items()
            if v.get("placeId") and (args.refresh or not v.get("primaryType"))]
    if args.limit:
        todo = todo[:args.limit]

    have = sum(1 for v in places.values() if v.get("primaryType"))
    noid = sum(1 for v in places.values() if not v.get("placeId"))
    print(f"장소 {len(places)}개 · 분류 있음 {have} · placeId 없음 {noid}")
    print(f"조회 대상 {len(todo)}개  [Place Details · 분류 세 필드만]")
    if args.dry_run:
        for pid in todo[:12]:
            print(f"   {places[pid]['name'][:52]}")
        if len(todo) > 12:
            print(f"   … 외 {len(todo) - 12}개")
        return 0

    api_key, got = key(), 0
    for i, pid in enumerate(todo, 1):
        v = places[pid]
        d = fetch_kind(v["placeId"], api_key)
        if not d:
            print(f"  {i:>3}/{len(todo)}  X {v['name'][:40]}")
            continue
        v["primaryType"] = d.get("primaryType")
        v["typeLabel"] = (d.get("primaryTypeDisplayName") or {}).get("text")
        # 겹치는 분류도 남긴다. 「아이스크림 가게이면서 과자점」 같은 자리를
        # 나중에 우리 종류로 묶을 때 primaryType 하나로는 모자란다.
        v["types"] = d.get("types") or []
        got += 1
        print(f"  {i:>3}/{len(todo)}  {v['name'][:32]:<34}"
              f"{str(v['typeLabel']):<14}{v['primaryType']}")
        time.sleep(0.05)
        if got % 25 == 0:
            save_places(places)

    save_places(places)
    print(f"\n채운 것 {got}개 → {PLACES}")
    c = Counter(v.get("primaryType") for v in places.values() if v.get("primaryType"))
    print(f"\n분류 {len(c)}가지")
    for k, n in c.most_common():
        print(f"   {k:<28}{n}")
    return 0


# ── 갈래: 이름 ─────────────────────────────────────────────
# googleName 은 ko, enName 은 en, jaName 은 ja 로 물은 값이다.
# 화면 규칙은 이 셋으로 끝난다 — 앞에는 읽을 수 있는 이름, 옆에는 원어.
JA_NAME = re.compile(r"[぀-ヿ一-鿿]")   # 가나·한자
NAME_FIELDS = "id,displayName"
NAME_FIELD = {"ja": "jaName", "en": "enName"}


def fetch_name(pid: str, lang: str, api: str) -> str | None:
    req = urllib.request.Request(
        f"{DETAILS}{pid}?languageCode={lang}",
        headers={"X-Goog-Api-Key": api, "Referer": REFERER,
                 "X-Goog-FieldMask": NAME_FIELDS})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return (json.load(r).get("displayName") or {}).get("text")
    except urllib.error.HTTPError as e:
        print(f"      HTTP {e.code}")
    except Exception as e:
        print(f"      {e}")
    return None


def run_names(args) -> int:
    fld = NAME_FIELD[args.lang]
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    todo = []
    for k, v in places.items():
        if not v.get("placeId") or (fld in v and not args.refresh):
            continue
        # ja: 구글이 준 이름이 이미 일본어면 그것이 원어다. 더 물을 것 없다.
        # en: 이름이 읽히면(가나·한자가 없으면) 로마자를 따로 받을 까닭이 없다.
        readable = not JA_NAME.search(v.get("googleName") or "")
        if (args.lang == "ja" and not readable) or (args.lang == "en" and readable):
            continue
        todo.append((k, v))

    print(f"장소 {len(places)}곳 · {args.lang} 이름을 물어볼 곳 {len(todo)}")
    if args.dry_run:
        for _, v in todo[:15]:
            print(f"   {(v.get('googleName') or v['name'])[:48]}")
        return 0

    api, got, none = key(), 0, 0
    for i, (k, v) in enumerate(todo, 1):
        nm = fetch_name(v["placeId"], args.lang, api)
        # ja 는 가나·한자가 있어야 원어다. en 은 반대로 없어야 읽을 수 있다.
        ok = bool(nm) and (bool(JA_NAME.search(nm)) if args.lang == "ja"
                           else not JA_NAME.search(nm))
        v[fld] = nm if ok else None
        if ok:
            got += 1
            print(f"  {i:>3}/{len(todo)}  {(v.get('googleName') or '')[:30]:<32}-> {nm}")
        else:
            none += 1        # 그 언어로 된 이름이 본디 없다. 지어내지 않는다.
        time.sleep(0.05)
        if i % 30 == 0:
            save_places(places)
    save_places(places)
    print(f"\n  얻은 곳 {got} · 본디 없는 곳 {none}  →  {PLACES}")
    return 0


# ── 갈래: 저장 목록 ────────────────────────────────────────
# CSV 에는 이름과 CID 뿐이고 좌표가 없다. 제목으로 다시 조회하던 때는
# 「Solano Terrace」가 캐나다로, 「Yu-Sa Market」이 이마트 영등포점으로 왔다.
# CID 는 placeId 와 같은 값이라 이름을 한 번도 안 거치고 물을 수 있다.
SAVED_CACHE = DATA / "saved_places.json"
SAVED_FIELDS = ("id,displayName,formattedAddress,location,"
                "primaryType,primaryTypeDisplayName")


def fetch_saved(pid: str, api: str) -> dict | None:
    req = urllib.request.Request(
        f"{DETAILS}{pid}?languageCode=ko",
        headers={"X-Goog-Api-Key": api, "Referer": REFERER,
                 "X-Goog-FieldMask": SAVED_FIELDS})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.code}
    except Exception as e:
        return {"error": str(e)[:60]}


def run_saved(args) -> int:
    from saved_lists import SAVED, cid_of, place_id_of, read_lists

    saved = read_lists(SAVED, args.keyword)
    if args.used:
        # 목록에는 오백 곳이 넘는데 여행에 쓰는 것은 백일흔 곳이다.
        # 대조에 필요한 것은 쓰는 자리뿐이라, 나머지는 받지 않는다.
        P = json.loads(PLACES.read_text(encoding="utf-8"))
        mine = {cid_of(v["placeId"]) for v in P.values() if v.get("placeId")}
        saved = [s for s in saved if s["cid"] in mine]
    cache = json.loads(SAVED_CACHE.read_text(encoding="utf-8")) if SAVED_CACHE.exists() else {}
    # 옛 캐시는 제목으로 조회한 값이라 믿을 수 없다. placeId 로 받은 것만 남긴다.
    cache = {k: v for k, v in cache.items() if v.get("byId")}

    todo = [s for s in saved if s["cid"] and s["cid"] not in cache]
    seen, uniq = set(), []
    for s in todo:
        if s["cid"] not in seen:
            seen.add(s["cid"])
            uniq.append(s)
    print(f"목록 {len(saved)}곳 · 받아 둔 것 {len(cache)} · 받을 것 {len(uniq)}")
    if args.dry_run:
        for s in uniq[:10]:
            print(f"   {s['title'][:44]}")
        return 0

    api = key()
    for i, s in enumerate(uniq, 1):
        d = fetch_saved(place_id_of(s["cid"]), api)
        if not d or "error" in d:
            err = d.get("error") if d else ""
            print(f"  {i:>3}/{len(uniq)}  X  {s['title'][:34]}  {err}")
            cache[s["cid"]] = {"byId": True, "title": s["title"], "found": None}
        else:
            cache[s["cid"]] = {
                "byId": True,
                "title": s["title"],
                "found": d["displayName"]["text"],
                "address": d.get("formattedAddress", ""),
                "lat": d["location"]["latitude"],
                "lng": d["location"]["longitude"],
                "primaryType": d.get("primaryType"),
                "typeLabel": (d.get("primaryTypeDisplayName") or {}).get("text"),
            }
        if i % 25 == 0:
            SAVED_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
            print(f"  {i:>3}/{len(uniq)} …")
        time.sleep(0.05)
    SAVED_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for v in cache.values() if v.get("lat") is not None)
    print(f"\n  자리를 안 곳 {ok}/{len(cache)}  →  {SAVED_CACHE}")
    return 0


def main() -> int:
    """구글에 묻는 일은 전부 여기 하나로 들어온다.

    한때 파일 넷이었다 — places_lookup · place_kinds · place_names ·
    saved_resolve. 열쇠와 요청 코드는 이미 이 파일 것을 셋이 import 해 쓰고
    있었으므로 나뉜 값어치가 없었고, 파이프라인 밖에 있어 「언제 무엇을
    돌려야 하나」를 사람이 기억해야 했다. 이제 --help 에 적혀 있다.
    """
    ap = argparse.ArgumentParser(
        description="Google Places API (New) — 좌표·영업시간·분류·이름·저장 목록")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--kinds", action="store_true", help="업종(분류)을 받는다")
    g.add_argument("--names", action="store_true",
                   help="언어별 이름을 받는다 (--lang 필요)")
    g.add_argument("--saved", action="store_true",
                   help="구글 저장 목록의 CID 로 그 자리를 받는다")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="이미 찾은 것도 다시 조회 (source=manual 은 제외)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", help="이 낱말이 이름에 든 곳만 (id 로 다시 묻는다)")
    ap.add_argument("--lang", choices=["ja", "en"], help="--names 에서 쓸 언어")
    ap.add_argument("--keyword", default="일본", help="--saved 에서 읽을 목록 이름")
    ap.add_argument("--used", action="store_true", help="--saved 에서 여행에 쓰는 자리만")
    args = ap.parse_args()

    if args.kinds:
        return run_kinds(args)
    if args.names:
        if not args.lang:
            sys.exit("--names 에는 --lang ja 또는 --lang en 이 필요합니다.")
        return run_names(args)
    if args.saved:
        return run_saved(args)
    return run_hours(args)


if __name__ == "__main__":
    sys.exit(main())
