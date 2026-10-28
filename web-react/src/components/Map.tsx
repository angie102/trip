import { useCallback, useEffect, useRef, useState } from 'react'
import type { Day, Item, Place } from '../types'
import { GOOGLE_MAPS_API_KEY } from '../config.local'
import { makeMarker, refit, setLook, sizeLabels } from './marker'
import type { Kind } from './maki'

/* 지도에서 끄는 것은 이제 없다.
 *
 *  세 번 물러선 자리다. 처음에는 라벨 아이콘을 통째로 껐고(`labels.icon: off`),
 *  그러자 역·공원·랜드마크까지 다 지워졌다. 다음에는 다투는 것만 껐다 —
 *  가게·식당의 색 아이콘. 우리가 고른 곳 옆에 구글이 고른 가게가 같이 서면
 *  무엇을 보라는 것인지 흐려진다는 까닭이었다.
 *
 *  그런데 화면이 비어 보인 진짜 까닭은 그것이 아니었다. 줌이었다.
 *  하루를 통째로 담느라 줌이 10~11 에 머물렀고, 그 줌에서는 구글도 시·군
 *  이름밖에 안 그린다 — 끄고 켤 것이 애초에 없었다. 시야를 오늘의 주 무대로
 *  좁히자(mainStage) 평균 줌이 15 로 올라갔고, 그러자 껐던 것이 아쉬워졌다.
 *
 *  그래서 되돌린다. 색이 들어오지만 그 자리에서 색이 하는 일은 「여기 뭔가
 *  있다」를 한눈에 알리는 것이고, 글자만 있을 때보다 훨씬 빨리 읽힌다.
 *  우리 마커는 흰 원에 검은 글리프라 꼴이 뚜렷이 달라 뒤섞이지 않는다.
 *
 *  다만 눌리지는 않게 둔다(clickableIcons:false). 구글 아이콘을 누르면
 *  구글의 말풍선이 우리 이름표와 같은 자리를 두고 다툰다.
 */

let loading: Promise<void> | null = null
function loadMaps() {
  if (loading) return loading
  loading = new Promise<void>((res, rej) => {
    if (!GOOGLE_MAPS_API_KEY) return rej(new Error('no key'))
    if (window.google?.maps) return res()
    const s = document.createElement('script')
    s.src = `https://maps.googleapis.com/maps/api/js?key=${GOOGLE_MAPS_API_KEY}&language=ko&region=JP&loading=async&callback=__mapReady`
    s.async = true
    ;(window as any).__mapReady = () => res()
    s.onerror = () => rej(new Error('load failed'))
    document.head.appendChild(s)
  })
  return loading
}

/* ── 마커를 얹는 판 ────────────────────────────────────
 *  마커가 DOM 이 되었으니 지도 위에 DOM 을 놓을 자리가 필요하다.
 *  OverlayView 가 그 자리를 내어 준다 — 지도가 움직일 때마다 draw() 를
 *  불러 주고, 우리는 좌표를 픽셀로 바꿔 얹기만 한다.
 *
 *  판은 overlayMouseTarget 을 쓴다. 그 아래 판들은 클릭이 안 닿는다.
 */
type Pin = {
  el: HTMLButtonElement
  at: google.maps.LatLng
  kind: Kind
  itemId: string
  /** places.json 의 id. focus 와 맞춰 「짚은 하나」를 가린다 */
  id: string
}
type Layer = google.maps.OverlayView & { pins: Pin[]; root: HTMLDivElement }

/* 클래스는 구글 스크립트가 온 뒤에야 만들 수 있다 — OverlayView 가
   그때 생기기 때문이다. 그래서 처음 쓸 때 만들어 두고 돌려쓴다. */
