# 도호쿠 여행 일정 앱

2026-09-18~10-02 도호쿠 여행의 일정, 지도, 동선을 보는 웹앱이다. 여행이 끝나 보관 중이다.

- 배포: https://tohoku-2026-9pf.pages.dev
- 화면: React + Vite (`web-react/`)
- 데이터: 구글 시트가 정본이고 `tools/`의 Python 스크립트가 화면용 JSON으로 가공한다.

## 폴더

```
data/        정본(master.json)과 장소 캐시, 손으로 적는 예외
tools/       시트 → master.json → web-react/src/data/trip.json
web-react/   앱
docs/route-style.json   벡터 지도 Map ID에 붙일 지도 스타일
```

## 열쇠

저장소에 넣지 않는다. 직접 만든다.

`web-react/src/config.local.ts` (앱의 지도)

```ts
export const GOOGLE_MAPS_API_KEY = "..."
export const GOOGLE_MAPS_MAP_ID = ""   // 비우면 래스터 지도
```

`.env` (Places API 조회, `build.py --lookup`일 때만)

```
GOOGLE_PLACES_API_KEY=...
```

## 앱 실행

```
cd web-react
npm install
npm run dev      # http://localhost:5180
npm run build    # dist/
```

## 데이터 다시 만들기

```
python tools/build.py            # master.json → trip.json, 검사까지
python tools/pull_sheet.py       # 시트를 data/sheet.xlsx로 받는다
python tools/build.py --reparse  # 시트를 고쳤을 때. 위 pull_sheet 다음에
python tools/build.py --lookup   # 새 장소를 Places API로 조회 (유료)
```

`tools/parse_trip.py`를 따로 돌리지 않는다. `fix_master.py`의 손수정이 사라진다. 다시 뽑을 때는 `build.py --reparse`만 쓴다.

엑셀로 담을 수 없는 수정은 `data/exceptions.json`, 엑셀 이름과 구글 장소를 잇는 표는 `data/place_map.json`에 적는다. 두 파일의 `_설명`에 값의 뜻이 있다.
