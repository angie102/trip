/** export_web.py 가 내보내는 뷰 모델. 날짜 기준으로 이미 다 풀려 있다. */

export type Range = { open: string; close: string }

export type Place = {
  id: string
  // 후보들의 중점(approx)에는 이름이 없다 — 자리가 아니라 「대충 이쯤」이라
  // 부를 이름이 없다. 제목을 빌려 넣던 때는 그것이 장소로 보여 헛짚었다.
  name?: string
  lat?: number
  lng?: number
  gid?: string            // 구글 place_id — 딥링크에 붙이면 정확한 가게로 열린다
  address?: string
  hours?: Range[]         // 그 날짜 요일의 영업시간. 두 개면 브레이크 타임
  /** 고를 시각 — 료칸 조식·석식은 「18:00, 18:30 중 선택」처럼 정해져 있다 */
  hoursPick?: string[]
  closed?: true           // 그날 휴무 (추측이 아니라 구글이 준 사실)
  // 그날은 정기휴일인데 예약이 잡혀 있다. 휴무 표시 대신 여느 날 영업시간이
  // hours 에 들어온다 — 닫는 날이어도 나에게는 여는 집이다.
  byReservation?: true
  always?: boolean        // 24시간
  approx?: true           // 후보들의 중심이라 정확한 지점이 아님
  // 지도 마커의 종류. 구글이 준 업종(primaryType)을 여섯으로 묶은 값이고,
  // 예약이 잡힌 자리는 그 위를 'resv' 가 덮는다 — 업종이 아니라 약속이
  // 먼저 보여야 한다. 묶는 표는 tools/place_kinds.py 에 있다.
  kind?: 'resv' | 'food' | 'cafe' | 'shopping' | 'onsen' | 'place'
}

export type Reservation = {
  booker?: string           // 타베로그 · 테이블체크 · HOT PEPPER
  costJpy?: number         // 셈할 때 쓰는 첫 숫자
  costText?: string        // 엑셀 금액 칸에 적힌 그대로 — 화면은 이쪽
  pay?: string              // 「현지 결제」 등
  name?: string             // 예약한 집 이름
  note?: string
  /** 예약 확인서 파일 이름. 숙소의 것과 같은 자리(public/resv/)에 얹혀 있다 */
  doc?: string
}

export type Spot = {
  /** 이 집으로 예약이 잡혀 있다 */
  reserved?: boolean
  name: string              // 읽는 이름 (한글·영문)
  nameJa?: string           // 원어 이름 — 상세에서 둘째 줄
  depth: number
  group?: true            // 아래에 후보를 거느린 묶음 제목
  note?: true             // 장소가 아닌 메모
  desc?: string
  /** 시트에 <https://…> 로 적어 둔 주소 */
  link?: string
  cost?: string             // 엑셀 금액 칸에 적힌 그대로 — 셈하지 않는다
  reservation?: Reservation
  place?: Place
}

export type Item = {
  id: string
  type: string
  title: string
  time: string | null
  end: string | null
  detail?: string
  detailJa?: string
  detailDesc?: string       // 확정된 곳의 설명 — 후보의 desc 와 같은 것
  fixed?: true              // 노란 칸 = 지켜야 하는 시각 (예약·렌터카)
  /** 괄호로 감싼 시각 — 시간축에는 앉히되 화면에는 띄우지 않는다 */
  hideTime?: true
  cost?: string             // 엑셀 금액 칸에 적힌 그대로 — 셈하지 않는다
  covered?: boolean
  /** 메모에 <https://…> 로 적어 둔 주소 */
  link?: string
  notes?: string[]
  reservation?: Reservation
  tasks?: string[]        // '***' 로 적은 할 일. 메모(notes)와 다른 것이다
  image?: string          // '{이미지}' 표식이 가리킨 안내도
  place?: Place
  /** 고를 후보가 아니라 갈 곳이 정해진 목록 — '따로 먹기' */
  settled?: boolean
  spots?: Spot[]
}

