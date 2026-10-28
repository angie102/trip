# -*- coding: utf-8 -*-
"""구글 시트를 xlsx 로 내려받는다.

시트가 정본이다. 로컬 파일은 그 사본일 뿐이므로 매번 새로 받는다.
직전 파일은 sheet.prev.xlsx 로 남겨 되돌릴 수 있게 한다.

    python tools/pull_sheet.py            # 받아서 바뀐 곳 요약
    python tools/pull_sheet.py --diff     # 셀 단위로 무엇이 달라졌는지
"""
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 시트에 이모지가 들어 있어 cp949 콘솔이 못 쓴다(🚝 에서 죽었다).
# 파일은 그대로고 막히는 것은 화면 출력뿐이라 여기서 바꿔 둔다.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SHEET_ID = "1TyckfYGxkET7k8ZWzXvo9zU3uu3IhgRzBpEr63EYsmw"
OUT = DATA / "sheet.xlsx"
PREV = DATA / "sheet.prev.xlsx"


def download() -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"내려받기 실패 HTTP {e.code} — 공유 설정이 '링크가 있는 모든 사용자' 인지 확인하세요.")
    if data[:2] != b"PK":
        sys.exit("xlsx 가 아닙니다. 공유 권한을 확인하세요.")
    return data


def cells(path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and str(c.value).strip():
                    out[(ws.title, c.coordinate)] = str(c.value)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true", help="셀 단위로 차이를 보여준다")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    old = cells(OUT) if OUT.exists() else None
    if OUT.exists():
        shutil.copy2(OUT, PREV)

    data = download()
    OUT.write_bytes(data)
    print(f"내려받음 {len(data)//1024} KB → {OUT}")

    if old is None:
        print("  (첫 내려받기 — 비교 대상 없음)")
    else:
        new = cells(OUT)
        added = [k for k in new if k not in old]
        gone = [k for k in old if k not in new]
        changed = [k for k in new if k in old and new[k] != old[k]]
        print(f"  추가 {len(added)} · 삭제 {len(gone)} · 변경 {len(changed)}")
        if args.diff:
            for k in changed[:40]:
                print(f"    ~ {k[0]}!{k[1]}")
                print(f"        전: {old[k][:70]}")
                print(f"        후: {new[k][:70]}")
            for k in added[:20]:
                print(f"    + {k[0]}!{k[1]}  {new[k][:66]}")
            for k in gone[:20]:
                print(f"    - {k[0]}!{k[1]}  {old[k][:66]}")

    print("\n  다음: python tools/build.py --reparse")
    return 0


if __name__ == "__main__":
    sys.exit(main())
