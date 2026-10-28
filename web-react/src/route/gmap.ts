import { GOOGLE_MAPS_API_KEY, GOOGLE_MAPS_MAP_ID } from '../config.local'
import type { Canvas, Mount, Pad } from './canvas'
import { km, type LatLng } from './plan'

/* Canvas 를 구글 지도로 구현한다.
 *
 *  이 파일 밖으로 google.maps 가 새지 않는다. 화면은 canvas.ts 의 다섯 가지만
 *  알고, 그것을 무엇으로 그리는지는 여기서 끝난다 — 지도를 갈아끼우려면
 *  이 파일과 같은 꼴로 하나 더 쓰고 View 의 import 를 돌리면 된다.
 *
 *  나누어 쓰는 것은 열쇠(config.local.ts)뿐이다. 코드가 아니라 자격증명이라
 *  두 벌로 두면 한쪽만 바뀌어 어긋난다.
 */

/** 가게 아이콘만 걷는다. 색은 건드리지 않는다.
 *
 *  한때 바탕과 물과 도로까지 회색으로 눌러 두었는데, 그것은 시킨 적 없는
 *  일이었다 — 일정 화면이 흑백이라 여기도 그래야 한다고 여긴 탓이다.
 *  이 화면은 지나온 자취를 보는 자리이고, 그 아래 지도가 무슨 색이냐는
 *  선이 읽히는 한 상관이 없다. 구글이 칠한 대로 둔다.
 *
 *  끄는 것은 가게·명소의 아이콘과 이름뿐이다. 그 자리는 우리가 지나온 길을
 *  보는 자리라, 구글이 고른 가게가 같이 서면 무엇을 보라는 것인지 흐려진다.
 *
 *  벡터로 그릴 때는 이것이 쓰이지 않는다 — Map ID 를 붙이면 클라우드 쪽
 *  스타일이 대신 선다. 래스터로 물러섰을 때의 몫이다. */
const BARE: google.maps.MapTypeStyle[] = [
  { featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] },
]

/* 스크립트는 한 번만 받는다.
 *
 *  일정 화면(components/Map.tsx)도 제 로더를 갖고 있다 — 소스를 갈라 둔
 *  대가다. 그쪽이 스크립트를 받고 있는 동안 이 화면을 열면 window.google 이
 *  아직 없어, 여기서 두 번째 <script> 를 꽂게 된다. 구글 지도를 두 번
 *  올리면 타일이 깨지고 콘솔에 「included multiple times」가 뜬다.
 *
 *  그래서 붙이기 전에 남이 이미 부르고 있는지 본다. 있으면 올 때까지
 *  기다리기만 한다 — 콜백 이름이 달라 그쪽 콜백을 가로챌 수는 없으므로,
 *  전역에 지도가 생겼는지를 짧은 사이로 살핀다. */
const SRC = 'maps.googleapis.com/maps/api/js'
let loading: Promise<void> | null = null
function loadMaps() {
  if (loading) return loading
  loading = new Promise<void>((res, rej) => {
    if (!GOOGLE_MAPS_API_KEY) return rej(new Error('no key'))
    if (window.google?.maps) return res()
    if (document.querySelector(`script[src*="${SRC}"]`)) {
      const t = setInterval(() => {
        if (!window.google?.maps) return
        clearInterval(t)
        res()
      }, 40)
      setTimeout(() => {
        clearInterval(t)
        if (!window.google?.maps) rej(new Error('load timeout'))
      }, 20000)
      return
    }
    const s = document.createElement('script')
    s.src = `https://maps.googleapis.com/maps/api/js?key=${GOOGLE_MAPS_API_KEY}&language=ko&region=JP&loading=async&callback=__routeMapReady`
    s.async = true
    ;(window as any).__routeMapReady = () => res()
    s.onerror = () => rej(new Error('load failed'))
    document.head.appendChild(s)
  })
  return loading
}

/** 화면의 색을 CSS 에서 꺼내 온다. 선은 캔버스에 그려지므로 var() 가 닿지
 *  않는다 — 여기에 값을 적어 두면 화면과 갈라진다. */
/** 이 화면의 색을 꺼낸다.
 *
 *  받는 것은 지도가 들어앉은 엘리먼트다. :root 에서 읽으면 안 된다 —
 *  이 화면의 색은 .routeview 에 매달려 있고(style.css), :root 에는 일정 앱의
 *  같은 이름이 다른 값으로 산다. 한동안 사람 아이콘이 제 먹빛(#1f1f1f)이
 *  아니라 일정 앱의 것(#191f28)으로 그려지고 있었다. 값이 비슷해 눈에 띄지
 *  않았을 뿐, 갈라 둔 소스가 새고 있던 자리다.
 *
 *  el 은 .routeview 의 자식이므로 커스텀 속성이 상속으로 내려온다.
 *
 *  못 읽으면 검정이다. 여기에 진짜 색을 적어 두면 style.css 와 두 벌이
 *  되어 한쪽만 고쳤을 때 조용히 갈라진다 — 색의 정본은 CSS 한 곳이다.
 *  검정으로 떨어지면 무언가 잘못되었다는 것이 화면에 그대로 드러난다. */
