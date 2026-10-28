# trip: 도호쿠 여행 일정 앱

2026-09-18~10-02 도호쿠 여행 일정 앱. React + Vite(`web-react\`), 데이터는 구글 시트가 정본이고 `tools\`의 Python 스크립트가 가공한다. 배포: https://tohoku-2026-9pf.pages.dev. 상태: 보관(여행 끝남). 다시 열면 상태부터 확인한다. git 저장소(로컬, 원격 없음). 디자인 작업대(`docs\` 대부분, 문서 생성 도구)는 `.gitignore`로 뺐다.

- `tools\parse_trip.py`를 단독으로 돌리지 않는다. `fix_master.py`의 손수정이 사라진다. 데이터를 다시 만들 때는 `python tools\build.py --reparse`만 쓴다.
- 데이터 흐름, 금액 출처, 색과 화면 원칙은 이 프로젝트 메모리에 있다.
