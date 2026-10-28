# -*- coding: utf-8 -*-
"""정본(data/master.json) → 검증 · 문서 · React 뷰 모델.

정본은 엑셀이고 master.json 은 그 생성물이다.
엑셀을 고쳤으면 --reparse 로 다시 뽑는다. 직전 정본은 master.prev.json 에 남는다.

엑셀로 표현할 수 없는 수정(장소 아님 표시, 소요시간 계산 등)은
fix_master.py 에 규칙으로 두고, 재추출 때마다 다시 적용된다.

순서를 어기면 조용히 망가진다. 실제로 세 번 겪었다 —
places_keys 를 건너뛰면 placeId 가 비고, 좌표도 영업시간도 0 이 된 채로
뷰 모델이 나가는데 에러는 안 난다. 그래서 순서를 코드로 고정한다.

    python tools/build.py            # 검증 + 문서 + 뷰 모델
    python tools/build.py --reparse  # 엑셀을 고쳤을 때 (정본을 다시 뽑는다)
    python tools/build.py --lookup   # 새로 생긴 장소를 Places API 로 조회 (유료)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# 하위 스크립트의 출력을 여기서 다시 찍는다. 그 안에 이모지와
# 치환 문자(�)가 섞여 있어 cp949 콘솔이 죽는다 — 실패 원인을
# 보여 주려던 print 가 도리어 원인을 가렸다. 목이 여기 하나뿐이라
# 이 줄이 파이프라인 전체의 출력을 살린다.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(script: str, *args: str) -> None:
    cmd = [PY, str(ROOT / "tools" / script), *args]
    print(f"\n▶ {script} {' '.join(args)}".rstrip())
    # 출력을 파이프로 받으면 하위 파이썬의 stdout 이 로케일(cp949)로 잡혀,
    # 이모지나 — 한 글자에 스크립트가 통째로 죽는다. 실제로 parse_trip 이
    # 「파싱 결과」를 찍다가 넘어졌다 — 일은 다 해 놓고 보고하다 죽는 셈이라
    # 원인을 찾기도 어려웠다. 도구마다 인코딩 줄을 붙이는 대신 여기서 물려준다.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
    # 경고(!·✗·X)는 어디에 있든 보여 준다. 마지막 네 줄만 찍던 때는
    # 「한글 읽기 없음」이 위로 밀려 며칠씩 묻혀 있었다 —
    # 안 보이는 경고는 없는 경고와 같다.
    warn = [x for x in lines if x.lstrip().startswith(("!", "✗", "X ", "X	"))]
    for line in warn:
        print("   " + line)
    for line in lines[-4:]:
        if line not in warn:
            print("   " + line)
    if r.returncode:
        print((r.stderr or "")[-600:])
        sys.exit(f"  ✗ {script} 실패")


def guard() -> None:
    """뷰 모델이 비어 있지 않은지 확인한다. 조용한 실패를 막는 마지막 관문."""
    out = ROOT / "web-react" / "src" / "data" / "trip.json"
    d = json.loads(out.read_text(encoding="utf-8"))
    items = [i for day in d["days"] for i in day["items"]]
    coords = sum(1 for i in items if (i.get("place") or {}).get("lat") is not None)
    hours = sum(1 for day in d["days"] for i in day["items"]
                for s in i.get("spots", []) if (s.get("place") or {}).get("hours"))
    print(f"\n  항목 {len(items)} · 좌표 {coords} · 후보 영업시간 {hours}")
    # 임의의 수로 재지 않는다. 이 관문이 잡을 것은 「조용히 비었다」이고,
    # 몇 개부터 괜찮은가는 check.py 가 훨씬 촘촘히 본다. 한때 50 이었는데
    # 실제 값이 81·127 이라 어떤 실패도 못 잡는 그물이었다.
    if not items or not coords or not hours:
        sys.exit("  ✗ 좌표나 영업시간이 비어 있습니다. 순서가 틀렸을 가능성이 큽니다.")
    print("  ✓ 통과")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reparse", action="store_true",
                    help="엑셀에서 정본을 다시 뽑는다 (엑셀을 고쳤을 때)")
    ap.add_argument("--lookup", action="store_true",
                    help="새 장소를 Places API 로 조회한다 (유료 호출)")
    args = ap.parse_args()

    if args.reparse:
        run("parse_trip.py", "--all", "--force")   # 직전 정본 → master.prev.json
        run("fix_master.py", "--apply")            # 엑셀로 못 쓰는 수정 재적용

    # 정본의 이름에 키를 박고, 없는 자리를 만들고, 안 쓰는 키를 걷어낸다.
    # 이 단계를 빼먹으면 placeId 가 비고 좌표도 영업시간도 0 이 된다.
    run("places_keys.py", "--apply")
    if args.lookup:
        run("places_lookup.py")       # 좌표 + 요일별 영업시간
    run("links.py")                   # 일정에 붙여 둔 지도 링크 풀기 (키 없이)
    run("export_web.py")              # React 뷰 모델

    # 엑셀에 붙어 있던 그림을 웹에서 볼 수 있게 옮긴다
    src, dst = ROOT / "data" / "media", ROOT / "web-react" / "public" / "media"
    if src.exists():
        dst.mkdir(parents=True, exist_ok=True)
        # 시트에서 없어진 것은 여기서도 지운다 — 덮어쓰기만 하면
        # 옛 그림이 아무도 가리키지 않는 채로 웹에 실려 나간다.
        keep = {f.name for f in src.glob("*.png")}
        for f in dst.glob("*.png"):
            if f.name not in keep:
                f.unlink()
        n = 0
        for f in src.glob("*.png"):
            (dst / f.name).write_bytes(f.read_bytes())
            n += 1
        if n:
            print(f"\n▶ media\n   그림 {n}개 → web-react/public/media/")

    guard()
    run("check.py")                   # 정본 · 데이터 · 규칙 · 화면
    return 0


if __name__ == "__main__":
    sys.exit(main())