const cssOf = (el: HTMLElement) => (name: string) =>
  getComputedStyle(el).getPropertyValue(name).trim() || '#000'

/* ── 걷는 사람 ─────────────────────────────────────────
   Phosphor 의 person-simple-walk(fill). 256 격자다.

   선과 같은 길로 그린다. 마커도 선도 지도가 제 캔버스에 함께 그리므로
   한 프레임도 어긋나지 않는다 — 사람을 DOM 으로 화면에 못 박아 두었을
   때는 지도가 늦게 그려지는 프레임마다 사람만 앞서 나가 선을 벗어났다.

   라벨만 화면에 남는다. 글자는 선 위에 있을 까닭이 없고, 사람이 한가운데
   서므로 그 위에 붙박아 두면 그만이다. */
const WALK_BOX = '0 0 256 256'
const WALK_D = 'M120,48a32,32,0,1,1,32,32A32,32,0,0,1,120,48Zm88,88c-28.64,0-41.81-13.3-55.75-27.37-3.53-3.57-7.18-7.26-11-10.58-37-32.14-96.22,22.73-98.72,25.08a8,8,0,0,0,10.95,11.66A163.88,163.88,0,0,1,84,113c13.78-7.38,25.39-10.23,34.7-8.58L64.66,228.81a8,8,0,0,0,4.15,10.52A7.84,7.84,0,0,0,72,240a8,8,0,0,0,7.34-4.81l33.59-77.27L144,180.12V232a8,8,0,0,0,16,0V176a8,8,0,0,0-3.35-6.51l-37.2-26.57L132.88,112c2.64,2.44,5.26,5.07,8,7.84C155.05,134.19,172.69,152,208,152a8,8,0,0,0,0-16Z'

const DOT = 28               // 사람이 서는 원의 지름
const GLYPH = 15             // 그 안의 글리프
const SHADOW_PAD = 6         // 그림자가 잘리지 않게 두르는 여유
const ICON_BOX = DOT + SHADOW_PAD * 2

/* 올린 그림은 따로 잰다.
   기본꼴의 상자를 그대로 쓰던 때는 그림이 상자를 꽉 채워, 둘레의 흰 후광이
   갈 데가 없어 네모로 잘렸다 — 필터는 그려지는 판(SVG) 밖으로 못 나간다.
   그림 크기는 그대로 두고 상자만 키운다. 후광이 가장 멀리 번지는 것이
   stdDeviation 3(≈9px)이라 열 몫이면 잘리지 않는다. */
const SKIN = 40              // 그림 자체의 크기
const SKIN_PAD = 10          // 후광이 번질 자리
const SKIN_BOX = SKIN + SKIN_PAD * 2

/** 사람 아이콘을 데이터 URI 로 그린다.
 *
 *  AdvancedMarkerElement 로도, 화면에 못 박은 DOM 으로도 해 보았다.
 *  앞엣것은 라이브러리를 따로 받아야 해 화면에 뜨지 않았고, 뒤엣것은
 *  카메라가 여유를 두고 따라가게 되면서 쓸 수 없게 되었다 — 사람이 늘
 *  한가운데 있는 것이 아니기 때문이다. 지도 위에 얹는 마커가 맞다.
 *
 *  마커의 그림은 이미지라 CSS 가 닿지 않는다. 색을 여기 적어 두면 화면과
 *  갈라지므로 그릴 때 꺼내 온다. */
const PILL_H = 22            // 이름표 알약의 키
const TAIL_H = 5             // 말풍선 꼬리의 길이
const TAIL_W = 10            // 그 밑변
const PILL_GAP = 3           // 꼬리 끝과 사람 사이
const PILL_PAD = 9           // 알약 좌우 안쪽 여백
const PILL_FS = 12           // 이름표 글자 크기

/** 이름표의 글자 폭을 어림한다.
 *
 *  캔버스로 재면 정확하지만, 이 그림은 <img> 로 실려 나가므로 잴 자리가
 *  없다. 12px 600 에서 한글은 글자만큼(12), 라틴·숫자는 그 절반 남짓(6.8)이다.
 *  넘치게 잡는 편이 낫다 — 모자라면 글자가 알약 밖으로 나간다. */
const textWidth = (s: string) =>
  [...s].reduce((n, ch) => n + (ch.charCodeAt(0) < 128 ? 6.8 : PILL_FS), 0)

/** 사람과 이름표를 한 장으로 그린다.
 *
 *  이름표를 따로 띄우지 않는다. 화면 위쪽에 붙박아 두었을 때는 사람이
 *  어디를 지나든 글자가 한자리에 서 있어, 지금 그 이름이 누구를 가리키는지
 *  눈으로 이어야 했다. 한 장으로 그리면 어긋날 자리가 없다.
 *
 *  @return 그림과 그 크기, 그리고 사람의 발이 놓일 자리(anchor).
 *          이름표가 길수록 그림이 넓어지므로 앵커도 함께 옮겨 간다. */
