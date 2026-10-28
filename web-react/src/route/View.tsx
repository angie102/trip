import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { allDates, frameAt, km, pathUpto, planTrip, type LatLng } from './plan'
import type { Canvas } from './canvas'
import { mount } from './gmap'      // ← 지도를 갈아끼우려면 이 한 줄만 바꾼다
import { loadWalker, samples, saveWalker, shrink } from './walkers'
import './style.css'

/* 열닷새를 한 줄로 되감아 본다.
 *
 *  일정과 아무것도 나누지 않는다. 저쪽 지도는 「어디를 갈까」를 고르는 자리라
 *  마커가 서고 목록이 따라 움직이고 짚은 것이 이름을 편다. 이쪽은 「어디를
 *  다녔나」를 한 번 보는 자리다 — 고를 것이 없으니 마커도 이름도 없다.
 *
 *  **소스가 갈라져 있다.**
 *
 *  이 폴더(src/route)는 일정 앱(src/)의 것을 하나도 쓰지 않는다 —
 *  types.ts 도 lib.ts 도 icons.tsx 도 styles.css 도, 무엇보다 trip.json 을
 *  읽지 않는다. 날짜조차 stops.json 의 키에서 얻는다. 나누어 쓰는 것은 딱
 *  하나, 지도 열쇠(config.local.ts)다 — 코드가 아니라 자격증명이라 두 벌로
 *  두면 한쪽만 바뀌어 어긋난다.
 *
 *  갈라 둔 것은 소스이지 화면의 자리가 아니다. 일정 앱 안에서 준비 화면과
 *  같은 갈래로 산다 — 날짜 줄은 그대로 있고 그 아래만 갈린다. 나가는 길도
 *  같다: 날짜를 누르면 일정으로 돌아간다. 그래서 제 닫기 단추를 두지 않는다.
 *
 *  **지도도 갈라져 있다.**
 *
 *  이 파일에 google.maps 는 한 글자도 없다. 지도에게 시키는 일은 canvas.ts 의
 *  다섯 가지뿐이고, 그것을 무엇으로 그리는지는 gmap.ts 가 안다. 구글을 떠나려면
 *  같은 꼴로 파일 하나를 더 쓰고 위의 import 를 돌리면 된다.
 */

/** 「10월 2일」. 열닷새가 모두 2026년이라 해는 적을 자리가 없다.
 *
 *  일정 쪽은 「10.2」로 줄여 쓴다 — 날짜 칩 열다섯 개가 한 줄에 서야 하기
 *  때문이다. 여기는 한 번에 하나만 뜨므로 줄일 까닭이 없고, 점 하나로 가른
 *  숫자보다 「월」과 「일」이 붙은 쪽이 지도 위에서 날짜로 먼저 읽힌다. */
const ymd = (iso: string) => `${+iso.slice(5, 7)}월 ${+iso.slice(8, 10)}일`

/* ── 어디를 담을까 ─────────────────────────────────────
 *
 *  사람이 늘 한가운데 있으므로 중심은 정할 것이 없다. 정하는 것은 줌뿐이고,
 *  그것은 그 날이 얼마나 넓은가를 따른다.
 *
 *  여백은 사방을 같게 둔다. 사람이 가운데 서는 화면이라 위아래가 다르면
 *  그만큼 사람이 가운데에서 밀린다 — 아래 모서리의 재생 단추와 날짜는
 *  지도 위에 떠 있고 사람은 한복판이라 서로 가리지 않는다.
 */
const PAD = { top: 48, bottom: 48, left: 48, right: 48 }

/* 다 보고 난 뒤 열닷새를 한눈에 보여 줄 때만, 인천을 잘라 낸다.
 *
 *  인천이 서쪽으로 1100km 나가 있어 다 담으면 가로 1369km · 세로 584km 가
 *  되는데, 세로로 긴 화면에 그 비율을 담으면 일본이 가운데 가느다란 띠로
 *  눌린다. 인천을 빼면 295 × 584km 라 세로 화면에 꼭 맞는다.
 *
 *  잘라 내는 자는 백분율이 아니다. 「경도 아래쪽 3%」로 잘랐더니 카루이자와까지
 *  나갔다 — 세는 것이 자리(아흔둘)가 아니라 길 위의 점(천육백)이라, 3% 가
 *  마흔아홉 점이었기 때문이다.
 *
 *  옳은 자는 「가장 크게 벌어진 곳」이다. 인천과 일본 사이가 11.9 도로 전체
 *  폭의 여덟 할을 차지하는데 다른 어디에도 그만한 틈이 없다. 그 틈에서 끊으면
 *  버려지는 점은 인천 하나다. 틈이 그만큼 크지 않은 여정이라면 아무것도
 *  자르지 않는다 — 자를 것이 없다는 뜻이다.
 */
