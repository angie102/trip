# -*- coding: utf-8 -*-
"""정본(master.json) → React 가 그대로 렌더링할 수 있는 뷰 모델.

React 쪽에서 계산할 일을 여기서 미리 끝낸다.

  * 요일 계산      — 그 날짜의 영업시간을 이미 골라서 붙인다
  * places 조회    — 좌표·placeId 를 항목에 직접 박는다
  * 중첩 평탄화     — subItems/candidates 를 하나의 spots 배열로
  * 파생값         — 하루 경비, 지도 중심, 경계 상자, 패스 일차

내보내는 곳: web-react/src/data/trip.json

사용:
    python tools/export_web.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from place_kinds import kind_of      # noqa: E402  구글 분류 → 마커 여섯

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "web-react" / "src" / "data" / "trip.json"

DOW = "월화수목금토일"
MODE_LABEL = {"car": "렌트카", "bus": "버스", "train": "기차", "plane": "항공", "walk": "도보"}






# ── 길찾기 ─────────────────────────────────────────────
# 일정의 「길찾기」 줄이 붙은 구간만 버튼을 갖는다(parse_trip 의 DIR_CELL).
# 여기서는 그 줄이 가리키는 양 끝을 실제 자리로 푼다.
#
# 그 줄에 적힌 지도 링크는 links.py 가 미리 풀어 둔다. 여기서 묻지 않는다 —
# 「정본 → 뷰 모델」에 네트워크가 끼면 인터넷이 없을 때 화면이 달라진다.
LINKS: dict = {}


def end_view(pv: dict, text: str | None) -> dict | None:
    """푼 자리를 길찾기의 한쪽 끝으로 옮긴다. 영업시간 따위는 안 싣는다 —
    여기 필요한 것은 「어디인가」뿐이다."""
    out = {"text": text or pv.get("name") or ""}
    if pv.get("lat") is not None:
        out["lat"], out["lng"] = pv["lat"], pv["lng"]
    if pv.get("gid"):
        out["gid"] = pv["gid"]
    return out if (out["text"] or out.get("gid")) else None


def leg_end(written: dict | None, item: dict | None, fallback: str | None,
            stay: dict | None, links: dict) -> dict | None:
    """길찾기의 한쪽 끝을 푼다. 위에서부터 이긴다.

        ① 일정의 「길찾기」 줄에 적은 것 — 지도 링크가 붙어 있으면 그 자리
        ② 그 끝에 맞닿은 항목의 자리 — placeId 까지 온다
        ③ 끝이 「숙소」면 그날 묵는 곳. 숙소는 날마다 달라 이름으로 못 짚는다
        ④ 제목에서 뽑힌 이름 그대로

    ① 이 ② 를 이기는 까닭은, 자동으로 푼 것이 틀려서 적었을 것이기 때문이다.

    ④ 는 이름을 구글에 넘기는 것이다. 이 프로젝트는 이름으로 장소를 찾는 길을
    걷어냈는데(places_lookup 의 「48km 떨어진 슈퍼」), 그 규칙이 막으려던 것은
    틀린 좌표가 지도에 점 하나로 조용히 찍히는 것이다. 아무도 안 물어본다.
    길찾기는 다르다 — 틀리면 구글 지도가 열려서 눈앞에 보이고 거기서 고칠 수
    있다. 틀림이 보이는 자리라서 허용한다.
    여기서 푼 끝은 지도 마커에 절대 쓰지 않는다.
    """
    if written:
        name, link = written.get("name"), written.get("link")
        # 링크를 풀어 두었으면 그것이 가장 정확하다 — 사람이 지도에서 짚은 자리다
        r = links.get(link) if link else None
        if r:
            out = {"text": name or r.get("name") or ""}
            if r.get("lat") is not None:
                out["lat"], out["lng"] = r["lat"], r["lng"]
            if r.get("gid"):
                out["gid"] = r["gid"]
            return out
        if name:
            return {"text": name}
    pv = (item or {}).get("place")
    # 후보들의 중점(approx)은 「대충 이쯤」이라 길을 찾아갈 자리가 아니다
    if pv and not pv.get("approx") and (pv.get("lat") is not None or pv.get("gid")):
        return end_view(pv, fallback or pv.get("name"))
    if fallback and "숙소" in fallback and (stay or {}).get("place"):
        return end_view(stay["place"], stay.get("name") or fallback)
    if fallback:
        return {"text": fallback}
    return None


def dir_of(leg: dict, want: dict | None, by_id: dict,
           stay: dict | None, links: dict) -> dict | None:
    """'길찾기' 시트에 적힌 구간의 양 끝.

    목적지를 못 풀면 아예 없다 — 열 곳이 없는 버튼은 안 다는 것이 낫다.
    출발지는 없어도 된다. 빼면 구글이 「내 위치에서」로 연다.
    """
    if not want:
        return None
    a, b = want.get("from"), want.get("to")
    to = leg_end(b, by_id.get(leg["to"]), leg["dest"], stay, links)
    if not to:
        return None
    out = {"to": to}
    frm = leg_end(a, by_id.get(leg["from"]), leg["origin"], stay, links)
    if frm:
        out["from"] = frm
    return out


def stay_of(d: dict, places: dict | None = None, iso: str = "") -> dict | None:
    """그날 묵는 곳. 이름과, 여행 중에 쓸모가 있는 것만.

    이미 낸 돈('결제완료')은 현지에서 할 일이 없으므로 금액을 싣지 않는다.
    화면에 뜨는 금액은 '아직 낼 돈' 이라는 뜻이어야 한다.

    좌표는 여기 한 번만 싣는다. 체크인·체크아웃 항목은 좌표를 갖지 않으므로
    (places_keys 가 건너뛴다) 호텔의 자리는 이 줄이 유일하게 안다.
    """
    st = d.get("stay") or {}
    name = st.get("name")
    if not name:
        return None
    out = {"name": name}
    if places is not None and st.get("placeId"):
        pv = place_view(st["placeId"], places, iso, st.get("hours"),
                        st.get("hoursPick"))
        if pv and pv.get("lat") is not None:
            out["place"] = pv
    if st.get("pay"):
        out["pay"] = st["pay"]
    if st.get("booker"):
        out["booker"] = st["booker"]
    if st.get("terms"):
        out["terms"] = st["terms"]
    if st.get("pay") == "현지 결제" and st.get("costJpy"):
        out["costJpy"] = st["costJpy"]
    return out


def weekday(iso: str) -> str:
    y, m, d = map(int, iso.split("-"))
    return DOW[date(y, m, d).weekday()]


def to_min(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


KO = re.compile(r"[가-힣]")
JA = re.compile(r"[ぁ-んァ-ヶ一-龥]")


def ja_of(place: dict | None, ko: str) -> str:
    """그 자리의 원어 이름. 없으면 빈 문자열.

    구글에 ja 로 한 번 물어 받아 둔 값(jaName)이 전부다.

    한때는 조회에 쓴 검색어(searchAs)에서 짜냈다. 검색어는 곳을 특정하려고
    지역을 덧붙인 말이라(「無印良品 新潟」) 꼬리를 떼는 목록을 들고 있었고,
    떼고 나서도 원어인지 아닌지 다시 가려야 했다. CID 로 자리를 맞추게 된
    뒤로 이름 조회가 없어졌으니 검색어도, 꼬리 떼기도 함께 걷어냈다.

    읽는 이름이 원어 안에 그대로 들어 있으면 원어가 아니다 —
    같은 말이 두 번 서기 때문이다.
    """
    ja = ((place or {}).get("jaName") or "").strip()
    if not JA_RE.search(ja):
        return ""
    return "" if ko and ko.lower() in ja.lower() else ja


def split_name(raw: str, google: str = "") -> tuple[str, str]:
    """가게 이름을 (읽는 이름, 원어 이름) 으로 가른다.

    '鮨㐂 やまだ藤七(와쇼쿠 레스토랑 스시기 야마다 후지시치)'
        → ('와쇼쿠 레스토랑 스시기 야마다 후지시치', '鮨㐂 やまだ藤七')
    '미네무라 브루어리(峰村醸造) 구경'
        → ('미네무라 브루어리', '峰村醸造')

    목록에서는 읽는 이름만 쓰고, 원어는 상세에서 둘째 줄에 둔다.
    """
    segs = [s.strip(" :：,·/-") for s in re.split(r"[（(]|[)）]", raw)]
    segs = [s for s in segs if s]
    # 앞에 나온 조각이 대개 본이름이다. 'Kitari(炭火焙煎珈琲 きらり): 모닝커피' 에서
    # 한글만 보고 고르면 설명 조각(': 모닝커피')을 이름으로 잡는다.
    ko = next((s for s in segs if not JA.search(s)), "")
    if not ko and google and KO.search(google) and not JA.search(google):
        ko = google                                              # 구글의 한국어 표기
    ja = next((s for s in segs if JA.search(s)), "")
    if not ko:
        ko = raw
    if ja == ko:
        ja = ""
    return ko, ja


# '따로 먹기' — 고를 후보가 아니라 각자 갈 집이 정해진 것이다
SEPARATE = re.compile(r"따로")
NORM = re.compile(r"[\s()（）\[\]「」『』・·,.:：/\-—–~〜～!?'’\"]+")



def place_view(pid: str | None, places: dict, iso: str,
               own: list | None = None,
               pick: list[str] | None = None) -> dict | None:
    """그 날짜 기준으로 이미 풀린 장소 정보.

    own 은 일정에 직접 적어둔 영업시간이다. 구글이 준 값보다 **우선한다** —
    '호텔 조식 뷔페 6:00~9:00' 같은 것은 구글에는 호텔 영업시간으로 나오지
    조식 시간으로 나오지 않는다. 더 구체적인 출처가 이긴다.
    """
    p = places.get(pid or "")
    # 장소가 없으면 시각만으로 자리를 만들지 않는다.
    #
    # 한때 {id: null, name: ""} 이라는 껍데기가 나왔다 — 「츠타 온천 료칸
    # 체크인」의 메모에서 긁힌 (10:00 ～ 12:00) 이 그 집 영업시간 행세를 했다.
    # 그것은 남녀 교대 온천 시간이지 그 집이 여닫는 시각이 아니다.
    # 그 시각은 메모에 그대로 남으니 잃는 것도 없다.
    if not p:
        return None
    out: dict = {"id": pid, "name": p.get("googleName") or p.get("name") or "",
                 "kind": kind_of(p)}
    if isinstance(p.get("lat"), (int, float)):
        out["lat"], out["lng"] = p["lat"], p["lng"]
    if p.get("placeId"):
        out["gid"] = p["placeId"]            # 구글 place_id — 딥링크에 쓴다
    if p.get("address"):
        out["address"] = p["address"]
    # 「18:00, 18:30 중 선택」 — 료칸 조식·석식처럼 고를 시각이 정해진 자리.
    # 여닫는 시각이 아니라 고르는 시각이라 따로 싣는다.
    if pick:
        out["hoursPick"] = pick
        return out
    if own:
        out["hours"] = own                   # 일정에 적어둔 시간이 이긴다
        return out
    hours = p.get("hours")
    if hours:
        today = hours.get(weekday(iso))
        if today:
            out["hours"] = today             # [{open, close}] — 브레이크면 2개
            out["always"] = bool(p.get("always"))
        else:
            out["closed"] = True             # 그날 휴무 (추측이 아니라 사실)
    return out


def usual_hours(p: dict | None) -> list[dict] | None:
    """그 가게의 여느 날 영업시간.

    정기휴일에 예약이 잡힌 자리에 쓴다. 그날의 시간은 없지만(닫는 날이니까)
    예약 손님은 받는다 — 9/21 은 월요일이고 天㐂あらた 도 能登新 도 월요일이
    휴일인데, 그날 낮과 저녁에 예약이 잡혀 있다. 그러면 화면이 비어 있을 게
    아니라 여느 날 시간을 적어야 한다. 몇 시에 문을 여는 집인지는 알아야
    한다 — 예약 시각이 그 안에 드는지, 브레이크 타임에 걸리는지.

    요일마다 다르면 가장 잦은 꼴을 고른다. 일요일만 점심을 하는 집(能登新)
    에서 그 하루짜리 꼴을 「여느 날」이라 부를 수는 없다.
    """
    hours = (p or {}).get("hours") or {}
    if not hours:
        return None
    c = Counter(json.dumps(v, sort_keys=True, ensure_ascii=False)
                for v in hours.values())
    return json.loads(c.most_common(1)[0][0])


def open_by_reservation(pv: dict | None, places: dict, pid: str | None) -> None:
    """예약이 잡혀 있으면 「그날 휴무」는 나에게 적용되지 않는다.

    정기휴일에도 예약 손님은 받고, 실제로 그렇게 잡아 두었다. 닫는 날이라고
    화면을 비워 두면 몇 시에 여는 집인지조차 알 수 없으니 여느 날 시간을 적는다.
    같은 다섯 줄이 항목·후보·예약된 후보 세 군데에 흩어져 있던 것을 모았다.
    """
    if not pv or not pv.get("closed"):
        return
    pv.pop("closed", None)
    pv["byReservation"] = True
    if (u := usual_hours(places.get(pid or ""))):
        pv["hours"] = u


def spot_view(name: str, src: dict, places: dict, iso: str, depth: int,
              group: bool) -> dict:
    pv = place_view(src.get("placeId"), places, iso, src.get("hours"),
                    src.get("hoursPick"))
    ko, ja = split_name(name, (pv or {}).get("name", "")
                        if not (pv or {}).get("approx") else "")
    if not ja:
        # 시트에도 구글에도 한글 이름뿐인 곳이 있다 — 렌터카 영업소가 그렇다.
        ja = ja_of(places.get(src.get("placeId")), ko)
    out: dict = {"name": ko, "depth": depth}
    if ja:
        out["nameJa"] = ja
    if group:
        out["group"] = True
    if src.get("link"):
        out["link"] = src["link"]
    if src.get("notPlace"):
        out["note"] = True
    desc = src.get("desc") or " · ".join(src.get("notes", []))
    if desc:
        out["desc"] = desc
    if src.get("reservation"):
        out["reservation"] = src["reservation"]
        open_by_reservation(pv, places, src.get("placeId"))
    if pv:
        out["place"] = pv
    return out


def spots_of(item: dict, places: dict, iso: str, depth: int = 0) -> list[dict]:
    """하위 항목 + 후보를 한 배열로 편다. 순서는 화면에 나오는 순서."""
    out: list[dict] = []
    for s in item.get("subItems", []):
        inner = spots_of(s, places, iso, depth + 1)
        out.append(spot_view(s["title"], s, places, iso, depth, bool(inner)))
        out += inner
    for c in item.get("candidates", []):
        out.append(spot_view(c["name"], c, places, iso, depth, False))
    return out


def load_exceptions() -> dict:
    """규칙으로 담을 수 없는 것 — data/exceptions.json 한 곳이다.

    한때 셋으로 갈라져 있었다. 표기는 names.json, 분류는 overrides.json,
    지역·구간·항목은 fix_master.py 의 코드 상수. 「지금 무엇이 걸려 있나」를
    보려면 세 군데를 봐야 했고, 그중 하나는 코드였다.
    """
    f = DATA / "exceptions.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def load_overrides() -> dict:
    """구글이 준 업종이 틀린 자리 — 지도 마커 종류를 덮는다."""
    return {"kind": load_exceptions().get("분류") or {}}


def load_names() -> dict:
    """화면에 쓸 이름 — 표기 표.

    표기 규칙 자체는 일괄이다: 일본 상호는 한글 읽기로 적고 원어는 nameJa 로
    남긴다. 다만 한글 읽기는 기계가 만들 수 없어 사람이 적은 값이 필요하다.
    """
    return load_exceptions().get("표기") or {}


JA_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")   # 가나·한자


def apply_overrides(view: dict, ov: dict) -> tuple[int, int, list[str]]:
    """이름으로 찾아 마지막에 덮어쓴다.

    여기 오는 것은 「구글이 준 업종이 틀린 자리」뿐이다.
    규칙이 모자라 생긴 예외가 아니라 바깥 데이터가 틀려서 생긴 예외라,
    규칙을 아무리 다듬어도 줄지 않는다.

    돌려주는 값은 (예외, 표기, 죽은 예외) 셋이다. 예외와 표기를 섞어 세던
    때는 「예외 82건」이 되어 규칙이 흔들리는 것처럼 보였는데, 그중
    일흔여섯은 예외가 아니라 한글 표기 사전이었다.
    """
    kinds = ov.get("kind") or {}
    rename = load_names()
    n, named, used = 0, [0], set()

    def touch(name: str, holder: dict, field: str | None = None) -> int:
        """이름은 정확히 같지 않아도 된다.

        예외에 '중앙 제1 리프트' 라고 적어두면 '자오 중앙 로프웨이 & 중앙 제1
        리프트' 도 같은 것으로 본다. 표기 변형마다 예외를 늘리지 않기 위해서다.
        """
        hit = 0
        nn = NORM.sub("", name).lower()

        def pick(table):
            return next((k for k in table if NORM.sub("", k).lower() in nn), None)

        pl = holder.get("place")
        # 예외는 이미 있는 장소를 고칠 뿐, 장소를 만들지 않는다.
        if pl:
            if (k := pick(kinds)) and pl.get("kind") != kinds[k]:
                pl["kind"] = kinds[k]
                used.add(k)
                hit += 1
        if (k := pick(rename)):
            # 어느 이름으로 맞췄는지를 그대로 고쳐야 한다. field 를 받지 않으면
            # detail 로 맞춘 것도 title 로 흘러가, 「역에서 기차에서 먹을거 사기」가
            # 「엔무스」가 되어 버린다 — 이름을 바꾸랬더니 제목을 갈아 끼운 셈이다.
            key = field or ("name" if "name" in holder else "title")
            # 한글이 없던 이름은 원어로 내려 이름 옆에 남긴다. 가나·한자만
            # 보던 때는 「Nagaiki no Chaya」 를 바꾸면 로마자 표기가 통째로
            # 사라졌다 — 간판에 적힌 것이 그쪽인데도.
            ja = {"name": "nameJa", "detail": "detailJa"}.get(key)
            if ja and not holder.get(ja) and not KO_RE.search(holder[key]):
                holder[ja] = holder[key]
            holder[key] = rename[k]
            named[0] += 1
        return hit

    for day in view["days"]:
        for it in day["items"]:
            # 이름마다 고칠 자리를 짝지어 넘긴다
            for name, field in ((it.get("detail"), "detail"), (it["title"], "title")):
                if name:
                    n += touch(name, it, field)
            for s in it.get("spots", []):
                n += touch(s["name"], s, "name")
    dead = [k for k in kinds if k not in used]
    return n, named[0], dead


# 한자·가나가 있는데 한글이 없으면 읽기를 아직 안 적은 것이다.
# rename 이 적용된 뒤에 세야 한다 — 화면에 무엇이 뜨느냐가 요점이다.
KO_RE = re.compile(r"[가-힣]")


def missing_ko(view: dict) -> list[tuple[str, str]]:
    out, seen = [], set()
    for d in view["days"]:
        names = []
        for it in d["items"]:
            names.append(it.get("detail"))
            names += [s.get("name") for s in it.get("spots", [])]
        for lg in d.get("legs", []):
            names += [s.get("name") for s in lg.get("spots", [])]
        for nm in names:
            if not nm or nm in seen:
                continue
            seen.add(nm)
            # 가나·한자가 든 이름에 한글이 없으면 반드시 고쳐야 한다 —
            # 읽을 수가 없다.
            #
            # 로마자는 다르다. 「Nagaiki no Chaya」 처럼 일본어를 로마자로
            # 적은 것도 있지만 「Skip Egg」 같은 영어 상호도 있고, 라틴
            # 알파벳은 그대로 읽힌다. 기계는 이 둘을 못 가르므로 경고로
            # 올리지 않고 아래에서 세어만 둔다 — 사람이 한 번 훑을 목록이다.
            if JA_RE.search(nm) and not KO_RE.search(nm):
                out.append((d["date"][5:], nm))
    return out


def label_places(out: dict) -> list[tuple[str, str, str]]:
    """장소 행세를 하는 라벨을 찾는다.

    라벨은 「내가 무엇을 하는가」이고 장소는 「그 자리가 어디인가」다.
    둘이 섞이면 지도가 「점심 따로 먹기」를 찍으려 들고, 데이터를 훑는 사람도
    그것을 가게로 읽는다. 실제로 되풀이해 헛짚었다.

    셋을 본다.
      · 좌표도 id 도 없는 장소 — 무엇에도 걸리지 않는 껍데기다
      · 이름이 항목 제목과 똑같은데 id 가 없는 장소 — 제목을 베낀 것이다
      · 중점(approx)에 달린 이름 — 중점은 자리가 아니라 「대충 이쯤」이다
    """
    bad: list[tuple[str, str, str]] = []
    for d in out["days"]:
        for it in d["items"]:
            holders = [("항목", it)] + [("후보", s) for s in it.get("spots", [])]
            for tag, h in holders:
                pl = h.get("place")
                if not pl:
                    continue
                if not pl.get("id") and pl.get("lat") is None:
                    bad.append((d["date"], tag, f"껍데기 {pl}"))
                elif pl.get("approx") and pl.get("name"):
                    bad.append((d["date"], tag, f"중점에 이름 {pl['name']}"))
                elif not pl.get("id") and pl.get("name") == it.get("title"):
                    bad.append((d["date"], tag, f"제목을 베낌 {pl['name']}"))
    return bad


def export(trip: dict, places: dict) -> dict:
    days = []
    for d in trip["days"]:
        iso = d["date"]
        items, pts = [], []

        for it in d["items"]:
            pid = it.get("placeId") or (it.get("detail") or {}).get("placeId")
            own = it.get("hours") or (it.get("detail") or {}).get("hours")
            pick = (it.get("hoursPick")
                    or (it.get("detail") or {}).get("hoursPick"))
            pv = place_view(pid, places, iso, own, pick)
            spots = spots_of(it, places, iso)

            # 자기 좌표가 없으면 후보들의 중심을 쓴다.
            #
            # 이름은 달지 않는다. 한때 항목 제목을 이름 자리에 넣었는데
            # (「🍚점심 따로 먹기」), 그것은 자리 이름이 아니라 내가 할 일이다.
            # 지도는 approx 를 안 찍으니 화면에는 안 나왔지만, 데이터를 훑을
            # 때마다 장소로 보여 같은 자리에서 되풀이해 헛짚었다.
            # 이 값은 「이 항목이 대충 어디쯤인가」일 뿐이다.
            child = [s["place"] for s in spots
                     if s.get("place", {}).get("lat") is not None]
            if (not pv or "lat" not in pv) and child:
                pv = {
                    "lat": sum(c["lat"] for c in child) / len(child),
                    "lng": sum(c["lng"] for c in child) / len(child),
                    "approx": True,
                }

            row: dict = {
                "id": it["id"],
                "type": it["type"],
                "title": it["title"],
                "time": (it.get("time") or {}).get("start"),
                "end": (it.get("time") or {}).get("end"),
            }
            if it.get("detail"):
                det = it["detail"]
                # 확정된 한 곳이다. 후보와 같은 규칙으로 이름을 가른다 —
                # 앞에는 읽는 이름, 옆에는 원어.
                ko, ja = split_name(det["name"], (pv or {}).get("name", "")
                                    if not (pv or {}).get("approx") else "")
                if not ja:
                    ja = ja_of(places.get(det.get("placeId")), ko)
                row["detail"] = ko
                if ja:
                    row["detailJa"] = ja
                if det.get("desc"):
                    row["detailDesc"] = det["desc"]
            if it.get("link"):
                row["link"] = it["link"]
            if it.get("notes"):
                row["notes"] = it["notes"]
            # 할 일은 글로 내보낸다. 예전에는 True 만 보내고 화면이 notes 를
            # 대신 그렸는데, 그 바람에 메모까지 할 일 상자에 담겼다.
            if it.get("tasks"):
                row["tasks"] = it["tasks"]
            # 그림은 이동만 싣고 있었다. 정본에는 항목에도 붙는데 여기서
            # 떨어져 나가, 「리무진 버스 타러 가기」 아래 안내도가 화면
            # 어디에도 없었다 — 붙이는 쪽과 내보내는 쪽이 어긋난 꼴이다.
            if it.get("image"):
                row["image"] = it["image"]
            if it.get("fixedTime"):
                row["fixed"] = True
            if it.get("hideTime"):
                row["hideTime"] = True
            if it.get("reservation"):
                row["reservation"] = dict(it["reservation"])
                open_by_reservation(pv, places, pid)
                # 예약한 집이 후보 중 하나면 그 줄에 표식을 단다.
                # 견주는 것은 후보의 이름 하나다 — place.name 은 자리마다
                # 구글이 준 이름이기도 하고 시트 원문이기도 해서 기준이 못 된다.
                rname = it["reservation"].get("name") or ""
                for s in spots:
                    if not rname:
                        break
                    if rname == s["name"]:
                        s["reserved"] = True
                        sp = s.get("place")
                        open_by_reservation(sp, places, (sp or {}).get("id"))
                        break
            # 「따로 먹기」는 고를 후보가 아니라 각자 갈 집이 정해진 것이다
            if spots and SEPARATE.search(it["title"]):
                row["settled"] = True
            if pv:
                row["place"] = pv
                if pv.get("lat") is not None:
                    pts.append(pv)
            if spots:
                row["spots"] = spots
                pts += [s["place"] for s in spots
                        if s.get("place", {}).get("lat") is not None]
            items.append(row)

        legs = []
        by_id = {r["id"]: r for r in items}
        # 「숙소」로 적힌 끝은 이 줄이 푼다 — 체크인·체크아웃 항목은 좌표가 없다
        stay = stay_of(d, places, iso)
        for lg in d.get("legs", []):
            notes = lg.get("notes", [])
            head = lambda p: next((x[len(p):] for x in notes
                                   if x.startswith(p)), None)
            leg = {
                "id": lg["id"], "mode": lg["mode"],
                "modeLabel": MODE_LABEL.get(lg["mode"], lg["mode"]),
                "title": lg["title"],
                "fixed": bool(lg.get("fixedTime")),
                "vehicle": lg.get("vehicle") or "",
                "time": (lg.get("time") or {}).get("start"),
                "end": (lg.get("time") or {}).get("end"),
                "from": lg.get("fromItem"), "to": lg.get("toItem"),
                "min": lg.get("durationMin"),
                "cost": lg.get("costText"),
                "covered": bool(lg.get("covered")),
                # 출발지·도착지는 메모에 「도착: 오미야역」 꼴로 들어 있다.
                # 꺼내 자리에 앉히고, 메모에서는 뺀다 — 두 번 보일 까닭이 없다.
                "dest": head("도착: "),
                "origin": head("출발: "),
                "notes": [x for x in notes
                          if not x.startswith(("도착: ", "출발: "))],
                "image": lg.get("image"),
                "seat": lg.get("seat"),
            }
            # 할 일은 항목만 지고 있었다. 그래서 「*** 리무진 버스 타러 가는 길」을
            # 이동 아래 적어도 화면 어디에도 안 뜨고 그날 체크리스트에만 남았다 —
            # 정작 그것이 필요한 자리는 그 이동 곁이다.
            if lg.get("tasks"):
                leg["tasks"] = lg["tasks"]
            # '길찾기' 시트에 적어 둔 구간만 길찾기를 갖는다
            route = dir_of(leg, lg.get("wayfind"), by_id, stay, LINKS)
            if route:
                leg["dir"] = route
            way = spots_of(lg, places, iso)
            if way:
                leg["spots"] = way          # 가는 길에 들를 곳
                pts += [s["place"] for s in way
                        if s.get("place", {}).get("lat") is not None]
            legs.append(leg)

        flags = []
        for p in trip.get("passes", []):
            if p["from"] <= iso <= p["to"]:
                n = (date(*map(int, iso.split("-")))
                     - date(*map(int, p["from"].split("-")))).days + 1
                flags.append({"kind": "pass", "text": f"JR패스 {n}일차",
                              "full": f"{p['name']} {n}/{p['days']}일차"})
        car_slots = set()
        for c in trip.get("cars", []):
            if c["from"][:10] <= iso <= c["to"][:10]:
                flags.append({"kind": "car", "text": "렌트카"})
            # 차를 주고받는 시각. 그 자리가 렌터카 영업소라는 것은 이 표가 안다 —
            # 구글에게 업종을 물어 볼 까닭이 없다.
            for t in (c["from"], c["to"]):
                if t[:10] == iso:
                    car_slots.add(t[11:16])

        # 렌터카 영업소는 「시각을 지켜야 하는 약속」이라 예약과 같은 자리에 둔다.
        # place_kinds 에도 같은 규칙이 있지만(car_rental → resv) 그쪽은 구글이 준
        # 업종을 보므로, 조회가 덜 된 자리에서는 서지 않는다 — 넷 중 셋이 그랬다.
        # 여기서 못 박으면 조회와 무관하게 늘 선다.
        for it in items:
            if it.get("time") in car_slots and it.get("place"):
                it["place"]["kind"] = "resv"

        bounds = None
        if pts:
            bounds = {
                "n": max(p["lat"] for p in pts), "s": min(p["lat"] for p in pts),
                "e": max(p["lng"] for p in pts), "w": min(p["lng"] for p in pts),
            }

        days.append({
            "date": iso, "dow": weekday(iso), "region": d.get("region"),
            "stay": stay,
            "flags": flags, "items": items, "legs": legs,
            "moveMin": sum(l["min"] for l in legs if l.get("min")),
            "bounds": bounds,
            "tasks": [t for t in trip.get("checklist", []) if t["due"] == iso],
        })

    return {
        "title": trip["title"],
        "passes": trip.get("passes", []),
        "checklist": trip.get("checklist", []),
        "prep": trip.get("prep", []),        # 날짜가 없는 준비 목록
        "days": days,
    }


def main() -> int:
    master = DATA / "master.json"
    if not master.exists():
        sys.exit("data/master.json 이 없습니다.")
    trip = json.loads(master.read_text(encoding="utf-8"))
    places = json.loads((DATA / "places.json").read_text(encoding="utf-8"))
    lm = DATA / "link_map.json"
    LINKS.update(json.loads(lm.read_text(encoding="utf-8")) if lm.exists() else {})

    out = export(trip, places)
    hits, named, dead = apply_overrides(out, load_overrides())
    print(f"  예외 {hits}건 · 표기 {named}건  (data/exceptions.json)")
    if dead:
        # 걸릴 자리가 없어진 예외는 지운다. 남겨 두면 무엇이 살아 있는
        # 규칙인지 알 수 없어지고, 예외가 실제보다 많아 보인다.
        print(f"  ! 걸리지 않는 예외 {len(dead)}건 — 지운다: " + " · ".join(dead))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    n_it = sum(len(d["items"]) for d in out["days"])
    n_sp = sum(len(i.get("spots", [])) for d in out["days"] for i in d["items"])
    n_pt = sum(1 for d in out["days"] for i in d["items"]
               if i.get("place", {}).get("lat") is not None)
    n_hr = sum(1 for d in out["days"] for i in d["items"]
               for s in i.get("spots", []) if s.get("place", {}).get("hours"))
    ko = missing_ko(out)
    if ko:
        print(f"  ! 한글 읽기 없음 {len(ko)}건 — "
              f"data/exceptions.json 의 표기에 적는다")
        for d, n in ko[:8]:
            print(f"      {d} {n}")
        if len(ko) > 8:
            print(f"      … 외 {len(ko) - 8}건")
    lb = label_places(out)
    if lb:
        print(f"  ✗ 라벨이 장소 행세하는 자리 {len(lb)}곳")
        for d, tag, why in lb:
            print(f"      {d} {tag} {why}")

    kb = OUT.stat().st_size / 1024
    print(f"  날짜 {len(out['days'])} · 항목 {n_it} (좌표 {n_pt}) · 후보 {n_sp} (영업시간 {n_hr})")
    print(f"  -> {OUT}  ({kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