function walkerIcon(ink: string, paper: string, label?: string,
                    src?: string | null) {
  const top = label ? PILL_H + TAIL_H + PILL_GAP : 0   // 이름표가 차지하는 높이
  const pillW = label ? textWidth(label) + PILL_PAD * 2 : 0
  const box = src ? SKIN_BOX : ICON_BOX
  const w = Math.max(box, Math.ceil(pillW))
  const h = top + box
  const cx = w / 2
  const cy = top + ICON_BOX / 2                    // 사람 원의 한가운데
  const g = GLYPH / 2
  const svg = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"`,
    ` viewBox="0 0 ${w} ${h}">`,
    '<filter id="s" x="-40%" y="-40%" width="180%" height="180%">',
    '<feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000" flood-opacity=".24"/>',
    '<feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000" flood-opacity=".16"/>',
    '</filter>',
    /* 올린 그림에 두르는 흰 후광.
       그림마다 색이 제각각이라 어떤 것은 짙은 지붕 위에서, 어떤 것은 흰
       건물 위에서 묻힌다. 흰빛을 사방으로 번지게 하면 어느 바탕에서도
       테두리가 살아난다 — 밝은 바탕에서는 후광이 안 보일 뿐이고,
       어두운 바탕에서는 그림을 도려낸 듯 떼어 놓는다.

       feDropShadow 는 알파를 따라 번진다. 그래서 누끼 딴 그림의 투명한
       자리에는 아무것도 생기지 않는다 — 네모난 얼룩을 걱정할 일이 없다.
       세 겹으로 겹치는 까닭은 한 겹으로는 옅어 검은 지붕 위에서 사라지기
       때문이다. 마지막 한 겹만 아래로 1px 내려 바닥에 닿은 느낌을 준다. */
    '<filter id="w" x="-50%" y="-50%" width="200%" height="200%">',
    '<feDropShadow dx="0" dy="0" stdDeviation="1.2" flood-color="#fff" flood-opacity="1"/>',
    '<feDropShadow dx="0" dy="0" stdDeviation="2" flood-color="#fff" flood-opacity=".9"/>',
    '<feDropShadow dx="0" dy="1" stdDeviation="3" flood-color="#fff" flood-opacity=".7"/>',
    '</filter>',
    /* 이름표 — 흰 바탕에 먹글씨. 지도가 밝으므로 흰쪽이 배경에서 떨어진다.

       알약과 꼬리를 한 무리(g)에 담고 그림자는 그 무리에 건다. 따로 걸면
       둘이 맞닿는 자리에 서로의 그림자가 얹혀 없는 선이 보인다. */
    label
      ? `<g filter="url(#s)"><rect x="${(w - pillW) / 2}" y="0" width="${pillW}"`
        + ` height="${PILL_H}" rx="${PILL_H / 2}" fill="${paper}"/>`
        + `<path d="M${cx - TAIL_W / 2} ${PILL_H - 1}`
        + `L${cx} ${PILL_H + TAIL_H}L${cx + TAIL_W / 2} ${PILL_H - 1}Z"`
        + ` fill="${paper}"/></g>`
        + `<text x="${cx}" y="${PILL_H / 2}" fill="${ink}"`
        + ` font-family="system-ui,-apple-system,'Malgun Gothic',sans-serif"`
        + ` font-size="${PILL_FS}" font-weight="600" letter-spacing="-.2"`
        + ` text-anchor="middle" dominant-baseline="central">${esc(label)}</text>`
      : '',
    /* 고른 그림이 있으면 원을 그리지 않고 그것을 그대로 앉힌다.
       누끼 딴 PNG 를 원 안에 가두면 그 그림의 꼴이 사라지므로 자르지 않는다.

       xMidYMax 로 아래 가운데를 맞춘다 — 가로로 긴 그림이든 세로로 긴
       그림이든 발이 놓일 자리가 한결같아야 선 위를 걷는 것으로 보인다.
       흰 후광(#w)을 두른다 — 위의 필터에 까닭을 적어 두었다. */
    src
      ? `<image x="${cx - SKIN / 2}" y="${top + SKIN_PAD}" width="${SKIN}"`
        + ` height="${SKIN}" preserveAspectRatio="xMidYMax meet"`
        + ` filter="url(#w)" href="${esc(src)}"/>`
      : `<circle cx="${cx}" cy="${cy}" r="${DOT / 2}" fill="${ink}" filter="url(#s)"/>`
        + `<svg x="${cx - g}" y="${cy - g}" width="${GLYPH}" height="${GLYPH}"`
        + ` viewBox="${WALK_BOX}" fill="${paper}"><path d="${WALK_D}"/></svg>`,
    '</svg>',
  ].join('')
  return {
    url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
    w, h,
    ax: cx,
    // 기본꼴은 원의 한가운데가 발이지만, 올린 그림은 아래끝이 발이다.
    // 후광이 번질 자리(SKIN_PAD)만 빼고 바닥에 세운다.
    ay: src ? h - SKIN_PAD : cy,
  }
}