const FAR_GAP = 0.3

function corePoints(pts: LatLng[]): LatLng[] {
  const lngs = [...new Set(pts.map((p) => p.lng))].sort((a, b) => a - b)
  let cut = lngs[0], widest = 0
  for (let i = 1; i < lngs.length; i++) {
    const gap = lngs[i] - lngs[i - 1]
    if (gap > widest) { widest = gap; cut = lngs[i] }
  }
  const span = lngs[lngs.length - 1] - lngs[0]
  const west = widest > span * FAR_GAP ? cut : lngs[0]
  return pts.filter((p) => p.lng >= west)
}

/* ── 얼마나 넓게 볼까 ──────────────────────────────────
 *
 *  카메라는 사람을 따라간다. 그러면 화면이 얼마나 빨리 흐르는지가 문제가
 *  되는데, 구간을 화면에 꽉 채우면 0.6초에 한 폭이 지나간다 — 초당 167%다.
 *  지도가 타일을 받아 올 수 있는 속도가 아니다.
 *
 *  풀 곳은 속도가 아니라 배율이다. 빠른 구간은 넓게, 느린 구간은 가깝게
 *  보면 화면에서는 같은 빠르기로 흐른다. 신칸센이 초당 641km 라도 2100km 를
 *  담으면 골목을 걷는 것과 다르지 않게 보인다.
 *
 *  그래서 담을 폭을 이동 속도로 정한다 — 「초당 화면의 36% 만 흐르게 하려면
 *  얼마를 담아야 하는가」. 아흔한 구간이 좁은 띠 안으로 모인다(전에는 6~167%).
 *
 *  30% 로 두었더니 지역이 멀찍했다. 자리마다 머무는 텀이 생겨(plan 의 dwell)
 *  이동 중에 배율을 손볼 일이 줄었으므로, 그만큼 더 당겨도 화면이 따라온다 —
 *  하치노헤 11.9→12.4, 도쿄 14.1→14.2. 더 올리면 화면이 빨리 흘러
 *  타일이 못 따라온다. */
const TARGET = 0.36          // 초당 화면의 이만큼만 흐르게
/* 아무리 느려도 이보다 좁게 당기지 않는다(km).
 *
 *  4 로 두었더니 자오 온천처럼 하루가 2.6km 안에서 끝나는 날에도 그 절반만
 *  차서 멀찍했다. 1.5 로도 모자랐다 — 자오는 구간이 0.78~1.07km 라 화면에
 *  담을 것이 1km 남짓인데 1.5km 를 담고 있었다.
 *
 *  1.0 이면 그 걸음이 화면을 채운다. 여기서 더 당기는 데는 배율 한계
 *  (gmap 의 MAX_ZOOM, 15)가 먼저 걸린다 — 그 위는 건물이 하나씩
 *  그려지기 시작하는 자리라 움직이며 보기에는 무겁다. */
const MIN_SPAN = 1.0
/* 아무리 빨라도 이보다 넓게 물러서지 않는다(km).
 *
 *  2600 으로 두었을 때는 신칸센 구간에서 화면이 온 나라를 담았다. 그러면
 *  「먼 데를 지난다」는 알겠지만 사람은 점이 되고, 시내로 돌아올 때마다
 *  배율이 아홉 단을 오르내려 정신이 없다.
 *
 *  먼 거리를 다 담을 까닭이 없다. 조금만 물러서고 사람을 따라가면 그 자체가
 *  「쭉 이동한다」는 그림이다.
 *
 *  40 으로 두었더니 아사무시 온천으로 가는 14km 길에도 40km 를 담아,
 *  가까운 데를 가면서 멀찍이 물러서 있었다. 24 로 좁혔어도 그날은 여전히
 *  줌 11.2 까지 물러섰다 — 아오모리와 아사무시를 잇는 14km 를 통째로
 *  담으려 했기 때문이다.
 *
 *  그래서 12 까지 좁혀 보았지만, 그러면 신칸센으로 삼백 킬로를 갈 때도
 *  12km 만 담아 화면이 초당 스물일곱 폭씩 흘렀다. 가까운 데를 지킨 값으로
 *  먼 데를 망친 것이다.
 *
 *  두 요구는 한 값으로 못 푼다 — 가까운 걸음은 당기고 먼 이동은 물러서야
 *  하니, 값 하나가 아니라 **둘 사이의 벌어짐**을 키워야 한다. 그 벌어짐을
 *  막고 있던 것은 이 상한이 아니라 아래의 PEAK_MIX 였다(거기 적어 두었다).
 *
 *  **끝내 이 값이 비례를 깨고 있었다.**
 *
 *  담을 폭은 v / TARGET 이다 — 그대로 두면 화면은 어디서나 초당 36% 로
 *  흐른다. 40 은 그 셈을 잘랐다. 오미야에서 야마가타까지 268km 를 5.3초에
 *  가면 초당 50km 라 140km 를 담아야 하는데 40 에서 끊기니, 화면이 겨눔의
 *  세 배 반으로 흘렀다. 인천-니가타는 스무 배였다.
 *
 *  400 이면 이 여정의 어느 걸음도 잘리지 않는다(가장 빠른 인천-니가타가
 *  387km 를 부른다). 잘리지 않으면 비례가 저절로 지켜지므로, 「하늘길은
 *  따로」 같은 예외도 필요 없어진다 — 그 규칙은 이 자리에서 걷어냈다.
 *
 *  넓게 담아도 사람이 점이 되지는 않는다. 그 폭은 그 순간의 빠르기가 부른
 *  것이라, 화면에서 사람은 늘 같은 걸음으로 움직인다. */
