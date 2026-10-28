import type { CSSProperties } from 'react'

/** Majesticons 에서 가져온 열둘과, 없어서 옮겨 그린 하나(train).
 *
 *  규칙 — 24 격자 · stroke-width 2 · 둥근 끝 · fill none · 여백 3px.
 *  자세한 대조는 docs/icons.html 에 있다.
 *
 *  시각 옆 종류 아이콘(식사·카페·온천…)은 걷어냈다 — 무엇을 하는지는 제목이
 *  이미 말하고, 항목마다 아이콘이 서면 제목의 시작선이 그만큼 밀린다.
 *  그때 함께 쓰이던 bed·utensils·onsen 도 자리를 잃었다.
 *
 *  색은 currentColor 를 따른다 — 부모의 글자색이 곧 아이콘 색이다.
 */
const PATHS: Record<string, string> = {
  // noteblock-text — 준비 화면
  prep: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 3v4m4 0V3m4 0v4m-8 4h8m-8 4h4m-6 6h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z"/>`,
  // bookmark — 잡아 둔 자리
  resv: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 3H7a2 2 0 0 0-2 2v15.138a.5.5 0 0 0 .748.434l5.26-3.005a2 2 0 0 1 1.984 0l5.26 3.006a.5.5 0 0 0 .748-.435V5a2 2 0 0 0-2-2z"/>`,
  // bookmark solid — 예약 표식
  resvOn: `<path fill="currentColor" fill-rule="evenodd" d="M7 2a3 3 0 0 0-3 3v15.138a1.5 1.5 0 0 0 2.244 1.303l5.26-3.006a1 1 0 0 1 .992 0l5.26 3.006A1.5 1.5 0 0 0 20 20.138V5a3 3 0 0 0-3-3H7z" clip-rule="evenodd"/>`,
  /* 맨 체크 표시. Majesticons 에는 없다 — 거기 체크는 늘 클립보드나 폴더
     안에 들어 있어, 목록 앞에 스물다섯 번 세우면 클립보드가 스물다섯 개로
     보인다. 그래서 그 팩의 규격을 따라 직접 그렸다:
     24 격자 · 획 2 · 둥근 끝과 이음. 옆에 서는 다른 아이콘과 무게가 맞는다. */
  tick: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m5 12.5 4.5 4.5L19 7"/>`,
  /* 채운 네모 안 흰 체크 — 「체크리스트에 적힌 것」이라는 표시다.
     맨 체크(tick)는 「했다」로 읽히므로 아직 안 한 것에는 못 쓴다.

     먹 면에 흰 체크, 획은 2 다. 눌러서 켜는 체크칸이 있던 시절의 비율을
     그대로 옮겼다 — 22px 칸에 8px 반경이었으니 24 격자에서는 rx 6 이다.

     한가운데에 선다. 네모는 3..21 이라 중심이 12,12 이고,
     체크는 x 7.8..16.2 · y 8.9..15.1 이라 중심이 꼭 같은 12,12 다.
     둥근 끝이 사방으로 1 씩 넓히지만 그것도 고르게 넓어져 중심은 그대로다.

     흰색은 --paper 를 style 로 참조한다. presentation attribute 에는
     var() 가 안 들어가고, #fff 로 박아 두면 바탕이 바뀔 때 따라오지 못한다. */
  checkbox: `<rect x="3" y="3" width="18" height="18" rx="6" fill="currentColor"/><path style="stroke:var(--paper)" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m7.8 12.2 2.9 2.9 5.5-6.2"/>`,
  // map-marker — 지도 버튼
  map: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 10c0 3.976-7 11-7 11s-7-7.024-7-11 3.134-7 7-7 7 3.024 7 7z"/><circle cx="12" cy="10" r="3" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>`,
  // open — 구글 지도로 나간다
  // 화살표만 — 네모 없는 대각선. 「여기서 밖으로 나간다」를 link 보다 조용히 말한다.
  // link(네모+화살표)는 딴 앱으로 건너간다는 뜻이 상호 이름 뒤에 붙어 서 있고,
  // 이쪽은 이미 「길 찾기」라 적혀 있어 그림이 말을 되풀이할 필요가 없다.
  //
  // 꼴은 Lucide arrow-up-right 를 따른다 — 화살촉의 두 팔이 대각선과 거의
  // 같은 길이라 닫힌 삼각으로 읽힌다. 팔을 6 으로 짧게 그렸던 때는
  // 「선 끝에 뭔가 붙은 것」이 됐고, 14px 에서는 획끼리 붙어 뭉갰다.
  //
  // 격자는 6→18 이다. Lucide 원본은 7→17 인데, 이 파일의 아이콘들은
  // close(6.5~17.5) · chevron(7~17) · tick(4.5~19) 처럼 그보다 넓게 쓴다 —
  // 원본 격자 그대로면 곁의 아이콘들 사이에서 혼자 작아 보였다.
  //
  // 팔은 11 이다. 12(대각선과 똑같이)로 두면 삼각이 완전히 닫혀 꼭짓점 셋이
  // 다 뾰족해진다. 한 눈금 물리면 왼쪽 아래가 열려, 획이 어디서 시작해
  // 어디로 가는지가 읽힌다 — 화살표는 방향을 말하는 그림이다.
  //
  // 획만 2.5 다. 이 파일에서 유일한 예외다 — 다른 아이콘은 저 혼자 서지만
  // 이것은 600 굵기 글자 옆에 나란히 눕는다. 14px 로 그리면 획 2 는 1.17px 이
  // 되는데, 13px/600 한글의 세로획이 1.5px 쯤이라 그림만 여위어 보였다.
  // 2.5 면 1.46px 으로 글자와 나란하다. 크기가 바뀌면 이 값도 다시 재야 한다.
  goto: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18 18 6M7 6h11v11"/>`,
  link: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4m-8-2 8-8m0 0v5m0-5h-5"/>`,
  /* 재생 — 날짜 줄 맨 앞, 전체 동선으로 나가는 링크.
     Majesticons 에 마땅한 것이 없어 팩의 규격대로 그렸다(24 격자 · 획 2 ·
     둥근 끝과 이음). 삼각형은 획으로 그린다 — 채우면 옆의 획 아이콘들
     사이에서 저만 무거워진다.
     멈춤 아이콘은 여기 없다. 그것은 동선 화면 안에서만 쓰이고, 그쪽은
     제 아이콘을 따로 갖는다(src/route/View.tsx). */
  play: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.5 5.8v12.4a1 1 0 0 0 1.53.85l9.7-6.2a1 1 0 0 0 0-1.7l-9.7-6.2a1 1 0 0 0-1.53.85z"/>`,
  // 닫기 — 떠 있는 단추가 켜졌을 때
  close: `<path stroke="currentColor" stroke-linecap="round" stroke-width="2" d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>`,
  // chevron-down
  chevron: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m17 10-5 5-5-5"/>`,
  // image — 안내도가 붙어 있다
  image: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v11m18-4v7a2 2 0 0 1-2 2h-3m5-9c-6.442 0-10.105 1.985-12.055 4.243M3 16v3a2 2 0 0 0 2 2v0h11M3 16c1.403-.234 3.637-.293 5.945.243M16 21c-1.704-2.768-4.427-4.148-7.055-4.757M8.5 7C8 7 7 7.3 7 8.5S8 10 8.5 10 10 9.7 10 8.5 9 7 8.5 7z"/>`,
  car: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m3 11 2.48-5.788A2 2 0 0 1 7.32 4h9.362a2 2 0 0 1 1.838 1.212L21 11M3 11h18M3 11v7m18-7v7m-3 0v.5a1.5 1.5 0 0 0 1.5 1.5v0a1.5 1.5 0 0 0 1.5-1.5V18m-3 0H6m12 0h3M6 18v.5A1.5 1.5 0 0 1 4.5 20v0A1.5 1.5 0 0 1 3 18.5V18m3 0H3m4-4h.001M17 14h.001"/>`,
  bus: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 19v0a2 2 0 0 1-2-2v-4m2 6v1.5a.5.5 0 0 0 .5.5v0a.5.5 0 0 0 .5-.5V19m-1 0h1m11 0v0a2 2 0 0 0 2-2v-4m-2 6v1.5a.5.5 0 0 1-.5.5v0a.5.5 0 0 1-.5-.5V19m1 0h-1M4 13V7m0 6h8m8 0V7m0 6h-8m-5 6h10M4 7v0a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v0M4 7h8m8 0h-8m0 0v6m-4 3h.001M16 16h.001"/>`,
  plane: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 9h5.5a2.5 2.5 0 0 1 2.5 2.5v0a2.5 2.5 0 0 1-2.5 2.5h-4.02a1 1 0 0 0-.78.375l-3.4 4.25a1 1 0 0 1-.78.375H9.476a1 1 0 0 1-.928-1.371l.902-2.258A1 1 0 0 0 8.523 14H4.659a1 1 0 0 1-.919-.606l-2.143-5A1 1 0 0 1 2.517 7h1.865a1 1 0 0 1 .894.553l.448.894A1 1 0 0 0 6.618 9H10m5 0-2.7-3.6a1 1 0 0 0-.8-.4H9.618a1 1 0 0 0-.894 1.447L10 9m5 0h-5"/>`,
  // Lucide 를 참고해 옮겨 그린 것
  train: `<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" fill="none" d="M8 4v3a4 4 0 0 0 8 0V4"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" fill="none" d="M9 19a5 5 0 0 1-5-5v-4a8 8 0 0 1 16 0v4a5 5 0 0 1-5 5z"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" fill="none" d="m9 15-1-1M15 15l1-1"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" fill="none" d="M9 19l-3 3M15 19l3 3"/>`,
}

