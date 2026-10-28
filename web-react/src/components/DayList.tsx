import { useState } from 'react'
import type { Day, Item, Leg, Place, Spot } from '../types'
import { clean, dots, dur, full, gmapDir, gmapPlace, gmapSearch, host, hoursText, leadEmoji, legsByFrom, resvMeta } from '../lib'
import { Icon, MODE_ICON } from './icons'


type Props = {
  day: Day
  openId: string | null
  onToggle: (id: string) => void
  /** 자리를 눌렀다 — 지도를 펴서 그곳을 보여준다 */
  onShow: (id: string, place?: Place) => void
  /** 지금 지도가 보고 있는 자리 — 목록에서도 표시한다 */
  focusId: string | null
}

/** 상세 화면을 두지 않는다. 적어 둔 것은 그 자리에 다 적히고,
 *  후보가 여럿일 때만 첫 곳을 남기고 접는다 — 그것 말고는 접을 것이 없다. */
export default function DayList({ day, openId, onToggle, onShow, focusId }: Props) {
  // 크게 보는 그림은 여기 하나만 둔다 — 이동 줄마다 제 모달을 들면
  // 여러 개가 겹쳐 뜨고 닫는 몸짓도 저마다 달라진다.
  const [big, setBig] = useState<string | null>(null)
  const legs = legsByFrom(day)
  // 그날 첫 일정보다 앞선 이동 — 붙을 항목이 없어 목록 맨 앞에 선다.
  // (09-23 오전 7시 신칸센처럼 숙소에서 곧장 떠나는 날)
  const lead = legs.get('__') ?? []
  return (
    <>
    <ol className="list">
      {lead.map((l) => (
        <li key={l.id}>
          <LegRow leg={l} open={openId === l.id} onToggle={onToggle} onBig={setBig} />
        </li>
      ))}
      {day.items.map((it) => (
        <li key={it.id}>
          <Row item={it} onShow={onShow} focusId={focusId} onBig={setBig} />
          {(legs.get(it.id) ?? []).map((l) => (
            <LegRow key={l.id} leg={l} open={openId === l.id} onToggle={onToggle}
                    onBig={setBig} />
          ))}
        </li>
      ))}
    </ol>

    {/* 안내도를 크게 — 화면을 덮는다. 아무 데나 눌러 닫는다.
        띄우는 자리를 여기 하나만 두어야 여러 장이 겹쳐 뜨지 않는다. */}
    {big && (
      <div className="bigimg" role="dialog" aria-label="안내도"
           onClick={() => setBig(null)}>
        <img src={big} alt="안내도" />
      </div>
    )}
    </>
  )
}

/* ── 가게 한 곳 ─────────────────────────────────────────── */

type PlaceProps = {
  name: string
  nameJa?: string
  place?: Spot['place']
  /** 묶음이 끝나고 새 묶음이 시작하는 자리 — 위를 한 단 벌린다 */
  sep?: boolean
  desc?: string
  cost?: string
  reserved?: boolean
  group?: boolean
  resv?: Item['reservation']
  focus?: boolean
  onShow?: () => void
}

/** 이름과 원어가 한 줄, 영업시간과 설명이 그 아래 한 줄.
 *  후보든 단독이든 같은 모양으로 그린다.
 *
 *  이름 줄은 넘치면 줄인다(…). 접어 내리면 긴 이름 하나 때문에 그 후보만
 *  두 줄이 되어 목록의 결이 어긋난다 — 어디인지는 원어와 지도가 마저 알려 준다.
 *  설명은 두 줄까지 내려간다. 그쪽은 읽어야 뜻이 서는 말이라 줄이면 잃는다. */