const MAX_SPAN = 400


/* 속도를 구간이 아니라 시간의 창으로 잰다.
 *
 *  구간마다 재어 두고 그 사이를 이었더니 두 군데서 어긋났다. 구간 안에서도
 *  빠르기가 고르지 않고(멈출 때와 떠날 때를 부드럽게 하느라 한복판이 빠르다),
 *  구간이 0.6초뿐이라 배율을 옮길 참이 너무 짧았다 — 4km 에서 1077km 로
 *  0.2초에 물러서면 한 프레임에 줌이 통째로 튄다.
 *
 *  지금 자리의 앞뒤 1.2초를 함께 보면 그 둘이 한꺼번에 풀린다. 창이 겹치며
 *  흐르므로 배율도 저절로 이어지고, 구간의 경계라는 것이 사라진다. */
const SAMPLE = 100           // 이 간격으로 재어 둔다(ms)

/* 창은 앞뒤가 다르다.
 *
 *  앞뒤로 똑같이 2.5초를 보았더니 니가타 시내를 걷는 동안에도 줌이 자꾸
 *  물러섰다 — 2.5초 뒤에 있을 큰 이동이 창에 들어와, 가장 빠른 순간으로
 *  잡는 셈이 그 한 번에 끌려간 탓이다.
 *
 *  지나온 쪽은 짧게 본다. 1초로 두었더니 도쿄 도심이 화면에 2.9km 씩
 *  담겼다 — 오미야에서 도쿄까지 32km 를 온 여파가 도심 첫 자리까지 창에
 *  걸려 있었던 탓이다. 0.6초면 큰 이동을 그만큼 빨리 잊어 골목 걸음(0.03~
 *  5km)에 맞춰 당긴다(배율 13.0 → 13.4). 잔떨림은 아래의 고르기(SMOOTH)가
 *  맡으므로 창까지 넓힐 까닭이 없다.
 *
 *  다가올 쪽은 멀리 본다.
 *
 *  0.7초로 두었을 때는 큰 이동이 닥쳐서야 배율을 넓히기 시작했다. 배율은
 *  초당 0.4단으로 묶여 있으므로(gmap 의 ZOOM_RATE) 세 단을 넓히는 데
 *  7.5초가 걸리는데, 0.7초 전에 알아서는 제때 닿을 수가 없다 — 폭이 못
 *  따라간 채로 이동이 끝나고, 그 사이 화면만 미친 듯이 흘렀다.
 *
 *  3.5초를 내다보면 천천히 넓혀도 제때 닿는다. 화면 흐름이 하늘길에서
 *  초당 6892% → 275%, 먼 구간에서 1015% → 275% 로 떨어진다.
 *
 *  시내가 손해 보지 않느냐 하면, 오히려 나아진다(83% → 54%). 멀리 보는
 *  것은 「언제 넓힐까」를 일찍 아는 일이지 「지금 넓게 보라」가 아니고,
 *  그 판단은 평균이 하므로 먼 이동 하나에 끌려가지 않는다(PEAK_MIX 0). */
const BACK = 600            // 지나온 쪽(ms)
const AHEAD = 3500           // 다가올 쪽(ms)

/** 시각마다 화면에 담을 폭(km)을 미리 재어 둔다. SAMPLE 간격의 배열이다.
 *
 *  창의 두 끝을 곧게 이어 재면 안 된다. 그 안에서 갔다 돌아오는 자리가
 *  있으면(야히코를 들렀다 카쿠다하마로 되돌아오는 날처럼) 두 끝이 가까워
 *  「거의 안 움직였다」로 나오고, 그 좁은 배율에서 실제 걸음이 화면을
 *  열두 배 속도로 가로지른다.
 *
 *  그래서 조각조각 이어 잰다 — 먼저 자리를 촘촘히 찍고, 이웃한 두 자리
 *  사이를 다 더한 것이 그 창에서 실제로 지난 길이다. */
