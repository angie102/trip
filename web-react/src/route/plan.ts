import book from './stops.json'
import paths from './paths.json'

/* 하루의 동선을 되감아 본다.
 *
 *  지도는 그날의 자리를 한꺼번에 뿌린다. 열 개가 흩어져 있으면 어디서
 *  어디로 갔는지는 안 보인다 — 아침에 어디를 들르고 저녁에 어디로 넘어가는지가
 *  일정표에는 적혀 있는데 지도에는 없다. 그것을 시간 순으로 한 번 훑어 주는 것이
 *  여기서 하는 일이다.
 *
 *  **일정을 읽지 않는다.**
 *
 *  전에는 여기서 trip.json 을 헤집어 항목마다 자리를 골랐다 — 후보가 여럿이면
 *  예약된 것을 먼저, approx 는 빼고, 이름이 없으면 버리고. 그 규칙이 전부
 *  도구로 옮겨 갔고 이 파일은 이제 두 데이터만 읽는다.
 *
 *      stops.json   자리들. 이 파일이 정본이고 사람이 손으로 고친다
 *      paths.json   자리 사이를 잇는 길 (tools/make_paths.py)
 *
 *  갈라 두는 까닭은 동선이 일정에서 저절로 나오지 않기 때문이다. 후보 셋 중
 *  첫째가 실제로 갈 집이라는 보장이 없고, 공항처럼 일정에 좌표가 없는 자리도
 *  동선에는 있어야 한다.
 *
 *  한때 도구가 일정에서 자리를 뽑아 주었지만 지금은 그러지 않는다. 손으로
 *  넣은 자리가 쉰 넘게 쌓여서, 다시 뽑으면 157 자리가 102 로 줄어 그것들이
 *  통째로 날아갔다. 이제 stops.json 을 따로 기르고 시트는 보지 않는다.
 *
 *  그래서 이 파일은 지도도 일정도 모른다. 좌표를 받아 시각표를 만들고
 *  「t 밀리초일 때 어디에 있나」를 답할 뿐이다.
 *
 *  일정 앱(src/)의 것을 하나도 쓰지 않는다. types.ts 도 lib.ts 도 trip.json 도
 *  건드리지 않고, 그래서 저쪽이 바뀌어도 여기는 흔들리지 않는다.
 */

export type LatLng = { lat: number; lng: number }

/** 하루에 들르는 한 자리. */
type Stop = {
  /** 화면에 나가지 않는다. route.json 을 사람이 고칠 때 어느 줄이 어디인지
   *  알아보라고 함께 적어 둔 것이고, 검증할 때도 이것으로 짚는다. */
  name: string
  /** 화면에 띄울 때 name 대신 쓸 이름.
   *
   *  「ANA 크라운 플라자 니가타 호텔」처럼 긴 이름이 그대로 뜨면 읽히지
   *  않으므로, 그런 자리에만 「니가타」처럼 짧게 적어 둔다. 없으면 name 이
   *  그대로 뜬다 — 적는 것은 덮어쓰기이지 켜고 끄는 것이 아니다. */
  label?: string
  at: LatLng
  /** 하루의 매듭에서만 뜨는 이름(「3일 차」).
   *
   *  label 과 따로 둔다. 한 자리가 두 가지로 불리기 때문이다 — 그리로
   *  향해 갈 때는 「카쿠다하마」이고, 닿아서 서 있는 동안은 「3일 차」다.
   *  하나로 합쳐 두었더니 오는 길 내내 「3일 차」가 떠 있었다. */
  dayLabel?: string
}

type StopRow = { name: string; at: [number, number]; label?: string }
type PathRow = { a: [number, number]; b: [number, number]; line: string } | null

const BOOK = book as unknown as Record<string, StopRow[]>
const PATHS = paths as unknown as Record<string, PathRow[]>

/** 적혀 있는 날짜들. 이르는 날부터.
 *  일정에서 받아 오지 않는다 — 키가 곧 날짜라 여기서 다 안다. */
export const allDates = (): string[] => Object.keys(BOOK).sort()

/** 그날의 자리들. 적혀 있지 않은 날은 빈 목록이다. */
function routeOf(date: string): Stop[] {
  return (BOOK[date] ?? []).map((r) => ({
    name: r.name,
    label: r.label,
    at: { lat: r.at[0], lng: r.at[1] },
  }))
}