/** 이름에 &, <, > 가 들어와도 그림이 깨지지 않게 한다 */
const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/* ── 카메라 ────────────────────────────────────────────
   한 화면에 여러 구간을 담고, 그것을 다 지날 때까지 서 있는다.
   사람만 그 안을 걷는다.

   프레임마다 중심을 사람에게 밀던 때는 구간 하나가 늘 화면에 꽉 차서,
   0.6초에 화면 한 폭이 흐르는 꼴이었다(초당 화면의 167%). 지도가 타일을
   받아 올 수 있는 속도가 아니었고, 사람이 한가운데 붙박여 있으니 걷는
   것으로 보이지도 않았다. */

/** 래스터로 그릴 때 배율을 끊는 눈금.
 *
 *  담을 폭이 조금이라도 달라질 때마다 setZoom 을 불렀더니 초당 열두 번이
 *  되었다. 래스터에서 setZoom 은 가진 타일을 늘려 그린 뒤 새 배율의 타일이
 *  오면 다시 그리는 일이라, 그 열두 번이 지도의 힘을 다 먹었다 —
 *  사람을 따라오지 못하고 크기만 툭툭 바뀐 것이 그 탓이다.
 *
 *  0.25 로 끊으면 초당 네 번으로 준다. 배율 0.25 는 크기로 4% 차이라
 *  한 걸음 사이에 알아채지 못한다.
 *
 *  벡터로 그릴 때는 끊지 않는다(0). 벡터는 도형을 GPU 가 그리므로 배율
 *  사이라는 것이 없고, 연속으로 흘려야 줌이 바뀌는 것이 보인다. */
const ZOOM_STEP = 0.25

/* 사람이 화면 한가운데에서 이만큼 안에 있으면 카메라는 가만있는다.
 *
 *  화면 짧은 쪽에 담는 거리(spanKm)에 대한 비율이다. 벗어난 만큼만 밀므로
 *  사람은 늘 이 테두리에 붙어 간다 — 그래서 이 값이 곧 「얼마나 뒤처져
 *  보이는가」다.
 *
 *  **한 값으로는 안 된다.**
 *
 *  0.16(지름 32%)으로 두었을 때는 동네를 걷는 동안에도 지도가 따라 흔들렸다.
 *  0.3 으로 넓히니 그 흔들림은 멎었지만, 이번에는 먼 이동에서 사람이 화면
 *  30% 지점에 계속 붙어 가 「따라가는 게 느리다」가 되었다.
 *
 *  같은 값이 가까운 걸음에는 넉넉함이고 먼 이동에는 뒤처짐인 것이다.
 *  그래서 담을 폭에 따라 옮겨 간다 — 폭이 넓다는 것은 곧 멀리 간다는 뜻이라
 *  따로 물어볼 것이 없다.
 *
 *      폭 5km 이하  → 0.35 (지름 70%)  동네를 걷는 동안 지도는 서 있고
 *      폭 30km 이상 → 0.05 (지름 10%)  사람이 한가운데를 지킨다
 *
 *  그 사이는 곧게 잇는다. 먼 구간에서 사람이 한가운데서 벗어난 몫이
 *  24% 에서 7% 로 줄고, 가까운 구간은 23% 그대로다. */
/** 서 있는 동안 가운데로 되돌아오는 몫(프레임마다).
 *
 *  먼 이동 중에는 테두리가 좁아(DEAD_FAR) 사람이 한가운데 있는데, 닿는
 *  순간 테두리가 넓어지므로(DEAD_NEAR) 치우친 채로 그 안에 들어간다.
 *  카메라는 「테두리 안」이라 가만있고, 그 치우침이 그대로 굳는다 —
 *  도쿄역과 자오 온천에서 사람이 오른쪽에 붙어 있던 까닭이다.
 *
 *  서 있는 동안에만 가운데로 민다. 그때 카메라는 달리 할 일이 없고,
 *  다시 떠날 때 한가운데에서 출발하게 된다. 3% 면 자오에서 사람이 가운데를
 *  벗어난 몫이 내내 31% 에서 8% 로, 도쿄에서 28% 에서 16% 로 준다.
 *
 *  테두리를 좁히는 길도 있었지만 그쪽은 한 프레임에 경계까지 당겨 급하다. */
const CENTER_EASE = 0.03

const DEAD_NEAR = 0.35       // 가까운 걸음일 때
const DEAD_FAR = 0.05        // 먼 이동일 때
const DEAD_FROM = 5          // 이 폭(km)까지는 DEAD_NEAR
const DEAD_TO = 30           // 이 폭(km)부터는 DEAD_FAR

/** 담을 폭에 맞는 고정 범위(폭에 대한 비율). */
const deadFor = (spanKm: number) => {
  const k = Math.max(0, Math.min(1, (spanKm - DEAD_FROM) / (DEAD_TO - DEAD_FROM)))
  return DEAD_NEAR + (DEAD_FAR - DEAD_NEAR) * k
}

