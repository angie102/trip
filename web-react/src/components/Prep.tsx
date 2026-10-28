import type { PrepGroup } from '../types'
import { Icon } from './icons'

/* 준비 화면 — 떠나기 전에 훑는 목록.
 *
 *  체크를 달지 않는다. 짐은 손으로 챙기면서 눈으로 훑는 것이고, 화면을 눌러
 *  지워 나가는 일과는 결이 다르다 — 누르는 동안 손이 짐에서 떠난다.
 *  표시는 「이 줄이 챙길 것」만 말하면 된다.
 *
 *  시트가 세 열로 적히므로 항목이 스물다섯을 넘는다. 한 줄에 하나씩 세우면
 *  화면 두 배를 넘어가므로 두 열로 흘린다 — 낱말이 짧아 두 열이면 넉넉하다.
 */
export default function Prep({ groups }: { groups: PrepGroup[] }) {
  if (!groups.length) {
    return (
      <div className="prepview empty">
        <p>아직 적어 둔 것이 없습니다.</p>
        <p className="sub">시트의 <b>준비</b> 탭에 적으면 여기에 나옵니다.</p>
      </div>
    )
  }

  return (
    <div className="prepview">
      <h1 className="prephead">준비</h1>

      {groups.map((g) => (
        <section className="pgroup" key={g.name}>
          <h2>{g.name}</h2>
          {/* 메모는 챙길 것이 아니라 읽을 것이라 표시를 달지 않는다 */}
          {g.name === '메모' ? (
            g.items.map((it, i) => (
              <p className="pmemo" key={i}>
                {it.text}
                {it.note && <span className="ja">{it.note}</span>}
              </p>
            ))
          ) : (
            <ul className="plist">
              {g.items.map((it, i) => (
                <li className="pitem" key={i}>
                  <Icon name="tick" size={14} className="ptick" />
                  <span className="t">{it.text}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