function buildSpans(plan: ReturnType<typeof planTrip>): number[] {
  const pos: LatLng[] = []
  for (let t = 0; t <= plan.total + SAMPLE; t += SAMPLE) pos.push(frameAt(plan, t).at)

  const step: number[] = []           // step[i] = pos[i] → pos[i+1] 거리
  for (let i = 1; i < pos.length; i++) step.push(km(pos[i - 1], pos[i]))


  /* 평균과 가장 빠른 순간 사이를 잡는다.
   *
   *  평균으로 두면 그 창에서 딱 30% 가 되지만, 창 안에 느린 데와 빠른 데가
   *  섞여 있으면 빠른 쪽이 넘친다 — 평균 31% 인데 어떤 순간은 272% 였다.
   *  그렇다고 가장 빠른 순간에 맞추면 나머지가 다 답답해진다(평균 7%).
   *
   *  둘 사이 마흔다섯 몫에 둔다. 빠른 데가 튀지 않을 만큼은 물러서되,
   *  느린 데를 쓸데없이 넓게 보지는 않는다 — 예순으로 두었을 때는 시내를
   *  걷는 동안에도 창에 든 한 번의 빠른 순간에 끌려 물러섰다. */
  /* 재어 둔 폭을 한 번 더 고른다.
   *
   *  창으로 재는 것만으로는 걸음이 바뀌는 자리에서 값이 툭 튄다 — 배율을
   *  눈금으로 끊어 두면 그 튐이 「덜그럭」으로 보인다. 이웃한 값들을 섞어
   *  매끄럽게 만들면 눈금 없이 흘려도 흔들리지 않는다. */
  const SMOOTH = 4            // 앞뒤로 이만큼씩 섞는다 (0.4초)
  /* 가장 빠른 순간을 얼마나 섞을까.
   *
   *  0.45 로 두었더니 도쿄·자오·하치노헤에서 시내를 걷는 내내 물러서 있었다.
   *  그런 날은 시내 걸음(0.03~5km) 앞뒤에 큰 이동(32·39km)이 붙어 있어,
   *  창에 그것이 조금이라도 걸리면 가장 빠른 순간이 그 값으로 잡히기 때문이다.
   *
   *  0.2 로 낮춰도 남아 있었다. 창(뒤 0.6 + 앞 0.7 = 1.3초)이 구간 하나의
   *  길이(평균 1.28초)와 거의 같아, 시내 걸음의 창에 이웃한 큰 이동이 **늘**
   *  걸리기 때문이다. 조금만 섞여도 「가장 빠른 순간」은 그쪽으로 잡힌다.
   *
   *  0 으로 둔다. 평균만 보면 가까운 걸음과 먼 이동이 서로를 끌지 않아
   *  둘 사이가 벌어진다 — 가까운 데 13.1→13.4, 먼 데 11.5→10.5(벌어짐
   *  1.7→2.8). 「가까운 건 당기고 먼 건 물러서라」는 것이 이 벌어짐이다.
   *
   *  급가속을 놓치지 않느냐 하면, 그것은 앞을 내다보는 창(AHEAD)이 맡는다 —
   *  0.7초 뒤의 큰 이동은 평균에도 잡히므로 닿기 전에 물러서기 시작한다. */
  const PEAK_MIX = 0
  const back = Math.round(BACK / SAMPLE)
  const fwd = Math.round(AHEAD / SAMPLE)
  const perSec = SAMPLE / 1000
  const raw = pos.map((_, i) => {
    let peak = 0, run = 0, n = 0
    for (let j = Math.max(0, i - back); j < Math.min(step.length, i + fwd); j++) {
      if (step[j] > peak) peak = step[j]
      run += step[j]
      n++
    }
    const avg = n > 0 ? run / n : 0
    const v = (avg + (peak - avg) * PEAK_MIX) / perSec
    return Math.max(MIN_SPAN, Math.min(MAX_SPAN, v / TARGET))
  })

  // 이웃한 값들을 섞어 모서리를 없앤다
  return raw.map((_, i) => {
    let sum = 0, n = 0
    for (let j = Math.max(0, i - SMOOTH); j <= Math.min(raw.length - 1, i + SMOOTH); j++) {
      sum += raw[j]
      n++
    }
    return sum / n
  })
}

