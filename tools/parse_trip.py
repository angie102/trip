# -*- coding: utf-8 -*-
"""여행 일정 엑셀 → data/master.json (정본)

설계 문서(docs/plan.html)에서 확정한 규칙을 그대로 구현한다.

  * A열 시간은 12시간제와 24시간제가 섞여 있음 → 단조 증가 제약으로 해석
  * C·D열은 위치가 아니라 값 패턴으로 비용/소요시간 판별
  * 회색(#CCCCCC) 글자 = JR 동일본 패스가 커버하는 금액 → 실지출에서 제외
  * B열 앞머리 이모지 + 키워드로 8종 타입 분류
  * 이동(move)은 항목이 아니라 두 항목 사이의 leg
  * 하위 '-' 라인에서 후보·영업시간·가격·예약정보 추출

사용:
    python tools/parse_trip.py                # 9.19-20 시트만 (프로토타입)
    python tools/parse_trip.py --all          # 전체 15일
    python tools/parse_trip.py --sheet 9.21   # 특정 시트
    python tools/parse_trip.py --dry-run      # 파일 쓰지 않고 콘솔 출력만
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import time as Time
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
# 정본은 구글 시트다. pull_sheet.py 로 받아둔 사본만 읽는다.
#
# 없을 때 옛 사본으로 물러서던 길이 있었는데, 그 사본은 8월 것이라
# 조용히 다섯 달 묵은 일정을 읽게 된다. 없으면 없다고 말하는 편이 낫다.
XLSX = ROOT / "data" / "sheet.xlsx"
DATA = ROOT / "data"
YEAR = 2026
GREY = "FFCCCCCC"          # 글자색: JR 패스가 커버하는 금액
YELLOW = "FFFFFF00"        # 셀 배경: 확정 시각 (예약·렌터카 인수/반납)
IMAGES: dict[str, list[list]] = {}   # {시트: [[행, 파일명]]}
SHEET_RESV: list[dict] = []      # '예약' 시트에서 읽은 예약
SHEET_SEATS: list[dict] = []     # '지정석' 시트에서 읽은 열차 예약
SHEET_HOTELS: dict[str, dict] = {}   # '호텔' 시트에서 읽은 숙박 (날짜 → 정보)
SHEET_CARS: list[dict] = []      # 같은 시트의 렌터카

# ─────────────────────────────────────────────────────────────
# 패턴
# ─────────────────────────────────────────────────────────────
DAY_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\s*\[(.)\]")
SECTION_RE = re.compile(r"^(오전|오후|숙박)$")
TIME_RANGE_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*[~〜～ー–—\-]\s*(\d{1,2}):(\d{2})")
TIME_ONE_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")
COST_RE = re.compile(r"([\d,]+)\s*(?:엔|円)")
HOURS_RE = re.compile(r"(오전|오후)?\s*(\d{1,2}):(\d{2})\s*[~〜～ー–—\-]\s*(오전|오후)?\s*(\d{1,2}):(\d{2})")
# '조식 / 7:30, 8:00, 8:30 중 선택' — 고를 시각의 목록.
#
# 료칸 조식·석식이 이 꼴이다. 여닫는 시각이 아니라 HOURS_RE 에 걸리지 않아
# 통째로 설명으로 흘러갔고, 영업시간 자리는 비어 구글이 가진 그 료칸의
# 체크인 시간대(12:30~16:00)가 아침 줄에 대신 붙었다.
PICK_RE = re.compile(r"((?:\d{1,2}:\d{2})(?:\s*,\s*\d{1,2}:\d{2})+)\s*중\s*선택")


# 하위 줄을 체크리스트로 올리는 표시. '***' 와 같은 뜻이다.
# 표기 규칙 — 시트에서 쓰는 접두어
STAR3 = re.compile(r"^\s*\*{3,}\s*")      # *** 체크리스트
STAR1 = re.compile(r"^\s*\*{1,2}\s*")     # *  메모 (체크리스트가 아니다)
LABEL = re.compile(r"^\s*#+\s*")          # #  묶음 라벨 (아래 '-' 들의 이름)

MOVE_EMOJI = {"🚗": "car", "🚌": "bus", "🚝": "train", "✈️": "plane", "✈": "plane"}
TYPE_EMOJI = {"🍚": "food", "🏨": "stay"}

# 이모지가 없는 항목을 분류. 위에 있는 규칙이 이긴다.
KEYWORD_TYPE: list[tuple[str, tuple[str, ...]]] = [
    ("task", ("렌트", "렌터카", "반납", "인수", "패스 교환", "발권", "할인권",
              "짐 맡기", "짐맡기", "입국", "출국", "수속", "환전")),
    ("onsen", ("온천", "족욕", "노천", "대욕장")),
    ("cafe", ("카페", "커피", "디저트", "파르페", "간식", "빵", "도넛", "케이크", "모닝")),
    ("shop", ("쇼핑", "기념품", "오미야게", "마트", "슈퍼", "시장", "백화점", "아울렛", "직판장", "사기", "구매")),
    ("food", ("아침", "점심", "저녁", "식사", "먹기", "먹을", "석식", "조식")),
    ("sight", ("구경", "산책", "드라이브", "해안", "공원", "신사", "미술관", "전망대",
               "관람", "갤러리", "전시", "축제", "로프웨이", "리프트", "유람선", "테라스")),
]



# ─────────────────────────────────────────────────────────────
# 자료구조
# ─────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    name: str
    desc: str = ""
    hours: list[dict] = field(default_factory=list)   # [{"open":"09:30","close":"20:30"}]
    hoursVariants: list[dict] = field(default_factory=list)   # 특정 요일만의 시간
    closed: dict | None = None                        # {"days":["수","목"], "nth":3}
    always: bool = False                              # 24시간 영업
    hoursPick: list[str] = field(default_factory=list)  # ['18:00','18:30'] 중 골라 예약
    link: str | None = None                           # <https://…> 로 적어 둔 주소
    raw: str = ""
    placeId: str | None = None


@dataclass
class Reservation:
    booker: str | None = None
    costJpy: int | None = None                        # 셈할 때 쓰는 첫 숫자
    costText: str | None = None                       # 엑셀 금액 칸에 적힌 그대로
    note: str = ""
    name: str = ""                                    # 예약 시트에 적힌 상호
    pay: str = ""                                     # 결제방법


@dataclass
class Item:
    id: str
    type: str
    title: str
    time: dict | None = None
    placeId: str | None = None
    costText: str | None = None      # 엑셀 금액 칸에 적힌 그대로
    covered: str | None = None
    durationMin: int | None = None
    reservation: Reservation | None = None
    notes: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    fixedTime: bool = False                           # 노란 칸 = 확정 시각
    hasTask: bool = False                             # '***' 준비사항이 달린 항목
    tasks: list[str] = field(default_factory=list)    # '***' 로 적은 할 일
    costSource: str | None = None                     # "note"면 메모에서 끌어온 추정치
    hours: list[dict] = field(default_factory=list)   # 항목 자체의 영업시간
    link: str | None = None                          # 메모에 <https://…> 로 적어 둔 주소
    detail: Candidate | None = None                   # 후보가 하나뿐이면 그건 부연설명이다
    subItems: list["Item"] = field(default_factory=list)
    suspectTime: bool = False
    image: str | None = None     # {이미지} 표식이 가리킨 그림
    hideTime: bool = False           # 괄호로 감싼 시각 — 앉히되 띄우지 않는다
    src: str = ""            # 원본 셀 위치 — 검수용


@dataclass
class Leg:
    id: str
    mode: str
    title: str
    vehicle: str = ""                                 # 무엇을 타는가
    fixedTime: bool = False                           # 노란 칸 = 확정 시각
    fromItem: str | None = None
    toItem: str | None = None
    time: dict | None = None
    durationMin: int | None = None
    costText: str | None = None      # 엑셀 금액 칸에 적힌 그대로
    covered: str | None = None
    notes: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)    # '***' 로 적은 할 일
    subItems: list["Item"] = field(default_factory=list)   # 가는 길에 들를 곳
    image: str | None = None                          # {이미지} 표식이 가리킨 그림
    seat: dict | None = None         # '지정석' 시트에서 붙인 열차 예약
    wayfind: dict | None = None      # '길찾기' 시트에서 붙인 구간
    source: str = "excel"
    src: str = ""
    link: str | None = None                          # <https://…> 로 적어 둔 주소


# ─────────────────────────────────────────────────────────────
# 값 해석
# ─────────────────────────────────────────────────────────────
def cell_is_yellow(cell) -> bool:
    """A열이 노랗게 칠해져 있으면 '대략' 이 아니라 지켜야 하는 시각이다."""
    f = getattr(cell, "fill", None)
    if not f or not f.patternType:
        return False
    rgb = getattr(getattr(f, "fgColor", None), "rgb", None)
    return isinstance(rgb, str) and rgb.upper() == YELLOW


def cell_is_grey(cell) -> bool:
    color = cell.font.color if cell.font else None
    return bool(color and getattr(color, "rgb", None) == GREY)


def parse_cost(text: str) -> int | None:
    m = COST_RE.search(text)
    return int(m.group(1).replace(",", "")) if m else None


def parse_duration(text: str) -> int | None:
    """'1시간 45분' / '40분' / '2시간' → 분. 비용 문자열이면 None."""
    if COST_RE.search(text):
        return None
    h = re.search(r"(\d+)\s*시간", text)
    mi = re.search(r"(\d+)\s*분", text)
    if not h and not mi:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(mi.group(1)) if mi else 0)


def read_cd(c_cell, d_cell) -> tuple[str | None, str | None, int | None]:
    """C·D 열에서 (비용, 커버, 소요분)을 위치가 아닌 값 패턴으로 뽑는다.

    비용은 숫자로 바꾸지 않고 적힌 그대로 둔다. 돈으로 셈해야 하는 것은
    호텔('호텔' 시트)과 예약('예약' 시트)뿐이고, 그 둘은 표에서 따로 읽는다.
    여기 적힌 '5,460엔' 은 읽으라고 적어둔 글이라 글로 남긴다.
    """
    cost = covered = dur = None
    for cell in (c_cell, d_cell):
        if cell is None or cell.value is None:
            continue
        s = str(cell.value)
        if parse_cost(s) is not None:
            cost = s.strip()
            covered = "jr_east_wide" if cell_is_grey(cell) else None
            continue
        d = parse_duration(s)
        if d is not None:
            dur = d
    return cost, covered, dur


PAREN_TIME = re.compile(r"^[（(]\s*(.+?)\s*[)）]$")


def unwrap_time(raw) -> tuple[str, bool]:
    """'(1:30)' → ('1:30', True).

    괄호로 감싼 시각은 '이쯤' 이라는 뜻이다. 시간축에는 그대로 앉히되
    화면에는 띄우지 않는다 — 지키려고 적은 시각이 아니기 때문이다.
    """
    if raw is None or isinstance(raw, Time):
        return raw, False
    s = str(raw).strip()
    m = PAREN_TIME.match(s)
    return (m.group(1), True) if m else (s, False)


def raw_hm(raw) -> tuple[int, int] | None:
    if raw is None:
        return None
    if isinstance(raw, Time):
        return raw.hour, raw.minute
    s, _ = unwrap_time(raw)
    s = str(s).strip()
    m = TIME_RANGE_RE.match(s) or TIME_ONE_RE.match(s)
    return (int(m.group(1)), int(m.group(2))) if m else None


def raw_end_hm(raw) -> tuple[int, int] | None:
    if isinstance(raw, Time) or raw is None:
        return None
    s, _ = unwrap_time(raw)
    m = TIME_RANGE_RE.match(str(s).strip())
    return (int(m.group(3)), int(m.group(4))) if m else None


def hhmm(mins: int | None) -> str | None:
    return None if mins is None else f"{mins // 60 % 24:02d}:{mins % 60:02d}"


def parse_hours(text: str) -> tuple[list[dict], list[dict]]:
    """영업시간을 (기본 구간, 요일 변형) 으로 나눈다.

    '오전 8:00~오후 3:00, 오후 4:00~오후 7:00'  → 기본 2구간 (브레이크 타임)
    '오전 8:00~오후 10:00 (금 오전 8:00~오후 5:00)' → 기본 1 + 금요일 변형 1

    앞에 요일 글자가 붙은 구간은 그날만의 시간이므로 브레이크로 섞으면 안 된다.
    """
    main: list[dict] = []
    variants: list[dict] = []
    for m in HOURS_RE.finditer(text):
        ap1, h1, m1, ap2, h2, m2 = m.groups()
        h1, m1, h2, m2 = int(h1), int(m1), int(h2), int(m2)
        start = (h1 % 12 + 12 if ap1 == "오후" and h1 != 12 else h1) * 60 + m1
        if ap2 == "오후":
            end = (h2 % 12 + 12 if h2 != 12 else 12) * 60 + m2
        elif ap2 == "오전":
            end = (h2 % 12) * 60 + m2
        else:
            cands = sorted({h2 * 60 + m2, (h2 % 12 + 12) * 60 + m2})
            end = next((c for c in cands if c > start), cands[-1])
        rec = {"open": hhmm(start), "close": hhmm(end)}
        lead = text[max(0, m.start() - 10):m.start()]
        vm = VARIANT_LEAD.search(lead)
        if vm:
            variants.append({**rec, "days": [c for c in vm.group(1) if c in DOW]})
        else:
            main.append(rec)
    if not main and variants:          # 전부 변형으로 잡혔다면 오탐이다
        main = [{k: v for k, v in x.items() if k != "days"} for x in variants]
        variants = []
    return main, variants


def classify(title: str) -> tuple[str, str | None]:
    """(type, transport). transport는 move일 때만."""
    head = title.strip()
    for emo, mode in MOVE_EMOJI.items():
        if head.startswith(emo):
            return "move", mode
    for emo, typ in TYPE_EMOJI.items():
        if head.startswith(emo):
            return typ, None
    for typ, keys in KEYWORD_TYPE:
        if any(k in head for k in keys):
            return typ, None
    return "sight", None


ARROW_RE = re.compile(r"(.{1,40}?)\s*[→▶>⇒~-]{1,2}>?\s*(.{1,40})$")


def split_arrow(text: str) -> tuple[str | None, str | None]:
    """'니가타 공항 → 니가타역' 에서 출발·도착을 뽑는다."""
    m = re.match(r"^\s*(.{1,40}?)\s*[→⇒▶]\s*(.{1,40}?)\s*$", text)
    return (m.group(1).strip(), m.group(2).strip()) if m else (None, None)


# ── 「길찾기」 ─────────────────────────────────────────
# 시각 칸에 시각 대신 「길찾기」라 적은 줄. 항목도 구간도 아니다 —
# 바로 아래 이동에 붙어 「길 찾기」 버튼이 된다.
#
# 구간마다 달지 않는 까닭은, 길을 찾을 때 환승을 나눠 잡을 일이 없기 때문이다.
# 「니가타역 → 오미야역 → 카루이자와역」은 일정에서는 두 구간이지만 길찾기로는
# 하나다 — 환승은 구글이 잡는다. 그래서 「어디서 어디까지」를 사람이 한 줄로
# 적고, 그 줄이 뒤따르는 이동에 붙는다.
DIR_CELL = re.compile(r"^\s*길\s*찾기\s*$")

# 끝을 가르는 표. 화살표를 먼저 본다 — 붙임표(-)는 이름 안에도 들어가므로
# (「다이와 로이넷 호텔 오미야-니시구치」) 마지막에 두고 한 번만 가른다.
DIR_SEPS = ("→", "⇒", "▶", "〜", "～", "~", "–", "—", "-")

# 이름 뒤 괄호 안의 구글 지도 링크. 이름은 사람이 읽을 것이고 자리는 링크가 짚는다.
# 이름으로 장소를 찾는 길은 걷어냈지만(48km 떨어진 슈퍼) 링크는 사람이
# 「이 자리다」라고 짚은 것이라 다르다 — places_lookup 이 인정하는 두 출처 중 하나다.
DIR_LINK = re.compile(r"^\s*(.*?)\s*\(\s*(https?://[^)\s]+)\s*\)\s*$")


def one_end(text: str) -> dict | None:
    """「이름(지도링크)」·「(지도링크)」·「이름」 을 길찾기의 한쪽 끝으로.

    링크만 적어도 된다 — 이름은 링크를 풀면 나온다(links.py). 두 번 적을 까닭이 없다.

    빈 괄호는 아직 안 채운 자리다. 「()-()」 를 이름으로 받으면 길찾기가
    「()」 라는 곳을 찾아 나서므로, 지우고 없는 셈 친다 — 그러면 제목에서
    뽑은 출발·도착으로 물러선다.
    """
    text = re.sub(r"\(\s*\)", "", (text or "")).strip()
    if not text:
        return None
    m = DIR_LINK.match(text)
    if m:
        return {"name": m.group(1) or None, "link": m.group(2)}
    return {"name": text}


def split_ends(title: str) -> dict:
    """「A-B」를 출발·도착으로 가른다.

    링크가 붙어 있으면 괄호가 닫힌 뒤의 표에서 가른다 — 링크 안에도 붙임표가
    들어갈 수 있어서다. 둘로 안 갈리면 하나뿐인 것을 도착으로 본다.
    """
    t = (title or "").strip()
    for sep in DIR_SEPS:
        # 괄호 밖에서만 가른다
        depth, cut = 0, -1
        for i, ch in enumerate(t):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and t.startswith(sep, i):
                cut = i
                break
        if cut >= 0:
            # 한쪽이 비어 있어도 가른 것은 가른 것이다. 「()-()」 처럼 아직 안 채운
            # 자리를 두고 「못 갈랐다」며 통째로 이름 삼으면, 길찾기가 「-」 라는
            # 곳을 찾아 나선다.
            return {"from": one_end(t[:cut]), "to": one_end(t[cut + len(sep):])}
    return {"from": None, "to": one_end(t)}


MODE_WORD = {"car": "렌트카", "bus": "버스", "train": "기차", "plane": "항공", "walk": "도보"}


def split_vehicle(title: str, mode: str) -> str:
    """무엇을 타는지 뽑는다. 역 이름이 아니라 운송수단이 알고 싶은 정보다.

    'A에서 야마가타 신칸센 츠바사타고 B로 이동'  → 야마가타 신칸센 츠바사
    '대한항공 타고 니가타 공항으로 이동'          → 대한항공
    '리무진 버스'                                → 리무진 버스
    """
    s = title
    for emo in MOVE_EMOJI:
        s = s.replace(emo, "")
    s = s.strip()
    m = re.search(r"에서\s*(.+?)\s*타고", s)      # A에서 [수단] 타고
    if not m:
        m = re.match(r"^(.+?)\s*타고", s)          # [수단] 타고
    v = (m.group(1) if m else s).strip(" ·,-")
    v = re.sub(r"^(차|기차|버스|비행기)$", lambda x: MODE_WORD.get(mode, x.group(0)), v)
    v = re.sub(r"(으로|로)?\s*이동$", "", v).strip()
    return v or MODE_WORD.get(mode, mode)


def split_move(title: str) -> tuple[str | None, str | None]:
    """'A에서 X 타고 B로 이동' → (A, B). 없으면 None."""
    body = title
    for emo in MOVE_EMOJI:
        body = body.replace(emo, "")
    body = body.strip()
    dst = None
    m = re.search(r"(?:타고\s*)?([^\s].*?)(?:으로|로)\s*이동", body)
    if m:
        dst = re.sub(r"^.*?타고\s*", "", m.group(1)).strip() or None
    src = None
    m = re.match(r"(.+?)에서", body)
    if m:
        src = m.group(1).strip() or None
    return src, dst


NOT_A_NAME = re.compile(r"^(?:오전|오후)?\s*[\d일:~,.\s-]*$")


def valid_name(name: str) -> bool:
    """'오전 9', '22일 12' 같은 시각 조각은 장소 이름이 아니다.

    말끝으로 서술문을 가르던 때가 있었다 — 「하기·두기·보기·듯·같음…」
    열아홉 낱말로 「호텔에 짐 맡겨두기」 같은 줄을 걸렀다. 그런데 시트에는
    이미 표시가 있다: `-` 는 갈 곳, `*` 는 메모, `***` 는 할 일이다.
    할 일을 `-` 로 적어 둔 세 줄 때문에 낱말표를 들고 있었던 셈이라,
    시트를 고치고 표를 걷어냈다. 낱말로 추측하는 자리는 이제 없다.
    """
    n = name.strip()
    return len(n) >= 2 and not NOT_A_NAME.match(n)


# 손으로 적은 영업시간은 대괄호 안에 넣는다 — 「[11:00~19:00]」.
# 구글이 준 시간과 사람이 적은 시간을 눈으로도 코드로도 가를 수 있다.
BRACKET = re.compile(r"\[([^\]]*)\]")
DOW = "월화수목금토일"
# 시간 바로 앞에 '(금 ' / ', 토·일 ' 처럼 요일이 단독으로 붙은 경우만 변형으로 본다.
# '소금빵 / 오전 9:00' 의 '금', '토스트' 의 '토' 를 요일로 오인하면 안 된다.
VARIANT_LEAD = re.compile(r"(?:^|[（(/,、·])\s*((?:[월화수목금토일][·,・]?)+)\s*(?:요일)?\s*$")



def depar(s: str) -> str:
    """정보를 빼내고 남은 괄호 조각을 정리한다.

    '(재료 소진 시 종료 / 제3 수·목 휴무)' 에서 휴무만 빼면 괄호 짝이 어긋난다.
    빈 괄호를 지우고, 짝이 안 맞는 여는 괄호 뒤는 잘라낸다.
    """
    # 빈 괄호, 또는 요일만 남은 괄호 — '(금 오전 8:00~오후 5:00)' 에서
    # 시간을 빼면 '(금 )' 만 남는다. 원문은 raw 에 그대로 있다.
    s = re.sub(r"[（(][\s/·,~\-월화수목금토일]*[)）]", "", s)
    opens = s.count("(") + s.count("（")
    closes = s.count(")") + s.count("）")
    if opens > closes:                                  # 여는 괄호가 남았다
        i = max(s.rfind("("), s.rfind("（"))
        s = s[:i]
    elif closes > opens:                                # 닫는 괄호가 남았다
        i = min([x for x in (s.find(")"), s.find("）")) if x >= 0] or [-1])
        if i >= 0:
            s = s[:i] + s[i + 1:]
    return s


SLASH = re.compile(r"\s+/\s+")
# <https://…> — 꺾쇠는 사람이 「이건 주소다」라고 붙인 표시다.
# 그 표시가 있으니 글에서 주소처럼 생긴 것을 찾아 헤맬 까닭이 없다.
# [17:10~19:20] — 대괄호 안은 그 줄의 시각이다. 소괄호와 다르다:
# 소괄호 안의 시각은 설명이고(「온천 (10:00~12:00) 교대」),
# 대괄호는 사람이 「이건 이 줄의 시각」이라고 붙인 표시다.
BRACKET_TIME = re.compile(
    r"\[\s*((?:오전|오후)?\s*\d{1,2}:\d{2}\s*[~〜～ー–—-]\s*(?:오전|오후)?\s*\d{1,2}:\d{2})\s*\]")

LINK_RE = re.compile(r"<\s*(https?://[^>\s]+)\s*>")


def take_link(text: str) -> tuple[str, str | None]:
    """글에서 <주소> 를 떼어 (남은 글, 주소) 로 돌려준다."""
    m = LINK_RE.search(text or "")
    if not m:
        return text, None
    return LINK_RE.sub("", text).strip(), m.group(1)


def add_note(holder, text: str) -> None:
    """메모를 붙인다. 안에 든 <주소> 와 [시각] 은 떼어 그 줄의 값으로 싣는다.

    주소는 글이 아니라 갈 곳이고, 대괄호 안은 글이 아니라 시각이다.
    「제 2터미널 · KE2197 [17:10~19:20]」의 그 시각을 이동은 이미 시각
    열에 들고 있어, 메모에 남겨 두면 같은 값이 한 줄에 두 번 선다.
    아직 시각을 모르는 줄이면 그것으로 채운다.
    """
    text, link = take_link(text)
    if link and getattr(holder, "link", None) is None:
        holder.link = link
    m = BRACKET_TIME.search(text)
    if m:
        hrs, _ = parse_hours(m.group(1))
        t = getattr(holder, "time", None) or {}
        if hrs and hasattr(holder, "time") and not t.get("start"):
            holder.time = {"start": hrs[0]["open"], "end": hrs[0]["close"]}
        text = BRACKET_TIME.sub("", text).strip(" ·,")
    if text:
        holder.notes.append(dot_slash(text))


def dot_slash(text: str) -> str:
    """구분자로 쓴 「 / 」 를 중간점으로 바꾼다.

    붙어 있는 「/」 는 구분자가 아니라 뜻이다 — 「트래블카드/엔화」는 둘 중
    하나라는 말이고, 「1/5일차」는 분수이며, 「CANTON8/喜粤8号」는 상호다.
    사람이 조각을 가르려고 쓴 것에는 앞뒤에 공백이 있다. 그것만 바꾼다.
    """
    return SLASH.sub(" · ", text or "")


def tidy(text: str) -> str:
    """영업시간을 걷어낸 뒤 남는 '식료품점 /  / 주차 있음' 같은 빈칸을 정리한다.

    조각 끝의 마침표는 뗀다. 화면에서는 조각을 중간점으로 잇는데,
    「식료품점. · 주차 있음」처럼 마침표와 중간점이 잇달아 서면 무엇이
    구분자인지 흐려진다. 문장 하나를 끝맺는 마침표는 정보가 아니다 —
    말줄임(…, ...)은 뜻이 있으므로 남긴다.
    """
    # 줄바꿈도 조각을 가른다. 시트에서 표시 없이 줄을 바꾼 것은 앞줄에
    # 이어지는 말이고(fold), 여기서는 그것이 곧 다음 조각이다 —
    # 「ETC 카드 물어보기」와 「반납도 이르게 되는지」는 물어볼 것 둘이다.
    parts = [x.strip(" ·,") for x in re.split(r"\s+/\s+|\n", depar(text))]
    parts = [x[:-1] if x.endswith((".", "。")) and not x.endswith(("..", "…"))
             else x for x in parts]
    return " · ".join(x for x in parts if x and x not in "()（）")


def make_candidate(line: str) -> Candidate | None:
    """'이름: 설명 / 오전 9:00~오후 6:00' → Candidate. 이름을 못 뽑으면 None(=메모)."""
    text = line.strip()
    if not text:
        return None
    # 대괄호가 있으면 그 안이 사람이 적은 영업시간이다. 밖의 숫자는 안 본다 —
    # 「6,600엔(1인)」 이나 「8호차 20번」 을 시각으로 읽던 자리가 없어진다.
    inner = BRACKET.search(text)
    hours, variants = parse_hours(inner.group(1) if inner else text)
    # 콜론 뒤에 숫자가 오면 시각이다 ('6:00'). 이름/설명 구분자로 쓰면
    # 'ANA … 조식 뷔페 / 6' 처럼 시각 조각이 이름에 붙어버린다.
    #
    # 설명이 두 줄이면 이 정규식이 통째로 빗나갔다 — '.' 은 줄바꿈을 안 넘고
    # '$' 는 문자열 끝을 요구해서, 뒤에 한 줄이 더 있으면 매치가 실패했다.
    # 그러면 콜론째로 줄 전체가 이름이 되어, 「일본렌트가 니가타역 북쪽 출구
    # 지점: ETC 카드 물어보기…」 가 통째로 가게 이름이 됐다.
    # 이름은 첫 줄 안에서만 찾고, 설명은 줄을 넘도록(re.S) 둔다.
    m = re.match(r"^([^\n]{1,60}?)[:：](?!\d)\s*(.*)$", text, re.S)
    if m:
        name, rest = m.group(1).strip(), m.group(2).strip()
    elif hours:
        name, rest = BRACKET.sub("", HOURS_RE.sub("", text)).strip(" /·-"), text
    else:
        # 콜론도 시간도 없는 한 줄. '- 도요타 렌트카 아오모리 야스카타 점' 처럼
        # 설명 없이 상호만 적은 경우다. 줄 전체를 이름으로 본다.
        # 서술문은 valid_name 이 걸러낸다.
        name, rest = text, ""
    if not valid_name(name):
        return None
    rest, link = take_link(rest)
    picks: list[str] = []
    if (mp := PICK_RE.search(rest)):
        picks = [f"{int(t.split(':')[0]):02d}:{t.split(':')[1]}"
                 for t in re.split(r"\s*,\s*", mp.group(1))]
        rest = PICK_RE.sub("", rest)
    desc = BRACKET.sub("", HOURS_RE.sub("", rest))
    always = bool(re.search(r"24\s*시간", text))
    # 금액은 문장에서 긁지 않는다 — 아래 「금액은 표의 금액 칸에서만 온다」 참고.
    return Candidate(name=name, desc=tidy(desc), hours=hours, always=always,
                     link=link,
                     hoursPick=picks, hoursVariants=variants,
                     raw=text)


def resv_from_row(row: dict) -> Reservation:
    """'예약' 시트의 한 행을 그대로 옮긴다. 문장에서 캐내지 않는다.

    한때 예약 내용에서 「3인」을 정규식으로 뽑아 앞줄에 세웠다. 그러면 같은
    말이 두 번 선다 — 「3인 · 타베로그 …」 아래에 「무라카미 소 나오는 코스 3인」.
    인원은 사람이 예약 내용에 이미 적어 두었으므로 그것을 그대로 띄우면 된다.

    금액의 「(1인)」 도 같은 까닭으로 떼지 않는다. 인원을 앞에 세우던 때는
    겹쳐 보여 뗐지만, 안 세우면 그것은 「1인당」이라는 뜻을 지운 값이 된다.
    숫자는 셈에 쓰고 화면에는 적힌 그대로 띄운다(Item.costText 와 같은 규칙).
    """
    price = " ".join(str(row.get("price", "") or "").split())
    return Reservation(
        booker=row.get("site") or None,
        costJpy=parse_cost(price),
        costText=price if price and price != "-" else None,
        note=row.get("detail", "")[:200],
        name=row.get("name", ""),
        pay=row.get("pay", ""),
    )


def absorb_sub(target: "Item | Leg", lines: list[str], coord: str,
               date: str, checklist: list[dict]) -> None:
    """하위 줄을 표기 규칙대로 나눈다.

        ***  체크리스트 (뒤따르는 접두어 없는 줄은 같은 블록의 세부)
        *    메모
        -    후보 장소
    """
    star_block: list[str] = []
    group: Item | None = None          # '#' 로 연 묶음. 이후 '-' 들이 여기 붙는다
    for line in lines:
        s = line.strip()
        if not s:
            continue

        # {이미지} — 표식이 선 자리가 곧 그림 자리다.
        #
        # 갈래는 하나뿐이다. *** 블록이 열려 있으면 그 할 일의 그림이고,
        # 아니면 이 자리(항목·이동)의 그림이다. 적는 사람이 정하는 것은
        # 「어디에 적었는가」 하나뿐이라야 한다.
        #
        # 한때 이 판단이 두 곳에 있었다. 위쪽(sub 갈래)에서 표식을 모조리
        # 걷어 항목에 붙이고 나머지만 여기로 넘겼는데, 그래서
        # 「*** 지도는 체크리스트 참고 ⏎ {이미지}」는 그림이 할 일이 아니라
        # 항목에 붙었다 — 같은 표식인데 한 셀에 어떻게 적었느냐로 가는 길이
        # 갈렸다. 판단하는 곳이 둘이면 규칙도 둘이 된다.
        if IMAGE_MARK.match(s):
            if star_block:
                star_block.append(s)      # flush_star 가 그 할 일에 붙인다
            else:
                take_image(target, coord)
            continue

        if LABEL.match(s):
            flush_star(star_block, target, date, coord, checklist)
            star_block = []
            label = LABEL.sub("", s).strip()
            if isinstance(target, Item) and label:
                group = Item(id=f"{target.id}-g{len(target.subItems)+1}",
                             type=classify(label)[0], title=label, src=coord)
                target.subItems.append(group)
            continue

        if STAR3.match(s):
            flush_star(star_block, target, date, coord, checklist)
            star_block = [STAR3.sub("", s).strip()]
            continue


        if STAR1.match(s):
            # 메모 — 새 장소를 만들지는 않지만, 이 항목 자신의 정보는 읽는다.
            # '* 왕복 4,400엔 / 8:30~17:00' 은 그 로프웨이의 시간·가격이다.
            flush_star(star_block, target, date, coord, checklist)
            star_block = []
            body = STAR1.sub("", s).strip()
            holder = group if group is not None else target
            hrs, _ = parse_hours(body)
            if hrs and isinstance(holder, Item) and not holder.hours:
                holder.hours = hrs
            add_note(holder, body)
            continue

        if s.startswith(("-", "·", "‧")):     # 후보 장소
            flush_star(star_block, target, date, coord, checklist)
            star_block = []
            body = s.lstrip("-·‧ ").strip()
            hrs, _ = parse_hours(body)
            cand = make_candidate(body)
            holder = group if group is not None else target
            if cand and isinstance(holder, Item):
                holder.candidates.append(cand)
            elif hrs and isinstance(holder, Item) and not holder.hours:
                holder.hours = hrs
            else:
                add_note(holder, body)
            continue

        if star_block:                        # *** 블록의 이어지는 줄
            star_block.append(s)
            continue

        add_note(target, s)                # 그 밖은 메모
    flush_star(star_block, target, date, coord, checklist)


def flush_star(block: list[str], target, date: str, coord: str,
               checklist: list[dict]) -> None:
    """'***' 로 시작한 블록을 체크리스트 한 건으로 마감한다.

    신칸센 시각 목록처럼 여러 줄이 이어지는 경우가 있어 첫 줄을 제목으로,
    나머지를 세부로 묶는다. 다섯 줄이 다섯 건이 되면 목록이 못 쓰게 된다.
    """
    if not block:
        return

    # {이미지} 는 할 일 문구가 아니라 그림 자리다.
    #
    # **줄 표식이다.** 블록에 홀로 섰든 할 일 아래 둘째 줄로 붙었든 같게
    # 다룬다. 엑셀은 한 칸에 글자와 그림을 같이 담지 못하므로, 그림이 들어갈
    # 자리를 글로 미리 잡아 두는 것이 이 표식이고 진짜 그림은 그 아래 행에
    # 떠 있다(image_below).
    #
    # 한때 「블록 전체가 표식일 때」만 걷어냈다. 그래서
    # 「*** 리무진 버스 타러 가는 길 ⏎ {이미지}」처럼 한 칸에 같이 적으면
    # 표식이 글자로 남아 체크리스트에 그대로 찍혔다 — 시트를 적는 쪽에서는
    # 그림 위에 한 줄 적었을 뿐인데 어떤 데선 되고 어떤 데선 안 되는 셈이라,
    # 갈래를 나누지 않고 줄만 본다.
    # 여기까지 온 표식은 *** 블록 안에 있던 것이라 그 할 일의 그림이다.
    # 항목에는 붙이지 않는다 — 「지도는 체크리스트 참고」라고 적어 두고
    # 바로 옆에 같은 그림을 또 띄우면 그 문구가 스스로를 부정한다.
    # 자리에 두고 싶으면 *** 밖에 표식을 적으면 된다(absorb_sub 를 볼 것).
    marks = [x for x in block if IMAGE_MARK.match(x.strip())]
    block = [x for x in block if not IMAGE_MARK.match(x.strip())]
    shot = image_below(coord) if marks else None

    if not block:
        # 표식만 있던 블록 — 글자 없이 그림만 지닌 건으로 남긴다.
        # 별을 붙여 적은 것은 「체크리스트에 보여도 좋다」는 뜻이고,
        # 자리를 옮기거나 앞 건에 얹지 않는다. 놓은 자리가 곧 그 자리다.
        #
        # text 를 빈 줄로 남긴다. 이 목록을 읽는 다른 자리(export_web 의 날짜별
        # tasks)가 text 를 당연히 있는 것으로 다루기 때문이다.
        if shot:
            checklist.append({"due": date, "text": "", "image": shot, "src": coord})
        return

    # 할 일도 메모와 같은 규칙을 탄다 — 구분자로 쓴 「 / 」 는 중간점이다.
    #
    # <주소> 도 마찬가지다. 메모에 적힌 것은 add_note 가 떼어 항목의 link 로
    # 싣는데, 할 일에 적힌 것만 글자로 남아 체크리스트에 꺾쇠째 찍혔다 —
    # 「JR 패스 교환」 아래에 예약 사이트 주소가 통째로 한 줄이었다.
    # 주소는 글이 아니라 갈 곳이므로 여기서도 자리를 갈라 준다.
    body, link = take_link(block[0])
    entry = {"due": date, "text": dot_slash(body), "src": coord}
    if link:
        entry["link"] = link
    if shot:
        entry["image"] = shot
    if len(block) > 1:
        entry["detail"] = [dot_slash(x) for x in block[1:]]
    checklist.append(entry)
    # 항목에도 남긴다 — 그날의 체크리스트만 보면 어느 자리의 일인지 모른다.
    # notes 에 섞지 않는다. 시트는 `*`(메모)와 `***`(할 일)를 갈라 적는데
    # 여기서 합치면 「조식 신청하고 싶으면 할까?」 같은 혼잣말이
    # 체크리스트 문구가 된다. 화면이 둘을 다르게 그리므로 자리도 달라야 한다.
    # 붙을 항목이 없으면(그날 첫 항목보다 앞에 선 것) 체크리스트에만 남는다
    if target is not None:
        target.tasks.append(dot_slash(block[0]))
        target.hasTask = True


# ─────────────────────────────────────────────────────────────
# 파싱
# ─────────────────────────────────────────────────────────────
def collect_images(wb) -> dict[str, list[list]]:
    """엑셀에 붙어 있는 그림을 꺼내 시트마다 행 순으로 늘어놓는다.

    9.18 리무진 버스 아래에 니가타역 승강장 안내도가 붙어 있다.
    값만 읽으면 이런 것이 통째로 사라진다.

    **셀 좌표로 색인하지 않는다.**

    엑셀의 그림은 셀에 담기는 것이 아니라 그 위에 떠 있다. 어느 칸에
    걸쳤는지는 앵커가 알려 주지만 그것은 그림의 왼쪽 위 모서리일 뿐이라,
    한 줄만 밀려도 다른 셀이 된다. 실제로 안내도가 D20 에 앵커되어 C19 의
    리무진 버스를 찾지 못했고, 그림 자리가 통째로 비어 있었다.

    그래서 좌표로 맞추지 않고 **행 순서**만 남긴다. 어느 자리에 넣을지는
    사람이 시트에 {이미지} 라고 적어 알려 준다(image_below 를 볼 것) —
    그림은 그 표식 아래에서 찾는다.

    @return {시트이름: [[행, 파일명], ...]}  행 오름차순
    """
    out: dict[str, list[list]] = {}
    media = ROOT / "data" / "media"
    fresh: set[str] = set()
    for ws in wb.worksheets:
        rows: list[list] = []
        for i, im in enumerate(getattr(ws, "_images", []), 1):
            a = im.anchor._from
            data = im._data() if callable(getattr(im, "_data", None)) else None
            if not data:
                continue
            # 이름에 내용 해시를 넣는다.
            #
            # 순번만 쓰던 때는 시트에서 그림을 갈아 끼워도 파일 이름이 그대로라,
            # 새 그림이 옛 이름을 뒤집어썼다. 파일은 바뀌었는데 주소가 같으니
            # 브라우저와 CDN 이 캐시에 든 옛 그림을 계속 내주었다 —
            # 고쳤는데 안 고쳐진 것처럼 보이는, 가장 알아채기 어려운 꼴이다.
            #
            # 내용이 바뀌면 이름이 바뀌므로 캐시가 옛것을 줄 수 없고,
            # 이름을 잃은 옛 파일은 아래의 정리가 지운다.
            stem = ws.title.replace(".", "_").replace(" ", "")
            name = f"{stem}_{i}-{hashlib.sha1(data).hexdigest()[:8]}.png"
            media.mkdir(parents=True, exist_ok=True)
            (media / name).write_bytes(data)
            fresh.add(name)
            rows.append([a.row + 1, name])
        if rows:
            out[ws.title] = sorted(rows)

    # 시트에서 없어진 그림은 여기서도 지운다.
    #
    # 쌓이기만 하던 자리다. 시트 이름이 9.18 에서 9.18-9.22 로 바뀌자
    # 9_18_1.png 가 아무도 가리키지 않는 채로 남아, 지금 시트에 있지도 않은
    # 그림이 웹에 실려 나갔다. 정본이 시트인 이상 여기 남은 것도 시트를
    # 따라야 한다.
    if media.exists():
        for f in media.glob("*.png"):
            if f.name not in fresh:
                f.unlink()
                print(f"     - 시트에 없어진 그림 {f.name} 지움")
    return out


# 시트에 적는 표식. 이 줄 아래의 그림이 그 자리에 들어간다.
IMAGE_MARK = re.compile(r"^\{\s*이미지\s*\}$")


def take_image(target, coord: str) -> None:
    """표식이 가리킨 그림을 target 에 붙인다. 자리가 없으면 조용히 넘어간다.

    target 이 None 인 때는 그날 첫 항목보다 앞에 표식이 선 것이다 —
    붙일 데가 없으므로 그림도 꺼내지 않는다(다음 표식이 쓰게 남겨 둔다).
    """
    if target is None:
        return
    got = image_below(coord)
    if got:
        target.image = got


def image_below(coord: str) -> str | None:
    """표식이 선 자리에서 아래로 가장 가까운 그림 하나.

    한 번 꺼내면 목록에서 지운다. 표식이 여럿이면 위에서부터 차례로
    짝지어지므로, 그림 순서와 표식 순서만 맞으면 된다.

    행이 같거나 아래인 것만 본다 — 표식은 그림 위에 적는 것이라서다.
    """
    sheet, _, cell = coord.partition("!")
    m = re.search(r"(\d+)$", cell)
    if not m:
        return None
    row = int(m.group(1))
    rows = IMAGES.get(sheet) or []
    for i, (r, name) in enumerate(rows):
        if r >= row:
            rows.pop(i)
            return name
    return None


SKIP_SHEETS = {"일정", "예약", "호텔", "준비", "지정석"}   # 날짜 시트가 아닌 것


RANGE_RE = re.compile(
    r"(\d{1,2})일\s*(\d{1,2}):(\d{2})\s*[~〜～-]\s*(\d{1,2})일\s*(\d{1,2}):(\d{2})")


def read_seats(wb) -> list[dict]:
    """'지정석' 시트 → 열차 예약 목록.

        예약일 · 시간 · 예약(열차명) · 출발역 · 도착역 · 좌석

    좌석까지 잡아 둔 구간은 자유석과 다르다 — 그 차를 놓치면 표가 죽는다.
    날짜와 출발 시각으로 이동 구간에 붙인다.
    """
    if "지정석" not in wb.sheetnames:
        return []
    ws = wb["지정석"]
    head, out = None, []
    for row in ws.iter_rows():
        vals = [str(c.value or "").strip() for c in row[:6]]
        if head is None:
            if vals[0] == "예약일":
                head = True
            continue
        if not vals[0] or not vals[1]:
            continue
        date = vals[0][:10]
        start = re.split(r"[~〜～-]", vals[1])[0].strip()
        if len(start) == 4:
            start = "0" + start
        out.append({"date": date, "start": start[:5], "span": vals[1],
                    "train": vals[2], "from": vals[3], "to": vals[4], "seat": vals[5]})
    return out


def read_prep(wb) -> list[dict]:
    """'준비' 시트 → 구역별 목록.

        A열  구역 이름 (해야할 일 · 준비물 · 메모)
        B~D열  나란한 목록. 한 줄에 셋까지 적는다

    한때 B열을 항목, C열을 그 설명으로 읽었다. 시트가 두 열이던 때의 규칙인데,
    지금은 세 열이 나란한 목록이라 「여권」의 설명이 「충전기」가 되어 있었다.
    B열이 비고 C열만 있는 줄(「공항 라운지 이용권」)은 통째로 사라지기도 했다.

    「메모」 구역만 다르다 — 거기는 B열이 말이고 C열이 그 원어다
    (「주차장 검색 시 · 駐車場」). 구역 이름으로 가른다.

    날짜가 없는 목록이라 일정과 섞이지 않는다. 챙길 것은 사람마다 다르므로
    체크 상태는 시트로 되돌리지 않는다.
    """
    if "준비" not in wb.sheetnames:
        return []
    ws = wb["준비"]
    groups: list[dict] = []
    for row in ws.iter_rows(min_col=1, max_col=4):
        head = str(row[0].value or "").strip()
        cells = [str(c.value or "").strip() for c in row[1:4]]
        if head:
            groups.append({"name": head, "items": []})
            continue
        if not groups or not any(cells):
            continue
        if groups[-1]["name"] == "메모":
            # 말과 그 원어 — 한 줄이 한 항목이다
            if cells[0]:
                groups[-1]["items"].append(
                    {"text": cells[0], **({"note": cells[1]} if cells[1] else {})})
        else:
            for c in cells:
                if c:
                    groups[-1]["items"].append({"text": c})
    return [g for g in groups if g["items"]]


def fold(cell: str) -> list[str]:
    """셀을 줄로 나누되, 표시 없는 줄은 앞줄에 이어 붙인다.

    시트의 표기가 곧 규칙이다 — `-` 는 갈 곳, `*` 는 메모, `#` 은 묶음이고
    저마다 매 줄에 붙는다. 표시가 없으면 새로 시작하는 것이 아니라
    앞줄이 길어 넘어온 것이다(택배 주소, 두 문장짜리 메모).

    `{이미지}` 는 그 예외다. 표시로 시작하지 않지만 앞줄의 연장이 아니라
    「여기에 그림이 온다」는 제 몫의 줄이다. 엑셀은 한 칸에 글자와 그림을
    같이 담지 못해서, 그림이 들어갈 자리를 글로 미리 잡아 두는 표식이다.

    이어 붙이던 때는 「*** 리무진 버스 타러 가는 길 ⏎ {이미지}」가 한 줄로
    뭉쳐, 뒤에서 표식을 걷어내려 해도 걷을 줄이 없었다 — 체크리스트에
    「{이미지}」라는 글자가 그대로 찍혔다. 무엇이 새 줄인가를 정하는 곳이
    여기이므로 표식도 여기에 등록한다.

    첫 줄은 무엇이든 그대로 둔다 — 이어 붙일 앞줄이 없다.
    """
    out: list[str] = []
    blank = False
    for raw in cell.split("\n"):
        s = raw.strip()
        if not s:
            # 덩어리 안의 빈 줄은 적은 사람이 일부러 띄운 자리다 —
            # 택배 주소 앞의 한 줄이 그렇다. 다음 줄이 이어질 때 되살린다.
            blank = bool(out)
            continue
        if out and s[0] not in "-*#·‧" and not IMAGE_MARK.match(s):
            out[-1] += ("\n\n" if blank else "\n") + s
        else:
            out.append(s)
        blank = False
    return out


def read_hotels(wb) -> dict[str, dict]:
    """'호텔' 시트 → 날짜별 숙박 정보.

    예약을 '예약' 시트 표에서만 읽는 것과 같은 이유다. 일정 시트 메모의
    '* 현지 결제 / 39,600엔' 을 긁으면 적는 것을 빠뜨린 날은 조용히 사라지고,
    '전세온천 50분 4,000엔' 같은 딴 금액을 숙박비로 오해한다.

    이 시트에는 머리글이 없어 열 자리로 읽는다. 대신 날짜(B 열)가 선 줄만
    표의 몸통으로 보아, 위쪽 제목 줄이 늘거나 줄어도 견딘다.

        A 월('9월')·특기('일본 휴일')   B 일   D 요일   E 지역
        F 호텔   G 조건   H 원화   I 결제   J 예약처   K 엔화

    연박은 첫날 줄에만 조건·금액이 적히고 이어지는 날은 이름만 있다.
    그 금액은 '그날 낼 돈' 이 아니라 '그 숙박의 값' 이므로 복사하지 않는다.
    """
    if "호텔" not in wb.sheetnames:
        return {}
    ws = wb["호텔"]
    out: dict[str, dict] = {}
    month = None
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        def val(i: int):
            c = row[i] if i < len(row) else None
            v = c.value if c is not None else None
            return None if v is None or str(v).strip() == "" else v

        a = val(0)
        if a is not None:
            m = re.match(r"(\d{1,2})\s*월", str(a).strip())
            if m:
                month = int(m.group(1))
        b = val(1)
        if b is None or month is None:
            continue
        try:
            dd = int(float(str(b).strip()))
        except ValueError:
            continue

        name = val(5)
        if name is None or str(name).strip() == "귀국":
            continue

        date = f"{YEAR}-{month:02d}-{dd:02d}"
        yen = val(10)
        cost = parse_cost(str(yen)) if yen is not None else None
        krw = val(7)
        info = {
            "name": str(name).strip(),
            "region": str(val(4)).strip() if val(4) is not None else None,
            "terms": dot_slash(str(val(6)).strip()) if val(6) is not None else None,
            "pay": str(val(8)).strip() if val(8) is not None else None,
            "booker": str(val(9)).strip() if val(9) is not None else None,
            "costJpy": cost,
            "costKrw": int(float(krw)) if krw is not None else None,
            "src": f"호텔!F{row[5].row}",
        }
        out[date] = {k: v for k, v in info.items() if v is not None}
    return out


def read_reservations(wb) -> tuple[list[dict], list[dict]]:
    """'예약' 시트 → (예약 목록, 렌터카 목록).

    메모에서 '3인 / 타베로그 / 9,900엔' 을 정규식으로 긁던 것을 대체한다.
    시트에 이미 표로 정리돼 있으므로 추측할 이유가 없다.
    """
    if "예약" not in wb.sheetnames:
        return [], []
    ws = wb["예약"]
    head_row = None
    cols: dict[str, int] = {}
    for row in ws.iter_rows(min_row=1, max_row=10):
        for c in row:
            if str(c.value or "").strip() == "예약일":
                head_row = c.row
                break
        if head_row:
            # 머리글 행의 열 이름 → 열 인덱스(1-기준)
            for c in ws[head_row]:
                name = str(c.value or "").strip()
                if name:
                    cols[name] = c.column
            break
    if head_row is None:
        return [], []

    def cell(row, name):
        i = cols.get(name)
        if i is None:
            return ""
        j = i - row[0].column          # 행이 시작하는 열을 뺀다
        if j < 0 or j >= len(row):
            return ""
        v = row[j].value
        if v is None:
            return ""
        if hasattr(v, "strftime"):
            return (v.strftime("%Y-%m-%d") if hasattr(v, "year")
                    else v.strftime("%H:%M"))
        return str(v).strip()

    resv: list[dict] = []
    cars: list[dict] = []
    for row in ws.iter_rows(min_row=head_row + 1):
        name = cell(row, "예약 ") or cell(row, "예약")
        if not name:
            continue
        date = (cell(row, "예약일") or "")[:10]
        time = cell(row, "시간")
        rec = {
            "date": date, "time": time, "name": name,
            "site": cell(row, "사이트"),
            # 줄바꿈도 조각을 가른다 — 사람이 줄을 바꾼 것은 다음 조각이다
            "detail": " · ".join(dot_slash(x).strip() for x in
                                 (cell(row, "예약 내용") or "").split("\n") if x.strip()),
            "pay": cell(row, "결제방법"),
            "price": cell(row, "가격"),
        }
        m = RANGE_RE.search(time)
        if m and "렌터카" in name:
            d1, h1, m1, d2, h2, m2 = m.groups()
            mm = date[:8] if date else "2026-09-"
            # 지점이 다르면 시트에 「수령 지점 / 반납 지점」으로 나눠 적는다.
            # 하나만 적혀 있으면 받은 자리에 그대로 돌려주는 것이다.
            spot = [x.strip() for x in name.split("/") if x.strip()]
            d_from = f"{mm[:8]}{int(d1):02d}"
            d_to = f"{mm[:8]}{int(d2):02d}"
            t_from = f"{int(h1):02d}:{m1}"
            t_to = f"{int(h2):02d}:{m2}"

            # 기간은 깃발이 쓴다 — 그 며칠 동안 차가 있다는 뜻이다.
            cars.append({"vendor": spot[0],
                         "from": f"{d_from}T{t_from}",
                         "to": f"{d_to}T{t_to}"})

            # 그리고 한 줄을 둘로 편다 — 받는 자리와 돌려주는 자리.
            #
            # 시간 칸이 「19일 15:00 ~ 22일 11:00」 이라 (날짜, 시각) 으로
            # 붙는 보통 길에 걸리지 않았고, 그래서 화면을 만들 때 렌트만
            # 따로 이어 붙이는 특례가 있었다. 여기서 펴 두면 그 특례가
            # 필요 없다 — 렌트도 다른 예약과 똑같이 시각으로 붙는다.
            #
            # 지점은 적지 않는다 — 일정의 그 줄이 이미 그 이름을 말한다.
            # 상자에 되풀이하면 「3인」이 두 줄에 겹쳐 서던 것과 같아진다.
            #
            # 돈도 받는 자리에만 적는다. 한 번 내는 것이라 두 번 뜨면 두
            # 건으로 읽힌다. 그래서 돌려주는 자리에는 적을 것이 남지 않고,
            # 화면은 적을 것이 없는 예약의 상자를 세우지 않는다.
            resv.append({**rec, "date": d_from, "time": t_from,
                         "name": spot[0]})
            resv.append({**rec, "date": d_to, "time": t_to,
                         "name": spot[-1], "detail": "",
                         "site": "", "price": "", "pay": ""})
        else:
            resv.append(rec)
    return resv, cars


def detect_base(ws) -> int | None:
    """날짜 머리글('9.18 [금]')이 있는 열을 찾는다. 그 열이 시각 열이다.

    로컬 파일은 A 열에서, 구글 시트는 B 열에서 시작한다.
    열 번호를 코드에 박아두면 시트를 조금만 손봐도 통째로 안 읽힌다.
    """
    for row in ws.iter_rows(min_row=1, max_row=60):
        for c in row[:4]:
            if c.value is not None and DAY_RE.match(str(c.value).strip()):
                return c.column - 1        # 0-기준
    return None


def parse(sheets: list[str] | None) -> dict:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    global IMAGES
    IMAGES = collect_images(wb)
    SHEET_RESV[:], SHEET_CARS[:] = read_reservations(wb)
    SHEET_HOTELS.clear()
    SHEET_HOTELS.update(read_hotels(wb))
    prep = read_prep(wb)
    SHEET_SEATS[:] = read_seats(wb)
    days: list[dict] = []
    checklist: list[dict] = []

    for ws in wb.worksheets:
        if sheets and ws.title not in sheets:
            continue
        if ws.title in SKIP_SHEETS:
            continue
        base = detect_base(ws)
        if base is None:
            continue                        # 날짜가 없는 시트는 건너뛴다

        day = None
        raw_rows: list[tuple] = []   # (row_no, kind, payload)

        for row in ws.iter_rows():
            def col(i):
                j = base + i
                return row[j] if len(row) > j else None

            a, b, c, d = col(0), col(1), col(2), col(3)
            a_v = a.value if a is not None else None
            b_v = b.value if b is not None else None
            a_s = str(a_v).strip() if a_v is not None else ""
            b_s = str(b_v).strip() if b_v is not None else ""

            m = DAY_RE.match(a_s)
            if m:
                if day:
                    days.append(finish_day(day, raw_rows, checklist))
                mm, dd, dow = m.groups()
                day = {
                    "date": f"{YEAR}-{int(mm):02d}-{int(dd):02d}",
                    "dow": dow,
                    "region": b_s or None,
                    "sheet": ws.title,
                    "stay": None,
                }
                raw_rows = []
                continue
            if day is None:
                continue

            if SECTION_RE.match(a_s):
                if a_s in ("오전", "오후") and b_s and (
                        STAR3.match(b_s)):
                    # '오전' 행에 적힌 *** 는 붙을 항목이 없다. 하루 전체의 할 일이다.
                    txt = STAR3.sub("", b_s.strip()).strip()
                    checklist.append({"due": day["date"], "text": txt,
                                      "src": f"{ws.title}!{b.column_letter}{b.row}"})
                    continue
                if a_s in ("오전", "오후"):
                    # 12시제 시각('1:00')을 어느 쪽으로 읽을지 정하는 기준이다
                    raw_rows.append((a.row if a is not None else b.row,
                                     "section", a_s))
                if a_s == "숙박":
                    name = b_s or None
                    day["stay"] = {
                        "name": name,
                        "room": str(c.value).strip() if c is not None and c.value else None,
                        "nights": str(d.value).strip() if d is not None and d.value else None,
                        "placeId": None,
                    }
                    # 이름·객실은 일정 시트가 부르는 대로 두고(장소 짝짓기가 여기 걸려 있다),
                    # 얼마를 어떻게 냈는지는 '호텔' 시트 표에서 가져온다.
                    book = SHEET_HOTELS.get(day["date"])
                    if book:
                        for k in ("pay", "booker", "costJpy", "costKrw", "terms"):
                            if book.get(k) is not None:
                                day["stay"][k] = book[k]
                        day["stay"]["bookedAs"] = book["name"]
                elif b_s:
                    raw_rows.append((a.row if a is not None else b.row, "note", b_s))
                continue

            if not b_s:
                continue

            lines = fold(b_s)
            head = lines[0]
            tail = lines[1:]
            coord = f"{ws.title}!{b.column_letter}{b.row}"

            if LABEL.match(head):
                # '#라벨' 로 시작하는 셀은 묶음이다. 라벨을 제목으로 쓰고
                # 뒤따르는 '-' 들을 그 묶음의 후보로 넣는다.
                raw_rows.append((b.row, "group",
                                 (LABEL.sub("", head).strip(), tail, coord)))
            elif head.startswith(("-", "*", "·", "‧")):
                raw_rows.append((b.row, "sub", (lines, coord)))
            else:
                raw_rows.append((b.row, "item",
                                 (head, tail, a_v, c, d, coord, cell_is_yellow(a))))

        if day:
            days.append(finish_day(day, raw_rows, checklist))

    return {
        "title": "2026 9월 일본 여행",
        "passes": [{
            "id": "jr_east_wide",
            "name": "JR 동일본 와이드 패스",
            "days": 5,
            "from": f"{YEAR}-09-22",
            "to": f"{YEAR}-09-26",
            "priceJpy": 35000,
        }],
        "cars": SHEET_CARS or [
            {"vendor": "일본렌트카", "from": f"{YEAR}-09-19T15:00", "to": f"{YEAR}-09-22T11:00"},
            {"vendor": "도요타렌터카", "from": f"{YEAR}-09-26T19:00", "to": f"{YEAR}-09-29T18:00"},
        ],
        "reservations": SHEET_RESV,
        "prep": prep,
        "checklist": checklist,
        "days": days,
    }


def finish_day(day: dict, rows: list[tuple], checklist: list[dict]) -> dict:
    """한 날짜분 행들을 항목/구간으로 조립한다."""
    date = day["date"]
    seq = 0
    entries: list[dict] = []   # {"kind":"item"|"move", "obj":..., "hm":(h,m)|None, "end":...}

    target: Item | Leg | None = None      # 하위 라인이 붙을 대상
    last_item: Item | None = None         # subItem을 매달 상위 항목
    pending_dir: dict | None = None       # 「길찾기」 줄 — 뒤따르는 이동에 붙는다

    section = None                     # 직전에 지나온 '오전' / '오후'
    for _, kind, payload in rows:
        if kind == "section":
            section = payload
            continue
        if kind == "note":
            if target is not None:
                add_note(target, payload)
            continue

        if kind == "group":
            label, tail, coord = payload
            # 바로 위가 이동이면 '가는 길에 들를 곳' 이다. 그 위 항목이 아니라 이동에 붙는다
            holder = target if isinstance(target, Leg) else last_item
            if holder is None or not label:
                continue
            g = Item(id=f"{holder.id}-g{len(holder.subItems)+1}",
                     type=classify(label)[0], title=label, src=coord)
            holder.subItems.append(g)
            target = g
            for line in tail:
                absorb_sub(g, [line], coord, date, checklist)
            continue

        if kind == "sub":
            lines, coord = payload
            # {이미지} 는 장소가 아니라 「여기에 그림이 온다」는 표식이다.
            #
            # 그냥 두면 장소 이름으로 읽힌다 — 실제로 저녁 항목의 detail 이
            # '{이미지}' 가 되고 placeId 까지 p_이미지 로 생겼다. 있지도 않은
            # 곳이 일정에 앉는 셈이라, 장소로 넘기기 전에 여기서 걷어낸다.
            #
            # 붙는 자리는 target 이다. 줄을 위에서 아래로 읽으므로 표식을
            # 만나는 순간의 target 은 바로 위에 적힌 것 — 리무진 버스 아래에
            # 표식을 두면 그 이동에 붙는다.
            if target is not None:
                # 표식을 여기서 가려내지 않는다 — absorb_sub 가 줄을 갈래별로
                # 나누는 곳이고, 표식이 어디에 속하는지도 거기서만 정한다.
                absorb_sub(target, lines, coord, date, checklist)
                continue
            elif STAR3.match(lines[0]):
                # 그날 첫 항목보다 앞에 선 *** — 숙박 줄과 '오전' 줄 사이에
                # 적히곤 한다. 붙을 자리가 없을 뿐 「하루 전체의 할 일」이라는
                # 뜻은 '오전' 행에 적은 것과 같다.
                #
                # 버리지 않는다. 전에는 target 이 없다는 이유로 조용히 사라져,
                # 시트에 적은 셋(도시락·수건·가방)이 화면 어디에도 없었다 —
                # 적은 사람은 적었다고 믿고 있으므로 이런 유실이 가장 나쁘다.
                flush_star([STAR3.sub("", lines[0]).strip(),
                            *(x.strip() for x in lines[1:])],
                           None, date, coord, checklist)
            continue

        head, tail, a_v, c_cell, d_cell, coord, fixed = payload

        # {이미지} 는 항목이 아니라 「이 자리에 그림이 온다」는 표식이다.
        #
        # 그냥 두면 제목이 '{이미지}' 인 항목이 서고, 후보가 하나뿐이라
        # 그것이 앞 항목의 detail 로 흡수된다 — 저녁 항목의 장소가
        # '{이미지}' 가 되고 placeId 까지 p_이미지 로 생겼었다.
        #
        # 붙는 자리는 target, 곧 바로 위에 적힌 것이다. 줄을 위에서 아래로
        # 읽으므로 리무진 버스 아래에 표식을 두면 그 이동에 붙는다.
        if IMAGE_MARK.match(head.strip()):
            take_image(target, coord)
            continue

        typ, mode = classify(head)
        cost, covered, dur = read_cd(c_cell, d_cell)
        hm, end_hm = raw_hm(a_v), raw_end_hm(a_v)
        has_emoji = head.strip().startswith(tuple(MOVE_EMOJI) + tuple(TYPE_EMOJI))
        seq += 1

        # ── 「길찾기」 줄 ──────────────────────────────────
        # 시각 칸에 「길찾기」라 적혀 있으면 이 줄은 일정이 아니라 표시다.
        # 붙여 두고 넘어간다 — 뒤따르는 첫 이동이 받는다.
        #
        # seq 는 그대로 먹인다. 건너뛰면 뒤 항목의 번호가 하나씩 당겨지는데,
        # master_fixes.json 이 「2026-09-23-l11」처럼 그 번호로 짚고 있어
        # 규칙이 엉뚱한 줄에 걸린다. 사라지면 눈치채지만 옮겨 가면 아무도
        # 안 물어본다.
        if DIR_CELL.match(str(a_v or "")):
            pending_dir = split_ends(head)
            continue

        # 이동 이모지가 붙었다고 다 구간은 아니다 ('🚗주차는 근방에').
        # 제목의 단어가 아니라 실체로 가른다 — 소요시간·비용이 있거나,
        # 제목/하위 줄에 'A → B' 가 적혀 있으면 구간이다.
        if typ == "move":
            has_route = bool(ARROW_RE.search(head)) or any(
                ARROW_RE.search(x) for x in tail)
            looks_move = ("이동" in head or "귀국" in head
                          or dur is not None or cost is not None or has_route)
            if not looks_move:
                typ, mode = "note", None

        if typ == "move":
            obj = Leg(id=f"{date}-l{seq:02d}", mode=mode or "car", title=head,
                      durationMin=dur, costText=cost, covered=covered, src=coord,
                      fixedTime=fixed)
            entries.append({"kind": "move", "obj": obj, "hm": hm, "end": end_hm})
            target = obj
            if pending_dir is not None:
                # 'on' 을 두는 까닭 — 양 끝이 다 비면 남는 값이 없어 strip_none 이
                # 빈 dict 로 만들고, 그러면 「적어 뒀다」는 사실 자체가 사라진다.
                obj.wayfind = {"on": True, **pending_dir}
                pending_dir = None

        elif hm is None and not has_emoji and last_item is not None:
            # 시각도 이모지도 없는 줄 = 직전 항목의 하위 (식당 후보, 상가 등)
            sub_type = classify(head)[0]
            if sub_type == "sight" and last_item.type in ("food", "cafe", "shop"):
                sub_type = last_item.type      # '점심' 아래의 식당은 식당이다
            obj = Item(id=f"{last_item.id}-s{len(last_item.subItems)+1}",
                       type=sub_type, title=head,
                       costText=cost, covered=covered, durationMin=dur, src=coord)
            last_item.subItems.append(obj)
            target = obj

        else:
            obj = Item(id=f"{date}-i{seq:02d}", type=typ if typ != "note" else "sight",
                       title=head, costText=cost, covered=covered,
                       durationMin=dur, src=coord, fixedTime=fixed,
                       hideTime=unwrap_time(a_v)[1])
            entries.append({"kind": "item", "obj": obj, "hm": hm, "end": end_hm,
                            "sec": section})
            target = last_item = obj

        for line in tail:
            absorb_sub(target, [line], coord, date, checklist)

    # 「길찾기」를 이동 아래에 적은 경우. 앞에 적는 것이 제자리지만, 뒤에 적었다고
    # 적은 것이 사라지면 안 된다 — 그날 마지막 이동이 받는다.
    if pending_dir is not None:
        last_move = next((e["obj"] for e in reversed(entries)
                          if e["kind"] == "move"), None)
        if last_move is not None:
            last_move.wayfind = {"on": True, **pending_dir}

    # ── 시각 해석: 단조 증가 제약 ──────────────────────────
    prev = -1
    for e in entries:
        if e["hm"] is None:
            continue
        # '오후' 아래의 1:00 은 13:00 이다. 다만 이 경계는 앞선 항목이 하나도
        # 없을 때만 세운다. 오전 항목이 이미 있으면 그 시각이 더 나은 기준이고,
        # 무턱대고 12:00 으로 밀면 24시간제로 적은 '11:00' 이 23:00 이 된다.
        if e.get("sec") == "오후" and prev < 0:
            prev = 12 * 60
        h, mi = e["hm"]
        cands = sorted({h * 60 + mi, (h % 12 + 12) * 60 + mi})
        pick = next((x for x in cands if x >= prev), cands[-1])
        suspect = pick < prev
        if suspect:                       # 역행이 남으면 직전 시각으로 밀고 표시
            pick = prev
        e["mins"], e["suspect"] = pick, suspect
        prev = pick

        end = None
        if e["end"] is not None:
            eh, em = e["end"]
            ecands = sorted({eh * 60 + em, (eh % 12 + 12) * 60 + em})
            end = next((x for x in ecands if x >= pick), ecands[-1])
        e["endmins"] = end

    for e in entries:
        mins = e.get("mins")
        if mins is None:
            continue
        e["obj"].time = {"start": hhmm(mins), "end": hhmm(e.get("endmins"))}
        if isinstance(e["obj"], Item):
            e["obj"].suspectTime = e.get("suspect", False)

    # ── 금액은 표의 금액 칸에서만 온다 ──────────────────────
    #
    # 전에는 메모와 후보 설명에서 '1,760엔' 같은 숫자를 긁어 항목 값으로 삼았다.
    # 문장 속 숫자는 그 항목의 값일 수도, 대안일 수도, 딸린 옵션일 수도 있는데
    # 코드가 가릴 방법이 없어 실제로 이런 것들이 값으로 붙었다 —
    #   'B플랜: 자오 로프웨이 1인 6,600엔'   (가지 않는 쪽의 값)
    #   '전세온천 50분 4,000엔'              (숙박비가 아니라 딸린 요금)
    #   '유료 전세온천 … 추가도 1,100엔'      (무료 1회 뒤의 추가 요금)
    #
    # 금액이 오는 곳은 셋뿐이다. 일정 시트의 금액 칸, '예약' 시트, '호텔' 시트.
    # 칸이 스스로 '이건 금액' 이라고 말해주는 자리들이다.
    # 문장에 적힌 값은 글 그대로 메모에 남아 사람이 읽는다.

    # ── 지정석 ────────────────────────────────────────────
    # 좌석까지 잡은 구간은 자유석과 다르다. 그 차를 놓치면 표가 죽는다.
    # 시각이 다 정해진 뒤라 출발 시각으로 가릴 수 있다.
    seats = [x for x in SHEET_SEATS if x["date"] == date]
    for e in entries:
        lg = e["obj"]
        if not isinstance(lg, Leg):
            continue
        hm = (lg.time or {}).get("start")
        for x in seats:
            if hm and hm == x["start"]:
                lg.seat = {k: x[k] for k in ("train", "seat", "span", "from", "to")}
                break

    # ── 예약은 '예약' 시트 표에서만 온다 ────────────────────
    # 메모의 '1인 1음료 필수' 같은 문구를 예약으로 오독하던 추측을 걷어낸다.
    rows = [r for r in SHEET_RESV if r.get("date") == date]
    taken: set[int] = set()

    def find_row(it: Item) -> int | None:
        """예약은 (날짜, 시각) 으로 붙는다.

        날짜는 이미 rows 로 걸렀으므로 남은 것은 시각뿐이다. 그 자리에 서는
        항목은 하나라서 이름을 볼 까닭이 없다 — 예약 시트의 상호와 구글이 준
        이름은 대개 다르다(「나나베야」와 「Shichibei ya」). 이름으로 이으려
        했기에 건초더미를 만들고 한글·일본어를 쪼개 견주는 기계가 필요했다.

        한 항목에 후보가 둘 이상일 때 그중 어느 줄에 표식을 달지는
        export_web 이 이름으로 가른다 — 거기서는 시각이 답을 못 준다.
        """
        start = (it.time or {}).get("start")
        if not start:
            return None
        for i, r in enumerate(rows):
            if i not in taken and r.get("time", "")[:5] == start:
                return i
        return None

    def attach_resv(it: Item) -> None:
        i = find_row(it)
        if i is not None:
            taken.add(i)
            it.reservation = resv_from_row(rows[i])
            # 시트 표가 정본이므로 '예약정보:' 줄은 중복이다
        for s in it.subItems:
            attach_resv(s)

    for e in entries:
        if isinstance(e["obj"], Item):
            attach_resv(e["obj"])

    # ── 후보가 하나뿐이면 선택지가 아니라 그 항목의 실체다 ──
    def fold_solo(it: Item) -> None:
        # '#' 묶음의 제목은 가게 이름이 아니라 분류다.
        # 접으면 '구경' 만 남고 정작 千年鮭 きっかわ 가 사라진다.
        if "-g" in it.id:
            return
        # 하위 항목이 하나뿐이고 그 아래가 비어 있으면 그것이 이 항목의 실체다.
        # ('🍚 점심' 아래 'The Front Room' 한 줄 — 선택지가 아니라 그 집이다)
        if len(it.subItems) == 1 and not it.candidates:
            s = it.subItems[0]
            if not s.candidates and not s.subItems:
                it.subItems = []
                it.detail = Candidate(name=s.title, hours=s.hours, raw=s.title)
                if not it.hours and s.hours:
                    it.hours = s.hours
                if it.costText is None and s.costText:
                    it.costText = s.costText
                it.notes.extend(s.notes)
                if s.reservation and not it.reservation:
                    it.reservation = s.reservation
        if len(it.candidates) == 1 and not it.subItems:
            c = it.candidates.pop()
            it.detail = c
            if not it.hours and c.hours:
                it.hours = c.hours          # 영업시간은 항목 자체의 것이 된다
        for s in it.subItems:
            fold_solo(s)

    for e in entries:
        if isinstance(e["obj"], Item):
            fold_solo(e["obj"])

    # ── 이동을 앞뒤 항목에 연결 ────────────────────────────
    items = [e["obj"] for e in entries if e["kind"] == "item"]
    legs: list[Leg] = []
    for i, e in enumerate(entries):
        if e["kind"] != "move":
            continue
        leg: Leg = e["obj"]
        before = next((entries[j]["obj"] for j in range(i - 1, -1, -1) if entries[j]["kind"] == "item"), None)
        after = next((entries[j]["obj"] for j in range(i + 1, len(entries)) if entries[j]["kind"] == "item"), None)
        leg.fromItem = before.id if before else None
        leg.toItem = after.id if after else None
        src, dst = split_move(leg.title)
        if not (src and dst):
            # 제목이 짧으면 하위 줄의 'A → B' 를 쓴다
            for n in list(leg.notes):
                a2, b2 = split_arrow(n)
                if a2 and b2:
                    src, dst = src or a2, dst or b2
                    leg.notes.remove(n)
                    break
        leg.vehicle = split_vehicle(leg.title, leg.mode)
        if src:
            leg.notes.insert(0, f"출발: {src}")
        if dst:
            leg.notes.insert(0, f"도착: {dst}")
        legs.append(leg)

    day["items"] = [strip_none(asdict(x)) for x in items]
    day["legs"] = [strip_none(asdict(x)) for x in legs]
    day["flags"] = day_flags(date)
    return day


def day_flags(date: str) -> list[str]:
    flags = []
    if "2026-09-22" <= date <= "2026-09-26":
        flags.append("jrpass")
    if "2026-09-19" <= date <= "2026-09-22" or "2026-09-26" <= date <= "2026-09-29":
        flags.append("car")
    return flags


def strip_none(d):
    if isinstance(d, dict):
        return {k: strip_none(v) for k, v in d.items()
                if v not in (None, [], {}, "", False)}
    if isinstance(d, list):
        return [strip_none(x) for x in d]
    return d


# ─────────────────────────────────────────────────────────────
# 출력
# ─────────────────────────────────────────────────────────────
def report(trip: dict) -> None:
    print("=" * 74)
    print(f" {trip['title']} — 파싱 결과")
    print("=" * 74)
    for day in trip["days"]:
        stay = (day.get("stay") or {}).get("name") or "—"
        flags = " ".join(f"[{f}]" for f in day.get("flags", []))
        print(f"\n■ {day['date']} ({day['dow']})  {day.get('region') or '지역 미기재'}  {flags}")
        print(f"  숙박: {stay}")
        legs_by_from = defaultdict(list)
        for lg in day["legs"]:
            legs_by_from[lg.get("fromItem")].append(lg)
        for it in day["items"]:
            t = (it.get("time") or {}).get("start") or "  ·  "
            end = (it.get("time") or {}).get("end")
            span = f"{t}~{end}" if end else f"{t}     "
            warn = " ⚠시각보정" if it.get("suspectTime") else ""
            cost = ""
            if it.get("costText"):
                mark = "※" if it.get("covered") else ""
                cost = f"  {it['costText']}{mark}"
            print(f"  {span}  {it['type']:<6} {it['title'][:44]}{cost}{warn}")
            if it.get("reservation"):
                r = it["reservation"]
                bits = [x for x in (
                    f"{r.get('people')}인" if r.get("people") else None,
                    r.get("booker"),
                    f"¥{r['costJpy']:,}" if r.get("costJpy") else None) if x]
                print(f"           ★ 예약 {' / '.join(bits)}")
            if it.get("detail"):
                print(f"           = {it['detail']['name'][:52]}")
            if it.get("hours"):
                print("           ⏰ " + ", ".join(f"{h['open']}-{h['close']}" for h in it["hours"]))
            for cd in it.get("candidates", []):
                hrs = ""
                if cd.get("hours"):
                    hrs = "  " + ", ".join(f"{h['open']}-{h['close']}" for h in cd["hours"])
                print(f"           · {cd['name'][:38]:<38}{hrs}")
                extra = " · ".join(x for x in (
                    cd.get("desc"),) if x)
                if extra:
                    print(f"               {extra[:62]}")
            for nt in it.get("notes", []):
                print(f"           - {nt[:60]}")
            for sb in it.get("subItems", []):
                print(f"           ▸ {sb['type']:<6} {sb['title'][:44]}")
                if sb.get("reservation"):
                    r = sb["reservation"]
                    bits = [x for x in (
                        f"{r.get('people')}인" if r.get("people") else None,
                        r.get("booker"),
                        f"¥{r['costJpy']:,}" if r.get("costJpy") else None) if x]
                    print(f"                ★ 예약 {' / '.join(bits)}")
                for cd in sb.get("candidates", []):
                    hrs = ""
                    if cd.get("hours"):
                        hrs = "  " + ", ".join(f"{h['open']}-{h['close']}" for h in cd["hours"])
                    print(f"                · {cd['name'][:33]:<33}{hrs}")
                for nt in sb.get("notes", []):
                    print(f"                - {nt[:55]}")
            for lg in legs_by_from.get(it["id"], []):
                dur = f"{lg['durationMin']}분" if lg.get("durationMin") else "?"
                cst = ""
                if lg.get("costText"):
                    cst = " " + lg["costText"] + ("※" if lg.get("covered") else "")
                print(f"    ↓ {lg['mode']:<5} {dur}{cst}   {lg['title'][:40]}")

    # 요약
    n_item = sum(len(d["items"]) for d in trip["days"])
    n_leg = sum(len(d["legs"]) for d in trip["days"])
    def walk(day):
        for i in day["items"]:
            yield i
            yield from i.get("subItems", [])

    n_sub = sum(len(i.get("subItems", [])) for d in trip["days"] for i in d["items"])
    n_cand = sum(len(i.get("candidates", [])) for d in trip["days"] for i in walk(d))
    n_hours = sum(1 for d in trip["days"] for i in walk(d)
                  for c in i.get("candidates", []) if c.get("hours"))
    n_resv = sum(1 for d in trip["days"] for i in walk(d) if i.get("reservation"))
    print("\n" + "-" * 74)
    print(f"  날짜 {len(trip['days'])} · 항목 {n_item}(+하위 {n_sub}) · 구간 {n_leg}"
          f" · 후보 {n_cand} (영업시간 {n_hours}) · 예약 {n_resv}")
    print(f"  체크리스트 {len(trip['checklist'])}건")
    print("-" * 74)


def write(trip: dict) -> None:
    """엑셀에서 뽑은 결과를 정본(master.json)으로 저장한다.

    이후 모든 수정은 master.json 에서 한다. 엑셀은 다시 읽지 않는다 —
    다시 읽으면 손으로 고친 것이 전부 날아가기 때문이다.
    """
    DATA.mkdir(exist_ok=True)
    out = DATA / "master.json"
    if out.exists():
        (DATA / "master.prev.json").write_text(
            out.read_text(encoding="utf-8"), encoding="utf-8")
        print("  기존 정본을 master.prev.json 으로 백업")
    out.write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out}   (정본. 앞으로는 여기서 고친다)")
    print("  다음: python tools/build.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="전체 시트")
    ap.add_argument("--force", action="store_true",
                    help="master.json 이 있어도 엑셀에서 다시 추출")
    ap.add_argument("--sheet", action="append", help="특정 시트 (반복 가능)")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않음")
    args = ap.parse_args()

    if (DATA / "master.json").exists() and not args.force and not args.dry_run:
        sys.exit("data/master.json 이 이미 있습니다. 정본은 그쪽입니다. "
                 "엑셀에서 다시 뽑으려면 --force "
                 "(기존 정본은 master.prev.json 로 백업)")
    sheets = args.sheet or None          # 지정이 없으면 전 시트
    trip = parse(sheets)
    report(trip)
    if not args.dry_run:
        write(trip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