function Place({ name, nameJa, place, desc, cost, reserved, group, resv,
                 sep, focus, onShow }: PlaceProps) {
  /* 예약한 집도 영업시간을 적는다.
   *
   *  「예약 시각에 맞춰 가면 되니 볼 것 없다」고 여겨 감췄는데, 예약 자리
   *  여덟 곳 중 넷이 렌터카다 — 9/29 반납이 18:00 이고 그 영업소가 19:00 에
   *  닫는다. 늦으면 하루를 더 물어야 하는 자리에서 마감을 감추고 있었다.
   *  밥집 둘은 브레이크 타임이 있어, 예약이 어느 구간에 걸리는지도 보인다. */
  const hrs = hoursText(place)
  const wide = place?.hours && place.hours.length > 1 ? full(place.hours) : null
  const bits = dots(desc, cost)
  const mappable = !group && place?.lat != null
  /* 예약 표식은 지도와 같은 값을 본다.
   *
   *  목록은 reserved(「예약」 시트에서 이름이 맞은 후보)만 보고 있었는데,
   *  렌터카는 「호텔」 시트의 렌터카 표에서 오므로 그 표시가 안 붙는다.
   *  그런데 지도는 place.kind 로 보고 북마크를 그린다 — 같은 자리에
   *  한쪽만 표식이 섰다. 두 화면이 한 값을 봐야 어긋나지 않는다. */
  const booked = reserved || place?.kind === 'resv'

  return (
    <div className={'place' + (group ? ' grp' : '') + (onShow ? ' pick' : '')
                    + (sep ? ' sep' : '') + (focus ? ' on' : '')}
         data-place={place?.id}
         aria-current={focus || undefined}
         onClick={onShow && ((e) => {
           if ((e.target as HTMLElement).closest('a, button')) return
           e.stopPropagation()
           onShow()
         })}>
      <div className="pn">
        {/* 이름과 원어는 한 덩어리다. 넘치면 … 로 줄인다 */}
        <span className="nw">
          {name}
          {nameJa && <span className="ja">{nameJa}</span>}
        </span>
        {/* 표식과 링크는 이름 바로 뒤에 붙는다 — 줄 끝으로 밀어 두면
            이름이 짧을수록 멀어져 어느 가게 것인지 눈으로 이어야 했다 */}
        {booked && <Icon name="resvOn" size={16} className="resvmark" />}
        {mappable && (
          <a className="pin sm" href={gmapPlace(place) ?? gmapSearch(name)}
             target="_blank" rel="noopener" aria-label={`${name} 지도`}>
            <Icon name="link" size={16} />
          </a>
        )}
      </div>
      {/* 영업시간과 설명이 한 줄에 선다. 시각은 폭이 정해져 있어 왼쪽에 세우고,
          설명은 남는 자리를 받아 넘치면 두 줄째로 내려간다. */}
      {(hrs || bits) && (
        <p className="psub">
          {hrs && <span className="ph num">{wide ?? hrs}</span>}
          {bits && <span className="pd">{bits}</span>}
        </p>
      )}
      {resv && <Resv r={resv} />}
    </div>
  )
}

/** 첫 줄은 시트에 적힌 예약 내용 그대로, 둘째 줄은 어디서·어떻게·얼마.
 *  적은 사람의 말이 먼저 서고, 셈에 쓰는 값이 그 아래 한 줄로 붙는다. */
function Resv({ r }: { r: NonNullable<Item['reservation']> }) {
  const meta = resvMeta(r)
  // 적을 것이 없으면 상자를 세우지 않는다. 렌터카 반납이 그렇다 —
  // 지점은 항목 줄이 말하고 돈은 받는 자리에 적혀 있어, 여기 남는 것이
  // 없다. 빈 면만 두르면 「무언가 있다」고 말하는 셈이 된다.
  if (!r.note && !meta) return null
  return (
    <div className="bresv">
      {r.note && <p className="t">{r.note}</p>}
      {meta && <p className={r.note ? 'bd' : 't'}>{meta}</p>}
    </div>
  )
}

/* ── 항목 ───────────────────────────────────────────────── */

