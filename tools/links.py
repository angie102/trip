# -*- coding: utf-8 -*-
"""일정에 붙여 둔 구글 지도 링크를 풀어 data/link_map.json 에 담는다.

「길찾기」 줄에 적은 링크가 대상이다.

    길찾기 | 니가타 공항(https://maps.app.goo.gl/k8Xh…)-니가타역(https://maps.app.goo.gl/pMp…)

짧은 링크는 그대로 길찾기 URL 에 못 넣는다. 한 번 따라가면 긴 주소가 나오고
거기에 이름·좌표·CID 가 다 들어 있다.

    https://www.google.com/maps/place/니가타+공항/@37.9549441,139.1111814,17z/data=…1s0x5ff4…:0xcffc…

이름으로 장소를 찾는 길은 걷어냈지만(places_lookup 의 「48km 떨어진 슈퍼」)
링크는 다르다. 사람이 지도에서 「이 자리다」라고 짚은 것이고, places_lookup 이
인정하는 두 출처 중 하나가 바로 이것이다.

키가 필요 없다 — 리다이렉트만 따라간다. 한 번 푼 링크는 다시 묻지 않는다.

    python tools/links.py             # 아직 안 푼 것만
    python tools/links.py --dry-run   # 무엇을 물을지만 본다
    python tools/links.py --refresh   # 전부 다시
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from saved_lists import place_id_of                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "master.json"
CACHE = ROOT / "data" / "link_map.json"

UA = {"User-Agent": "Mozilla/5.0"}
CID = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+")
NAME = re.compile(r"/maps/place/([^/@]+)")

# 긴 주소에는 좌표가 두 벌 들어 있다. 뜻이 다르다.
#   !3d…!4d…   그 자리의 좌표
#   @…,…,…z    링크를 복사할 때 지도가 보고 있던 화면의 한가운데
# 화면 쪽을 읽으면 사람이 지도를 어디까지 밀어 놨느냐에 따라 값이 달라진다 —
# 가루이자와가 역에서 3.7km, 하치노헤가 8km 떨어진 자리로 왔던 까닭이 그것이다.
# 자리 쪽을 먼저 보고, 없을 때만 화면으로 물러선다.
PLACE_LL = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
VIEW_LL = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")


def wanted(master: dict) -> list[str]:
    """일정 안의 「길찾기」 줄이 들고 있는 링크. 순서는 나온 순서다."""
    out: list[str] = []
    for d in master.get("days", []):
        for lg in d.get("legs", []):
            w = lg.get("wayfind") or {}
            for side in ("from", "to"):
                link = (w.get(side) or {}).get("link")
                if link and link not in out:
                    out.append(link)
    return out


def resolve(link: str) -> dict | None:
    """짧은 링크를 따라가 이름·좌표·placeId 를 꺼낸다.

    좌표는 거의 늘 나오고 CID 는 자리에 따라 없을 때가 있다. 좌표만 있어도
    길은 찾을 수 있으므로 CID 가 없다고 버리지 않는다.
    """
    try:
        with urllib.request.urlopen(
                urllib.request.Request(link, headers=UA), timeout=20) as r:
            final = r.geturl()
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"     못 폄  {link}  ({e})")
        return None

    out: dict = {"url": final}
    m = NAME.search(final)
    if m:
        out["name"] = urllib.parse.unquote(m.group(1)).replace("+", " ")
    m = PLACE_LL.search(final) or VIEW_LL.search(final)
    if m:
        out["lat"], out["lng"] = float(m.group(1)), float(m.group(2))
    m = CID.search(final)
    if m:
        out["cid"] = m.group(0)
        try:
            out["gid"] = place_id_of(m.group(0))
        except (ValueError, OverflowError):
            pass
    return out if ("lat" in out or "gid" in out) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    if not MASTER.exists():
        print("   정본이 없다 — parse_trip 을 먼저 돌린다")
        return 1
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    links = wanted(master)
    todo = links if a.refresh else [x for x in links if x not in cache]
    print(f"   링크 {len(links)}개 / 캐시 {len(cache)}개 / 물을 것 {len(todo)}개")
    if a.dry_run:
        for x in todo:
            print("     " + x)
        return 0

    got = 0
    for x in todo:
        r = resolve(x)
        if r:
            cache[x] = r
            got += 1
            print(f"     {r.get('name', '?')}  {r.get('lat')},{r.get('lng')}")

    # 일정에서 사라진 링크는 캐시에서도 지운다 — 남겨 두면 무엇이 살아 있는
    # 링크인지 알 수 없어진다. 되찾는 값이 아니라 한 번 물으면 되는 값이다.
    stale = [k for k in cache if k not in links]
    for k in stale:
        cache.pop(k)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
    print(f"     새로 푼 것 {got}개 · 버린 것 {len(stale)}개 → {CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
