import type { Day, Leg, LegEnd, Place, Range, Reservation, Trip } from './types'

/** 화면에 적는 날짜는 늘 「9.19」 꼴이다.
 *  15일이 모두 2026년이라 해는 적을 자리가 없고, 앞자리 0 은 눈에 걸리기만 한다. */
export const md = (iso: string) => `${+iso.slice(5, 7)}.${+iso.slice(8, 10)}`

/** 「12,000엔」. 시트가 그렇게 적고, 이동의 금액도 그 표기 그대로 나온다 —
 *  한 화면에 ¥ 와 「엔」이 섞이지 않게 여기 하나로 모은다. */
export const yen = (n: number) => n.toLocaleString('ko-KR') + '엔'
export const dur = (m: number) =>
  m >= 60 ? `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ''}` : `${m}분`

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2708}]/gu
export const clean = (s: string) => s.replace(EMOJI, '').trim()

/** 제목 맨 앞에 붙은 이모지 — 시트가 「🍚점심」이라 적어 둔 그 글자를 그대로 돌려준다.
 *
 *  화면이 아이콘을 고르지 않는다. 종류마다 그림을 정해 두면 시트가 🍚 를 🍜 로
 *  바꿔도 화면은 옛 그림을 쥐고 있게 되고, 시트에 이모지가 빠진 자리에서는
 *  코드가 대신 하나를 지어내 「적혀 있다」와 「보인다」가 갈린다.
 *  적혀 있으면 뜨고 없으면 안 뜬다. 그것으로 끝이다 — 무엇을 세울지는
 *  시트가 정하므로, 빠진 자리를 코드가 채우지도 나무라지도 않는다.
 *
 *  EMOJI 의 글자 갈래를 다시 적지 않고 source 를 빌려 쓴다. 둘이 갈리면
 *  clean 이 떼는 것과 여기서 집는 것이 어긋나 이모지가 제목에도 남는다.
 *
 *  앞 공백은 정규식이 아니라 trimStart 로 턴다. 템플릿 리터럴 안의 \s 는
 *  한 겹 벗겨져 s 가 되므로(「^s*」가 된다), 안 쓰는 편이 안전하다. */
const LEAD_EMOJI = new RegExp(`^(${EMOJI.source}+)`, 'u')
export const leadEmoji = (s: string) => LEAD_EMOJI.exec(s.trimStart())?.[1] ?? ''

export function todayISO() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 목록용 — 브레이크가 있어도 바깥 범위 하나로 줄인다. */
export const brief = (h: Range[]) => `${h[0].open}–${h[h.length - 1].close}`
/** 상세용 — 구간을 전부 보여준다. */
export const full = (h: Range[]) => h.map((x) => `${x.open}–${x.close}`).join(', ')

/** 영업시간 표시. 상태를 판정하지 않고 시간만 적는다.
 *
 *  전에는 오늘이면 지금 시각과 견주어 「영업중 · N분 뒤 닫음 · 닫힘」을 붙였다.
 *  그 판정 때문에 now·isToday 가 화면 전체로 흐르고, 못 가는 곳을 아래로 미는
 *  정렬까지 딸려 있었다. 시각을 지키는 것은 사람이 할 일이라 전부 걷어냈다.
 */
export function hoursText(place: Place | undefined): string | null {
  if (!place) return null
  // 고를 시각이 정해진 자리는 적힌 그대로 적는다 — 여닫는 시각이 아니다
  if (place.hoursPick?.length) return place.hoursPick.join(', ') + ' 중 선택'
  if (place.closed) return '휴무'
  if (place.always) return '24시간'
  const h = place.hours
  return h && h.length ? brief(h) : null
}

/** 주소에서 도메인만. 어디로 나가는지 보이면 그만이고,
 *  긴 주소는 메모를 반 넘게 차지한다. */
export const host = (u: string) =>
  u.replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/.*$/, '')

export const gmapSearch = (q: string) =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q + ' 일본')}`

/** 구글맵에서 '그 장소' 를 연다. place_id 가 있으면 동명이인으로 새지 않는다. */
export function gmapPlace(p?: { name?: string; gid?: string }) {
  if (!p) return null
  const q = new URLSearchParams({ api: '1', query: (p.name ?? '') + ' 일본' })
  if (p.gid) q.set('query_place_id', p.gid)
  return `https://www.google.com/maps/search/?${q}`
}

/* 무엇을 타느냐를 구글의 이동수단으로 옮긴다.
   구글에는 항공 길찾기가 없다 — 그래도 사람이 「길찾기」라 적었으면 뜻이 있는
   것이므로 대중교통으로 연다. 공항까지 가는 길이라도 알려 주는 편이 낫다. */
