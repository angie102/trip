import { useEffect, type ReactNode } from 'react'

type Props = {
  label: string
  onClose: () => void
  children: ReactNode
}

/** 화면 가운데에 잠깐 뜨는 팝업.
 *
 *  화면을 다 덮지 않는다. 뒤의 일정이 어렴풋이 비쳐야 「그 위에 잠깐 뜬 것」으로
 *  읽히고, 닫으면 보던 자리로 돌아간다는 것이 몸에 남는다. 전면으로 덮으면
 *  화면이 바뀐 것처럼 보여 뒤로 가기를 찾게 된다.
 *
 *  제목을 두지 않는다. 무엇인지는 누른 버튼이 이미 말했고, 팝업 안에 든
 *  줄들이 스스로 무엇인지 보인다 — 세 줄짜리 목록 위의 제목은 자리만 먹는다.
 *  화면 읽어 주는 것에는 aria-label 로 남긴다.
 *
 *  닫기 단추를 두지 않는다. 바깥을 누르면 닫히고, 그 바깥이 화면의 대부분이라
 *  단추보다 넓고 가깝다 — 작은 팝업에서는 X 가 도리어 겨냥해야 하는 과녁이 된다.
 *
 *  Esc 는 여기서 받는다 — 열려 있는 것이 자기를 닫는 것이 순서다.
 */
export default function Popup({ label, onClose, children }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      onClose()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="scrim" onClick={onClose}>
      <div className="pop" onClick={(e) => e.stopPropagation()}
           role="dialog" aria-modal aria-label={label}>
        <div className="popbody">{children}</div>
      </div>
    </div>
  )
}