/* 배율에도 여유를 둔다.
 *
 *  담을 폭이 조금 달라질 때마다 배율을 고쳐 잡으면 걸음마다 깔짝거린다 —
 *  니가타에서 한 번 좁혀 든 뒤로는 그 화면 안에서 오가는 동안 배율을
 *  건드릴 까닭이 없다.
 *
 *  그래서 두 문턱을 둔다. 지금 배율로는 담기지 않을 만큼 넓어져야(WIDEN)
 *  물러서고, 한참 좁혀도 될 만큼 작아져야(TIGHTEN) 다가간다. 그 사이는
 *  그대로 둔다.
 *
 *  1.18/0.65 는 좁았다. 백쉰아홉 초 동안 사백세 번을 갈아 잡았으니 초당
 *  두 번 반이다 — 한 프레임씩 보면 매끄럽지만(뚝뚝 2), 통째로 보면 배율이
 *  쉬지 않고 오르내려 정신이 사납다.
 *
 *  3/0.3 으로 넓힌다. 세 배 넓어지거나 삼분의 일로 줄어야 갈아 잡으니
 *  일흔여덟 번으로 준다. 웬만한 걸음은 배율을 건드리지 않고 지나가고,
 *  정말 멀리 갈 때만 크게 물러선다 — 「멀리 갈 때만 많이」가 이것이다.
 *
 *  더 넓히면(4/0.25) 쉰한 번까지 주는 대신 자오 온천에서 못 당긴다
 *  (14.8 → 13.7). 하루가 1km 안에서 끝나는 날은 문턱을 넘을 일이 없어
 *  넓은 채로 남기 때문이다. */
const WIDEN = 3              // 지금 폭의 이만큼을 넘으면 물러선다
const TIGHTEN = 0.3         // 지금 폭의 이만큼 아래로 내려가야 다가간다

/** 배율의 위쪽 한계.
 *
 *  벡터라도 배율이 높을수록 받아 올 것이 많다 — 14 를 넘으면 건물 하나하나가
 *  그려지기 시작해, 사람이 그 배율에서 쉬지 않고 움직이면 버거워진다.
 *  한때 이것이 빠진 채로 14.1 까지 올라가 버벅였다.
 *
 *  14.3 은 폭 1.8km 남짓 — 도쿄나 니가타의 골목 걸음이 화면에 차면서도,
 *  건물 이름이 뜨기 시작하는 15 까지는 가지 않는 자리다.
 *  다시 버벅이면 여기부터 내린다(13.8 이 앞서 멀쩡했던 값이다). */
const MAX_ZOOM = 15

/** 보이는 배율이 목표로 다가가는 몫. 프레임마다 남은 만큼의 이만큼을 좁힌다.
 *
 *  붙들기(WIDEN·TIGHTEN)만 두었더니 배율이 계단처럼 튀었다 — 문턱을 넘는
 *  순간 목표가 확 달라지는데 그리로 곧바로 뛰었기 때문이다. 「뚝뚝」이
 *  그것이었다.
 *
 *  목표는 뜸하게 바꾸되(깔짝거리지 않게), 그리로 가는 길은 매끄럽게 둔다.
 *  0.05 면 남은 거리의 5% 씩이라 한 배가 되는 데 1초쯤 걸린다. */
const ZOOM_EASE = 0.02
/* 배율이 초당 이보다 빨리 바뀌지 않는다(단/초).
 *
 *  당기는 쪽과 물러서는 쪽을 가른다. 두 일은 성질이 다르다 —
 *  급히 물러서면 발밑이 꺼지듯 어지럽지만, 닿았을 때 빨리 당기는 것은
 *  오히려 시원하다.
 *
 *  한 값(0.4)으로 묶었더니 니가타에 닿고 시내가 보이기까지 열한 초가
 *  걸렸다. 하늘길의 배율 5 에서 시내의 14 까지 아홉 단을 초당 0.4 로
 *  좁히니 그렇다. 당기는 쪽을 1.5 로 올리면 2.5초다.
 *
 *  물러서는 쪽은 0.4 그대로다. 그쪽을 함께 올리면 가까운 걸음과 먼 이동이
 *  섞인 날(9/21)의 배율이 다시 요동친다. */
const ZOOM_IN_RATE = 1.5     // 당길 때
const ZOOM_OUT_RATE = 0.4    // 물러설 때

/** 웹 머카토르에서 줌 0 의 적도 한 픽셀이 덮는 거리(m). 배율 셈의 밑동이다. */
const M_PER_PX_0 = 156543.03392

/** 미리 훑을 때 한 화면에 머무는 시간.
 *
 *  타일이 다 오기를 기다리지 않는다 — 부르기만 시키고 넘어간다. 스물한
 *  화면이면 3초 남짓이고, 그 사이 받은 것은 곳간에 남아 재생 때 쓰인다. */
const WARM_MS = 150

const bounds = (pts: LatLng[]) => {
  const b = new google.maps.LatLngBounds()
  for (const p of pts) b.extend(p)
  return b
}