const TRAVEL: Record<string, string> = {
  car: 'driving', walk: 'walking',
  bus: 'transit', train: 'transit', plane: 'transit',
}

/** 구글 지도 길찾기를 연다. 앱이 깔려 있으면 앱이 받는다.
 *
 *  끝을 넣는 방식이 셋이고, 정확한 것부터 쓴다.
 *    좌표가 있으면       'lat,lng' (+ place_id 가 있으면 함께)
 *    place_id 만 있으면  이름 + place_id
 *    글자뿐이면          그대로. 역·공항은 이름이 오히려 정확하다
 *
 *  좌표를 이름보다 앞에 둔다. place_id 를 함께 넘기면 그것이 이길 줄
 *  알았는데 아니었다 — 구글은 글자 쪽을 먼저 찾고, 못 찾으면 place_id 로
 *  넘어가지 않고 그대로 멈춘다. 「리치몬드호텔 아오모리」가 그랬다.
 *  지도에 없는 한글 표기라 아오모리는커녕 서울을 띄우고
 *  「찾을 수 없습니다」로 끝났다. 좌표로 바꾸니 같은 자리가 바로 열린다.
 *
 *  그래서 어떤 이동은 되고 어떤 이동은 안 되는 것이었다 —
 *  「니가타 공항」처럼 한글 표기가 지도에 있는 곳만 살아남았다.
 *
 *  출발지가 없으면 넣지 않는다. 빠뜨린 것이 아니라, 그때는 구글이
 *  「내 위치에서」로 여는 것이 맞는 답이다. */
export function gmapDir(leg: Leg) {
  const d = leg.dir
  if (!d?.to) return null
  const q = new URLSearchParams({ api: '1' })
  const put = (k: 'origin' | 'destination', e: LegEnd) => {
    const at = e.lat != null ? `${e.lat},${e.lng}` : ''
    q.set(k, at || e.text)
    // 좌표만으로도 열리지만, 있으면 함께 넘겨 그 가게를 콕 집는다
    if (e.gid) q.set(`${k}_place_id`, e.gid)
  }
  if (d.from) put('origin', d.from)
  put('destination', d.to)
  const mode = TRAVEL[leg.mode]
  if (mode) q.set('travelmode', mode)
  return `https://www.google.com/maps/dir/?${q}`
}

export function initialDayIndex(trip: Trip) {
  const hash = location.hash.match(/d=(\d{4}-\d{2}-\d{2})/)
  if (hash) {
    const i = trip.days.findIndex((d) => d.date === hash[1])
    if (i >= 0) return i
  }
  const t = todayISO()
  const i = trip.days.findIndex((d) => d.date === t)
  return i >= 0 ? i : 0
}

export const legsByFrom = (day: Day) => {
  const m = new Map<string, Day['legs']>()
  for (const l of day.legs) {
    const k = l.from ?? '__'
    m.set(k, [...(m.get(k) ?? []), l])
  }
  return m
}


/** 딴 것들을 한 줄에 잇는다. 사이는 중간점이다.
 *
 *  띄어쓰기만으로 이으면 「HOT PEPPER ¥3,500 현지 결제」처럼 서로 다른 셋이
 *  한 문장처럼 읽힌다 — 어디까지가 예약처이고 어디부터가 금액인지 눈이
 *  가르지 못한다. 시트도 이미 중간점을 쓰고 있다(「문신있어도 괜찮은 온천 · 880엔」).
 *  빈 것은 셈에 넣지 않으므로 중간점이 홀로 남지 않는다. */
export const dots = (...xs: (string | null | undefined | false)[]) =>
  xs.filter(Boolean).join(' · ')


/* ── 예약 ──────────────────────────────────────────────── */

/** 예약 상자의 둘째 줄 — 어디서 잡았나 · 어떻게 내나 · 얼마인가.
 *  첫 줄은 시트의 「예약 내용」이 그대로 선다. 인원도 거기 적혀 있으므로
 *  따로 캐내지 않는다 — 캐내던 때는 「3인」이 두 줄에 겹쳐 섰다. */
export const resvMeta = (r: Reservation) => {
  // '-' 는 적을 것이 없다는 뜻이므로 띄우지 않는다
  const pay = r.pay && r.pay !== '-' ? r.pay : null
  // 금액은 시트에 적힌 그대로다. 숫자 하나로 줄이면 뜻이 달라진다 —
  // 「3,500엔+700엔(1인)」 은 뒤엣것이 통째로 사라지고,
  // 「(1인)」 을 떼면 1인당이라는 뜻이 사라진다.
  const money = r.costText || (r.costJpy ? yen(r.costJpy) : null)
  return dots(r.booker, pay, money)
}

