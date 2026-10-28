import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import raw from './data/trip.json'
import type { Place as PlaceT, Trip } from './types'
import { gmapPlace, gmapSearch, initialDayIndex, md, yen } from './lib'
import Map from './components/Map'
import DayList from './components/DayList'
import Checklist from './components/Checklist'
import RouteView from './route/View'
import Prep from './components/Prep'
import { Icon } from './components/icons'
import './styles.css'

const trip = raw as unknown as Trip

export default function App() {
  const [dayIdx, setDayIdx] = useState(() => initialDayIndex(trip))
  const [prep, setPrep] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [mapOpen, setMapOpen] = useState(false)   // 목록이 먼저다
  const [checklist, setChecklist] = useState(false)
  // 열닷새를 한 줄로 훑는 화면. 소스는 갈라져 있고(src/route) 화면만 위에 뜬다
  // 열닷새를 한 줄로 훑는 화면. 준비와 같은 갈래다 — 날짜 줄은 그대로 두고
  // 아래만 갈아 끼운다. 소스는 갈라져 있다(src/route)
  const [route, setRoute] = useState(false)
  const [mapDead, setMapDead] = useState(false)
  // 후보 하나를 지목한 자리. openId(항목 단위)로는 「야마신을 눌렀다」를 말할 수 없다
  const [focus, setFocus] = useState<PlaceT | null>(null)

  const dates = useRef<HTMLDivElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const day = trip.days[dayIdx]
  const dayTasks = day.tasks ?? []
  // 지도는 편 항목을 따라간다
  const selected = useMemo(
    () => day.items.find((i) => i.id === openId) ?? null,
    [day, openId],
  )

  useEffect(() => {
    history.replaceState(null, '', `#d=${day.date}`)
  }, [day.date])

  // ── 머리를 언제까지 붙여 둘 것인가 ────────────────────────
  //
  // sticky 는 부모 끝까지 무조건 붙어 있는 것이 전부라, 조건을 걸려면 재야 한다.
  //
  // 세 갈래다.
  //   ① 한 화면에 다 들어오는 항목 — 붙일 까닭이 없다. sticky 자체를 끈다
  //   ② 길고, 끝이 아직 멀다 — 붙어 있는다
  //   ③ 길고, 끝이 화면 6할까지 올라왔다 — 다 읽은 뒤라 살짝 올라가며 사라진다
  //
  // ① 을 따로 가르지 않으면 짧은 항목이 ③ 의 조건을 처음부터 만족해 버린다.
  // 붙은 적도 없는 머리가 투명해진다 — 「몇 할 지났는가」로 재면
  // 아직 아래를 읽는 중에 떨어지는 것과 함께, 이 화면에서 실제로 겪은 두 가지다.
  useEffect(() => {
    const box = body.current
    if (!box) return
    const TAIL = 0.6            // 끝이 화면 위에서 이만큼까지 올라오면 뗀다
    let raf = 0
    const measure = () => {
      raf = 0
      const c = box.getBoundingClientRect()
      for (const row of box.querySelectorAll<HTMLElement>('.row')) {
        const r = row.getBoundingClientRect()
        const tall = r.height > c.height          // 한 화면에 안 들어온다
        row.classList.toggle('nostick', !tall)
        row.classList.toggle('unstick', tall && r.bottom <= c.top + c.height * TAIL)
      }
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(measure) }
    measure()
    box.addEventListener('scroll', onScroll, { passive: true })
    addEventListener('resize', onScroll)
    return () => {
      box.removeEventListener('scroll', onScroll)
      removeEventListener('resize', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [dayIdx, prep, mapOpen])

  // 날짜를 바꾸면 목록도 처음으로. 스크롤이 남아 있으면 새 날의
  // 한복판부터 펼쳐져 아침 일정을 지나친 것처럼 보인다.
  useEffect(() => {
    body.current?.scrollTo({ top: 0 })
  }, [dayIdx, prep])

  // 고른 날짜를 가운데로. 양 끝 이틀은 브라우저가 경계에서 알아서 멈춘다.
  //
  // 스냅이 걸린 채로 부드럽게 옮기면 브라우저가 도중에 끊고 목적지로 튄다.
  // 옮기는 동안만 스냅을 끄고 돌려놓는다 — 손으로 미는 감은 그대로다.
  useEffect(() => {
    const lane = dates.current
    const el = lane?.querySelector<HTMLElement>('[aria-current="true"]')
    if (!lane || !el) return
    lane.style.scrollSnapType = 'none'
    el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
    const t = setTimeout(() => { lane.style.scrollSnapType = '' }, 360)
    return () => clearTimeout(t)
  }, [dayIdx, prep])

  // 한 번에 하나만 편다 — 여럿이 열려 있으면 훑기 어렵다
  const toggle = useCallback(
    (id: string) => setOpenId((cur) => (cur === id ? null : id)), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !openId) return
      setOpenId(null)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [openId])

  const goDay = (i: number) => {
    setDayIdx(i)
    setOpenId(null)
    setFocus(null)
    setPrep(false)
    setRoute(false)
  }

  /** 목록에서 자리를 눌렀다 — 지도가 접혀 있으면 펴서 보여준다.
   *  보이지 않는 곳에서 지도만 움직이면 아무 일도 없는 것처럼 보인다. */
  const showOnMap = useCallback((id: string, place?: PlaceT) => {
    if (place?.lat == null && !place) return
    if (!mapDead) setMapOpen(true)
    setOpenId(id)
    setFocus(place ?? null)
  }, [mapDead])

  /** 지도의 빈 곳을 눌렀다 — 짚은 것을 놓는다.
   *  이름표는 「이것을 보는 중」이라는 표시라, 그만 보겠다는 몸짓이 있어야 닫힌다.
   *  목록의 열린 줄은 건드리지 않는다 — 지도를 놓은 것이지 항목을 닫은 것이 아니다. */
  const blurMap = useCallback(() => setFocus(null), [])

  /** 지도에서 짚었다 — 목록도 그 줄로 데려간다.
   *  한쪽만 움직이면 어느 것을 짚었는지 알 수 없다. */
  const pickFromMap = useCallback((id: string, place: PlaceT) => {
    setOpenId(id)
    setFocus(place)
    // 그리기가 끝난 뒤에 찾아야 한다
    requestAnimationFrame(() => {
      const el = body.current?.querySelector<HTMLElement>('[data-place="' + place.id + '"]')
      el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }, [])

  /* 밀어서 넘긴다.
   *
   *  세 가지를 다 넘어야 듣는다. 하나로만 재면 목록을 세로로 훑다가 손끝이
   *  비스듬해진 것까지 스와이프로 읽는다.
   *    거리  정한 만큼   우연히 밀리는 폭보다 넉넉히 넘는다
   *    방향  다른 축의 1.6 배   엇갈리게 그은 손은 아무 일도 일으키지 않는다
   *    시간  600ms 안   천천히 끄는 것은 스와이프가 아니라 스크롤이다
   *
   *  touchmove 에서 preventDefault 를 하지 않는다. 막아 두면 스와이프가
   *  아니었던 것으로 판명나도 이미 스크롤을 잃은 뒤다. 끝난 뒤에 판단한다.
   */
  const swipe = useRef<{ x: number; y: number; t: number } | null>(null)

  const grab = (skip?: string) => (e: React.TouchEvent) => {
    if (skip && (e.target as HTMLElement).closest(skip)) return void (swipe.current = null)
    const p = e.touches[0]
    swipe.current = { x: p.clientX, y: p.clientY, t: e.timeStamp }
  }

  /** dir 이 1 이면 아래·오른쪽, -1 이면 위·왼쪽. 아무것도 아니면 0. */
  const drop = (axis: 'x' | 'y', min: number) => (e: React.TouchEvent): number => {
    const s = swipe.current
    swipe.current = null
    if (!s || e.timeStamp - s.t > 600) return 0
    const p = e.changedTouches[0]
    const dx = p.clientX - s.x
    const dy = p.clientY - s.y
    const [me, other] = axis === 'x' ? [dx, dy] : [dy, dx]
    if (Math.abs(me) < min || Math.abs(me) < Math.abs(other) * 1.6) return 0
    return me < 0 ? -1 : 1
  }

  /* 목록을 좌우로 밀면 날짜가 넘어간다. 왼쪽으로 밀면 다음 날 —
   * 종이를 넘기는 방향이다. 지도는 형제라 여기까지 오지 않고(제 패닝을 가진다),
   * 날짜 줄은 제 가로 스크롤이 있으므로 가려낸다. */
  const daySwipeEnd = (e: React.TouchEvent) => {
    const d = drop('x', 72)(e)
    if (!d) return
    const next = dayIdx + (d < 0 ? 1 : -1)
    if (next >= 0 && next < trip.days.length) goDay(next)
  }

  /* 머리(날짜 · 지역 · 숙소)를 위아래로 밀면 지도가 여닫힌다.
   * 지도가 머리 바로 위에 있으므로 아래로 당기면 내려오고 위로 밀면 올라간다 —
   * 손짓과 화면이 같은 방향이다.
   * 짧게 밀어도 듣게 48px 로 둔다. 머리 자체가 높지 않아 길게 그을 자리가 없다. */
  const mapSwipeEnd = (e: React.TouchEvent) => {
    const d = drop('y', 48)(e)
    if (!d || mapDead) return
    setMapOpen(d > 0)
  }

  // 지도는 제 자리를 가지므로 마커를 밀어 둘 이유가 없다
  const bottomPad = 24

  return (
    <div className="frame">
      <nav className="dates" aria-label="날짜 선택">
        <div className="dateslane" ref={dates}>
        {/* 준비는 9.18 앞에 놓인다 — 시간 순서로도 그 자리다 */}
        <button className={'chip prep' + (prep ? ' on' : '')}
                aria-current={prep}
                onClick={() => { setPrep(true); setRoute(false) }}
                aria-label="준비">
          <Icon name="prep" size={18} />
        </button>
        {trip.days.map((d, i) => (
          <button key={d.date} className="chip num"
                  aria-current={!prep && !route && i === dayIdx}
                  onClick={() => goDay(i)}>
            {md(d.date)}
          </button>
        ))}
        </div>
      </nav>

      {/* 지도는 접힌 채로 자리만 잡고 있다가 펴진다 */}
      {!mapDead && !prep && !route && (
        <div className={'map' + (mapOpen ? ' open' : '')}>
          <Map day={day} selected={selected} focus={focus} bottomPad={bottomPad}
               onPickSpot={pickFromMap} onBlur={blurMap}
               onFail={() => setMapDead(true)} />
        </div>
      )}

      {prep ? (
        <section className="card" aria-label="준비">
          <div className="cardbody" ref={body}>
            <Prep groups={trip.prep ?? []} />
          </div>
        </section>
      ) : route ? (
        /* 동선은 제 안에서 스크롤할 것이 없으므로 cardbody 를 두지 않는다 —
           그 자리를 지도가 통째로 쓴다 */
        <section className="card" aria-label="전체 동선">
          <RouteView onClose={() => { setRoute(false); setPrep(true) }} />
        </section>
      ) : (
      <section className="card" aria-label="일정"
               onTouchStart={grab('.dateslane')} onTouchEnd={daySwipeEnd}>
        <div className="cardhead"
             onTouchStart={grab()} onTouchEnd={mapSwipeEnd}>
          {/* 배지는 날짜와 같은 줄에. 아래 설명은 폭을 다 쓰게 둔다 */}
          <div className="titlerow">
            <h1 className="daytitle">
              <span className="num">{md(day.date)}</span>{' '}
              {day.dow}요일
            </h1>
            {/* 그날의 조건 — 렌터카 · 패스. 제목 옆에 붙여 줄을 늘리지 않는다 */}
            {day.flags.length > 0 && (
              <div className="flags">
                {day.flags.map((f) => (
                  <span key={f.text} className={`flag ${f.kind}`} title={f.full ?? f.text}>
                    {f.text}
                  </span>
                ))}
              </div>
            )}
            <div className="headbtns">
            {/* 지도 · 예약 · 체크리스트. 개수는 적지 않고 있고 없음만 흐리기로 가른다 */}
            {dayTasks.length > 0 && (
              <button className="hbtn task" onClick={() => setChecklist(true)}
                          aria-label="체크리스트">
                    <Icon name="tick" size={18} />
              </button>
            )}
            {!mapDead && (
              <button className={'hbtn' + (mapOpen ? ' on' : '')}
                          onClick={() => setMapOpen((v) => !v)}
                          aria-pressed={mapOpen} aria-label="지도">
                    <Icon name="map" size={18} />
              </button>
            )}
            </div>
          </div>
          {/* 지역은 제 줄에 선다. 날짜 옆에 붙였더니 깃발(JR패스 · 렌트카)과
              같은 층으로 보였는데, 지역은 그날의 무대이고 깃발은 곁들이는
              조건이라 층이 다르다. 크기도 한 단 올려(15px) 숙소보다 위에 둔다 —
              어디에 있느냐가 어디서 자느냐보다 하루를 크게 정한다. */}
          {day.region && <p className="daysub">{day.region}</p>}
          {/* 숙소 줄에 아이콘을 두지 않는다 — 그 줄만 20px 들여써져 위 두 줄과
              왼쪽 줄이 어긋난다. 머리 세 줄은 한 덩어리라 시작선이 맞아야 하고,
              숙소임은 자리와 금액이 이미 말한다. */}
          {day.stay && (
            <p className="daystay">
              <span className="n">{day.stay.name}</span>
              {/* 후보의 링크와 같은 것 — 구글 지도로 나간다.
                  호텔의 자리는 이 줄만 안다. 체크인·체크아웃 항목은 좌표를
                  갖지 않으므로(같은 곳을 여러 번 조회할 까닭이 없다),
                  좌표가 있으면 그 가게로 바로 열고 없으면 이름으로 찾는다 */}
              <a className="pin sm"
                 href={gmapPlace(day.stay.place) ?? gmapSearch(day.stay.name)}
                 target="_blank" rel="noopener" aria-label={`${day.stay.name} 지도`}>
                <Icon name="link" size={16} />
              </a>
              {/* 현지 결제만 금액이 온다 — 뜨면 「아직 낼 돈」 이라는 뜻이다 */}
              {day.stay.costJpy && (
                <span className="due num">{yen(day.stay.costJpy)}</span>
              )}
            </p>
          )}
            </div>
        <div className="cardbody" ref={body}>
          <DayList day={day} openId={openId} onToggle={toggle} onShow={showOnMap}
                   focusId={focus?.id ?? null} />
        </div>
      </section>
      )}

      {/* 전체 동선 — 어느 화면에서든 떠 있다.
          날짜 줄에 두었을 때는 날짜 칩들과 한 줄에 서서 「고르는 것」으로
          읽혔는데, 이것은 날짜를 고르는 일이 아니라 열닷새를 통째로 보는
          딴 갈래다. 떠 있는 단추는 그 줄 밖에 있어 뜻이 갈린다.

          오른쪽 아래인 것은 엄지가 닿는 자리이기 때문이다. 한때 왼쪽에
          두었는데 그것은 목록을 넘기는 손과 다투지 않으려는 뜻이었다 —
          그러나 준비 화면에는 넘길 목록이 없고, 이 단추를 누른 뒤에도 같은
          자리에서 재생과 멈춤을 오가야 하므로 손에 가까운 쪽이 낫다.
          동선 화면의 .rvplay 가 이 자리를 이어받는다. */}
      {/* 준비 화면에서만 선다.
          하루 목록을 볼 때는 「지금 어디를 가는가」를 읽는 중이라 열닷새를
          통째로 되감는 단추가 낄 자리가 아니다. 동선은 떠나기 전에 앉아서
          훑는 것이라 준비와 같은 갈래다 — 걸으면서 길을 찾는 화면이 아니다.

          동선을 보는 동안에는 그 화면이 제 단추를 같은 자리에 세운다
          (route/style.css 의 .rvplay). 그때는 재생과 멈춤을 오가는 것이라
          하는 일이 다르고, 그 상태는 동선 화면만 알기 때문이다. */}
      {prep && !route && (
        <button className="fab"
                onClick={() => { setRoute(true); setPrep(false) }}>
          <Icon name="play" size={16} />전체 동선 보기
        </button>
      )}

      {checklist && (
        <Checklist trip={trip} today={day.date} onClose={() => setChecklist(false)} />
      )}

    </div>
  )
}