/** 그 시각의 폭. 재어 둔 두 값 사이를 곧게 잇는다. */
function spanAt(spans: number[], t: number): number {
  const x = Math.max(0, Math.min(t / SAMPLE, spans.length - 1))
  const i = Math.floor(x)
  const j = Math.min(i + 1, spans.length - 1)
  return spans[i] + (spans[j] - spans[i]) * (x - i)
}

/* ── 아이콘 ────────────────────────────────────────────
   셋뿐이라 여기 둔다. 일정 쪽 icons.tsx 를 가져다 쓰면 그 파일이 바뀔 때마다
   이 화면이 따라 흔들린다 — 갈라 둔 뜻이 그것이다.
   규격은 같다: 24 격자 · 획 2 · 둥근 끝. */
const GLYPH = {
  // 사람 — 걸어갈 그림을 고르는 단추
  skin: 'M12 12.5a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4ZM5.5 19.5a6.5 6.5 0 0 1 13 0',
  play: 'M8.5 5.8v12.4a1 1 0 0 0 1.53.85l9.7-6.2a1 1 0 0 0 0-1.7l-9.7-6.2a1 1 0 0 0-1.53.85z',
  pause: 'M9.5 6v12M14.5 6v12',
  back: 'M15 5.5 8.5 12l6.5 6.5',
}

function Ic({ d, round }: { d: string; round?: boolean }) {
  return (
    <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden
         style={{ display: 'block', flex: 'none' }}>
      <path d={d} stroke="currentColor" strokeWidth={2} strokeLinecap="round"
            strokeLinejoin={round ? 'round' : undefined} />
    </svg>
  )
}