/** 길찾기의 한쪽 끝.
 *
 *  좌표가 없어도 글자만으로 열 수 있다 — 역·공항은 오히려 이름이 정확하다.
 *  Place 를 재활용하지 않는 까닭이 둘이다. Place.id 가 필수인데 글자뿐인 끝에는
 *  id 가 없고, Place 에는 영업시간·휴무처럼 길 찾는 데 쓸모없는 것이 딸려 온다.
 *
 *  여기 실린 좌표는 지도 마커에 쓰지 않는다. 이름으로 푼 끝이 섞여 있어서다 —
 *  틀린 길찾기는 구글 지도가 열려 눈앞에 보이지만, 틀린 마커는 점 하나로
 *  조용히 찍힌다. 자세한 까닭은 export_web.py 의 leg_end 에 적어 두었다. */
export type LegEnd = {
  /** 화면에 쓰는 이름이자 링크의 마지막 기댈 곳 */
  text: string
  lat?: number
  lng?: number
  gid?: string              // 구글 place_id — 동명이인으로 새지 않는다
}

export type Leg = {
  /** 가는 길에 들를 곳 */
  spots?: Spot[]
  id: string
  mode: string
  modeLabel: string
  title: string
  vehicle: string           // 무엇을 타는가 (리무진 버스, 야마가타 신칸센 츠바사…)
  time: string | null
  end: string | null
  from: string | null
  to: string | null
  min: number | null
  cost: string | null
  covered: boolean
  fixed?: boolean
  dest: string | null
  origin: string | null
  notes: string[]
  image: string | null      // 엑셀 셀에 붙어 있던 그림 (승강장 안내도 등)
  /** '지정석' 시트에서 붙인 열차 예약. 좌석까지 잡았으면 그 차를 놓치면 안 된다 */
  /** '***' 로 적은 할 일. 항목의 것과 같은 뜻이고 자리만 이동 곁이다 */
  tasks?: string[]
  seat?: { train: string; seat: string; span: string; from: string; to: string }
  /** 시트에 「길찾기」라 적어 둔 경로만 갖는다. 있다는 것이 곧 버튼을 단다는 뜻이라
   *  따로 켜고 끄는 값을 두지 않는다. 출발지는 없을 수 있다 — 빼면 「내 위치에서」다 */
  dir?: { from?: LegEnd; to: LegEnd }
}

/** 체크리스트 한 건.
 *
 *  image 만 있고 text 가 빈 건이 있다 — 시트에 '*** {이미지}' 로 적어 둔
 *  자리다. 글자 대신 그림 한 장이 그 자리에 선다. */
export type Task = { due: string; text: string; detail?: string[]
                     image?: string; link?: string }

/** '준비' 시트 — 날짜가 없는 목록. 해야할 일 · 준비물 · 메모 */
export type PrepGroup = {
  name: string
  items: { text: string; note?: string }[]
}

export type Day = {
  date: string
  dow: string
  region: string | null
  stay: {
    name: string
    pay?: string            // 현지 결제 / 결제완료
    booker?: string         // 아고다 · 홈페이지 · 쟈란넷 …
    terms?: string          // 조식 포함 · 저녁,아침 포함 …
    costJpy?: number        // 현지 결제일 때만 — 아직 낼 돈
    /** 호텔의 자리. 체크인·체크아웃 항목은 좌표를 갖지 않으므로 여기가 유일하다 */
    place?: Place
    /** 예약 확인서 파일 이름. public/resv/ 아래에 그대로 얹혀 있다 */
    doc?: string
  } | null
  flags: { kind: string; text: string; full?: string }[]
  items: Item[]
  legs: Leg[]
  moveMin: number
  bounds: { n: number; s: number; e: number; w: number } | null
  tasks: Task[]
}

export type Trip = {
  title: string
  passes: { id: string; name: string; days: number; from: string; to: string; priceJpy: number }[]
  checklist: Task[]
  prep: PrepGroup[]
  days: Day[]
}