let Ctor: (new () => Layer) | null = null
function newLayer(): Layer {
  if (!Ctor) {
    class L extends google.maps.OverlayView {
      pins: Pin[] = []
      root = document.createElement('div')
      constructor() {
        super()
        this.root.className = 'mklayer'
      }
      onAdd() { this.getPanes()!.overlayMouseTarget.appendChild(this.root) }
      onRemove() { this.root.remove() }
      draw() {
        const p = this.getProjection()
        if (!p) return
        for (const pin of this.pins) {
          const pt = p.fromLatLngToDivPixel(pin.at)
          if (!pt) continue
          pin.el.style.left = `${pt.x}px`
          pin.el.style.top = `${pt.y}px`
        }
      }
    }
    Ctor = L as unknown as new () => Layer
  }
  return new Ctor()
}

/* ── 카메라 ────────────────────────────────────────────
 *  panTo 는 「옮길 거리가 지도의 폭·높이보다 작을 때만」 부드럽고,
 *  setZoom 은 언제나 즉시다. 둘을 나란히 부르면 밀리다 줌만 뚝 끊긴다.
 *  그래서 직접 몬다 — 중심과 줌을 한 곡선 위에서 같이 움직인다.
 */

/** 위경도를 0‥1 세계 좌표로. 줌이 함께 바뀔 때 화면에서 고르게 흐르려면
 *  위경도가 아니라 이 평면에서 이어야 한다 — 위도는 북으로 갈수록 촘촘해져
 *  그대로 이으면 남북으로 갈 때만 속도가 달라진다. */
const world = (lat: number, lng: number) => {
  const s = Math.sin((lat * Math.PI) / 180)
  return { x: (lng + 180) / 360,
           y: 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI) }
}
const toLat = (y: number) =>
  ((2 * Math.atan(Math.exp((0.5 - y) * 2 * Math.PI)) - Math.PI / 2) * 180) / Math.PI

/* ── 오늘의 주 무대 ────────────────────────────────────
 *  하루를 통째로 담던 규칙 하나로는 안 됐다. 하루의 펼침이 0.2km 부터
 *  276km 까지라 「전부 담아라」가 이동일에는 줌 7 이 된다 — 자리가 있는
 *  열네 날 가운데 열하루가 줌 13 아래였고, 그 줌에서 구글은 시·군 이름밖에
 *  안 그린다. 「지도에 정보가 없다」는 말이 곧 그 뜻이었다.
 *
 *  그래서 양 끝이 아니라 머무는 곳을 담는다. 도시 날은 거의 다 한 덩어리라
 *  하루를 훑는 감각이 그대로 남고, 이동일에는 오늘의 주 무대만 담긴다.
 */
const KNIT = 2                       // km. 이 안에서 이어지면 한 덩어리다

/** 두 자리 사이 대략의 거리(km). 자오선 수렴만 보정한다 —
 *  하루가 오가는 범위에서는 이 어림이 정확한 계산과 갈리지 않는다. */
const apart = (a: google.maps.LatLngLiteral, b: google.maps.LatLngLiteral) =>
  Math.hypot((a.lat - b.lat) * 111,
             (a.lng - b.lng) * 111 * Math.cos((a.lat * Math.PI) / 180))

/** 가까운 것끼리 이어 붙여(단일 연결) 가장 큰 덩어리를 고른다.
 *  같은 크기면 먼저 나온 것을 둔다 — 그날 앞쪽 일정이 이긴다. */
function mainStage(ps: google.maps.LatLngLiteral[]) {
  const seen = new Set<number>()
  let best: google.maps.LatLngLiteral[] = []
  for (let i = 0; i < ps.length; i++) {
    if (seen.has(i)) continue
    seen.add(i)
    const q = [i]
    const g: google.maps.LatLngLiteral[] = []
    while (q.length) {
      const k = q.pop()!
      g.push(ps[k])
      for (let j = 0; j < ps.length; j++)
        if (!seen.has(j) && apart(ps[k], ps[j]) <= KNIT) { seen.add(j); q.push(j) }
    }
    if (g.length > best.length) best = g
  }
  return best
}