export default function View({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<Canvas | null>(null)
  const raf = useRef(0)
  const clock = useRef(0)
  /** 지나온 길. 구간이 넘어갈 때만 다시 만든다 — 프레임마다 천육백 점을
   *  새로 이으면 지도가 타일을 그릴 겨를이 없다 */
  const done = useRef<{ leg: number; pts: LatLng[] }>({ leg: -1, pts: [] })


  const [playing, setPlaying] = useState(false)
  /** 지날 화면을 미리 훑는 중. 그 사이 지도를 감춰 둔다 —
   *  스물한 화면이 3초 만에 지나가는 것은 볼 것이 아니라 채비다 */
  const [warming, setWarming] = useState(true)
  const [dead, setDead] = useState(false)
  /** 지금 지나는 날. 바뀔 때만 다시 그린다 — 사람이나 선과 달리 초당
   *  예순 번 갈아 끼울 것이 아니다 */
  const [today, setToday] = useState('')
  /** 걸어갈 그림. 지난번에 고른 것이 있으면 그것으로 연다 */
  const [skin, setSkin] = useState<string | null>(() => loadWalker())
  /** 고르는 판이 열려 있나 */
  const [picking, setPicking] = useState(false)
  /** 날짜 고르는 판이 열려 있나 */
  const [jumping, setJumping] = useState(false)
  /** 올리다 잘못된 것. 판 안에 한 줄로 띄운다 */
  const [oops, setOops] = useState('')

  /* 고른 그림을 지도에 물려준다.
     지도가 늦게 서므로(mount 가 약속이다) 세워진 뒤와 고른 뒤 둘 다에서
     불러야 한다 — 한쪽만 보면 「열자마자는 기본, 고쳐야 바뀜」이 된다. */
  useEffect(() => { canvas.current?.setWalker(skin) }, [skin, warming])

  /* 고를 그림들. 판을 열 때 짓는다 — 색을 .routeview 에서 읽어 오므로
     화면이 선 뒤라야 제 먹빛이 나온다(walkers.ts 의 ink). */
  const picks = useMemo(() => (picking ? samples() : []), [picking])

  const plan = useMemo(() => planTrip(allDates()), [])
  /** 시각마다 담을 폭. 한 번 재어 두고 프레임마다 꺼내 쓴다 */
  const spans = useMemo(() => buildSpans(plan), [plan])

  /** 날짜를 눌러 건너뛸 자리. 그 날 첫 자리에 **닿은** 시각이다.
   *
   *  자리 번호(days[i].at)를 시각으로 바꾼다 — 시각표는 구간의 목록이고
   *  날짜는 자리로 적혀 있어, 둘을 잇는 자리가 여기다.
   *
   *  떠나는 시각(leg.start)이 아니라 닿는 시각(leg.end)을 쓴다. 그 자리에
   *  서 있는 동안에만 「10일 차」가 뜨는데(plan.ts 의 dayLabel), 떠나는
   *  시각으로 건너뛰면 그 참을 지나쳐 이미 다음 자리로 걷고 있었다 —
   *  하루의 첫머리를 보러 온 사람이 그 첫머리만 못 보는 셈이었다.
   *
   *  첫 날은 닿을 구간이 없다. 여정의 처음이므로 0 이다. */
  const jumps = useMemo(() => plan.days.map((d) => {
    const back = plan.legs.find((l) => l.to === d.at)
    return { date: d.date, at: back ? back.end : 0 }
  }), [plan])

  /** 날짜 줄. 지금 보는 날이 화면 밖에 있으면 밀어 준다 */
  const daysBox = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!jumping) return
    // 열닷새가 한 줄이라 오늘이 오른쪽 끝에 숨어 있을 수 있다. 재생 중이면
    // 날이 바뀔 때마다 따라 민다 — 고른 날이 어디쯤인지가 늘 보여야 한다.
    daysBox.current?.querySelector('[data-on]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [jumping, today])

  /** 날짜 판에 쓸 달별 묶음. 「9월 → 18 19 20 …」 꼴이다. */
  const months = useMemo(() => {
    const out: { label: string; days: typeof jumps }[] = []
    for (const j of jumps) {
      const label = `${Number(j.date.slice(5, 7))}월`
      const last = out[out.length - 1]
      if (last && last.label === label) last.days.push(j)
      else out.push({ label, days: [j] })
    }
    return out
  }, [jumps])

  /** 그 시각이 어느 날인가. 자리 번호로 찾는다. */
  const dayAt = useCallback((t: number) => {
    const i = plan.legs.findIndex((leg) => t < leg.end)
    const at = i >= 0 ? plan.legs[i].from : plan.stops.length - 1
    let found = plan.days[0]?.date ?? ''
    for (const d of plan.days) if (d.at <= at) found = d.date
    return found
  }, [plan])

  /** 한 프레임. React 를 거치지 않는다 — 지도만 움직인다. */
  const paint = useCallback((t: number) => {
    const c = canvas.current
    if (!c) return
    const f = frameAt(plan, t)
    /* 프레임마다 움직이는 것은 사람과 선뿐이다. 카메라는 아래에서 화면이
       넘어갈 때만 옮긴다 — 둘은 지도가 함께 그리므로 어긋나지 않는다. */
    c.walker(f.at, f.label)
    if (done.current.leg !== f.leg) {
      done.current = { leg: f.leg, pts: pathUpto(plan, f.leg) }
    }
    c.trail(done.current.pts, f.now)

    /* 카메라는 사람을 따라간다. 얼마나 넓게 볼지는 앞뒤 1.2초의 빠르기가
       정한다 — 창이 앞을 함께 보므로, 니가타가 가까워지면 아직 바다 위일 때
       이미 시내 배율로 좁혀지기 시작한다. */
    c.follow(f.at, spanAt(spans, t))
    setToday((cur) => {
      const next = dayAt(t)
      return next === cur ? cur : next
    })
  }, [plan, dayAt])

  // 지도를 세우고 선을 깐다. 다 받으면 첫 자리를 그려 두고 선다 —
  // 재생은 사람이 누를 때 시작한다.
  useEffect(() => {
    let gone = false
    if (!box.current) return
    mount(box.current).then((c) => {
      if (gone) return c.destroy()
      canvas.current = c
      /* 지날 자리를 한 번 훑어 타일을 받아 두고 시작한다. 이것이 없으면
         화면이 넘어갈 때마다 회색 바탕이 먼저 오고 지도가 나중에 온다. */
      /* 지날 자리를 띄엄띄엄 훑어 타일을 받아 둔다. 아흔한 구간을 다 훑으면
         여는 데만 열넷 초라, 다섯에 하나씩 열여덟 자리만 본다. */
      const step = Math.max(1, Math.round(plan.total / SAMPLE / 18))
      const shots: { at: LatLng; span: number }[] = []
      for (let i = 0; i < spans.length; i += step) {
        shots.push({ at: frameAt(plan, i * SAMPLE).at, span: spans[i] })
      }
      c.warm(shots).then(() => {
        if (gone) return
        // 첫 자리를 그려 두고 선다. 재생은 사람이 누를 때 시작한다 —
        // 들어서자마자 흐르면 무엇을 볼지 마음을 정하기 전에 지나가 버리고,
        // 걸어갈 그림을 고르는 일(왼쪽 아래)도 멈춰 세운 뒤에야 할 수 있다.
        paint(0)
        setWarming(false)
      })
    }).catch(() => setDead(true))
    return () => { gone = true }
  }, [plan, paint])

  // 재생. playing 이 켜져 있는 동안만 시계가 흐른다.
  useEffect(() => {
    if (!playing) return
    /* 기준 시각은 첫 프레임이 알려 준다.
     *
     *  performance.now() 로 미리 잡아 두었더니 시계가 뒤로 갔다.
     *  rAF 가 넘겨주는 시각은 「그 프레임이 시작된 때」인데, 누름을 받아
     *  React 가 그리고 이 자리에 닿기까지가 이미 그 프레임 안이면
     *  넘겨받는 값이 지금보다 이르다 — 13ms 를 뒤로 감았다.
     *
     *  그 13ms 가 하루의 매듭을 거슬러, 날짜를 옮겨 두고 재생을 누르면
     *  전날 자리의 이름표가 한 프레임 스쳤다. 첫 프레임에서는 시간이
     *  흐르지 않은 것으로 치면 그럴 일이 없다. */
    let last: number | null = null
    // 시계가 돌기 전에 지금 자리를 한 번 그려 둔다
    paint(clock.current)
    const step = (now: number) => {
      if (last === null) last = now
      clock.current += now - last
      last = now
      if (clock.current >= plan.total) {
        clock.current = plan.total
        paint(plan.total)
        setPlaying(false)
        return
      }
      paint(clock.current)
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [playing, plan, paint])

  useEffect(() => () => {
    cancelAnimationFrame(raf.current)
    canvas.current?.destroy()
  }, [])

  /* 다 보고 나면 물러서서 열닷새를 한눈에 보여 준다.
   * 하루씩 따라오던 눈이 마지막에 여정 전체를 본다. */
  useEffect(() => {
    if (playing || clock.current < plan.total) return
    const c = canvas.current
    if (!c) return
    const core = corePoints(plan.whole)
    // 여기서만 중심도 옮긴다. 사람은 마지막 자리에 서 있고, 보여 줄 것은
    // 여정 전체라 그 한가운데로 물러선다
    c.fit(core, PAD)
    // 사람은 물러선다. 한가운데는 이제 여정의 한복판이지 사람의 자리가 아니다
    c.walker(plan.stops[plan.stops.length - 1].at, undefined, false)
  }, [playing, plan])

  /** 그 날의 첫 걸음으로 건너뛴다.
   *
   *  지나온 길을 다시 깐다 — 시계만 옮기면 앞서 그려 둔 자취가 그대로 남아
   *  「간 적 없는 데를 이미 지난」 그림이 된다. done 을 비워 두면 다음 프레임이
   *  그 자리까지의 길을 새로 잇는다.
   *
   *  재생 중이었으면 그대로 이어 간다. 서 있었으면 그 자리에 세워 둔다 —
   *  날짜를 고른 것은 「거기서부터 보겠다」이지 「지금 재생하라」가 아니다. */
  const jumpTo = (ms: number) => {
    clock.current = ms
    done.current = { leg: -1, pts: [] }
    paint(ms)
    setJumping(false)
  }

  /** 다 본 뒤에 누르면 처음부터, 아니면 이어서 */
  const toggle = () => {
    if (playing) return setPlaying(false)
    if (clock.current >= plan.total) {
      clock.current = 0
      done.current = { leg: -1, pts: [] }   // 지나온 길도 처음으로
    }
    setPlaying(true)
  }

  return (
    <div className="routeview">
      <div className={'rvmap' + (warming ? ' is-warm' : '')} ref={box} />
      {warming && <p className="rvwarm">지도를 받는 중</p>}

      {dead ? (
        <p className="rvdead">지도를 열지 못했다</p>
      ) : warming ? null : (
        <>
          {/* 날짜는 막대 위에 따로 뜬다. 막대 안에 끼워 두었을 때는 단추와
              한 덩어리로 보여 「누르는 것」쪽으로 읽혔는데, 이것은 누르는 것이
              아니라 지금이 며칠인지 말해 주는 표시다. 알약 하나로 떼어 놓으면
              그 뜻이 꼴에서 먼저 읽힌다.

              걷는 동안에만 뜬다. 서 있을 때의 날짜는 「지금 며칠을 지나는가」가
              아니라 「어디서 멈춰 섰는가」라 할 말이 다르고, 다 보고 물러선
              뒤에는 열닷새가 한 화면에 있으므로 하루를 짚을 까닭이 없다. */}
          {today && (
            <button className="rvday" onClick={() => setJumping(true)}
                    aria-label={`${ymd(today)} — 날짜 고르기`}>
              {ymd(today)}
            </button>
          )}

          {jumping && (
            <div className="rvsheet" onClick={() => setJumping(false)}>
              <div className="rvsheetbox" onClick={(e) => e.stopPropagation()}>
                {/* 제목을 적지 않는다. 날짜만 늘어놓으면 무엇을 고르는 자리인지
                    꼴로 읽힌다 — 누른 것이 날짜 알약이었으므로 손이 기억한다.

                    한 줄로 밀어 본다. 달마다 줄을 나누면 10월이 두 칸짜리
                    줄 하나를 차지해 판이 헐거워지는데, 이어 붙이면 열닷새가
                    한 흐름으로 읽힌다 — 여정이 실제로 그렇게 이어진다. */}
                <div className="rvdays" ref={daysBox}>
                  {months.map((m) => (
                    <div className="rvmonth" key={m.label}>
                      <p className="rvmonthname">{m.label}</p>
                      <div className="rvrow">
                        {m.days.map((j) => (
                          <button key={j.date}
                                  data-on={j.date === today || undefined}
                                  className={'rvdaypick' + (j.date === today ? ' on' : '')}
                                  onClick={() => jumpTo(j.at)}
                                  aria-pressed={j.date === today}>
                            {Number(j.date.slice(8))}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 나가는 길. 왼쪽 위에 홀로 선다 — 재생을 누르는 손과 멀리
              두어야 보다가 잘못 눌러 나가지 않는다. */}
          <button className="rvback" onClick={onClose} aria-label="뒤로">
            <Ic d={GLYPH.back} round />
          </button>

          {/* 재생과 멈춤. 들어올 때 누른 그 자리에 그대로 선다 —
              화면이 바뀌었다고 단추가 옮겨 다니면 손이 다시 찾아야 한다. */}
          <button className="rvplay" onClick={toggle} aria-pressed={playing}
                  aria-label={playing ? '멈춤' : '재생'}>
            <Ic d={playing ? GLYPH.pause : GLYPH.play} round={!playing} />
          </button>

          {/* 걸어갈 그림 고르기. 왼쪽 아래다 — 재생(오른쪽 아래)과 대각선으로
              마주 서서, 자주 누르는 것과 한 번 정하고 마는 것이 섞이지 않는다. */}
          <button className="rvskin" onClick={() => { setOops(''); setPicking(true) }}
                  aria-label="걸어갈 그림 고르기">
            <Ic d={GLYPH.skin} round />
          </button>

          {picking && (
            /* 판 밖을 눌러도 닫힌다. 고르는 일은 되돌릴 것이 없어
               「취소」라는 단추를 따로 둘 까닭이 없다. */
            <div className="rvsheet" onClick={() => setPicking(false)}>
              {/* 제목을 적지 않는다. 그림 넷과 올리기 단추만 놓이면
                  「고르는 자리」라는 것이 꼴로 이미 읽힌다 — 누른 단추가
                  사람 모양이었으므로 무엇을 고르는지도 손이 기억한다. */}
              <div className="rvsheetbox" onClick={(e) => e.stopPropagation()}>
                <div className="rvskins">
                  {picks.map((w) => (
                    <button key={w.id}
                            className={'rvskinpick' + (skin === w.src ? ' on' : '')}
                            onClick={() => {
                              setSkin(w.src)
                              saveWalker(w.src)
                              setPicking(false)   // 고른 순간 판을 접는다
                            }}
                            aria-pressed={skin === w.src} aria-label={w.name}>
                      {w.src
                        ? <img src={w.src} alt="" />
                        : <span className="rvskindot" />}
                    </button>
                  ))}
                  {/* 올린 것은 샘플 뒤에 한 자리로 선다. 여러 장을 쌓아 두지
                      않는다 — 고르는 자리이지 모아 두는 자리가 아니다. */}
                  {skin && !picks.some((w) => w.src === skin) && (
                    <button className="rvskinpick on" aria-pressed
                            aria-label="올린 그림">
                      <img src={skin} alt="" />
                    </button>
                  )}
                {/* 올리기는 그림들과 한 줄에, 오른쪽 끝에 선다.
                    고르는 일과 같은 갈래라 따로 떼어 아래에 두면 두 켜가 된다.
                    오른쪽 끝인 것은 그림이 늘어도 자리가 밀리지 않게 하려는 것이다. */}
                <label className="rvupload" aria-label="그림 올리기">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path d="M12 16V5m0 0L8 9m4-4 4 4M5 19h14" stroke="currentColor"
                          strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <input type="file" accept="image/*" onChange={async (e) => {
                    const f = e.target.files?.[0]
                    e.target.value = ''      // 같은 파일을 다시 골라도 열리게
                    if (!f) return
                    try {
                      const src = await shrink(f)
                      setSkin(src)
                      saveWalker(src)
                      setOops('')
                      setPicking(false)
                    } catch (err) {
                      setOops(err instanceof Error ? err.message : '올리지 못했습니다')
                    }
                  }} />
                </label>
                </div>
                {oops && <p className="rvoops">{oops}</p>}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