/* 후보를 접지 않으므로 여닫이(open·onToggle)를 받지 않는다 —
   그것은 이동 줄(LegRow)의 일이다. */
function Row({ item, onShow, focusId, onBig }:
  { item: Item
    onShow: (id: string, place?: Place) => void; focusId: string | null
    onBig: (src: string) => void }) {
  const spots = item.spots ?? []
  const resvSpot = spots.find((s) => s.reserved)
  const resvHere = !!item.reservation && !resvSpot
  // 제목 앞의 이모지. 종류를 가리지 않는다 — 시트에 적혀 있으면 세우고
  // 없으면 안 세운다. 「식사일 때만」을 코드가 쥐고 있으면, 시트가 다른
  // 종류에 이모지를 붙이는 날 화면만 조용히 안 따라온다.
  // 무엇을 세울지는 시트가 정하고, 화면은 적힌 것을 옮기기만 한다.
  const emoji = leadEmoji(item.title)
  // 후보는 접지 않는다. 한 줄 감추자고 「더 보기」를 다는 것이 34 곳 중 15 곳은
  // 그 버튼이 감추는 줄만큼 자리를 먹어 이득이 없었다. 자리가 아쉬운 것은
  // 지도가 맡는다 — 흩어진 곳을 훑는 데는 목록보다 지도가 낫다.
  // 적어 둔 순서를 그대로 지킨다.
  const ordered = spots
  /* 메모는 메모다.
   *
   *  전에는 「할 일이 걸린 항목은 메모가 곧 그 할 일의 세부」라 여겨 task 가
   *  붙은 항목의 메모를 통째로 상자에 담았다. 그런데 시트는 둘을 갈라 적는다 —
   *  `*` 는 메모, `***` 는 할 일이고, 할 일은 이미 그날의 체크리스트로 갔다.
   *  그래서 「조식 신청하고 싶으면 할까?」 같은 혼잣말이 체크리스트 문구가 됐다.
   *  파서가 갈라 놓은 것을 화면이 도로 합치고 있었다. */
  const notes = item.notes

  /* 묶음 라벨('#' 줄)은 띄우지 않는다. 「구경」「음식」처럼 그냥 가르기만 하는
   * 말이 대부분이고, 그것은 간격이 더 조용히 한다. 자리를 말하는 라벨
   * (「도쿄역 1번가」)은 시트에서 후보 쪽으로 옮긴다 — 화면이 아니라
   * 정본이 정할 일이다.
   *
   * 묶음이 사라지면 후보들이 그냥 이어지므로, 묶음이 바뀌던 자리에만
   * 한 단을 벌려 그 경계를 남긴다. */
  const place = (s: Spot, i: number) => (
    <Place key={i} name={s.name} nameJa={s.nameJa} place={s.place}
           desc={s.desc} cost={s.cost}
           sep={i >= 2 && !!ordered[i - 1]?.group}
           reserved={s.reserved} group={s.group}
           resv={s.reserved ? item.reservation : undefined}
           focus={!!s.place?.id && s.place.id === focusId}
           onShow={s.place?.lat != null && !s.group
             ? () => onShow(item.id, s.place) : undefined} />
  )

  return (
    <div className="item">
      <div className="row"
           onClick={(e) => {
             if ((e.target as HTMLElement).closest('a, button')) return
             onShow(item.id)
           }}>
        {/* 시각과 제목은 한 줄이다. 따로 두면 각자의 상자 안에서 각각 붙고 떨어져
            12px 씩 어긋난 채 덜그럭거린다. */}
        <div className="rtop">
          {/* 괄호로 적은 시각은 자리만 지키고 글자는 띄우지 않는다 —
              열 너비가 그대로라 아래위 항목의 제목이 어긋나지 않는다 */}
          {/* 괄호로 적은 시각은 자리만 지키고 글자는 띄우지 않는다 */}
          <div className={'rtime num' + (item.fixed ? ' fixed' : '')}>
            {!item.hideTime && <span>{item.time ?? '·'}</span>}
          </div>
          <div className="rhead">
            {/* 아이콘은 두지 않는다. 「식사」인지 「구경」인지는 제목이 이미
                말하고, 항목마다 아이콘이 서면 제목의 시작선이 그만큼 밀려
                시각 열과의 사이가 헐거워진다.

                시각을 괄호로 적은 항목(앞 일정에서 이어지는 것)에는 화살표를
                세웠었는데, 그것도 뗐다 — 시각 자리가 비어 있다는 사실이
                이미 「이어진다」를 말한다. */}
            {/* 제목뿐이다. 끝 시각과 예약 표식을 뒤에 달던 갈래가 있었는데
                시트에 그런 항목이 하나도 없었다 — 끝 시각은 적히지 않고,
                예약은 늘 그 집(detail·후보)에 붙어 그쪽에 표식이 선다.
                한 줄에 하나만 서면 사이 간격을 정할 일도 없다. */}
            {/* 시트의 이모지를 시각 옆·제목 앞에 세운다.
                종류 아이콘을 통째로 걷어낸 그때의 까닭(제목 시작선이 밀린다)은
                그대로다. 다만 지금 시트에 이모지가 붙는 것은 밥때뿐이라
                줄마다 서지 않는다 — 걷어낸 것은 「모든 줄에 아이콘」이었지
                「이모지」가 아니었다.
                이동은 여기 오지 않는다. 이동 줄은 제 블록(LegRow)에서
                수단 아이콘(MODE_ICON)을 세우므로, 🚗·🚝 를 여기서 또 세우면
                한 줄에 같은 말이 두 번 선다. */}
            {emoji && <span className="remoji" aria-hidden>{emoji}</span>}
            <span className="rtitle">{clean(item.title)}</span>
          </div>
        </div>

        <div className="rbody">

          {/* 그날 해야 할 일 — 예약과 같은 꼴의 상자에, 색만 민트로.
              제목 바로 아래에 둔다. 후보 뒤로 밀면 「역 근처 구경」 처럼
              들를 곳이 여럿인 항목에서 정작 지켜야 하는 것이 맨 끝에 놓인다. */}
          {/* 그날 해야 할 일(엑셀 '***' 줄). 메모('*' 줄)와 다른 것이라
              자리도 다르다 — 시트가 갈라 적은 것을 여기서 합치지 않는다.
              제목 바로 아래에 둔다. 후보 뒤로 밀면 「역 근처 구경」처럼
              들를 곳이 여럿인 항목에서 정작 지켜야 하는 것이 맨 끝에 놓인다. */}
          {item.tasks?.length ? (
            <div className="btask">
              {item.tasks.map((n, i) => (
                <p className="t" key={i}><Icon name="checkbox" size={16} /> {head(n)}</p>
              ))}
            </div>
          ) : null}
          {/* 안내도 — 할 일 바로 아래다. 「지도는 체크리스트 참고」 같은 줄이
              가리키는 것이 이 그림이라, 사이에 다른 것이 끼면 무엇을 가리키는지
              흐려진다. 이동의 것(.legimg)과 같은 재질이고 눌러 크게 본다. */}
          {item.image && (
            <button className="legimg" aria-label="안내도 크게 보기"
                    onClick={() => onBig(`media/${item.image}`)}>
              <img src={`media/${item.image}`} alt="안내도" />
            </button>
          )}

          {/* 그 항목 자신의 메모(엑셀 '* ' 줄). 할 일과 같은 자리다.
              가게에 딸린 말(엑셀 '- 이름: 설명')은 그 후보 안에 그대로 둔다 —
              소속이 다른 둘을 같은 높이에 놓으면 누구 말인지 알 수 없다. */}
          {notes?.map((n, i) => <p className="bnote" key={i}><span>{n}</span></p>)}
          {/* 시트에 <https://…> 로 적어 둔 주소. 메모와 같은 자리에 서되
              긴 주소 대신 도메인만 적는다 — 어디로 나가는지가 전부다. */}
          {item.link && (
            <p className="bnote">
              <a className="weblink" href={item.link} target="_blank" rel="noopener">
                {host(item.link)}
              </a>
            </p>
          )}

          {/* 후보가 하나로 접힌 항목 — 그 이름이 곧 이 항목의 실체다 */}
          {item.detail && (
            <Place name={item.detail} nameJa={item.detailJa} place={item.place}
                   desc={item.detailDesc} cost={item.cost} reserved={resvHere}
                   resv={resvHere ? item.reservation : undefined}
                   focus={!!item.place?.id && item.place.id === focusId}
                   onShow={item.place?.lat != null
                     ? () => onShow(item.id, item.place) : undefined} />
          )}

          {/* 후보 목록 — 다 보인다 */}
          {ordered.map((s, i) => (s.group ? null : place(s, i)))}

          {item.cost && !item.detail && !item.reservation ? (
            <p className={'pcost num' + (item.covered ? ' cov' : '')}>
              {item.cost}{item.covered && <span className="covtag">패스 커버</span>}
            </p>
          ) : null}

          {/* 가게 이름이 없는 항목은 예약을 여기서 말한다 */}
          {item.reservation && !item.detail && !spots.length && (
            <Resv r={item.reservation} />
          )}

        </div>
      </div>
    </div>
  )
}