/** 이 아래로 내려가면 마커가 아이콘을 버리고 점이 된다. 칠하는 쪽과 나는 쪽이
 *  같은 값을 봐야 한다 — 갈라 두면 나는 도중에 문턱을 넘나든다. */
const FAR = 13

/** 즉시 나가서 부드럽게 멈춘다 — styles.css 의 --ease 와 같은 결이다 */
const ease = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2)

const still = () =>
  typeof matchMedia !== 'undefined'
  && matchMedia('(prefers-reduced-motion: reduce)').matches

/** 그리로 날아간다. 멈추는 손잡이를 돌려준다. */
function flyTo(m: google.maps.Map, to: google.maps.LatLngLiteral, z1: number) {
  const c = m.getCenter()
  const z0 = m.getZoom()
  if (!c || z0 == null || still()) {
    m.setCenter(to)
    m.setZoom(z1)
    return () => {}
  }
  /* 도는 동안만 소수 줌을 켠다. 이게 없으면 줌이 정수로 튀어 애써 이은
     곡선이 계단이 되고, 켠 채로 두면 래스터 타일이 늘어나 글자가 뭉갠다.
     내릴 때(land)는 반드시 되돌린다 — 중간에 손이 지도를 잡아도 마찬가지다.
     끄는 순간 지도가 제 줌을 정수로 맞춰 준다. */
  m.setOptions({ isFractionalZoomEnabled: true })
  const land = () => m.setOptions({ isFractionalZoomEnabled: false })
  const a = world(c.lat(), c.lng())
  const b = world(to.lat, to.lng)
  /* 얼마나 먼가 — 도착했을 때의 화면 폭을 자로 쓴다.
     같은 1km 라도 줌 17 에서는 몇 화면이고 줌 11 에서는 한 뼘이다. */
  const px = Math.hypot(b.x - a.x, b.y - a.y) * 256 * 2 ** z1
  const screens = px / (m.getDiv()?.clientWidth || 320)
  /* 화면 몇 개를 건너뛰는 길이면 잠깐 물러섰다 다시 다가간다.
     등속으로 스쳐 지나가면 도중에 아무것도 안 보여 순간이동과 구별되지 않는다.
     sin 이라 시작과 끝에서 0 이다 — 목적지 줌은 그대로 지킨다.

     다만 점이 되는 문턱 아래로는 안 내려간다. 물러서는 까닭이 「지나가는 것을
     보여 주려고」인데 그것들이 점으로 바뀌면 물러선 뜻이 없어지고, 오가며
     문턱을 두 번 넘어 마커가 쪼그라들었다 커지는 것만 보인다. */
  const room = Math.min(z0, z1) - FAR
  const dip = screens > 1
    ? Math.max(0, Math.min(1.8, Math.log2(screens), room))
    : 0
  const dur = 380 + 120 * Math.min(screens, 3)
  const t0 = performance.now()
  let raf = 0
  const step = (now: number) => {
    const t = Math.min(1, (now - t0) / dur)
    const e = ease(t)
    m.setCenter({ lat: toLat(a.y + (b.y - a.y) * e),
                  lng: (a.x + (b.x - a.x) * e) * 360 - 180 })
    m.setZoom(z0 + (z1 - z0) * e - dip * Math.sin(Math.PI * t))
    if (t < 1) raf = requestAnimationFrame(step)
    else land()
  }
  raf = requestAnimationFrame(step)
  return () => { cancelAnimationFrame(raf); land() }
}

type Props = {
  day: Day
  selected: Item | null
  /** 후보 하나를 지목했을 때 그 자리. 있으면 여기로 당긴다 */
  focus: Place | null
  bottomPad: number
  /** 지도에서 후보를 짚었다 — 목록도 그리로 따라간다 */
  onPickSpot: (itemId: string, place: Place) => void
  /** 지도의 빈 곳을 눌렀다 — 짚은 것을 놓는다 */
  onBlur: () => void
  onFail: () => void
}