/** 레이아웃을 보는 동안 모양을 지운다. 24 격자의 3px 여백을 그대로 지켜
 *  3~21 에 네모를 놓으므로, 실제 아이콘이 차지하던 자리와 크기가 같다.
 *  true 로 두면 네모가 나온다. */
const PLACEHOLDER = false
const BLOCK = '<rect x="3" y="3" width="18" height="18" rx="2" fill="currentColor"/>'

export type IconName = keyof typeof PATHS

type Props = {
  name: IconName
  size?: number
  className?: string
  style?: CSSProperties
}

/** 글줄 가운데에 서도록 display:block 으로 둔다.
 *  inline 이면 baseline 에 걸려 글자보다 아래로 처진다. */
export function Icon({ name, size = 16, className, style }: Props) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      className={className ? `ic ${className}` : 'ic'}
      style={{ display: 'block', flex: 'none', ...style }}
      aria-hidden
      dangerouslySetInnerHTML={{ __html: PLACEHOLDER ? BLOCK : PATHS[name] }}
    />
  )
}

/** 이동 수단 → 아이콘. 걷는 구간은 아이콘을 두지 않는다 —
 *  탈것이 아닌데 탈것 자리에 무언가를 세우면 그것도 수단으로 읽힌다. */
export const MODE_ICON: Record<string, IconName> = {
  car: 'car', bus: 'bus', train: 'train', plane: 'plane',
}