/* ── 이동 ───────────────────────────────────────────────── */

/** 할 일의 첫 줄. 첫 줄이 곧 그 할 일이고, 뒤따르는 줄은 그것을 하는 데
 *  필요한 것이다(택배 보낼 주소가 그렇다). 전문은 머리의 체크리스트가
 *  그대로 보여 준다 — 여기서 되풀이하면 주소 여덟 줄이 목록 한가운데를
 *  차지한다. 이 화면은 훑는 자리이고, 그 화면은 하나씩 짚는 자리다. */
const head = (t: string) => t.split('\n')[0]

function LegRow({ leg, open, onToggle, onBig }:
  { leg: Leg; open: boolean; onToggle: (id: string) => void
    onBig: (src: string) => void }) {
  const way = leg.spots ?? []
  // 시트에 「길찾기」라 적어 둔 경로에만 붙는다. 안 적었으면 null 이다
  const dir = gmapDir(leg)
  // 접을 것이 있을 때만 셰브런을 단다
  const more = way.length > 0 || leg.notes.length > 0 || !!leg.image
    || !!leg.origin || !!leg.dest || !!leg.cost

  return (
    <div className="legwrap">
      {/* 점선은 시간이 흐르고 있음을, 상자는 이것이 이동임을 말한다 */}
      <div className="line" />
      {/* 이동 상자 위에, 드롭다운 밖에 선다.
          하나의 길찾기가 여러 구간을 아우를 수 있어서다 — 환승은 구글이 잡으므로
          「니가타역 → 카루이자와역」이 일정에서는 두 구간이어도 길찾기로는 하나다.
          그것을 첫 구간의 서랍 안에 넣으면 「이 구간의 것」으로 읽힌다. */}
      {/* 길찾기와 이동 상자는 격자의 한 칸을 같이 쓴다.
          행을 늘리면 점선이 따라 늘어나야 하는데, 암시적 격자에서 grid-row 의
          -1 은 명시적 격자의 마지막 선이라 첫 행 한 칸으로 풀린다 —
          점선이 길찾기 높이까지만 내려오고 상자와 서랍을 못 덮는다. */}
      <div className="legcol">
      {dir && (
        <p className="legdir">
          <a className="dirbtn" href={dir} target="_blank" rel="noopener">
            길 찾기<Icon name="goto" size={14} />
          </a>
        </p>
      )}
      <div className={'legbox' + (open ? ' open' : '') + (leg.seat ? ' booked' : '')}>
        <button className="lb" aria-expanded={more ? open : undefined}
                onClick={() => more && onToggle(leg.id)}>
          <Icon name={MODE_ICON[leg.mode] ?? 'car'} size={18} className="lm" />
          <span className="lv">{leg.vehicle || clean(leg.title)}</span>
          {/* 좌석까지 잡은 구간은 출발 시각을 띄운다 — 그 차를 놓치면 표가 죽는다.
              자리는 이름 뒤, 예약 표식 앞이다:
              「무엇을 · 몇 시에 · 잡아 두었다」 가 읽는 차례와 맞는다 */}
          {leg.seat && leg.time && <span className="ltime num">{leg.time}</span>}
          {leg.seat && <Icon name="resvOn" size={16} className="seatmark" />}
          {leg.min ? <span className="pill num">{dur(leg.min)}</span> : null}
          {more && <Icon name="chevron" size={18} className={'chev' + (open ? ' up' : '')} />}
        </button>

        <div className={'fold' + (open ? ' open' : '')}>
          <div className="foldin" aria-hidden={!open}>
          <div className="legbody">
            {(leg.origin || leg.dest) && (
              <p className="route">
                {leg.origin && <span>{leg.origin}</span>}
                {leg.origin && leg.dest && <span className="arrow">→</span>}
                {leg.dest && <span>{leg.dest}</span>}
                {/* 얼마인가는 어디서 어디로의 값이다 — 같은 줄 끝에 선다 */}
                {leg.cost && (
                  <span className={'pcost num' + (leg.covered ? ' cov' : '')}>
                    {leg.cost}{leg.covered && <span className="covtag">패스 커버</span>}
                  </span>
                )}
              </p>
            )}

            {way.map((s, i) => (
              <Place key={i} name={s.name} nameJa={s.nameJa} place={s.place}
                     desc={s.desc} cost={s.cost} group={s.group} />
            ))}

            {leg.image && (
              <button className="legimg" aria-label="안내도 크게 보기"
                      onClick={() => onBig(`media/${leg.image}`)}>
                <img src={`media/${leg.image}`} alt="안내도" />
              </button>
            )}
            {leg.notes.map((n, i) => <p className="bnote" key={i}><span>{n}</span></p>)}
          </div>
          </div>
        </div>
      </div>
      {/* 잡아 둔 좌석은 접힘 밖에 선다 — 늘 보인다.
          서랍 안에 있던 때는 이 줄이 대개 접혀 있어서, 「몇 호차 몇 번」이
          펴야만 나왔다. 개찰구 앞에서 펴 볼 것이 아니라 훑다 걸려야 하는 값이다.
          자리는 이동 상자 아래다 — 식당의 예약 상자가 곳 이름 아래에 서는 것과
          같은 차례다: 무엇을 타는가 → 어느 자리를 잡았는가. */}
      {/* 할 일은 접힘 밖이다 — 좌석과 같은 규칙이다.
          「리무진 버스 타러 가는 길」은 그 버스를 타기 직전에 봐야 하는 것이라,
          서랍을 열어야 나오면 늦다. 첫 줄만 그리는 것도 항목(.btask)과 같다 —
          전문과 딸린 안내도는 서랍 안과 머리의 체크리스트가 보여 준다. */}
      {leg.tasks?.length ? (
        <div className="btask">
          {leg.tasks.map((n, i) => (
            <p className="t" key={i}>
              <Icon name="checkbox" size={16} /> {head(n)}
            </p>
          ))}
        </div>
      ) : null}
      {leg.seat && (
        <div className="bseat">
          <p className="t">{leg.seat.train}</p>
          <p className="bd num">{leg.seat.seat}</p>
          <p className="bd num">{leg.seat.span}  {leg.seat.from} → {leg.seat.to}</p>
        </div>
      )}
      </div>
    </div>
  )
}