export default function Map({ day, selected, focus, bottomPad,
                              onPickSpot, onBlur, onFail }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<google.maps.Map | null>(null)
  const layer = useRef<Layer | null>(null)
  const pickSpot = useRef(onPickSpot)
  pickSpot.current = onPickSpot
  const blur = useRef(onBlur)
  blur.current = onBlur
  // 지도는 스크립트를 받아 온 뒤에야 생긴다. 그 전에 돌아 버린 이펙트는
  // 마커를 하나도 못 놓고 끝나는데, 지도가 생겼다는 것을 알릴 길이 없어
  // 다시 돌지도 않았다 — 날짜를 바꾸기 전까지 지도가 비어 있었다.
  const [ready, setReady] = useState(false)
  // 그날 찍은 자리들. 시야를 잡을 때 쓴다.
  const spots = useRef<google.maps.LatLngLiteral[]>([])
  // 시야를 이미 맞춰 둔 날. 같은 날 안에서는 다시 맞추지 않는다.
  const framed = useRef('')
  // 날아가는 중이면 멈추는 손잡이. 새 몸짓이 옛 몸짓을 이어받는다.
  const land = useRef<() => void>(() => {})

  useEffect(() => {
    let dead = false
    loadMaps()
      .then(() => {
        if (dead || !box.current || map.current) return
        const m = new google.maps.Map(box.current, {
          center: { lat: 37.9161, lng: 139.0364 },
          zoom: 12,
          disableDefaultUI: true,
          gestureHandling: 'greedy',
          clickableIcons: false,
          /* 소수 줌은 날아가는 동안만 켠다(flyTo). 켠 채로 두면 안 된다 —
             이 지도는 벡터가 아니라 래스터다. 소수 줌에서는 타일 비트맵을
             늘려 그리므로 글자가 리샘플되어 뭉갠다. 「도쿄역」처럼 여러 곳을
             담느라 fitBounds 로 온 날은 줌이 16.37 같은 값에 서고, 그래서
             스크롤을 몇 번 굴려 정수에 닿아야 글자가 또렷해졌다.
             한 곳뿐이라 setZoom(16)으로 선 날은 처음부터 멀쩡했다. */
          isFractionalZoomEnabled: false,
        })
        map.current = m
        // 빈 곳을 누르면 이름표를 닫는다. 마커를 누른 것은 여기까지 오지 않는다 —
        // 마커 쪽에서 preventMapHitsFrom 으로 막아 둔다.
        m.addListener('click', () => blur.current())
        // 손이 지도를 잡으면 우리가 몰던 것을 놓는다. 둘이 같이 밀면 싸운다.
        m.addListener('dragstart', () => land.current())
        const lay = newLayer()
        lay.setMap(m)
        layer.current = lay
        setReady(true)
      })
      .catch(onFail)
    return () => { dead = true }
  }, [onFail])

  /* 무엇을 어디에 놓을까 — 자리는 여기서 정하고, 어떻게 보일지는 아래에서 칠한다.
   *
   *  고른 항목(selected)은 이 이펙트의 관심사가 아니다. 그것이 바뀔 때마다
   *  마커를 새로 만들면 펴지던 이름표가 도중에 잘린다 — 트랜지션은 같은
   *  원소에 붙어 있어야 이어진다. 자리는 날이 바뀔 때만 다시 놓고,
   *  진하기는 칠하는 쪽이 맡는다.
   */
  useEffect(() => {
    const lay = layer.current
    if (!lay) return
    lay.root.textContent = ''
    lay.pins = []

    /** 한 자리를 놓는다. 시각은 얹지 않는다 — 목록에 이미 있고,
     *  마커에 담으면 글자 수마다 폭이 달라져 여럿이 놓일 때 줄이 안 선다. */
    const put = (place: Place, title: string, itemId: string) => {
      const kind = place.kind ?? 'place'
      const el = makeMarker(kind, title)
      // 판이 자리를 잡아 주기 전까지는 화면 밖에 둔다 — 안 그러면
      // 첫 프레임에 왼쪽 위 구석에 우르르 모였다 흩어진다.
      el.style.left = '-9999px'
      /* 지도에서 짚어도 목록이 따라오게 한다 — 한쪽만 움직이면 짝이 어긋난다.
       *
       * 후보와 항목을 갈라 항목 쪽은 toggle 만 부르던 때가 있었는데, 그러면
       * focus 가 안 잡혀 이름표도 안 뜨고 지도는 앞서 짚어 둔 자리로 도로
       * 날아갔다(「효우탄차야」처럼 후보 없이 detail 만 있는 항목이 그랬다).
       * 어느 쪽을 눌렀든 뜻은 하나다 — 「이 자리를 짚었다」. */
      el.addEventListener('click', (ev) => {
        ev.stopPropagation()
        pickSpot.current(itemId, place)
      })
      /* 마커를 누른 것이 「지도의 빈 곳을 눌렀다」로도 세이지 않게 한다.
         몸짓(끌기)까지 막지는 않는다 — 26px 원 위에서 시작한 스와이프도
         지도를 밀 수 있어야 한다. */
      google.maps.OverlayView.preventMapHitsFrom(el)
      lay.root.appendChild(el)
      lay.pins.push({ el, at: new google.maps.LatLng(place.lat!, place.lng!),
                      kind, itemId, id: place.id ?? '' })
    }

    // 갈 수 있는 곳만 찍는다.
    // 후보를 거느린 항목의 좌표는 그 후보들의 한가운데(approx)라 자리가 아니다 —
    // 「점심」 한복판에 가서 밥을 먹을 수는 없으므로 후보 쪽을 찍는다.
    for (const it of day.items) {
      const cands = (it.spots ?? []).filter((s) => s.place?.lat != null && !s.group)
      if (cands.length) {
        for (const s of cands) put(s.place!, s.name, it.id)
      } else if (it.place?.lat != null && !it.place.approx
                 && (it.detail || it.place.name)) {
        /* 이름표에는 가게 이름을 단다. 제목은 「내가 무엇을 하는가」이지
         * 「그 자리가 어디인가」가 아니다 —
         * 「역에서 기차에서 먹을거 사기」가 아니라 「엔무스」다.
         *
         * 제목으로 물러서던 갈래를 없앤다. 이름이 없으면 그 자리는 이름표를
         * 달 수 없는 것이지, 제목을 빌려 올 자리가 아니다. detail 이 있으면
         * 그것이 이 항목의 실체이고, 없으면 구글이 준 이름이다. */
        put(it.place, it.detail || it.place.name!, it.id)
      }
    }
    lay.draw()

    /* 알약 폭을 그려진 대로 고쳐 잡는다.
     *
     *  Pretendard 는 CDN 에서 오고, 그것도 쓰는 글자에 따라 조각조각 온다
     *  (dynamic subset). 마커를 만드는 순간에는 아직 대체 글꼴이라 그 폭으로
     *  재는데, 조금 뒤 진짜 글꼴이 오면 글자만 다시 그려져 알약이 안 맞는다 —
     *  오른쪽 여백이 먹힌다. 그래서 한 번 재고, 글꼴이 온 뒤에 다시 잰다.
     *
     *  ready 는 지금 받는 중인 것이 다 왔을 때 한 번이고, loadingdone 은
     *  조각이 올 때마다다. 조각으로 오는 글꼴이라 둘 다 듣는다. */
    const els = lay.pins.map((p) => p.el)
    sizeLabels(els)
    let dead = false
    const again = () => {
      if (dead) return
      els.forEach(refit)                 // 폭이 달라졌으니 자르는 자리도 다시
      sizeLabels(els)
    }
    const fonts = document.fonts
    fonts?.ready?.then(again)
    fonts?.addEventListener?.('loadingdone', again)
    return () => {
      dead = true
      fonts?.removeEventListener?.('loadingdone', again)
    }
  }, [day, ready])

  /* 어떻게 보일까 — 줌과 고른 것에 따라 꼴만 바꾼다.
   *
   *  줌이 낮으면 아이콘을 버리고 점만 남긴다. 멀리서 보는 눈은 「무엇이」가
   *  아니라 「어디에 몇 개가」를 읽고, 24px 원 열다섯이 겹치면 그것조차 못 읽는다.
   *  구글 지도도 줌을 내리면 아이콘을 점으로 줄이고 더 내리면 아예 지운다.
   *
   *  여기서 하는 일은 CSS 변수를 갈아 끼우는 것뿐이다. 원 → 알약도, 원 → 점도
   *  사이는 브라우저가 이어 준다.
   */
  useEffect(() => {
    const m = map.current
    const lay = layer.current
    if (!m || !lay) return

    /* 지금 점으로 보이고 있는가. 날아가는 동안 줌이 프레임마다 바뀌는데
       문턱(FAR)을 넘지 않는 한 다시 칠할 것이 없다 — 안 그러면 초당 예순 번
       마커 열다섯의 스타일을 새로 쓴다. */
    let was: boolean | null = null
    const paint = (force: boolean) => {
      const far = (m.getZoom() ?? 14) < FAR
      if (!force && far === was) return
      was = far
      const pts: google.maps.LatLngLiteral[] = []
      for (const p of lay.pins) {
        // 고른 항목의 것만 진하게. 고른 것이 없으면 다 같은 무게로 둔다.
        const near = !selected || selected.id === p.itemId
        const on = !!focus?.id && focus.id === p.id
        setLook(p.el, on ? 'label' : far ? 'dot' : 'circle', near)
        if (near) pts.push({ lat: p.at.lat(), lng: p.at.lng() })
      }
      spots.current = pts
    }
    paint(true)
    const h = m.addListener('zoom_changed', () => paint(false))
    return () => h.remove()
  }, [day, selected, focus, ready])

  /* 어디를 보여 줄까.
   *
   *  자리 놓기와 갈라 둔다. 한 이펙트에 묶여 있던 때는 짚은 것을 놓을 때마다
   *  (focus → null) 시야를 다시 잡아, 지도가 그날 전체로 튀어 보던 자리를
   *  잃었다. 「빈 곳을 눌러 이름표를 닫는다」가 「처음으로 되돌린다」가 된 셈이다.
   *
   *  이제 시야는 세 번 움직인다 — 짚었을 때 그리로, 날이 바뀌었을 때 전체로,
   *  그리고 접혀 있던 지도가 펴졌을 때.
   *
   *  움직이는 결은 둘로 가른다.
   *    짚었을 때    이어지는 몸짓이다. 손이 가리킨 것을 눈이 따라가야 하므로
   *                 중심과 줌을 한 곡선 위에서 같이 민다(flyTo)
   *    날이 바뀔 때  새 화면이다. 어제 자리에서 오늘 자리로 날아갈 까닭이 없다 —
   *                 따라갈 것이 없는 이동은 그냥 긴 기다림이다
   */
  const frame = useCallback((soft = true) => {
    const m = map.current
    const h = box.current?.clientHeight ?? 0
    /* 접힌 지도(높이 0)에 시야를 맞추면 「높이 0 에 이 범위를 담아라」가 되어
       줌이 끝까지 빠진다 — 세계지도가 뜬다.
       0 만 막아서는 모자랐다. 펴지는 중(5px)에 맞추면 「5px 안에 이 범위와
       98px 여백을 담아라」가 되어 마찬가지로 터무니없는 줌이 나온다.
       여백조차 못 담는 높이면 아직 맞출 때가 아니다. */
    const pad = { top: 74, bottom: bottomPad, left: 34, right: 34 }
    if (!m || h < pad.top + pad.bottom + 40) return
    land.current()
    if (focus?.lat != null) {
      const z = Math.max(m.getZoom() ?? 14, 16)
      // 짚어서 온 것이면 눈이 따라가야 하므로 날아가고,
      // 펴지거나 날이 바뀌어서 온 것이면 새 화면이라 그냥 선다.
      if (soft) land.current = flyTo(m, { lat: focus.lat, lng: focus.lng! }, z)
      else { m.setCenter({ lat: focus.lat, lng: focus.lng! }); m.setZoom(z) }
      return
    }
    if (framed.current === day.date) return
    const pts = spots.current
    if (!pts.length) return
    framed.current = day.date
    const stage = mainStage(pts)
    if (stage.length === 1) {
      m.setCenter(stage[0])
      m.setZoom(16)
      return
    }
    const b = new google.maps.LatLngBounds()
    stage.forEach((p) => b.extend(p))
    m.fitBounds(b, pad)
    /* 덩어리가 좁으면 너무 파고든다. 골목 하나만 남으면 그것대로 길을 잃는다 —
       어느 동네인지는 보여야 「여기가 어디」가 읽힌다.

       내림(floor)으로 정수에 앉힌다. 소수 줌을 꺼 두었어도 fitBounds 는
       제 계산으로 소수 값을 낼 수 있어서 한 번 더 못 박는다.
       올림이 아니라 내림인 까닭은 담기는 범위다 — 한 단 올리면 방금 맞춘
       가장자리가 화면 밖으로 밀린다. */
    const z = m.getZoom()
    if (z != null) m.setZoom(Math.min(17, Math.floor(z)))
  }, [day, focus, bottomPad])

  useEffect(() => { frame() }, [frame, ready])

  /* 지도가 펴지는 것을 여기서 안다.
   *
   *  펴고 접는 것은 부모(.map)의 높이가 하는 일이라 이 컴포넌트는 모른다.
   *  프로퍼티로 받아 오는 대신 제 크기를 지켜본다 — 높이가 0 에서 자라나면
   *  그때가 시야를 맞출 때다. 접힌 채로 맞춰 둔 「그날은 이미 맞췄다」는
   *  기록도 함께 지운다. */
  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let had = el.clientHeight > 0
    let opening = false
    let wait: number | undefined
    const ro = new ResizeObserver(() => {
      const has = el.clientHeight > 0
      if (has && !had) opening = true      // 펴지기 시작했다
      had = has
      if (!opening) return
      if (!has) { opening = false; clearTimeout(wait); return }
      /* 아직 자라는 중이다. 다 펴진 뒤에 맞춘다.
         타이머는 「로딩텀」이 아니다 — 280ms 를 짐작해 박아 두면 CSS 의
         여닫는 시간이 바뀔 때 조용히 어긋난다. 여기서 기다리는 것은
         「크기가 더 안 바뀌는 것」이고, 자라는 동안에는 매 프레임 다시 미뤄진다.
         마지막 한 번이 울렸을 때가 곧 다 펴진 때다. */
      clearTimeout(wait)
      wait = window.setTimeout(() => {
        opening = false
        framed.current = ''
        frame(false)                       // 펴져서 온 것이다 — 날지 않고 선다
      }, 80)
    })
    ro.observe(el)
    return () => { ro.disconnect(); clearTimeout(wait) }
  }, [frame])

  // 떠날 때 날던 것을 멈춘다 — 사라진 지도를 계속 밀지 않게.
  useEffect(() => () => land.current(), [])

  /* 재생은 지도 위에 얹히되 지도의 상태에는 손대지 않는다.
     제 선과 제 사람만 더하고, 이름표도 사람이 들고 다닌다 —
     focus 를 나눠 쓰면 목록·지도·재생 셋이 한 상태를 두고 다툰다. */
  return <div className="mapcanvas" ref={box} aria-label="지도" />
}
