# -*- coding: utf-8 -*-
"""구글 지도에 저장해 둔 목록과 우리 데이터를 맞춰 본다.

이름으로 맞추면 안 된다. 「도요타 렌터카 하치노헤역 서쪽 출구점」과
「Toyota Rent-a-car Hachinohe Station West」는 글자가 하나도 안 겹치고,
Takeout 은 제목을 짧은 영어로 내보내기도 한다 —
「ケンエレスタンド グランスタ八重北店」이 「Kenele Stand」로 나온다.
그 제목으로 다시 조회하면 아키하바라 지점이 온다.

CSV 의 URL 안에 든 CID 가 답이다.

    !1s0x60188bcdeddabc97:0xb41310e9ea66e419

그리고 이 CID 는 구글의 placeId 와 같은 값이다 — 앞뒤 8바이트를 리틀엔디언으로
적고 가운데 0x11 을 끼운 뒤 base64url 로 감싼 것이 placeId 다.

    ChIJ + base64url( le64(앞) + 0x11 + le64(뒤) )
    ChIJl7za7c2LGGARGeRm6ukQE7Q  ==  0x60188bcdeddabc97:0xb41310e9ea66e419

그러니 이름도, 좌표도, 조회도 필요 없다. 이미 갖고 있는 placeId 를 CID 로
바꿔 목록과 그대로 대면 된다. 같으면 같은 곳이고 아니면 아니다.

    python tools/saved_lists.py              맞춰 보고 알려 준다
    python tools/saved_lists.py --by-list    목록별로 나눠서 본다
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "data" / "places.json"
# 구글 지도 저장 목록을 내보낸 CSV. 프로젝트 안에 둔다.
#
# 한때 내려받기 폴더를 그대로 가리켰는데, 거기는 사람이 치우는 자리다.
# 실제로 폴더가 사라지자 check.py 가 통째로 멎었다 — 밖의 자리에 기대면
# 이 저장소만으로는 돌아가지 않는 셈이다.
#
# 새로 내보냈으면 그 CSV 를 여기 덮어쓴다.
SAVED = ROOT / "data" / "saved"

FTID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
NAME_IN_URL = re.compile(r"/maps/place/([^/]+)/")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def cid_of(place_id: str) -> str | None:
    """구글 placeId → CID. 못 풀면 None.

    placeId 는 ChIJ 뒤에 base64url 이 붙은 꼴이고, 그 안은
    「앞 8바이트(리틀엔디언) + 0x11 + 뒤 8바이트」다.
    """
    if not place_id or not place_id.startswith("ChIJ"):
        return None
    s = place_id[4:]
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return None
    if len(raw) < 17 or raw[8] != 0x11:
        return None
    return (f"0x{int.from_bytes(raw[:8], 'little'):x}"
            f":0x{int.from_bytes(raw[9:17], 'little'):x}")


def place_id_of(cid: str) -> str:
    """CID → placeId. cid_of 의 반대 방향이다."""
    a, b = (int(x, 16) for x in cid.split(":"))
    raw = a.to_bytes(8, "little") + bytes([0x11]) + b.to_bytes(8, "little")
    return "ChIJ" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def read_lists(folder: Path, keyword: str) -> list[dict]:
    """이름에 keyword 가 든 목록 CSV 를 다 읽는다."""
    out = []
    for n in sorted(os.listdir(folder)):
        if keyword not in nfc(n) or not n.lower().endswith(".csv"):
            continue
        for r in csv.DictReader((folder / n).read_text(encoding="utf-8-sig").splitlines()):
            url = (r.get("URL") or "").strip()
            if not url:
                continue
            m = FTID.search(url)
            u = NAME_IN_URL.search(url)
            out.append({
                "list": nfc(n).replace(".csv", "").replace("9월 일본여행 _ ", ""),
                "title": nfc(r.get("제목") or r.get("Title") or "").strip(),
                "urlName": (nfc(urllib.parse.unquote(u.group(1))).replace("+", " ")
                            if u else ""),
                "cid": m.group(1) if m else None,
                "note": nfc(r.get("메모") or "").strip(),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=str(SAVED))
    # 「9월 일본여행 _ …」 만 읽던 때는 목록의 절반을 안 봤다. 「긴자 그래픽
    # 갤러리」가 일본_WISH_장소 에 있는데도 「목록에 없다」고 나왔다.
    # 일본 여행에 쓰는 자리는 어느 목록에 담겨 있든 그 사람이 찍은 자리다.
    ap.add_argument("--keyword", default="일본", help="목록 이름에 든 말")
    ap.add_argument("--by-list", action="store_true", help="목록별로 나눠서 본다")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        sys.exit(f"목록 폴더가 없습니다: {folder}")
    saved = read_lists(folder, args.keyword)
    if not saved:
        sys.exit(f"「{args.keyword}」이 든 목록 CSV 를 못 찾았습니다: {folder}")

    places = json.loads(PLACES.read_text(encoding="utf-8"))

    ours: dict[str, dict] = {}
    noid: list[dict] = []
    for pid, v in places.items():
        c = cid_of(v.get("placeId") or "")
        if c:
            ours[c] = v
        else:
            noid.append(v)

    listed = {s["cid"]: s for s in saved if s["cid"]}
    print(f"저장 목록 {len(saved)}곳(CID {len(listed)}) · "
          f"우리 장소 {len(places)}곳(CID {len(ours)})\n")

    same = ours.keys() & listed.keys()
    only_us = [ours[c] for c in ours.keys() - listed.keys()]
    only_list = [listed[c] for c in listed.keys() - ours.keys()]

    print(f"  둘 다 있음   {len(same)}곳")
    print(f"  우리에게만   {len(only_us)}곳   ← 목록에 안 찍어 두셨거나 딴 곳을 집었다")
    print(f"  목록에만     {len(only_list)}곳   ← 일정에 안 넣었거나 안 갈 곳")
    if noid:
        print(f"  맞출 수 없음 {len(noid)}곳   ← placeId 가 없다")
        for v in noid:
            print(f"      {v.get('name', '')[:44]}")

    if only_us:
        print(f"\n[우리에게만 있는 곳 {len(only_us)}]")
        for v in sorted(only_us, key=lambda x: x.get("name", "")):
            print(f"     {v.get('name', '')[:34]:<36}{(v.get('address') or '')[:40]}")

    print(f"\n[목록에만 있는 곳 {len(only_list)}]")
    if args.by_list:
        for name in sorted({s["list"] for s in only_list}):
            rows = [s for s in only_list if s["list"] == name]
            print(f"\n  ── {name} ({len(rows)}) ──")
            for s in sorted(rows, key=lambda x: x["title"]):
                print(f"     {(s['title'] or s['urlName'])[:52]}")
    else:
        for s in sorted(only_list, key=lambda x: (x["list"], x["title"]))[:40]:
            print(f"     {s['list'][:6]:<8}{(s['title'] or s['urlName'])[:46]}")
        if len(only_list) > 40:
            print(f"     … 외 {len(only_list) - 40}곳  (--by-list 로 전부)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
