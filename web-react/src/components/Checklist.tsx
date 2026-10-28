import type { Trip } from '../types'
import { host, md } from '../lib'
import { Icon } from './icons'
import Popup from './Popup'

type Props = { trip: Trip; today: string; onClose: () => void }

/** 보고 있는 날짜의 할 일 — 읽기만 한다.
 *
 *  체크를 달지 않는다. 준비 화면이 먼저 그렇게 정했다 —
 *  「짐은 손으로 챙기면서 눈으로 훑는 것이고, 화면을 눌러 지워 나가는 일과는
 *  결이 다르다」. 여기도 같다. 표시는 「이 줄이 오늘 할 것」만 말하면 된다.
 *
 *  그날 것만 띄운다. 전체 보기를 두지 않는다 — 열닷새치를 한 자리에 쏟으면
 *  오늘 무엇을 해야 하는지가 묻힌다. 날짜는 위의 날짜 줄에서 고르면 된다.
 *
 *  무엇에 딸린 일인지는 시트의 문구가 말한다. 화면이 항목을 되짚어 붙이지
 *  않는다 — 읽는 사람이 알아야 한다면 그것은 문구에 적을 일이다.
 */
export default function Checklist({ trip, today, onClose }: Props) {
  const tasks = trip.checklist.filter((t) => t.due === today)

  return (
    <Popup label={`${md(today)} 체크리스트`} onClose={onClose}>
      {tasks.length === 0 && <p className="empty">이 날 할 일은 없습니다.</p>}

      {tasks.map((t, i) => {
        /* 그림만 있는 건 — 시트에 '*** {이미지}' 로 적어 둔 자리다.
           체크 네모를 달지 않는다. 눌러 지워 나갈 일이 아니라 그 자리에서
           보고 지나가는 것이라, 할 일 줄과 같은 모양을 하면 오히려 헷갈린다.

           글자가 있으면 아래 갈래로 내려가 할 일 줄 밑에 그림을 눕힌다.
           한때 여기서 t.image 만 보고 가로챘는데, 그림을 지닌 할 일은
           그림이 통째로 사라졌다 — 「지도는 체크리스트 참고」가 글자만
           남아, 참고하라는 그 그림이 정작 없었다. 그림은 글자를 대신하는
           것이 아니라 딸리는 것이다. 주소(t.link)가 그러는 것과 같다. */
        if (t.image && !t.text.trim()) {
          return (
            <div className="tkimg" key={i}>
              <img src={`media/${t.image}`} alt="" />
            </div>
          )
        }
        /* 첫 줄이 곧 그 할 일이고, 뒤따르는 줄은 그것을 하는 데 필요한 것이다
           (택배 보낼 주소가 그렇다). 일정 화면의 할 일 상자와 같은 규칙이다 —
           통째로 한 무게로 두면 주소 여덟 줄이 다 굵어진다.

           줄바꿈은 시트에 적힌 그대로 살린다(.tkd 의 pre-line) — 주소가
           한 줄로 이어 붙으면 어디서 끊어 읽을지가 사라진다. */
        const [head, ...rest] = t.text.split('\n')
        const body = [...rest, ...(t.detail ?? [])].join('\n').trim()
        return (
          <div className="tkrow" key={i}>
            <p className="tk">
              <Icon name="checkbox" size={16} />
              <span className="t">{head}</span>
            </p>
            {body && <p className="tkd num">{body}</p>}
            {/* 시트에 <https://…> 로 적어 둔 주소. 일정 화면(DayList 의 .weblink)과
                같은 규칙이다 — 긴 주소 대신 도메인만 적고, 이름 뒤가 아니라
                아랫줄에 선다. 한때 고리 그림 하나로 줄였는데, 장소의 지도
                링크(.pin)와 같은 그림이 되어 「어디로 나가는지」가 사라졌다. */}
            {t.link && (
              <p className="tkd">
                <a className="weblink" href={t.link} target="_blank" rel="noopener">
                  {host(t.link)}
                </a>
              </p>
            )}
            {/* 딸린 그림 — 할 일 줄 아래 눕는다. 여기서도 눌러 크게 보지
                않는다(.tkimg): 이미 판 안이라 넓게 들어가고, 판 위에 판을
                또 얹으면 닫는 길이 헷갈린다. */}
            {t.image && (
              <div className="tkimg">
                <img src={`media/${t.image}`} alt="" />
              </div>
            )}
          </div>
        )
      })}
    </Popup>
  )
}
