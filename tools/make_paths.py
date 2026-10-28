# -*- coding: utf-8 -*-
"""자리와 자리 사이를 잇는 길. 한 번 구워 두고 그 뒤로는 부르지 않는다.

stops.json 의 자리들은 점이다. 점과 점을 직선으로 이으면 지도 위에서 건물과
강을 가로지르는데, 실제로 그렇게 걷지는 않는다. 그래서 구간마다 길을 받아
paths.json 에 넣어 둔다. 화면은 그 길을 따라 사람을 걷게 한다.

**왜 구워 두는가.**

재생할 때마다 길을 물으면 요청이 끝없이 쌓이고, 재생을 누른 뒤 길이 올 때까지
기다려야 한다. 동선은 자주 바뀌는 것이 아니므로 한 번 받아 파일에 넣는 것으로
족하다 — 화면에서 나가는 요청은 0 이 된다.

**어디에 묻는가.**

OSRM(OpenStreetMap 기반 공개 라우팅)이다. 구글 Directions 를 쓰지 않는 까닭은
이 프로젝트의 키에 referer 제한이 걸려 있어 브라우저 밖에서는 거절당하기
때문이다(REQUEST_DENIED: "API keys with referer restrictions cannot be used
with this API"). 서버용 키를 따로 만들면 구글로도 되지만, 한 번 굽고 마는 일에
키를 하나 더 두고 과금을 붙일 까닭이 없다.

**길을 안 쓰는 구간.**

    · 너무 멀다 — 인천에서 니가타는 비행기다. 그런데 OSM 의 자동차 길에는
      페리 항로가 들어 있어, 바다 건너에도 그럴듯한 답이 온다(부산에서 배를 타고
      시마네를 거쳐 1658km). 크게 도는 것도 아니라(직선의 1.5배) 비율로는
      못 거른다. 이 여행의 육로는 아무리 멀어도 268km(신칸센 구간)이므로,
      그보다 한참 위에 선을 그어 그 너머는 날아간 것으로 본다
    · 길이 없다 — OSRM 이 못 찾으면 직선
    · 크게 돌아간다 — 도로가 직선의 2.5 배를 넘으면 열차나 배로 건넌 구간이라
      자동차 길이 실제와 딴판이다. 그럴 바에는 직선이 정직하다
    · 너무 가깝다 — 50m 안쪽은 길을 그릴 것이 없다

신칸센 구간(오미야→야마가타 268km 같은)은 자동차 길로 나온다. 터널로 곧게
가는 실제 노선과는 다르지만, 산을 뚫고 지나가는 직선보다는 「옮겨 갔다」가
읽힌다 — 크게 돌지만 않으면 그대로 쓴다.

    python tools/make_paths.py            # 물어보고 결과만 본다
    python tools/make_paths.py --apply    # paths.json 에 넣는다

이미 구워 둔 것이 있으면 좌표가 그대로인 구간은 다시 묻지 않는다.
stops.json 을 손으로 고친 자리만 새로 받는다.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
STOPS = ROOT / "web-react" / "src" / "route" / "stops.json"
OUT = ROOT / "web-react" / "src" / "route" / "paths.json"

OSRM = "https://router.project-osrm.org/route/v1/driving/"
DETOUR_MAX = 2.5     # 도로가 직선의 몇 배까지 봐줄까
NEAR_M = 50          # 이만큼 가까우면 길을 그릴 것이 없다
# 이보다 멀면 길을 그리지 않고 곧게 잇는다.
#
# 350 으로 두었을 때는 니가타에서 카루이자와까지 179km 를 자동차 길로
# 그렸다. 실제로는 신칸센이 산을 뚫고 곧게 가는데 화면에서는 국도를 따라
# 골짜기를 굽이굽이 돌았다 — 지나간 자취가 아니라 딴 길이다.
#
# 한때 90 으로 두어 기차 구간을 모두 곧게 이었다. 실제 노선을 그리려면
# 철도 길찾기가 있어야 하는데 공개된 것이 마땅치 않고, 구글 Directions 는
# 이 프로젝트 키에 referer 제한이 걸려 브라우저 밖에서는 거절당한다.
#
# 그런데 곧은 선이 뻣뻣했다. 차로 가는 길이라도 그려 두는 편이 낫다 —
# 신칸센이 그 길을 그대로 달리지는 않지만, 산과 강을 피해 가는 결은
# 철길도 도로도 크게 다르지 않아 「그쪽으로 갔다」가 읽힌다.
#
# 350 은 육로로 갈 수 있는 가장 먼 구간(268km, 오미야에서 야마가타)보다
# 넉넉히 위다. 그보다 먼 것은 하늘길뿐이라 길을 물을 것이 없다.
FLY_KM = 350
PAUSE = 0.15         # 공개 서버다. 잇달아 두드리지 않는다

# 파이썬이 들고 있는 CA 목록이 낡아 Let's Encrypt 의 새 중간 인증서를 모른다
# (curl 로는 같은 주소가 멀쩡히 열린다). certifi 가 있으면 그것으로 연다.
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = None


def km(a: list[float], b: list[float]) -> float:
    """두 자리 사이 킬로미터. 하버사인."""
    r, rad = 6371.0, math.pi / 180
    d_lat, d_lng = (b[0] - a[0]) * rad, (b[1] - a[1]) * rad
    h = (math.sin(d_lat / 2) ** 2
         + math.cos(a[0] * rad) * math.cos(b[0] * rad) * math.sin(d_lng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


# 케이블로 매달려 가는 것들. 길 위를 달리지 않으므로 도로를 물을 까닭이 없다.
CABLE = ("로프웨이", "ロープウェイ", "Ropeway", "케이블카", "곤돌라", "리프트")


def is_cable(a_name: str, b_name: str) -> bool:
    """양 끝이 다 케이블 자리인가.

    한쪽만 케이블이면 아니다 — 「호텔 → 로프웨이 산록역」은 걸어가는 길이라
    도로로 그리는 것이 맞다. 두 역 사이만 공중이다.
    """
    return all(any(k in n for k in CABLE) for n in (a_name, b_name))


def skip_reason(a: list[float], b: list[float],
                a_name: str = "", b_name: str = "") -> str | None:
    """묻기도 전에 직선으로 둘 구간인가. 캐시보다 먼저 본다 —
    여기 규칙이 바뀌면 전에 구워 둔 것도 다시 판정되어야 한다."""
    d = km(a, b)
    if d * 1000 < NEAR_M:
        return "너무 가깝다"
    if d > FLY_KM:
        return f"너무 멀다 ({d:.0f}km — 기차나 비행기다)"
    # 로프웨이는 케이블이라 길이 없다.
    #
    # 자오는 도로가 3.8 배 돌아 「크게 돈다」에 걸려 저절로 직선이 되었는데,
    # 핫코다는 산길이 제법 곧아 그 그물을 빠져나가 도로로 그려졌다.
    # 같은 로프웨이가 한쪽은 하늘을, 한쪽은 산길을 타고 있었던 셈이다.
    # 배율은 우연히 맞은 것이라 규칙이 못 된다 — 무엇인지로 가른다.
    if is_cable(a_name, b_name):
        return "케이블이라 길이 없다"
    return None


def ask(a: list[float], b: list[float]) -> tuple[str | None, float, str]:
    """한 구간의 길을 묻는다. (폴리라인, 도로 km, 왜) 를 돌려준다.

    폴리라인이 None 이면 직선으로 두라는 뜻이고, 그 까닭이 셋째 칸에 온다.
    """
    straight = km(a, b)
    url = (f"{OSRM}{a[1]},{a[0]};{b[1]},{b[0]}"
           "?overview=simplified&geometries=polyline")
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=30, context=CTX) as r:
                res = json.load(r)
            break
        except Exception as e:                      # noqa: BLE001
            if attempt == 2:
                return None, 0.0, f"못 물어봤다 ({type(e).__name__})"
            time.sleep(1.0)

    if res.get("code") != "Ok" or not res.get("routes"):
        return None, 0.0, "길이 없다"
    route = res["routes"][0]
    road = route["distance"] / 1000
    if road > straight * DETOUR_MAX:
        return None, road, f"크게 돈다 ({road / straight:.1f}배)"
    return route["geometry"], road, ""


def dumps(book: dict[str, list[dict | None]]) -> str:
    """한 줄에 한 구간. stops.json 과 같은 결로 적는다 — 다만 이쪽은 기계가
    굽는 파일이라 사람이 고칠 일이 없고, 폴리라인이 길어 줄도 길다."""
    days = []
    for date, legs in book.items():
        if not legs:
            days.append(f' "{date}": []')
            continue
        rows = ",\n".join(
            "  null" if leg is None else
            f'  {{ "a": [{leg["a"][0]:.6f}, {leg["a"][1]:.6f}],'
            f' "b": [{leg["b"][0]:.6f}, {leg["b"][1]:.6f}],'
            f' "line": {json.dumps(leg["line"])} }}'
            for leg in legs)
        days.append(f' "{date}": [\n{rows}\n ]')
    return "{\n" + ",\n".join(days) + "\n}\n"


def cached(old: dict, date: str, i: int, a: list[float], b: list[float]):
    """전에 구워 둔 것 중 좌표가 그대로인 구간. 손대지 않은 자리는 다시 묻지 않는다."""
    legs = old.get(date)
    if not legs or i >= len(legs):
        return None
    leg = legs[i]
    if not leg:
        return None
    if leg["a"] == [round(a[0], 6), round(a[1], 6)] \
       and leg["b"] == [round(b[0], 6), round(b[1], 6)]:
        return leg
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="구간마다의 길을 받아 둔다")
    ap.add_argument("--apply", action="store_true", help="paths.json 에 쓴다")
    args = ap.parse_args()

    book = json.loads(STOPS.read_text(encoding="utf-8"))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    fresh: dict[str, list[dict | None]] = {}
    asked = reused = drawn = 0
    for date, stops in book.items():
        legs: list[dict | None] = []
        for i in range(len(stops) - 1):
            a, b = stops[i]["at"], stops[i + 1]["at"]
            why = skip_reason(a, b, stops[i]["name"], stops[i + 1]["name"])
            if why:
                legs.append(None)
                print(f"  {date[5:]} {i}  직선 — {why}"
                      f"  ({stops[i]['name'][:14]} → {stops[i+1]['name'][:14]})")
                continue
            hit = cached(old, date, i, a, b)
            if hit:
                legs.append(hit)
                reused += 1
                drawn += 1
                continue
            line, road, why = ask(a, b)
            asked += 1
            time.sleep(PAUSE)
            if line is None:
                legs.append(None)
                print(f"  {date[5:]} {i}  직선 — {why}"
                      f"  ({stops[i]['name'][:14]} → {stops[i+1]['name'][:14]})")
                continue
            drawn += 1
            legs.append({"a": [round(a[0], 6), round(a[1], 6)],
                         "b": [round(b[0], 6), round(b[1], 6)],
                         "line": line})
        fresh[date] = legs

    total = sum(len(v) for v in fresh.values())
    print(f"\n구간 {total}개 — 길로 그림 {drawn}, 직선 {total - drawn}"
          f"  (새로 물어본 것 {asked}, 다시 쓴 것 {reused})")

    text = dumps(fresh)
    print(f"파일 크기: {len(text.encode()):,} B")
    if not args.apply:
        print("\n물어보기만 했다. 쓰려면 --apply 를 붙인다.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"\n썼다: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