/* ── 길 ────────────────────────────────────────────────
 *
 *  구글이 쓰는 encoded polyline 이다. 좌표를 1e5 배 정수로 만들어 앞 점과의
 *  차이만 적고, 그 차이를 5비트씩 잘라 아스키로 옮긴 것 — 스물여섯 점이
 *  백 자 남짓에 들어간다. 서식이 공개돼 있어 푸는 데 라이브러리가 필요 없다.
 */
function decode(s: string): LatLng[] {
  const out: LatLng[] = []
  let lat = 0, lng = 0, i = 0
  while (i < s.length) {
    let shift = 0, res = 0, b = 0
    do { b = s.charCodeAt(i++) - 63; res |= (b & 0x1f) << shift; shift += 5 }
    while (b >= 0x20)
    lat += res & 1 ? ~(res >> 1) : res >> 1
    shift = 0; res = 0
    do { b = s.charCodeAt(i++) - 63; res |= (b & 0x1f) << shift; shift += 5 }
    while (b >= 0x20)
    lng += res & 1 ? ~(res >> 1) : res >> 1
    out.push({ lat: lat / 1e5, lng: lng / 1e5 })
  }
  return out
}

/** 구운 길이 지금 자리의 것인가.
 *
 *  route.json 을 손으로 고치고 길을 다시 굽지 않으면 선이 엉뚱한 데를 지난다.
 *  그럴 때는 조용히 틀리기보다 직선으로 물러서는 편이 낫다 — 길이 안 보이는
 *  것은 눈에 띄지만, 그럴듯한 길이 딴 데로 뻗는 것은 알아채기 어렵다. */
const isAt = (p: [number, number], q: LatLng) =>
  Math.abs(p[0] - q.lat) < 1e-6 && Math.abs(p[1] - q.lng) < 1e-6

/** 그날 구간마다의 길. 없거나 어긋난 구간은 null 이고, 그때는 직선으로 잇는다. */
function pathsOf(date: string, stops: Stop[]): (LatLng[] | null)[] {
  const n = Math.max(0, stops.length - 1)
  const rows = PATHS[date]
  if (!rows || rows.length !== n) return Array(n).fill(null)
  return rows.map((row, i) => {
    if (!row) return null
    if (!isAt(row.a, stops[i].at) || !isAt(row.b, stops[i + 1].at)) return null
    const pts = decode(row.line)
    return pts.length >= 2 ? pts : null
  })
}

/* ── 언제 어디에 있는가 ──────────────────────────────── */

/** 두 자리 사이 킬로미터. 하버사인이다 — 위도 40도에서 경도 1도는
 *  위도 1도의 0.77 배라, 좌표 차를 그냥 제곱해 더하면 동서 거리가 부풀려진다. */
