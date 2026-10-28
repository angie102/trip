import { MAKI, type Kind } from './maki'

/* 지도에 놓는 마커.
 *
 *  전에는 SVG 를 데이터 URI 로 만들어 google.maps.Marker 의 아이콘에 끼웠다.
 *  그림이 곧 이미지라 CSS 가 닿지 않았고, 원에서 이름표로 바뀌는 것이
 *  「늘어난다」가 아니라 「갈아 끼운다」였다 — 그 자리에서 툭 튀었다.
 *  프레임마다 다시 끼워 흉내 낼 수는 있지만, 이미지 디코딩이 비동기라
 *  깜빡인다.
 *
 *  그래서 마커를 DOM 으로 옮긴다. AdvancedMarkerElement 는 Map ID 를 요구하고
 *  그것을 붙이면 코드의 styles 가 통째로 무시되지만(POI 끄기까지 클라우드로
 *  옮겨야 한다), OverlayView 는 Map ID 없이 제 판(pane)에 DOM 을 얹는다 —
 *  지금 스타일을 하나도 건드리지 않는다.
 *
 *  DOM 이 되면서 얻은 것이 둘이다.
 *    · 원 → 알약이 width 트랜지션이라 실제로 「펴진다」
 *    · 색을 var() 로 바로 읽는다. 전에는 SVG 문자열에 var() 를 못 써서
 *      getComputedStyle 로 꺼내 왔고, 그러다 옅은 글리프가 옛 mauve 로
 *      남아 화면과 갈라진 적이 있다
 *
 *  세 꼴이 있다. 사이는 CSS 가 잇는다.
 *    점        줌이 낮으면 아이콘을 버리고 자리만 남는다. 멀리서 보는 눈은
 *              「무엇이」가 아니라 「어디에 몇 개가」를 읽는다
 *    원        아이콘을 담은 흰 동그라미. 그날의 갈 곳들
 *    이름표    짚은 하나만 옆으로 늘어나며 이름을 편다. 늘 하나뿐이라
 *              겹칠 일이 없다 — 이름표를 다 달면 역 앞에서 무너진다
 */

/** 못 재는 자리에서 기댈 글꼴. 보통은 body 에서 실제로 쓰는 것을 꺼내 온다 */
const FALLBACK = 'Pretendard Variable, Pretendard, -apple-system, Segoe UI, sans-serif'
/* 활자는 화면의 세 단 중 가장 작은 것을 쓴다(13px · --ls-3).
   전에는 12px 이었다 — SVG 문자열 안에 있어 CSS 린터의 눈 밖이었고,
   그래서 아무도 「단 밖」이라고 말해 주지 않았다. 이제 CSS 로 나가면서 걸렸다. */
const FS = 13
const TRACK = -0.01 * FS             // --ls-3. 잴 때도 빼 줘야 맞는다

/* 치수. 예전 SVG 에서 그대로 옮겨 온다 — 눈으로 맞춰 둔 값이라 흔들지 않는다.
   달라진 것은 하나, 이제 이 값들이 CSS 변수로 나가고 그 사이를 브라우저가 잇는다. */
const DOT = { on: 10, off: 7.5 }     // 흰 점 + 테. 예전 r 4/3 에 테 2/1.5
const RIM = { on: 2, off: 1.5 }      // 점일 때의 테 두께. 원·이름표는 1
const CIRCLE = { on: 26, off: 23 }
const GLYPH = { on: 15, off: 13 }
const PILL_H = 28                    // 알약 높이
/* 안쪽 간격은 목록의 가로 규칙을 그대로 따른다.
     padL     왼쪽 끝 → 글리프. 원의 한가운데에 앉히면 저절로 6.5px 이다
     gap      글리프 → 글자. 앞에 서는 아이콘은 4px (--sp-1) —
              글자를 이끄는 것이라 뒤에 붙는 표식(2px)보다 넓다
     padR     글자 → 오른쪽 끝. 8px (--sp-2). 왼쪽이 6.5px 인데도 같아 보인다 —
              그쪽은 둥근 모서리가 여백을 더 내어 주기 때문이다 */
const PAD_L = (PILL_H - GLYPH.on) / 2
const GAP = 4
const PAD_R = 8
/* 이름표가 담는 글자의 최대 폭.
   150 이던 값을 활자 12 → 13px 만큼(13/12) 올려 잡았다. 폭을 그대로 두면
   같은 이름이 한 글자씩 덜 담겨 말줄임이 아홉 개 늘어난다 —
   「다카나와 게이트웨이 시티」처럼 딱 경계에 걸친 것들이다.
   알약은 최대 196px 이 되는데 화면 폭이 430px 이라 아직 여유가 있다. */
