# 도호쿠 여행 일정 앱

구글 시트에 적은 여행 계획을 날짜별 일정과 지도로 보여 주는 웹앱이다. 2026년 9월 18일부터 10월 2일까지 도호쿠 여행에 썼다.

배포 주소: https://tohoku-2026-9pf.pages.dev

## 데이터 넣기

일정은 구글 시트에 적는다. `tools/pull_sheet.py`가 시트를 `data/sheet.xlsx`로 받는다. 시트 주소를 바꾸려면 이 파일의 `SHEET_ID`를 고친다.

구글 지도에 저장한 장소 목록은 Google Takeout으로 내보낸 CSV를 `data/saved/`에 넣는다. 이름에 「일본」이 들어간 목록만 읽는다.

장소 위치를 바로잡고 싶으면 시트의 「길찾기」 줄에 구글 지도 공유 링크(`maps.app.goo.gl/…`)를 적는다.

시트로 고칠 수 없는 것은 `data/exceptions.json`에 적는다. 시트의 장소 이름과 저장 목록의 장소를 잇는 표는 `data/place_map.json`이다. 두 파일 맨 위의 `_설명`에 쓰는 법이 있다.

## API 키 넣기

키는 저장소에 올리지 않는다. 두 파일을 직접 만든다.

앱의 지도는 `web-react/src/config.local.ts`에서 키를 읽는다.

```ts
export const GOOGLE_MAPS_API_KEY = "키"
export const GOOGLE_MAPS_MAP_ID = ""   // 비워 두면 기본 지도
```

장소 좌표와 영업시간을 받아 오는 스크립트는 프로젝트 맨 위의 `.env`에서 키를 읽는다.

```
GOOGLE_PLACES_API_KEY=키
```

## 실행

```
cd web-react
npm install
npm run dev      # http://localhost:5180
npm run build    # dist/ 에 만든다
```

## 데이터 다시 만들기

시트를 고쳤으면 시트를 받고 다시 만든다.

```
python tools/pull_sheet.py
python tools/build.py --reparse
```

새 장소가 생겼으면 좌표와 영업시간을 받아 온다. Places API 요금이 나간다.

```
python tools/build.py --lookup
```

저장 목록 CSV를 새로 넣었으면 `python tools/places_lookup.py --saved`를 먼저 돌린다. 이것도 요금이 나간다.

`tools/parse_trip.py`는 따로 돌리지 않는다. 손으로 고친 내용이 사라진다. 다시 만들 때는 `build.py --reparse`만 쓴다.
