# 도호쿠 여행 일정 앱

구글 시트에 적은 여행 계획을 일정과 지도로 보여 주는 웹앱. 2026년 9월 18일부터 10월 2일까지 15일간 여행에 썼다.

https://tohoku-2026-9pf.pages.dev

## 화면

- 일정: 날짜별 항목, 사이사이 이동(수단, 좌석, 소요 시간), 후보 장소의 영업시간과 지도 링크
- 지도: 목록에서 누른 장소를 지도에서 보여 주고, 길 안내는 구글 지도로 넘긴다
- 동선: 하루 또는 15일 전체 이동을 지도 위에서 재생
- 준비: 출발 전 챙길 것, 날짜별 할 일

## 구현

```
구글 시트 → pull_sheet.py → parse_trip.py → master.json
          → places_keys.py, places_lookup.py, links.py (좌표, 영업시간)
          → export_web.py → trip.json → React 앱
```

- 데이터는 Python 스크립트가 미리 만들고 앱은 `trip.json`만 읽는다. 순서는 `build.py`가 고정하고 `check.py`가 결과를 검사한다.
- 장소는 이름 대신 구글 ID로 맞춘다. 저장 목록 CSV의 URL에 든 장소 번호(CID)를 Places API의 placeId로 바꿔 일정과 잇는다(`saved_lists.py`).
- 동선의 길은 OSRM(OpenStreetMap 길찾기)에서 한 번 받아 `paths.json`에 넣어 두었다. 재생할 때 나가는 요청이 없다.
- 동선 화면의 구글 지도 코드는 `route/gmap.ts` 안에만 있다. 다른 지도로 바꾸려면 같은 꼴의 파일을 하나 더 쓴다.
- 시트로 못 고치는 예외는 `data/exceptions.json` 한 곳에 둔다.

React 18, TypeScript, Vite, Google Maps JavaScript API, Places API, Python, Cloudflare Pages

## 돌려 보기

### 데이터

- 일정: 구글 시트. 주소는 `tools/pull_sheet.py`의 `SHEET_ID`
- 구글 지도 저장 목록: Google Takeout CSV를 `data/saved/`에 넣는다(이름에 「일본」이 든 목록만 읽음)
- 장소 위치 고치기: 시트의 「길찾기」 줄에 구글 지도 공유 링크를 적는다
- 그 밖의 예외: `data/exceptions.json` (쓰는 법은 파일 맨 위 `_설명`)

### API 키

저장소에 없으니 직접 만든다.

`web-react/src/config.local.ts` (앱 지도)

```ts
export const GOOGLE_MAPS_API_KEY = "키"
export const GOOGLE_MAPS_MAP_ID = ""
```

`.env` (장소 조회 스크립트)

```
GOOGLE_PLACES_API_KEY=키
```

### 실행

```
cd web-react
npm install
npm run dev
```

### 데이터 다시 만들기

```
python tools/pull_sheet.py
python tools/build.py --reparse
python tools/build.py --lookup    # 새 장소 조회, Places API 요금 발생
```

`parse_trip.py`만 따로 돌리면 `fix_master.py`의 손수정이 사라진다. `build.py --reparse`로 돌린다.