export function km(a: LatLng, b: LatLng): number {
  const R = 6371, rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

/* 재생이 얼마나 걸리는가.
 *
 *  한 구간을 실제 거리에 그대로 비례시키면 못 쓴다. 9.22 는 한 구간이
 *  178km(신칸센)이고 나머지가 1km 안팎이라, 비례로 두면 신칸센이 재생의
 *  99% 를 먹고 앞뒤 자리는 순간이동한다.
 *
 *  그래서 두 가지를 건다.
 *    · 그날 안에서의 상대 거리로 잰다. 하루가 다 도보권인 날(9.19)에도
 *      구간마다 길이 차가 나야 「가까운 데 들렀다 먼 데 갔다」가 보인다
 *    · 제곱근으로 누른다. 178km 대 0.3km 가 24 배에서 2.6 배로 좁혀져,
 *      멀리 간 것은 멀리 간 대로 읽히되 짧은 구간도 눈에 남는다
 *
 *  재는 것은 직선이 아니라 길의 길이다. 크게 돌아가는 구간은 그만큼 오래
 *  걸려야 「돌아서 갔다」가 읽힌다.
 *
 *  총 이동 시간은 고정이다. 어느 날을 틀어도 비슷한 길이로 끝나야
 *  「재생」이라는 몸짓이 예측된다. 다만 구간이 적은 날까지 12 초를 채우면
 *  한 구간이 하염없이 길어지므로, 구간 수에 따라 짧아지게 둔다. */
const MOVE_PER_LEG = 3200     // 구간이 적은 날은 이만큼씩만 쓴다
/* 가장 짧은 구간도 가장 긴 것의 이만큼은 쓴다.
 *
 *  화면에서 얼마나 빨리 흐르는가로 재야 한다. 0.6 으로 두었을 때는 인천에서
 *  니가타까지 1115km 를 0.9초에 가로질렀는데, 그 배율에서 화면 폭의 78% 를
 *  0.9초에 지나는 셈이라 지도가 타일을 받아 올 겨를이 없었다.
 *
 *  0.03 까지 낮춘다. 먼 구간과 가까운 구간의 시간 차이가 열 배에서 서른세
 *  배로 벌어져, 「멀리 갔다」가 시간으로도 읽힌다 — 인천에서 니가타까지가
 *  4.8초에서 15.3초가 되고 화면 흐름은 583% 에서 183% 로 느려진다.
 *
 *  짧은 구간은 0.5초 남짓으로 줄지만 자리마다 0.4초씩 머무므로(TRIP 의
 *  dwell) 지나치는 자리가 눈에서 사라지지는 않는다. */
const FLOOR = 0.03

/** 거리를 시간으로 옮길 때의 굽힘.
 *
 *  1 이면 거리에 그대로 비례한다 — 그러면 1115km 한 구간이 마흔네 초를
 *  먹고 0.03km 짜리는 0초가 된다(4만 3천 배). 볼 수 있는 그림이 아니다.
 *
 *  0.5(제곱근)는 반대로 너무 눌렀다. 1115 대 1 의 거리 차가 33 대 1 로
 *  줄고, 거기에 바닥값까지 더해져 먼 구간이 「멀다」고 느껴지지 않았다.
 *
 *  0.7 이 그 사이다. 다만 이대로 두면 가까운 걸음이 뭉개지므로 아래의
 *  MIN_LEG 가 바닥을 깐다 — 굽힘은 「멀수록 오래」를 말하고, 바닥은
 *  「아무리 가까워도 이만큼은」을 말한다. */
const GAMMA = 0.7

/** 열닷새를 통째로 훑는 데 쓰는 시간.
 *
 *  처음에 42초로 두었더니 눈이 따라가기 바빴다. 사람이 화면 한가운데
 *  붙박여 있어 배경이 흐르는 꼴인데, 그 흐름이 빠르면 어디를 지나는지
 *  읽히지 않는다. 이동에 여든 초를 준다.
 *
 *  **머무는 시간은 배율이 자리를 잡는 시간이다.**
 *
 *  110ms 로 두었을 때는 「줌을 미리 하는 느낌」이었다. 화면이 앞을 0.4초
 *  내다보며 배율을 맞추는데(View 의 AHEAD) 머무는 시간이 그보다 훨씬
 *  짧으니, 아직 자리를 안 떴는데 줌만 먼저 움직였다.
 *
 *  400ms 면 내다보는 창이 머무는 사이에 들어앉는다 — 자리에 닿고, 머무는
 *  동안 다음 구간에 맞춰 배율이 갈아타고, 그러고서 떠난다. 배율이 바뀌는
 *  몫이 이동 중에서 머무는 때로 옮겨 간다(초당 0.36 → 0.33 과 0.10 → 0.23).
 *
 *  덤으로 지역이 당겨진다. 머무는 동안은 속도가 0 이라 속도 창의 평균이
 *  내려가고, 그만큼 좁게 담기기 때문이다 — 아오모리가 11.7 에서 13.3 으로
 *  올라온 것은 확대를 따로 시켜서가 아니라 머물러서다.
 *
 *  값은 아흔한 자리에 곱해진다. 400ms 면 머무는 데만 36초라 통째로는
 *  129초가 된다. 여기서 더 늘리려면 그 셈을 먼저 볼 것. */
/** 어느 구간도 이보다 빨리 지나가지 않는다(ms).
 *
 *  거리에 견주어 시간을 나누면 가까운 걸음이 뭉개진다. 가장 먼 구간이
 *  1115km 라 5km 짜리는 몫이 0.047 뿐이고, 그 길을 0.46초에 지나갔다 —
 *  화면으로는 초당 네 폭이 흐르는 셈이라 눈이 따라잡지 못한다.
 *
 *  1.8초를 바닥으로 깐다. 먼 구간은 이 값에 걸리지 않으므로 그대로고
 *  (거기는 지금 빠르기가 알맞다), 가까운 걸음만 느긋해진다 —
 *  화면 흐름이 초당 443% 에서 222% 로 준다.
 *
 *  1.3초가 아니라 1.8초인 데는 까닭이 있다. 화면이 속도를 재는 창이
 *  앞뒤로 1.3초인데(View 의 BACK+AHEAD), 구간이 그보다 짧으면 그 구간의
 *  빠르기가 이웃과 섞여 제대로 잡히지 않는다 — 폭이 실제 속도를 못 따라가
 *  화면만 빨리 흐른다. 창보다 길어야 그 구간이 제 값으로 읽힌다.
 *
 *  바닥에 걸린 구간은 예산을 올려도 그대로다. 그래서 이 둘이 서로
 *  간섭하지 않는다 — 바닥은 가까운 걸음의 빠르기를 정하고, 예산(move)은
 *  먼 이동의 빠르기를 정한다. 예산을 70초에서 140초로 올렸을 때
 *  가까운 구간은 1.80초로 붙박여 있고 먼 구간만 3.3초에서 6.5초가 된다.
 *
 *  1.5초로 내리면 가까운 걸음이 다시 빨라진다(244% → 322%). */
const MIN_LEG = 1800

/** 어느 구간도 이보다 오래 끌지 않는다(ms).
 *
 *  거리에 견주어 나누면 인천에서 니가타까지 1115km 가 열여덟 초를 먹는다.
 *  그 열여덟 초 동안 화면에는 바다밖에 없다 — 지나온 자취를 보는 화면에서
 *  아무 자리도 없는 데를 그렇게 오래 지날 까닭이 없다.
 *
 *  여덟 초로 끊는다. 담는 폭이 넓어 화면은 느긋하게 흐르고(초당 5% 남짓),
 *  니가타가 가까워지며 저절로 좁혀 든다. */
const MAX_LEG = 8000

const TRIP = { move: 140000, dwell: 400, floor: FLOOR,
               minLeg: MIN_LEG, maxLeg: MAX_LEG }


/** 재생을 누르고 첫 걸음을 떼기까지. 여느 자리에 머무는 시간의 다섯 배다.
 *
 *  눌러 놓고 화면을 찾는 데도 한 박자가 걸린다. 그 사이에 이미 떠나 버리면
 *  「어디서 시작하는 여정인가」를 놓친다. 이 값은 한 번만 쓰이므로
 *  통째로는 1.6초가 늘 뿐이다. */
const START_HOLD = 2000

/** 하루가 끝나고 다음 날로 넘어갈 때 쉬는 참(ms).
 *
 *  열닷새가 한 줄로 이어져 있어 어디서 하루가 끝나는지 알 수 없었다.
 *  숙소에 닿아 한 번 쉬고 다시 나서면 그 이음매가 읽힌다 — 날짜 알약이
 *  바뀌는 것도 그 참에 눈에 들어온다.
 *
 *  그 자리에 머무는 시간(dwell, 400ms)에 얹히므로 통틀어 2초다.
 *  떠나는 자리에 서는 START_HOLD 와 같은 길이로 둔다 — 둘 다 이름표를
 *  읽고 지나가라는 참이고, 하루의 매듭에 적어 둔 「4일 차」는 그
 *  자리에서만 뜬다. 900ms 로 두었을 때는 읽기 전에 이미 떠났다. */
const DAY_PAUSE = 1600

export type Leg = {
  /** stops 의 인덱스 */
  from: number
  to: number
  /** 길을 따라 잰 거리. 직선 구간이면 곧 직선거리다 */
  km: number
  /** 재생 시각(ms). start 에 출발해 end 에 닿는다 */
  start: number
  end: number
  /** 지나는 길. 직선이면 두 점뿐이다. 양 끝은 늘 자리의 좌표다 */
  path: LatLng[]
  /** path[i] 까지 온 만큼(0..1). 진행률로 지금 점을 찾는 데 쓴다 */
  acc: number[]
}

type Plan = {
  stops: Stop[]
  legs: Leg[]
  total: number
  /** 여정의 길 전부를 한 줄로. 다 보고 물러설 때 시야를 맞추는 데 쓴다 */
  whole: LatLng[]
}

/** 구간 하나가 지나는 길.
 *
 *  받아 온 길의 양 끝은 도로에 붙여진 자리라 마커에서 비켜 있다. 그대로 두면
 *  사람이 마커 옆에서 출발해 마커 옆에서 멈춘다 — 양 끝을 제 자리로 못 박는다. */
function legPath(a: LatLng, b: LatLng, road: LatLng[] | null): LatLng[] {
  if (!road) return [a, b]
  const out = [...road]
  /* 양 끝을 제 자리로 못 박는다. 멀면 덧대고 가까우면 갈아 끼운다 —
     가까울 때 그냥 두었더니 선의 끝이 마커에서 5m 어긋난 채 끝났다.
     지도에서 몇 픽셀이지만, 「저 자리에 닿았다」를 말하는 선이 자리에
     안 닿아 있으면 그만큼 말이 흐려진다. */
  if (km(a, out[0]) * 1000 > 5) out.unshift(a)
  else out[0] = a
  const last = out.length - 1
  if (km(b, out[last]) * 1000 > 5) out.push(b)
  else out[last] = b
  return out
}

/** 여러 구간의 길을 한 줄로 잇는다.
 *  구간의 끝점은 다음 구간의 첫점과 같으므로 한 번만 넣는다. */
export const join = (legs: Leg[]): LatLng[] =>
  legs.reduce<LatLng[]>(
    (out, leg) => out.concat(out.length ? leg.path.slice(1) : leg.path), [])

/** 시각표를 짠다. 첫 자리에서 한 번 머문 뒤 움직이기 시작한다.
 *
 *  @param roads 구간마다의 길. null 인 자리는 직선으로 잇는다
 *  @param pace  이동에 쓸 총 시간과 자리마다 머무는 시간 */
function planRoute(stops: Stop[], roads: (LatLng[] | null)[],
                          pace = TRIP): Plan {
  const { move: MOVE_MAX, dwell: DWELL, floor = FLOOR,
          minLeg = MIN_LEG, maxLeg = MAX_LEG } = pace
  if (stops.length < 2) {
    return { stops, legs: [], total: stops.length ? DWELL : 0,
             whole: stops.map((s) => s.at) }
  }

  // 길을 먼저 짓고 그 길이로 시간을 나눈다
  const shapes = stops.slice(1).map((s, i) => {
    const path = legPath(stops[i].at, s.at, roads[i])
    const steps = path.slice(1).map((p, j) => km(path[j], p))
    const len = steps.reduce((a, b) => a + b, 0)
    // 누적을 0..1 로. 길이가 0 이면(같은 자리) 0 으로 나누지 않게 1 로 둔다
    const acc = [0]
    let run = 0
    for (const d of steps) { run += d; acc.push(len > 0 ? run / len : 1) }
    return { path, acc, len }
  })

  const far = Math.max(...shapes.map((s) => s.len))
  // 그날이 통째로 한 점에 가까우면 나눌 잣대가 없다. 다 같은 무게로 둔다.
  const weights = shapes.map((s) =>
    far > 0 ? floor + (1 - floor) * Math.pow(s.len / far, GAMMA) : 1)
  const sum = weights.reduce((a, b) => a + b, 0)
  const budget = Math.min(MOVE_MAX, MOVE_PER_LEG * shapes.length)

  const legs: Leg[] = []
  /* 첫 자리에는 오래 선다.
     여느 자리와 같은 400ms 를 두었더니 「인천공항 제2여객터미널」이 눈에
     닿기 전에 사라졌다 — 재생을 누른 그 순간이라 눈이 아직 사람을 찾고
     있는데, 0.4초 뒤에는 이름표가 벌써 「니가타」로 바뀌어 있었다.
     떠나는 자리가 어디인지는 그 여정에서 한 번만 말할 수 있다. */
  let t = START_HOLD
  shapes.forEach((s, i) => {
    const span = Math.min(maxLeg, Math.max(minLeg, (budget * weights[i]) / sum))
    legs.push({ from: i, to: i + 1, km: s.len, start: t, end: t + span,
                path: s.path, acc: s.acc })
    t += span + DWELL                 // 닿으면 또 한 번 머문다
  })

  return { stops, legs, total: t, whole: join(legs) }
}


/** 열닷새를 하나로 이은 시각표.
 *
 *  날마다 앞뒤에 묵는 곳을 넣어 두어서 그날 마지막 자리와
 *  다음 날 첫 자리가 같은 곳이다 — 열넷이 다 그렇다. 그래서 겹치는 자리를
 *  하나씩만 남기면 여정이 끊기지 않는 선 하나가 된다.
 *
 *  날이 언제 바뀌는지도 함께 준다. 화면 아래에 지금 며칠인지 띄우는 데 쓴다. */
type TripPlan = Plan & {
  /** 그 날이 시작하는 자리의 번호. days[i].at 번째 자리부터가 그 날이다 */
  days: { date: string; at: number }[]
}

export function planTrip(dates: string[] = allDates(), pace = TRIP): TripPlan {
  const stops: Stop[] = []
  const roads: (LatLng[] | null)[] = []
  const days: { date: string; at: number }[] = []

  for (const date of dates) {
    const mine = routeOf(date)
    if (!mine.length) continue
    const lanes = pathsOf(date, mine)
    // 앞의 날과 맞닿은 자리는 한 번만 넣는다. 그 사이에는 이을 길도 없다
    const seam = stops.length > 0
      && km(stops[stops.length - 1].at, mine[0].at) * 1000 < 10
    /* 합칠 때는 새 날의 이름표가 이긴다.
     *
     *  앞엣것만 남기던 때는 하루의 첫 자리에 적어 둔 「4일 차」가 통째로
     *  버려졌다 — 그 자리가 전날의 마지막 자리이기도 해서다. 남은 것은
     *  전날 도착할 때의 이름(「카쿠다하마」)이었다.
     *
     *  그리로 오는 동안 이미 그 이름이 떠 있었다(이동 중에는 닿을 곳의
     *  이름을 보여준다). 닿아서 서 있는 동안에는 날이 바뀐다는 것이 더
     *  할 말이 많다 — 열닷새를 한 번에 훑는 화면에서 하루의 매듭이
     *  그것밖에 없기 때문이다. */
    if (seam && mine[0].label) stops[stops.length - 1].dayLabel = mine[0].label
    days.push({ date, at: stops.length - (seam ? 1 : 0) })
    stops.push(...(seam ? mine.slice(1) : mine))
    if (!seam && stops.length > mine.length) roads.push(null)   // 벌어진 자리는 직선
    roads.push(...lanes)
  }
  const plan = planRoute(stops, roads, pace)

  /* 날이 바뀌는 자리마다 쉼표를 찍는다. 그 자리에 닿은 뒤로 뒤엣것을 통째로
     미는 것이라, 구간의 길이는 그대로 두고 사이만 벌어진다. */
  const opens = new Set(days.map((d) => d.at))
  let shift = 0
  for (const leg of plan.legs) {
    leg.start += shift
    leg.end += shift
    if (opens.has(leg.to)) shift += DAY_PAUSE
  }
  return { ...plan, total: plan.total + shift, days }
}

/* ── 지금 이 순간 ────────────────────────────────────── */

export type Frame = {
  /** 사람이 서 있는 자리 */
  at: LatLng
  /** 지금 지나는 구간의 번호.
   *
   *  지나온 길을 통째로 돌려주지 않고 이것만 준다. 마흔두 초가 지나면 길이
   *  천육백 점인데 그것을 프레임마다 지도에 다시 넘기면 초당 십만 점이다 —
   *  지도가 타일을 그릴 겨를이 없어 화면이 덜 그려지고 느려진다.
   *
   *  이 번호가 바뀔 때만 지나온 길이 늘어난다. 그때 한 번 pathUpto 로 만들어
   *  두면 그 사이 프레임들은 아래의 now 만 갈아 끼우면 된다. */
  leg: number
  /** 그 구간에서 온 만큼. 마지막 점이 곧 지금 자리라 선의 끝이 사람을 따라온다.
   *  한 구간의 길이라 길어야 예순 점 남짓이다 */
  now: LatLng[]
  /** 사람 위에 띄울 글자. 지나온 자리 중 마지막으로 라벨이 붙은 것이다.
   *
   *  「그 자리의 이름」이 아니라 「지금 어디쯤인가」다. 닿을 때만 떴다 지면
   *  마흔두 초 동안 깜빡임이 잦아 읽히지 않는다 — 한 번 뜨면 다음 라벨을
   *  만날 때까지 머문다. */
  label?: string
}

/** 멈출 때와 떠날 때를 부드럽게. 등속으로 두면 지점마다 딱딱 끊겨
 *  「이동」이 아니라 「순간이동을 여러 번」으로 보인다. */
const ease = (x: number) =>
  x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2

const lerp = (a: LatLng, b: LatLng, k: number): LatLng => ({
  lat: a.lat + (b.lat - a.lat) * k,
  lng: a.lng + (b.lng - a.lng) * k,
})

/** 구간의 길을 k(0..1)만큼 갔을 때. 지금 자리와, 이미 지나친 점의 개수를 준다.
 *
 *  누적 길이(acc)를 훑어 지금이 어느 마디인지 찾고 그 안에서만 보간한다.
 *  마디마다 길이가 다르므로 「점 개수의 k 배」로 세면 짧은 마디에서 굼뜨고
 *  긴 마디에서 튄다 — 길이로 재야 고르게 흐른다. */
function along(leg: Leg, k: number): { at: LatLng; past: number } {
  const { path, acc } = leg
  if (k <= 0) return { at: path[0], past: 1 }
  /* 다 왔을 때 past 가 path.length 이면 마지막 점까지 「지나친 것」이 되는데,
     그 점이 곧 지금 자리라 선에 두 번 들어간다 — 프레임이 넘어갈 때 선이
     한 점 줄어드는 것으로 드러났다. 마지막 점의 자리는 at 이 맡는다. */
  if (k >= 1) return { at: path[path.length - 1], past: path.length - 1 }
  let i = 1
  while (i < acc.length - 1 && acc[i] < k) i++
  const span = acc[i] - acc[i - 1]
  const at = lerp(path[i - 1], path[i], span > 0 ? (k - acc[i - 1]) / span : 0)
  return { at, past: i }
}

/** 재생 시각 t 일 때의 상태. */
/** 그 자리에 띄울 글자. 짧게 적어 둔 것이 있으면 그것, 없으면 이름 그대로.
 *
 *  한때 라벨을 적은 자리만 띄우고 그것을 다음 라벨까지 물고 갔다 —
 *  「지금 어느 고장인가」를 말하려던 것이다. 그러나 보고 싶은 것은
 *  「지금 어디를 지나는가」였다. 자리마다 이름이 바뀌는 편이 그 물음에 맞는다. */
function nameAt(stops: Stop[], at: number, resting = false): string | undefined {
  const s = stops[Math.max(0, Math.min(at, stops.length - 1))]
  // 서 있는 동안에만 하루의 매듭을 말한다. 걸어가면서 「3일 차」라고
  // 하면 그 이름이 향하는 자리를 가리키는 것처럼 읽힌다
  if (resting && s?.dayLabel) return s.dayLabel
  return s?.label ?? s?.name
}

/** 그 구간 앞까지 지나온 길. 구간이 넘어갈 때 한 번만 부르면 된다. */
export function pathUpto(plan: Plan, leg: number): LatLng[] {
  return join(plan.legs.slice(0, Math.max(0, leg)))
}

export function frameAt(plan: Plan, t: number): Frame {
  const { stops, legs } = plan
  if (!stops.length) return { at: { lat: 0, lng: 0 }, leg: 0, now: [] }
  if (!legs.length) {
    return { at: stops[0].at, leg: 0, now: [stops[0].at], label: nameAt(stops, 0) }
  }

  for (let i = 0; i < legs.length; i++) {
    const leg = legs[i]
    if (t >= leg.end) continue
    /* 떠난 자리가 아니라 향하는 자리를 띄운다. 길 위에서 궁금한 것은
       「어디서 왔나」가 아니라 「어디로 가나」다. 머무는 동안에는 방금 닿은
       자리가 곧 향하는 자리이므로 둘이 같아진다. */
    const resting = t < leg.start
    const label = nameAt(stops, resting ? leg.from : leg.to, resting)
    // 아직 떠나지 않았다 — 출발지에 머무는 중
    if (t < leg.start) return { at: stops[leg.from].at, leg: i, now: [], label }
    const { at, past } = along(leg, ease((t - leg.start) / (leg.end - leg.start)))
    return { at, leg: i, now: [...leg.path.slice(0, past), at], label }
  }
  // 다 왔다
  const last = legs[legs.length - 1]
  return { at: stops[stops.length - 1].at, leg: legs.length - 1,
           now: last.path, label: nameAt(stops, stops.length - 1) }
}