const NAME_MAX = 163
/** 글자가 시작하는 자리. 알약이 좁을 때는 넘쳐서 잘린다 — 그게 곧 접힌 모습이다.
 *  꼴마다 옮기지 않고 못 박아 둔다. 움직이면 펴질 때 글자가 따라 밀려
 *  「가려져 있다 드러난다」가 아니라 「밖에서 들어온다」로 읽힌다. */
const TEXT_X = PAD_L + GLYPH.on + GAP

/** 글자 폭을 실제로 잰다.
 *
 *  글자 수로 어림잡았더니 「The Front Room」이 12px 넓게 나왔다 — 라틴을 한 글자
 *  0.55em 으로 셌는데 공백은 그 절반도 안 되기 때문이다. 그만큼이 알약
 *  오른쪽에 빈 자리로 남았다.
 *
 *  DOM 이 되었으니 폭을 재지 말고 width:auto 로 둘 수도 있다. 그러면 안 된다 —
 *  auto 는 트랜지션이 안 걸린다. 펴지는 모습을 얻으려면 끝 폭이 px 이어야 한다.
 *  컨텍스트는 한 번 만들어 두고 쓴다. */
let ctx: CanvasRenderingContext2D | null | undefined
let font = ''
/** 재는 글꼴과 그리는 글꼴을 맞춘다.
 *
 *  SVG 이던 시절에는 문자열에 적어 둔 Pretendard 묶음으로 재고 그렸다. 이제
 *  그리는 것은 DOM 이라 body 의 묶음을 따르는데, 거기에는 한글 뒤에 일본어
 *  글꼴이 서 있다 — 「弥彦神社」를 Pretendard 로 재고 Yu Gothic 으로 그리면
 *  알약 오른쪽에 빈 자리가 남는다. 화면에 일본어 이름이 백쉰 곳이다.
 *  그래서 재기 전에 실제로 쓰는 묶음을 꺼내 온다. */
const measureFont = () => {
  if (!font) {
    font = (typeof getComputedStyle !== 'undefined' && document.body
      ? getComputedStyle(document.body).fontFamily : '') || FALLBACK
  }
  return `600 ${FS}px ${font}`
}
const textWidth = (s: string) => {
  if (ctx === undefined) ctx = document.createElement('canvas').getContext('2d')
  if (ctx) {
    ctx.font = measureFont()
    /* 캔버스는 못 알아들은 글꼴 이름을 조용히 버리고 앞의 것을 그대로 쓴다
       (처음 값은 10px sans-serif 다). 크기가 안 들어가 있으면 못 알아들은 것이다. */
    if (!ctx.font.includes(`${FS}px`)) ctx.font = `600 ${FS}px ${FALLBACK}`
    return Math.ceil(ctx.measureText(s).width + TRACK * (s.length - 1))
  }
  // 캔버스를 못 쓰는 자리에서는 어림잡는다 — 한글은 한 칸, 라틴은 절반쯤
  let w = 0
  for (const ch of s) w += /[가-힣ぁ-んァ-ヶ一-龥]/.test(ch) ? FS : FS * 0.55
  return Math.ceil(w)
}

/** 이름이 길면 줄인다. 글자 수가 아니라 폭으로 자른다 —
 *  「PRESS BUTTER SAND」와 「스시키 야마다」는 같은 열두 자라도 폭이 두 배 다르다. */
const fit = (s: string, max: number) => {
  if (textWidth(s) <= max) return s
  let cut = s
  while (cut.length > 1 && textWidth(cut + '…') > max) cut = cut.slice(0, -1)
  return cut + '…'
}

/** 마커가 지금 무엇으로 보이는가. */
export type Mode = 'dot' | 'circle' | 'label'

/** 한 자리의 마커를 만든다. 꼴은 아직 정하지 않는다 — setLook 이 입힌다. */
export function makeMarker(kind: Kind, name: string): HTMLButtonElement {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = 'mk'
  el.setAttribute('aria-label', name)          // 잘리지 않은 온이름은 여기 남는다

  const g = MAKI[kind]
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'mkglyph')
  svg.setAttribute('viewBox', g.box)
  svg.setAttribute('aria-hidden', 'true')
  svg.innerHTML = g.path
  el.appendChild(svg)

  const label = fit(name, NAME_MAX)
  const tag = document.createElement('span')
  tag.className = 'mkname'
  tag.textContent = label                      // 이름은 데이터다. 붙이지 말고 넣는다
  el.appendChild(tag)

  /* 다 펼쳤을 때의 폭. 여기서는 어림값이고, 화면에 붙인 뒤 sizeLabels 가
     실제로 그려진 폭으로 고쳐 잡는다. 비워 두면 첫 프레임에 알약이 무너진다. */
  el.style.setProperty('--mk-lw', `${TEXT_X + textWidth(label) + PAD_R}px`)
  // 글자가 앉는 자리도 여기서 내보낸다 — 치수는 이 파일 하나에만 적어 둔다
  el.style.setProperty('--mk-tx', `${TEXT_X}px`)
  return el
}