export const mount: Mount = async (el: HTMLElement): Promise<Canvas> => {
  const css = cssOf(el)
  await loadMaps()

  /* Map ID 가 있으면 벡터 지도로 그린다.
   *
   *  래스터는 배율마다 다른 그림을 내려받아 붙이므로, 카메라가 사람을 따라
   *  쉬지 않고 움직이면 받아 오는 쪽이 못 따라온다. 벡터는 도형을 GPU 가
   *  그려 팬도 줌도 끊기지 않는다.
   *
   *  Map ID 를 붙이면 아래 styles 는 무시된다 — 그때는 클라우드 쪽 스타일이
   *  대신 서고, 지금 쓰는 것과 같은 규칙을 docs/route-style.json 에 뽑아 두었다.
   *  비워 두면 지금까지처럼 래스터로 그린다. */
  const vector = !!GOOGLE_MAPS_MAP_ID
  const m = new google.maps.Map(el, {
    center: { lat: 38.5, lng: 139.8 },
    zoom: 6,
    ...(vector ? { mapId: GOOGLE_MAPS_MAP_ID } : { styles: BARE }),
    disableDefaultUI: true,
    /* 손으로 밀 수 있다. 사람이 지도 위에 있으므로 어디로 밀든 제 자리를
       가리키고, 재생 중이면 다음 프레임에 카메라가 도로 데려온다.
       사람을 화면에 못 박아 두었을 때는 이것을 막아야 했다 — 지도만 옮기면
       사람이 있지도 않은 자리를 가리켰기 때문이다. */
    gestureHandling: 'greedy',
    clickableIcons: false,
    /* 배율을 소수로 잡을 수 있게 켠다. 화면마다 담을 것에 꼭 맞추려면
       13 과 14 사이의 어디쯤이 필요하고, 정수로만 잡으면 그때마다 화면이
       남거나 넘친다. 사이를 흐르지는 않으므로(컷) 타일을 겹쳐 부르지 않는다. */
    isFractionalZoomEnabled: true,
    /* 벡터 지도는 기울이고 돌릴 수 있다. 여기서는 그러면 안 된다 —
       위에서 내려다본 한 장이라야 지나온 선의 모양이 그대로 읽힌다.
       손가락 둘로 비틀어 기울어지는 일이 없게 못 박아 둔다. */
    tilt: 0,
    heading: 0,
  })

  /* 사람은 선과 같은 길로 그린다(아래 walker). 라벨만 화면에 붙는다 —
     글자는 선 위에 있을 까닭이 없고, 사람이 한가운데 서므로 그 위에
     붙박아 두면 그만이다. */
  /* 사람은 지도 위에 얹는다. 카메라가 여유를 두고 따라가므로 사람이 늘
     한가운데 있는 것이 아니고, 그러니 지도의 좌표를 가져야 한다 —
     선과 같은 자리에 있어야 벗어나지도 않는다. */
  let who: google.maps.Marker | null = null
  /** 이미 지난 구간들 — 구간이 넘어갈 때만 다시 긋는다 */
  let doneLine: google.maps.Polyline | null = null
  /** 지금 지나는 구간 — 프레임마다 갈아 끼우지만 짧다 */
  let trailLine: google.maps.Polyline | null = null
  /** 지난 길의 점 수. 이것이 바뀔 때만 doneLine 을 손댄다 */
  let doneLen = -1
  /** 지금 붙어 있는 라벨. 바뀔 때만 손댄다 */
  let tagged: string | undefined
  /** 사람이 고른 그림(setWalker). null 이면 기본꼴이다 */
  let skin: string | null = null
  /** 마커에 실제로 박혀 있는 그림. skin 과 어긋날 때만 다시 그린다 */
  let inked: string | null = null
  /** 마지막으로 잡은 배율. 눈금이 달라질 때만 setZoom 을 부른다 */
  let lastZoom = -1
  /** 앞 프레임의 사람 자리. 서 있는지 가려내는 데 쓴다 */
  let lastAt: LatLng | null = null
  /** 붙들고 있는 담을 폭(km). 문턱을 넘을 때만 갈아 잡는다 */
  let held = -1

  /** 이만큼(km)을 화면의 짧은 쪽에 담는 배율.
   *
   *  머카토르에서 한 픽셀이 덮는 거리는 위도의 코사인만큼 줄어든다 —
   *  같은 배율이라도 아오모리(40°)가 도쿄(35°)보다 좁게 담긴다. */
  const shortSide = () =>
    Math.max(120, Math.min(el.clientWidth, el.clientHeight) || 320)

  const zoomFor = (spanKm: number, lat: number) => {
    const mPerPx = (spanKm * 1000) / shortSide()
    return Math.log2((M_PER_PX_0 * Math.cos((lat * Math.PI) / 180)) / mPerPx)
  }

  /** 그 배율에서 화면 짧은 쪽에 실제로 담기는 거리(km). zoomFor 의 반대다. */
  const spanOf = (zoom: number, lat: number) =>
    (M_PER_PX_0 * Math.cos((lat * Math.PI) / 180) / Math.pow(2, zoom))
    * shortSide() / 1000

  /** 새 그림으로 갈아 끼운다. **다 받아진 뒤에** 바꾼다.
   *
   *  setIcon 은 주소만 건네고 끝난다. 그 그림을 받아 그리는 일은 지도가
   *  나중에 하므로, 받는 동안에는 옛 그림이 그대로 서 있다. 서 있던 화면이
   *  다시 그려지는 때가 마침 재생을 누른 순간이라 — 날짜를 옮겨 두고
   *  재생하면 직전 이름표가 한 번 스쳐 보였다.
   *
   *  data: 주소라 받는 데 한 박자도 안 걸린다. 그 한 박자를 기다렸다가
   *  바꾸면 옛 그림이 비칠 틈이 없다. 못 받으면(onerror) 그냥 바꾼다 —
   *  이름표가 없는 것보다는 낫다. */
  const wear = (icon: google.maps.Icon, url: string) => {
    if (!who) return
    const put = () => who?.setIcon(icon)
    const im = new Image()
    im.onload = put
    im.onerror = put
    im.src = url
  }

  return {
    follow(at: LatLng, spanKm: number) {
      /* 여유를 두고 따라간다.
       *
       *  사람이 화면 가운데 언저리(deadFor 가 정하는 반경) 안에 있으면
       *  카메라는 가만있고, 그 선을 넘어서면 넘은 만큼만 밀려 따라간다 —
       *  사람이 그 테두리에 붙어 가는 꼴이다.
       *
       *  그 반경은 담을 폭을 따라 옮겨 간다. 동네를 걸을 때는 넓어서 지도가
       *  서 있고, 먼 데를 갈 때는 좁아서 사람이 한가운데를 지킨다 — 같은
       *  값을 두 자리에 쓰면 한쪽은 흔들리고 다른 쪽은 뒤처진다.
       *
       *  프레임마다 한가운데로 끌어당기던 때는 지도가 쉴 참이 없었다.
       *
       *  카메라는 한 몸짓으로 옮긴다. 중심과 배율을 따로 밀면 두 갱신 사이에
       *  중심만 옮겨진 어중간한 프레임이 끼어 깜빡인다. */
      /* 담을 폭을 붙들고 있다가 문턱을 넘을 때만 갈아 잡는다. 그 사이에는
         화면이 조금 넉넉하거나 조금 빡빡할 뿐, 목표는 가만있는다. */
      if (held < 0 || spanKm > held * WIDEN || spanKm < held * TIGHTEN) {
        held = spanKm
      }
      const want = Math.min(zoomFor(held, at.lat), MAX_ZOOM)

      /* 보이는 배율은 그 목표로 조금씩 다가간다. 목표가 뜸하게 바뀌므로
         깔짝거리지 않고, 다가가는 길이 매끄러우므로 뚝뚝 끊기지도 않는다. */
      if (lastZoom < 0) lastZoom = want
      const gap = want - lastZoom
      const zoomed = Math.abs(gap) > 0.004
      if (zoomed) {
        /* 다가가는 몫만으로는 급할 때가 있다.
         *
         *  목표가 세 단쯤 떨어져 있으면 그 2% 라도 한 프레임에 0.06 단이라,
         *  초당 네 단이 넘게 바뀐다 — 1초에 화면이 열여섯 배로 벌어지는
         *  꼴이라 무라카미처럼 가까운 걸음과 먼 이동이 섞인 날에는 배율이
         *  요동치는 것으로 보인다.
         *
         *  배율이 오가는 것 자체는 어쩔 수 없다(그 날은 2.5km 와 49.5km 가
         *  한 줄에 있다). 그러나 얼마나 빨리 오가는지는 정할 수 있다.
         *  초당 0.4 단으로 묶으면 같은 폭을 지나도 눈이 따라간다
         *  (9/21 의 배율 폭 3.1 → 2.0). */
        // gap 이 양수면 배율을 올려야 한다 — 당기는 쪽이다
        const cap = (gap > 0 ? ZOOM_IN_RATE : ZOOM_OUT_RATE) / 60
        lastZoom += Math.max(-cap, Math.min(cap, gap * ZOOM_EASE))
      }
      /* 래스터는 눈금에 걸릴 때만 넘긴다 — 배율마다 다른 그림을 받아야 해서
         연속으로 흘리면 받아 오는 일이 그치지 않는다. */
      const z = vector ? lastZoom : Math.round(lastZoom / ZOOM_STEP) * ZOOM_STEP

      const c = m.getCenter()
      if (!c) return void m.moveCamera({ center: at, zoom: z, tilt: 0, heading: 0 })

      const cur = { lat: c.lat(), lng: c.lng() }
      /* 자는 「담으려는 폭」이 아니라 「지금 담긴 폭」이다.
       *
       *  겨눈 폭으로 재던 때는 사람이 한가운데서 74% 까지 밀려 화면 밖으로
       *  나갔다. 배율은 목표를 향해 천천히 다가가므로(ZOOM_EASE) 그 사이
       *  화면은 아직 좁은데, 넓은 폭으로 잰 테두리는 그 화면보다 컸다 —
       *  테두리 안이라 카메라는 가만있는데 사람은 이미 밖이었다.
       *
       *  지금 배율을 되짚어 재면 둘이 어긋날 자리가 없다(35% 로 준다). */
      const away = km(cur, at)
      const real = spanOf(lastZoom, at.lat)
      const dead = real * deadFor(real)
      // 서 있는가 — 한 프레임에 1m 도 안 움직였으면 그렇다
      const resting = !!lastAt && km(lastAt, at) * 1000 < 1
      lastAt = at
      const moved = away > dead
      // 서 있는 동안에는 테두리 안이라도 가운데로 되돌린다(CENTER_EASE)
      const centering = resting && !moved && away > real * 0.01
      // 옮길 것도 없고 배율도 다 왔으면 지도를 건드리지 않는다
      if (!moved && !zoomed && !centering) return
      /* 넘은 만큼만 민다 — 사람이 테두리에 붙어 간다.
         서 있는 동안은 테두리를 잊고 조금씩 한가운데로 당긴다. */
      const k = moved ? (away - dead) / away : (centering ? CENTER_EASE : 0)
      m.moveCamera({
        ...(moved || centering
          ? { center: { lat: cur.lat + (at.lat - cur.lat) * k,
                        lng: cur.lng + (at.lng - cur.lng) * k } }
          : {}),
        ...(zoomed ? { zoom: z } : {}),
      })
    },

    fit(pts: LatLng[], pad: Pad) {
      lastZoom = -1        // 다시 따라갈 때 배율을 새로 잡게 한다
      held = -1
      m.fitBounds(bounds(pts), pad)
      const z = m.getZoom()
      if (z != null && z > MAX_ZOOM) m.setZoom(MAX_ZOOM)
    },

    async warm(shots: { at: LatLng; span: number }[]) {
      /* 벡터로 그릴 때는 미리 받을 것이 없다. 배율마다 다른 그림을 내려받는
         것이 아니라 도형 하나를 GPU 가 그때그때 그리기 때문이다 —
         3초를 기다릴 까닭이 사라진다. */
      if (vector) return
      for (const s of shots) {
        m.setCenter(s.at)
        m.setZoom(zoomFor(s.span, s.at.lat))
        await new Promise((r) => setTimeout(r, WARM_MS))
      }
    },

    trail(doneAt: LatLng[], now: LatLng[]) {
      if (!doneLine) {
        doneLine = new google.maps.Polyline({
          map: m, path: [], clickable: false, zIndex: 2,
          strokeColor: css('--route'), strokeOpacity: 0.7,
          strokeWeight: 6,
        })
        trailLine = new google.maps.Polyline({
          map: m, path: [], clickable: false, zIndex: 2,
          strokeColor: css('--route'), strokeOpacity: 0.7,
          strokeWeight: 6,
        })
      }
      // 길이로만 견준다. 지나온 길은 늘어나기만 하므로 이것으로 넉넉하다
      if (doneAt.length !== doneLen) {
        doneLen = doneAt.length
        doneLine.setPath(doneAt)
      }
      trailLine!.setPath(now)
    },

    walker(at: LatLng, label?: string, show = true) {
      /* 선과 같은 자리, 같은 길로 그린다. 마커와 선을 지도가 함께 그리므로
         어느 프레임에도 사람이 선을 벗어나지 않는다. 그 위(zIndex 3)에
         서는 것은 선이 사람의 발밑을 지나기 때문이다. */
      /* 그림은 이름이 바뀔 때만 다시 그린다. 프레임마다 그리면 그때마다
         글자 폭을 어림하고 데이터 URI 를 새로 엮는다 — 초당 예순 번이다.
         자리는 매 프레임 옮긴다. 그것이 걷는 일이다. */
      if (!who || label !== tagged || skin !== inked) {
        tagged = label
        inked = skin
        const ic = walkerIcon(css('--ink-1'), css('--paper'), label, skin)
        const icon = {
          url: ic.url,
          scaledSize: new google.maps.Size(ic.w, ic.h),
          // 이름표가 길수록 그림이 넓어지므로 발이 놓일 자리도 함께 옮긴다
          anchor: new google.maps.Point(ic.ax, ic.ay),
        }
        if (!who) {
          who = new google.maps.Marker({
            map: m, position: at, clickable: false, zIndex: 3, icon,
          })
        } else {
          wear(icon, ic.url)
        }
      }
      who.setPosition(at)
      who.setVisible(show)
    },

    setWalker(src: string | null) {
      skin = src
      // 서 있는 동안에도 그 자리에서 바로 갈아 끼운다.
      //
      // 다음 walker() 를 기다리게 두었더니, 재생 전에 고른 그림이 재생을
      // 눌러야 나타났다 — 고르는 판은 대개 서 있을 때 여는 것이라
      // 거의 언제나 늦게 바뀌는 셈이었다.
      //
      // 아직 마커가 없으면(자리를 한 번도 못 받았으면) 값만 두고 지나간다.
      // 첫 walker() 가 그때 제 그림으로 세운다.
      if (who) {
        inked = skin
        const ic = walkerIcon(css('--ink-1'), css('--paper'), tagged, skin)
        wear({
          url: ic.url,
          scaledSize: new google.maps.Size(ic.w, ic.h),
          anchor: new google.maps.Point(ic.ax, ic.ay),
        }, ic.url)
      }
    },

    destroy() {
      tagged = undefined
      doneLine?.setMap(null)
      trailLine?.setMap(null)
      who?.setMap(null)
      doneLine = trailLine = null
      doneLen = -1
      who = null
    },
  }
}
