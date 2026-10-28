# -*- coding: utf-8 -*-
"""세워 둔 규칙에 어긋난 자리를 찾는다.

세 갈래로 본다.

    데이터   정본과 장소 — 라벨이 장소 행세하나, 후보에 좌표·시간·읽기가 있나
    규칙     예외와 표가 아직 살아 있나 — 죽은 줄은 규칙을 복잡해 보이게 한다
    화면     값이 단 안에 있나, 간격이 사다리와 갈래에 맞나,
             색 문서가 화면보다 낡지 않았나

한때 lint_css · lint_gaps · excel_todo 셋으로 갈려 있었다. 갈려 있으니
어느 것이 무엇을 보는지 알 수 없었고, 세 도구가 다 통과인데도 눈으로 잡히는
어긋남이 남았다 — 가로 간격은 아무도 안 보고 있었고, 죽은 예외는 「걸렸다」로
세고 있었다.

    python tools/check.py              전부
    python tools/check.py 데이터        정본과 장소만
    python tools/check.py 규칙          예외와 표만
    python tools/check.py 화면          CSS 와 간격만
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web-react"
CSS = WEB / "src" / "styles.css"

OUT: dict[str, list[str]] = defaultdict(list)


def say(head: str, row: str) -> None:
    OUT[head].append(row)


# ── CSS 읽기 ────────────────────────────────────────────
def strip_comments(s: str) -> str:
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


_css = strip_comments(CSS.read_text(encoding="utf-8"))
TOK = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", _css[: _css.index("*{")]))
RULES: list[tuple[set[str], str]] = [
    ({s.strip() for s in m.group(1).split(",") if s.strip()}, m.group(2))
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _css)
]


def px(v: str) -> float:
    """var() · calc() 를 풀어 숫자로. 우리 CSS 안의 꼴만 다룬다."""
    v = v.strip()
    for _ in range(6):
        v = re.sub(r"var\((--[\w-]+)\)", lambda m: TOK.get(m.group(1), "0"), v)
    m = re.fullmatch(r"calc\((.+)\)", v)
    if m:
        return float(eval(m.group(1).replace("px", "")))
    if v in ("0", "auto", "none", "inherit", ""):
        return 0.0
    return float(v.rstrip("px"))


def parts(v: str) -> list[str]:
    """공백으로 나누되 괄호 안은 건드리지 않는다 —
    calc(-1 * var(--sp-2)) 를 넷으로 쪼개면 shorthand 가 여섯 조각이 된다."""
    out, buf, depth = [], "", 0
    for ch in v:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if buf:
                out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


SIDE = {"top": 0, "right": 1, "bottom": 2, "left": 3}
MISSING: list[str] = []


def shorthand(v: str, side: str) -> str:
    p = parts(v)
    if len(p) == 1:
        p = p * 4
    elif len(p) == 2:
        p = [p[0], p[1], p[0], p[1]]
    elif len(p) == 3:
        p = [p[0], p[1], p[2], p[1]]
    return p[SIDE[side]]


def decl(sels: list[str], prop: str, *, axis: int = 0, need: bool = False) -> float:
    """이 선택자들에 걸리는 값. 명시도는 안 따진다 —
    우리 CSS 는 같은 자리를 겹쳐 쓰지 않으므로 차례만으로 충분하다.

    axis 는 gap 을 읽을 때만 쓴다. gap 은 「세로 가로」 차례라 0 이 세로다.
    """
    want = set(sels)
    base, side = (prop.split("-", 1) if "-" in prop else (prop, None))
    if side not in SIDE:
        base, side = prop, None
    out, found = 0.0, False
    for rsels, body in RULES:
        if not (want & rsels):
            continue
        for m in re.finditer(r"(?:^|;)\s*([\w-]+)\s*:\s*([^;]+)", body):
            k, v = m.group(1), m.group(2).strip()
            if k == prop:
                p = parts(v)
                out, found = px(p[axis] if axis < len(p) else p[0]), True
            elif side and k == base:
                out, found = px(shorthand(v, side)), True
            elif side and k == f"{base}-block":
                out, found = px(v), True
    if not found and (need or prop in ("font-size", "line-height")):
        MISSING.append(f"{sels} 의 {prop}")
    return out


def lead(sels: list[str]) -> float:
    """글줄이 글자 한쪽에 남기는 여백."""
    return (decl(sels, "line-height") - decl(sels, "font-size")) / 2


# ── 화면 ① 값이 단 안에 있는가 ──────────────────────────
OK_SIZE = {"22", "15", "13", "26", "11"}
OK_WEIGHT = {"400", "500", "600", "700"}
OK_ICON = {"14", "16", "18"}
BARE = ("#fff", "#ffffff", "#000", "#000000")   # 흰색과 검정은 색이 아니라 바탕


def screen_values() -> None:
    css = CSS.read_text(encoding="utf-8")
    lh = {k: int(v.rstrip("px")) for k, v in TOK.items()
          if k.startswith("--lh") and v.strip().endswith("px")}

    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", strip_comments(css)):
        sel = m.group(1).strip().splitlines()[-1].strip()
        body = m.group(2)
        line = css[: m.start()].count("\n") + 1
        if sel.startswith(("@", ":root")) or "--" in sel or sel == "body":
            continue
        where = f"{line:>4}  {sel[:32]:<34}"

        for c in re.findall(r"#[0-9a-fA-F]{3,8}",
                            " ".join(re.findall(r"(?:color|background|border|fill)[^:]*:\s*([^;]+)", body))):
            if c.lower() not in BARE:
                say("색 — 다섯 단 밖", where + c)
        for v in re.findall(r"font-size:\s*([\d.]+)px", body):
            if v not in OK_SIZE:
                say("활자 — 세 단 밖", where + f"{v}px")
        for v in re.findall(r"font-weight:\s*(\d+)", body):
            if v not in OK_WEIGHT:
                say("굵기 — 네 단 밖", where + v)
        for v in re.findall(r"line-height:\s*([^;]+)", body):
            if "var(--lh" not in v and v.strip() not in ("1", "0"):
                say("글줄 — 토큰 밖", where + v.strip())
        for v in re.findall(r"letter-spacing:\s*([^;]+)", body):
            if "var(--ls" not in v and v.strip() != "0":
                say("자간 — 토큰 밖", where + v.strip())
        for v in re.findall(r"border-radius:\s*([^;]+)", body):
            if "var(--r" not in v and v.strip() not in ("50%", "999px", "0"):
                say("모서리 — 토큰 밖", where + v.strip())
        for m2 in re.finditer(r"(?:margin|padding|gap)[^:]*:\s*([^;]+)", body):
            if re.search(r"(?<![\w-])(?!0px)-?\d+px", m2.group(1)):
                say("간격 — 토큰 밖", where + m2.group(0).strip()[:32])
        for v in re.findall(r":\s*[^;]*?(\d+\.\d+)(?:px|em|rem)", body):
            say("소수점", where + v)

        # 글줄이 제 글자를 안는가 — 여백이 없으면 글자가 넘친다
        fs = re.search(r"font-size:\s*([\d.]+)px", body)
        lv = re.search(r"line-height:\s*var\((--lh[\w-]*)\)", body)
        if fs and lv and lv.group(1) in lh:
            room = lh[lv.group(1)] - float(fs.group(1))
            if room < 2:
                say("글줄 — 글자에 빠듯",
                    where + f"{fs.group(1)}px 글자에 {lh[lv.group(1)]}px 글줄")

    # CSS 밖에 박아 둔 색. 지도 마커는 SVG 문자열이라 var() 를 못 쓴다 —
    # 그 자리에 색을 적어 두면 화면과 갈라진다. 예전 mauve(#8b8d98)가 그렇게 남아
    # 있었는데 CSS 만 보던 검사는 못 잡았다.
    for p in sorted((WEB / "src").rglob("*.ts")) + sorted((WEB / "src").rglob("*.tsx")):
        for ln in strip_comments(p.read_text(encoding="utf-8")).splitlines():
            ln = ln.split("//")[0]
            for c in re.findall(r"#[0-9a-fA-F]{3,8}", ln):
                if c.lower() not in BARE:
                    say("색 — 코드에 박은 값", f"      {p.name:<28}{c}")
    for p in (WEB / "src").rglob("*.tsx"):
        for v in re.findall(r"<Icon[^>]*size=\{(\d+)\}", p.read_text(encoding="utf-8")):
            if v not in OK_ICON:
                say("아이콘 — 세 크기 밖", f"      {p.name:<34}{v}px")


# ── 화면 ② 세로 간격 — 사다리 ───────────────────────────
# 눈에 보이는 간격은 토큰 하나가 아니라 여럿의 합이다.
#     앞 요소의 글줄 여백 + 그 padding + 부모의 gap + 뒤 요소의 margin
#     + 그 padding + 뒤 요소의 글줄 여백
# 토큰은 저마다 격자 위에 있는데 합이 사다리에서 벗어나는 일이 잦다.
#
# 값이 아니라 층이다. 2px 차이는 눈이 세지 못하고, 세지 못하는 것은 층이 아니다.
RUNGS = [5, 9, 12, 16, 20.5, 24]
TOL = 2.0


class El:
    """lead_in  제 위 경계에서 첫 잉크까지
       lead_out 마지막 잉크에서 제 아래 경계까지
       면을 가진 것은 경계가 곧 잉크라 0 이다."""

    def __init__(self, name, sels, *, first=None, last=None, filled=False):
        self.name, self.sels = name, sels
        if filled:
            self.lead_in = self.lead_out = 0.0
        else:
            self.lead_in = decl(sels, "padding-top") + lead(first or sels)
            self.lead_out = decl(sels, "padding-bottom") + lead(last or sels)
        self.mt = decl(sels, "margin-top")
        self.mb = decl(sels, "margin-bottom")


def vgaps() -> list[tuple[str, str, float]]:
    """무엇이 무엇 뒤에 오는가 — DayList.tsx 에서 옮겨 적었다.
    마크업이 바뀌면 여기도 고쳐야 하므로, 선택자를 못 찾으면 조용히 넘기지 않는다."""
    TITLE = El("항목 제목", [".rtitle"])
    PLACE = El("후보", [".place"], first=[".pn"], last=[".psub"])
    NOTE = El("메모", [".bnote"])
    RESV = El("예약 상자", [".bresv", ".rbody > .bresv"], filled=True)
    RESV_P = El("예약 상자", [".bresv", ".place > .bresv"], filled=True)
    # 할 일은 면을 잃었다 — 네모 안 체크가 그 뜻을 진다.
    # 경계가 곧 잉크가 아니므로 글줄이 남기는 여백을 세어야 한다.
    # 할 일 상자는 제목 한 줄뿐이다(DayList 의 .btask 안에는 .t 밖에 없다).
    # 딸린 줄(.bd)은 예약·지정석 상자에만 있다 — 여기서 그것을 찾으면
    # 선택자가 바뀐 것처럼 보여 검사가 늘 빨간불이었다.
    TASK = El("할 일", [".btask", ".rbody > .btask"],
              first=[".btask .t"], last=[".btask .t"])
    SEAT = El("지정석 상자", [".bseat", ".legbody > .bseat"], filled=True)
    IMG = El("안내도", [".legimg", ".legbody > .legimg"], filled=True)
    ROUTE = El("경로 줄", [".route"])
    BOXT = El("상자 제목", [".bresv .t", ".btask .t", ".bseat .t"])
    BOXD = El("상자 몸통", [".bresv .bd", ".bseat .bd"])
    NAME = El("이름 줄", [".pn"])
    SUBL = El("설명 줄", [".psub"])
    DAY = El("날짜", [".daytitle"])
    SUB = El("지역 줄", [".daysub"])
    STAY = El("숙소 줄", [".daystay"])
    PITEM = El("준비 한 줄", [".pitem"])
    PMEMO = El("준비 메모", [".pmemo"])
    PH2 = El("구역 이름", [".pgroup h2"])

    G = px(TOK["--sp-h"])                 # .rbody · .legbody 의 gap
    SP1 = px(TOK["--sp-1"])
    out: list[tuple[str, str, float]] = []

    def case(where, what, val):
        out.append((where, what, round(val, 2)))

    def between(a, b, gap, extra=0.0):
        return a.lead_out + a.mb + gap + extra + b.mt + b.lead_in

    first = decl([".rbody > :first-child"], "margin-top", need=True)
    case("몸통", "제목 → 첫 후보", TITLE.lead_out + first + PLACE.lead_in)
    case("몸통", "제목 → 첫 메모",
         TITLE.lead_out
         + decl([".rbody > .bnote:first-of-type"], "margin-top", need=True)
         + decl([".bnote:first-of-type"], "padding-top", need=True) + lead([".bnote"]))
    case("몸통", "제목 → 할 일", TITLE.lead_out + first + TASK.lead_in)
    case("몸통", "메모 → 메모",
         between(NOTE, NOTE, G, decl([".bnote + .bnote"], "margin-top", need=True)))
    case("몸통", "메모 → 후보",
         between(NOTE, PLACE, G, decl([".bnote + :not(.bnote)"], "margin-top", need=True)))
    case("몸통", "후보 → 후보", between(PLACE, PLACE, G))
    case("몸통", "묶음이 바뀌는 자리",
         between(PLACE, PLACE, G, decl([".place.sep"], "margin-top", need=True)))
    case("몸통", "후보 → 예약 상자", between(PLACE, RESV, G))
    case("몸통", "할 일 → 후보", between(TASK, PLACE, G))
    case("몸통", "후보 → 마지막(항목 끝)",
         PLACE.lead_out + decl([".row"], "padding-bottom", need=True))
    case("후보 안", "이름 → 설명", between(NAME, SUBL, 0))
    case("후보 안", "설명 → 예약 상자", SUBL.lead_out + RESV_P.mt)
    case("상자 안", "제목 → 몸통", between(BOXT, BOXD, SP1))
    case("상자 안", "몸통 → 몸통", between(BOXD, BOXD, SP1))
    case("이동 상자", "누름 줄 → 지정석 상자",
         decl([".lb"], "padding-bottom", need=True)
         + decl([".legbody > .bseat:first-child"], "margin-top", need=True))
    case("이동 상자", "지정석 상자 → 경로 줄", between(SEAT, ROUTE, G))
    case("이동 상자", "경로 줄 → 후보", between(ROUTE, PLACE, G))
    case("이동 상자", "후보 → 안내도", between(PLACE, IMG, G))
    case("이동 상자", "안내도 → 메모", between(IMG, NOTE, G))
    case("이동 상자", "경로 줄 → 메모",
         between(ROUTE, NOTE, G, decl([":not(.bnote) + .bnote"], "margin-top", need=True)))
    case("이동 상자", "누름 줄 → 메모",
         decl([".lb"], "padding-bottom") + decl([".bnote:first-of-type"], "padding-top")
         + lead([".bnote"]))
    case("준비", "챙길 것 → 챙길 것",
         between(PITEM, PITEM, decl([".plist"], "gap", need=True)))
    case("준비", "구역 이름 → 첫 줄",
         PH2.lead_out + decl([".pgroup h2"], "margin-bottom", need=True) + PITEM.lead_in)
    case("준비", "메모 → 메모",
         between(PMEMO, PMEMO, decl([".pmemo"], "margin-bottom", need=True)))
    case("머리", "날짜 → 지역", between(DAY, SUB, 0))
    case("머리", "지역 → 숙소", between(SUB, STAY, 0))
    case("머리", "머리 → 첫 항목",
         STAY.lead_out + decl([".cardhead"], "padding-bottom", need=True)
         + decl([".row"], "padding-top", need=True) + TITLE.lead_in)
    case("항목", "항목 → 항목",
         PLACE.lead_out + decl([".row"], "padding-bottom")
         + decl([".row"], "padding-top") + TITLE.lead_in)
    case("항목", "항목 → 이동 블록",
         PLACE.lead_out + decl([".row"], "padding-bottom")
         + decl([".legwrap"], "padding-top", need=True))
    case("항목", "이동 블록 → 항목",
         decl([".legwrap"], "padding-bottom", need=True)
         + decl([".row"], "padding-top") + TITLE.lead_in)
    return out


# ── 화면 ③ 가로 간격 — 갈래 ─────────────────────────────
# 가로는 층이 아니라 갈래다. 무엇 옆이냐로 값이 정해진다.
#
# 세로에서 글줄 여백이 잉크 사이 거리를 만들 듯, 가로에서는 아이콘이 제 안에
# 품은 2px 이 그 노릇을 한다 — 규칙에 「4px 을 주면 눈에는 6px」이라 적힌 그것이다.
# 그래서 아이콘이 낀 자리는 잰 값에 2 를 더해 「눈에 보이는 거리」로 견준다.
KIND = {
    "앞 아이콘": ("--sp-1", "글자를 이끄는 것이라 여백이 필요하다"),
    "뒤 아이콘": ("--sp-h", "그 이름에 딸린 것이라 붙어야 소속이 읽힌다"),
    "딴 것끼리": ("--sp-2", "기준값"),
    "이어 읽는 짝": ("--sp-1", "이름↔원어 · A→B"),
    "큰↔작은": ("--sp-3", "눈은 큰 쪽을 기준으로 재어 좁아 보인다"),
    "열↔열": ("--sp-3", "시각 열과 본문 열"),
    "화면 좌우": ("--sp-4", ""),
}
ICON_PAD = 2.0       # 아이콘이 제 안에 품은 여백


def hgaps() -> list[tuple[str, str, str, float]]:
    """한 줄에 나란히 서는 짝 — 컴포넌트에서 옮겨 적었다.

    (어디, 무엇↔무엇, 갈래, 잰 값). 잰 값은 부모의 gap 에 두 자식의 좌우 margin
    을 더한 것이고, 아이콘이 끼면 그 안쪽 여백까지 더한다.
    """
    def g(sel: str) -> float:
        return decl([sel], "gap", axis=1, need=True)

    def ml(sel: str) -> float:
        return decl([sel], "margin-left")

    out: list[tuple[str, str, str, float]] = []

    def case(where, what, kind, val, icon=False):
        out.append((where, what, kind, round(val + (ICON_PAD if icon else 0), 2)))

    # 후보 이름 줄 — 이름·원어는 .nw 안에 있어 .pn 의 gap 을 안 받는다
    case("후보", "이름 ↔ 원어", "이어 읽는 짝", ml(".nw .ja"))
    case("후보", "원어 ↔ 예약 표식", "뒤 아이콘", g(".pn"), icon=True)
    case("후보", "예약 표식 ↔ 지도 링크", "뒤 아이콘", g(".pn"), icon=True)
    # 시각과 설명은 이어 읽는 짝이 아니라 딴 것끼리다.
    # 4px 이던 때는 한 낱말처럼 붙어 어디서 끊어 읽을지가 흐렸다 —
    # 「언제」와 「무엇을」은 한 줄에 서더라도 서로 다른 것이다.
    case("후보", "시각 ↔ 설명", "딴 것끼리", g(".psub"))
    # 항목 줄
    case("항목", "시각 열 ↔ 본문 열", "열↔열", g(".rtop"))
    # 머리
    case("머리", "숙소 ↔ 뒤따르는 값", "뒤 아이콘", g(".daystay"), icon=True)
    case("머리", "숙소 ↔ 금액", "이어 읽는 짝", ml(".daystay .due"))
    case("머리", "깃발 ↔ 깃발", "이어 읽는 짝", g(".flags"))
    case("머리", "깃발 안 아이콘 ↔ 글자", "앞 아이콘", g(".flag"), icon=True)
    # 날짜 칩끼리는 재지 않는다. 탭이 되면서 칩들이 맞붙었고(gap 없음),
    # 사이는 저마다의 좌우 여백이 만든다 — 그 여백은 「둘 사이 거리」가
    # 아니라 누르는 넓이라 이 갈래로 잴 것이 아니다. 붙여 둔 까닭은
    # 칩마다 지는 아래 선이 한 줄로 이어져야 하기 때문이다.
    # 상자
    case("상자", "아이콘 ↔ 제목", "앞 아이콘", g(".bresv .t"), icon=True)
    case("상자", "메모 아이콘 ↔ 글", "앞 아이콘", g(".bnote"), icon=True)
    case("이동", "아이콘 ↔ 탈것", "앞 아이콘", g(".lb"), icon=True)
    case("이동", "출발 → 도착", "이어 읽는 짝", g(".route"))
    case("이동", "이동 블록 좌우 여백", "열↔열", g(".legwrap"))
    # 준비·체크리스트
    case("준비", "체크 ↔ 글", "앞 아이콘", g(".pitem"), icon=True)
    case("준비", "말 ↔ 원어", "이어 읽는 짝", g(".pmemo"))
    case("준비", "열 ↔ 열", "열↔열", g(".plist"))
    case("체크", "아이콘 ↔ 글", "앞 아이콘", g(".tk"), icon=True)
    return out


def screen_gaps() -> None:
    for where, what, val in sorted(vgaps(), key=lambda r: (r[2], r[0])):
        near = min(RUNGS, key=lambda r: abs(r - val))
        if abs(near - val) > TOL:
            say("세로 간격 — 사다리 밖",
                f"  [{where}] {what:<20}{val:>6g}px   가장 가까운 층 {near:g}px")
    for where, what, kind, val in hgaps():
        tok, why = KIND[kind]
        want = px(TOK[tok]) + (ICON_PAD if "아이콘" in kind else 0)
        if abs(want - val) > 0.5:
            say("가로 간격 — 갈래 밖",
                f"  [{where}] {what:<22}{val:>5g}px   {kind} 는 {want:g}px — {why}")


# ── 데이터 ──────────────────────────────────────────────
JA = re.compile(r"[぀-ヿ一-鿿]")
KO = re.compile(r"[가-힣]")


def load(name: str):
    f = DATA / name if not name.startswith("web") else ROOT / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def data_checks() -> None:
    view = load("web-react/src/data/trip.json")
    places = load("places.json")
    if not view or not places:
        say("데이터", "  trip.json 이나 places.json 이 없다 — build.py 를 먼저")
        return

    for d in view["days"]:
        for it in d["items"]:
            holders = [("항목", it, it.get("detail") or it["title"])]
            holders += [("후보", s, s["name"]) for s in it.get("spots", [])]
            for tag, h, nm in holders:
                pl = h.get("place")
                # ① 라벨이 장소 행세를 하는가.
                #    라벨은 「무엇을 하는가」이고 장소는 「그 자리가 어디인가」다.
                if pl:
                    if not pl.get("id") and pl.get("lat") is None:
                        say("라벨이 장소 행세", f"  {d['date']} {tag} 껍데기 {pl}")
                    elif pl.get("approx") and pl.get("name"):
                        say("라벨이 장소 행세",
                            f"  {d['date']} {tag} 중점에 이름 {pl['name']}")
                    elif not pl.get("id") and pl.get("name") == it.get("title"):
                        say("라벨이 장소 행세",
                            f"  {d['date']} {tag} 제목을 베낌 {pl['name']}")
                # ② 읽을 수 있는 이름인가
                if JA.search(nm) and not KO.search(nm):
                    say("못 읽는 이름", f"  {d['date']} {nm}   data/exceptions.json 의 표기에 적는다")
            # ③ 후보인데 좌표가 없다
            for s in it.get("spots", []):
                if s.get("group") or s.get("note"):
                    continue
                if not (s.get("place") or {}).get("lat"):
                    say("후보인데 좌표 없음", f"  {d['date']} {s['name']}")

    # ④ 저장 목록과 어긋난다.
    #
    # 구글 지도에 찍어 둔 목록이 정본이다. placeId 를 CID 로 바꾸면 이름도
    # 조회도 없이 그대로 맞댈 수 있다 (tools/saved_lists.py 참고).
    # 좌표가 어긋나면 우리 쪽이 틀린 것이다 — 저장 목록에서 좌표까지
    # 그대로 가져온 넷이 수백 km 씩 어긋나 있었다.
    saved = load("saved_places.json") or {}
    if saved:
        sys.path.insert(0, str(ROOT / "tools"))
        from saved_lists import SAVED, cid_of, read_lists     # noqa: E402
        from places_keys import STRAY_KM, km_between          # noqa: E402
        from pathlib import Path as _P                        # noqa: E402
        for k, v in (places or {}).items():
            gid = v.get("placeId")
            s = saved.get(cid_of(gid) or "") if gid else None
            if not s or v.get("lat") is None or s.get("lat") is None:
                continue
            km = km_between(v, s)
            if km is not None and km > STRAY_KM:
                say("저장 목록과 좌표가 다르다",
                    f"  {v['name'][:30]:<32}{km:.1f}km   목록 {s['lat']:.4f},{s['lng']:.4f}")

        # ⑤ 다리 — 내보내기에 없는 자리는 사람이 답을 줘야 한다.
        #    두 정본(엑셀·내보내기)을 잇는 유일한 자리다. 낱말을 뜯어 맞추지
        #    않고, 어느 CID 가 맞는지 적어 두면 조회를 다시 해도 같은 답이 온다.
        bridge = (load("place_map.json") or {}).get("다리") or {}
        listed = {r["cid"] for r in read_lists(_P(SAVED), "일본") if r["cid"]}
        for k, v in (places or {}).items():
            gid = v.get("placeId")
            # id 가 없는 자리야말로 다리가 필요하다 — 대조할 짝조차 못 만든다.
            # 한때 「id 는 있는데 목록에 없는 자리」만 올렸더니, 좌표도 id 도
            # 없는 셋이 아무 데도 안 걸리고 조용히 남아 있었다.
            if gid and cid_of(gid) in listed:
                continue
            nm = v.get("name", "")
            hit = next((b for b in bridge if b and b in nm or nm in (b or "")), None)
            if hit is None:
                say("다리에 없는 자리", f"  {nm[:38]}   data/place_map.json 에 적는다")
            elif bridge[hit] is None:
                say("다리에 답이 비었다", f"  {hit[:38]}   어느 CID 인지 알려 주면 된다")

    # ⑥ 주소가 가리키는 곳과 좌표가 다르다.
    #
    # 구글이 준 주소에는 현(縣) 이름이 들어 있다. 그 현의 대략 범위와 좌표를
    # 맞대면, 신원은 맞는데 좌표만 엉뚱한 자리를 잡아낸다 — 저장 목록에서
    # 좌표까지 그대로 가져온 넷이 그랬다. 「Kitari」는 주소가 니가타인데
    # 좌표는 오사카였고, 주소만 보면 끝까지 안 보인다.
    #
    # 범위는 넉넉히 잡는다. 현 경계를 정밀히 아는 것이 목적이 아니라
    # 「몇백 km 떨어진 자리」를 잡는 것이 목적이다.
    KEN = {
        "Niigata": (36.8, 38.6, 137.6, 139.9),
        "Nagano": (35.2, 37.0, 137.3, 138.8),
        "Saitama": (35.7, 36.3, 138.7, 139.9),
        "Tokyo": (35.5, 35.9, 139.3, 139.9),
        "Yamagata": (37.7, 39.2, 139.5, 140.7),
        "Miyagi": (37.7, 39.0, 140.2, 141.7),
        "Iwate": (38.7, 40.5, 140.6, 142.1),
        "Aomori": (40.2, 41.6, 139.5, 141.7),
        "Akita": (38.8, 40.6, 139.6, 141.0),
        "Fukushima": (36.7, 38.0, 139.1, 141.1),
    }
    for k, v in (places or {}).items():
        la, ln = v.get("lat"), v.get("lng")
        addr = v.get("address") or ""
        if la is None or not addr:
            continue
        for ken, (s, n, w, e) in KEN.items():
            if ken not in addr:
                continue
            if not (s <= la <= n and w <= ln <= e):
                say("주소와 좌표가 다르다",
                    f"  {v['name'][:30]:<32}주소 {ken} · 좌표 {la:.2f},{ln:.2f}")
            break

    # ⑦ 한 항목의 후보들이 서로 멀다.
    #    같은 항목에 묶였다면 한 동네여야 한다 — 「Shop KASAI」가 48km 떨어진
    #    슈퍼로 잡혀 있던 것을 눈으로 찾았다. 눈이 할 일이 아니다.
    for d in view["days"]:
        for it in d["items"]:
            pts = [(s["name"], s["place"]["lat"], s["place"]["lng"])
                   for s in it.get("spots", [])
                   if (s.get("place") or {}).get("lat") is not None]
            if len(pts) < 2:
                continue
            mlat = sum(p[1] for p in pts) / len(pts)
            mlng = sum(p[2] for p in pts) / len(pts)
            for nm, la, ln in pts:
                km = ((la - mlat) * 111) ** 2 + ((ln - mlng) * 88) ** 2
                km = km ** 0.5
                if km > 30:
                    say("후보가 이웃과 멀다",
                        f"  {d['date']} {nm}   같은 항목 한가운데서 {km:.0f}km")


# ── 정본 ────────────────────────────────────────────────
def master_checks() -> None:
    """엑셀을 옮기다 조용히 틀렸을 만한 자리.

    한때 master.py 가 이 일을 하며 master.md · gaps.md 도 함께 찍었다.
    그 문서를 읽는 사람이 없어졌으므로 검사만 이리로 옮겼다.

    계획한 시각에 문을 여는지는 보지 않는다 — 갈지 말지는 사람이 정하고,
    구글이 준 시간이 그 집의 조·석식 시간인지도 알 수 없다.
    """
    trip = load("master.json")
    places = load("places.json") or {}
    if not trip:
        return

    def walk(items):
        for it in items:
            yield it
            yield from walk(it.get("subItems", []))

    def kids(it):
        out = []
        if it.get("detail"):
            out.append(it["detail"])
        out += it.get("candidates", [])
        for s in it.get("subItems", []):
            out += kids(s)
        return out

    for day in trip["days"]:
        iso = day["date"]
        if not day.get("region"):
            say("지역명 없음", f"  {iso}")
        for it in walk(day["items"]):
            where = f"  {iso[5:]} {it['title'][:28]}"
            # '#' 묶음 제목은 아래 후보들의 이름표라 시각이 없는 것이 맞다
            group = "-g" in it["id"]
            if not group and not (it.get("time") or {}).get("start"):
                say("시각 없는 항목", where)
            if it.get("suspectTime"):
                # 12시간제와 24시간제가 섞여 있어 단조 증가로 읽은 자리다.
                # 값을 지어내는 유일한 곳이라 눈으로 한 번 봐야 한다.
                say("시각을 추정함", where)
            for k in kids(it):
                if k.get("group"):
                    continue
                nm = k.get("name", "")
                if len(nm.strip()) < 2 or re.fullmatch(r"[\d\s:~.,\-]+", nm):
                    say("후보 이름이 이상함", f"{where} → {nm!r}")
                d = k.get("desc") or ""
                if d.count("(") != d.count(")"):
                    say("설명에 괄호 잔해", f"{where} → {d[:40]!r}")
        for lg in day.get("legs", []):
            if not lg.get("durationMin") and not lg.get("costText"):
                say("이동인데 시간·비용 둘 다 없음", f"  {iso[5:]} {lg['title'][:38]}")
            if not any(x.startswith("도착: ") for x in lg.get("notes", [])):
                say("도착지를 못 뽑음", f"  {iso[5:]} {lg['title'][:38]}")


# ── 규칙 ────────────────────────────────────────────────
NORM = re.compile(r"[\s()（）\[\]「」『』・·,.:：/\-—–~〜～!?'’\"]+")


def rule_checks() -> None:
    """예외와 표가 아직 살아 있는가.

    시트는 바뀐다. 그러면 예외가 걸릴 자리를 잃는데, 잃은 채로 남아 있으면
    「아직 이런 손질이 필요하구나」로 읽혀 규칙이 실제보다 복잡해 보인다.
    한 번 세어 보니 일곱 중 다섯이 죽어 있었다.

    「걸렸다」가 아니라 「값이 실제로 바뀌었다」를 센다. 이름만 맞고 아무 일도
    안 하는 줄을 살아 있다고 세던 때는 죽은 예외를 두 번 놓쳤다.
    """
    view = load("web-react/src/data/trip.json")
    master = load("master.json")
    places = load("places.json")
    if not view or not master:
        return

    ex = load("exceptions.json") or {}
    names = ex.get("표기") or {}
    kinds = ex.get("분류") or {}

    # 화면에 뜨는 이름과 그 자리의 마커 종류를 모은다
    shown, kindof = [], []
    for d in view["days"]:
        for it in d["items"]:
            for nm, pl in ([(it.get("detail") or it["title"], it.get("place"))]
                           + [(s["name"], s.get("place")) for s in it.get("spots", [])]):
                shown.append(nm)
                if pl:
                    kindof.append((nm, pl.get("kind")))
    flat = [NORM.sub("", x).lower() for x in shown]

    def hits(key: str) -> bool:
        k = NORM.sub("", key).lower()
        return any(k in x for x in flat)

    # 표기 — 적어 둔 이름이 정본 어딘가에 있는가.
    # 화면에는 이미 바뀐 이름이 뜨므로 정본(master) 쪽을 본다.
    raw: list[str] = []

    def walk(items):
        for it in items:
            raw.append(it["title"])
            if it.get("detail"):
                raw.append(it["detail"]["name"])
            for c in it.get("candidates", []):
                raw.append(c["name"])
            walk(it.get("subItems", []))

    for d in master["days"]:
        walk(d["items"])
        for lg in d.get("legs", []):
            walk(lg.get("subItems", []))
    rawflat = [NORM.sub("", x).lower() for x in raw]
    for k in names:
        kk = NORM.sub("", k).lower()
        if not any(kk in x for x in rawflat):
            say("죽은 표기", f"  data/exceptions.json 표기  {k}")

    # 예외 — 그 이름의 자리가 정말 그 종류로 서 있는가
    for k, want in kinds.items():
        kk = NORM.sub("", k).lower()
        touched = [v for nm, v in kindof if kk in NORM.sub("", nm).lower()]
        if not touched:
            say("죽은 예외", f"  data/exceptions.json 분류  {k} — 그런 자리가 없다")
        elif all(v == want for v in touched) and not hits(k):
            say("죽은 예외", f"  data/exceptions.json 분류  {k} — 안 고쳐도 같다")


def resv_doc_checks() -> None:
    """예약 확인서가 어딘가에 걸렸나.

    파일 이름이 곧 색인이라 매핑 표가 없다(export_web.resv_docs).
    표가 없으니 틀어질 표도 없지만, 이름이 한 끗 어긋나면 그 파일은
    아무 데도 안 걸린 채 조용히 서버에만 얹혀 있다 — 예약서가 링크에서
    사라진 것을 사람이 알아채는 때는 대개 가게 앞이다.

    숙소는 날짜 하나로 걸리지만 밥집은 날짜와 시각 둘로 걸린다.
    걸 자리가 둘이면 어긋날 자리도 둘이다. 그래서 여기서 되짚는다 —
    폴더에 있는 파일이 다 화면에 나왔는지, 화면이 가리키는 파일이
    다 있는지 양쪽으로 본다.
    """
    folder = ROOT / "web-react" / "public" / "resv"
    if not folder.exists():
        return
    view = load("web-react/src/data/trip.json")

    used: dict[str, str] = {}     # 파일이름 → 어디에 걸렸나
    for d in view["days"]:
        stay = d.get("stay") or {}
        if stay.get("doc"):
            used[stay["doc"]] = f"{d['date']} 숙소 {stay.get('name', '')}"
        for it in d["items"]:
            doc = (it.get("reservation") or {}).get("doc")
            if doc:
                used[doc] = f"{d['date']} {it.get('time') or ''} "                             f"{it.get('detail') or it['title']}"

    on_disk = {f.name for f in folder.glob("*.pdf")}
    for name in sorted(on_disk - used.keys()):
        say("걸 자리 없는 예약서",
            f"  web-react/public/resv/{name} — 이름의 날짜·시각이 일정과 맞는가")
    for name in sorted(used.keys() - on_disk):
        say("없는 예약서를 가리킨다", f"  {used[name]}  →  resv/{name}")


def doc_checks() -> None:
    """색 문서가 화면보다 낡았나.

    docs/color.html 은 실제 화면을 찍어 넣은 것이라, 화면이 바뀌면 문서가
    조용히 낡는다. 손으로 그리던 목업이 벌어졌던 것과 같은 일이다 —
    그때는 아무도 몰랐다. 그래서 넣은 styles.css 의 지문을 견준다.
    """
    doc = ROOT / "docs" / "color.html"
    if not doc.exists():
        return
    text = doc.read_text(encoding="utf-8")
    m = re.search(r"styles\.css ([0-9a-f]{8}) 를 그대로 넣었다", text)
    if not m:
        return
    now = hashlib.sha256(CSS.read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:8]
    if m.group(1) != now:
        say("낡은 문서",
            f"  docs/color.html  styles.css {m.group(1)} 로 만들었는데 지금은 {now} — "
            "node tools/render_mock.mjs 뒤 python tools/make_color_doc.py")

    # 들어갔어야 할 것이 실제로 들어갔나.
    #
    # 구조만 보는 검사로는 못 잡는다. 실제로 두 번 놓쳤다 —
    # 생성기에서 변수 이름이 겹쳐 styles.css 가 세트 CSS 로(40,764자 → 1,292자),
    # 날짜 칩이 색 견본으로 덮여 썼는데 태그도 CSS 문법도 JS 도 다 멀쩡했다.
    # 브라우저로 찍어 보고서야 알았다. 그래서 「몇 개인가」를 센다.
    css_len = len(CSS.read_text(encoding="utf-8"))
    want = [
        ("앱 스타일시트", len(re.search(
            r'<script type="text/css" id="appcss">(.*?)</script>', text, re.S).group(1)),
         css_len, "styles.css 가 통째로 들어가야 한다"),
        ("날짜 칩", len(re.findall(r'<button data-day="\d{4}-\d\d-\d\d">', text)),
         len(json.loads((ROOT / "docs" / "mock.json").read_text(encoding="utf-8"))),
         "찍어 둔 날짜만큼 있어야 한다"),
        ("판", len(re.findall(r'<iframe data-mood=', text)), 4, "갈래 넷"),
    ]
    for label, got, expect, why in want:
        if got != expect:
            say("문서 내용", f"  docs/color.html  {label} {got} 개 — {expect} 이라야 한다. {why}")


# ── 내보내기 ────────────────────────────────────────────
PARTS = {"정본": master_checks, "데이터": data_checks, "규칙": rule_checks,
         "화면": lambda: (screen_values(), screen_gaps(),
                          resv_doc_checks(), doc_checks())}


def main() -> int:
    want = [a for a in sys.argv[1:] if a in PARTS] or list(PARTS)
    for k in want:
        PARTS[k]()

    if MISSING:
        print("  ✗ CSS 에서 못 찾은 자리 — 선택자가 바뀌었다")
        for s in MISSING:
            print("     " + s)
        return 1

    total = 0
    for head, rows in OUT.items():
        print(f"\n[{head}]  {len(rows)}건")
        for r in rows[:12]:
            print(r if r.startswith(" ") else "  " + r)
        if len(rows) > 12:
            print(f"    … 외 {len(rows) - 12}건")
        total += len(rows)

    print("\n" + "=" * 60)
    print("본 것  " + " · ".join(want))
    print(f"어긋난 자리 {total}건" if total else "어긋난 자리 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