/** 화면에 붙인 뒤, 실제로 그려진 글자 폭에 알약을 맞춘다.
 *
 *  캔버스로 잰 값을 믿을 수 없다. Pretendard 는 CDN 에서 오는 웹글꼴이고,
 *  그것도 쓰는 글자에 따라 조각조각 온다(dynamic subset). 마커를 만드는
 *  순간에는 아직 대체 글꼴로 그려져 있어 그 폭으로 재는데, 조금 뒤 진짜
 *  글꼴이 도착하면 글자만 그 폭으로 다시 그려진다 — 알약은 그대로라
 *  오른쪽 여백이 먹힌다.
 *
 *  전에는 이 어긋남이 없었다. SVG 를 이미지로 넣었기 때문이다 — SVG 이미지
 *  안에서는 웹글꼴이 로드되지 않아 그림도 대체 글꼴이었고, 재는 것과 그리는
 *  것이 저절로 같았다. DOM 이 되면서 그림만 진짜 글꼴이 됐다.
 *
 *  그래서 짐작하지 않고 그려진 것을 잰다. 여럿을 한 번에 받는 까닭은
 *  붙이기(쓰기)와 재기(읽기)를 갈라야 레이아웃이 한 번만 돌기 때문이다 —
 *  하나씩 붙였다 재면 마커 수만큼 다시 잰다.
 *
 *  offsetWidth 를 쓴다. getBoundingClientRect 는 조상에 걸린 변형까지 곱해
 *  돌려주는데, 판을 얹은 자리가 그럴 수 있다. */
export function sizeLabels(els: HTMLElement[]) {
  const w = els.map(
    (el) => (el.querySelector('.mkname') as HTMLElement | null)?.offsetWidth ?? 0)
  els.forEach((el, i) => {
    if (w[i]) el.style.setProperty('--mk-lw', `${TEXT_X + w[i] + PAD_R}px`)
  })
}

/** 글꼴이 바뀌었으니 다시 자른다 — 폭이 달라지면 담기는 글자 수도 달라진다.
 *  자르지 않은 온이름은 aria-label 에 남아 있다. */
export function refit(el: HTMLElement) {
  const tag = el.querySelector('.mkname')
  if (!tag) return
  const next = fit(el.getAttribute('aria-label') ?? '', NAME_MAX)
  if (tag.textContent !== next) tag.textContent = next
}

/** 꼴을 입힌다. 값만 바꾸고 사이는 CSS 가 잇는다.
 *  @param near  고른 항목의 것인가 — 아니면 한 단 물러난다 */
export function setLook(el: HTMLElement, mode: Mode, near: boolean) {
  const s = el.style
  const put = (w: string, h: string, gx: string, glyph: number, rim: number) => {
    s.setProperty('--mk-w', w)
    s.setProperty('--mk-h', h)
    s.setProperty('--mk-gx', gx)
    s.setProperty('--mk-g', `${glyph}px`)
    s.setProperty('--mk-rim', `${rim}px`)
  }
  if (mode === 'label') {
    put('var(--mk-lw)', `${PILL_H}px`, `${PAD_L + GLYPH.on / 2}px`, GLYPH.on, 1)
  } else if (mode === 'circle') {
    const d = near ? CIRCLE.on : CIRCLE.off
    const g = near ? GLYPH.on : GLYPH.off
    put(`${d}px`, `${d}px`, `${d / 2}px`, g, 1)
  } else {
    const d = near ? DOT.on : DOT.off
    // 점일 때도 글리프 크기는 원의 것을 그대로 둔다. 어차피 지워지는데
    // 같이 줄이면 사라지면서 쪼그라들어 두 몸짓이 겹친다.
    put(`${d}px`, `${d}px`, `${d / 2}px`, near ? GLYPH.on : GLYPH.off,
        near ? RIM.on : RIM.off)
  }
  el.classList.toggle('is-on', mode === 'label')
  el.classList.toggle('is-far', mode === 'dot')
  el.classList.toggle('is-dim', !near)
  el.style.zIndex = mode === 'label' ? '30' : near ? '20' : '10'
}
