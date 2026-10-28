/** 동선을 걸어갈 그림.
 *
 *  샘플 몇 가지와, 사람이 올린 그림 하나를 같은 것으로 다룬다 —
 *  둘 다 `data:` URL 이라 고르는 쪽에서는 구별할 까닭이 없다.
 *
 *  **왜 파일이 아니라 코드에 그림이 들어 있나.**
 *
 *  지도 마커는 `data:image/svg+xml` 한 장이다. 그 안에서 `<image href="/x.png">`
 *  처럼 밖을 가리키면 브라우저가 막는다 — 이미지로 그려지는 SVG 는 외부를
 *  못 부른다는 규칙이 있어서다. 그러니 public/ 에 파일을 두는 길이 아예 없고,
 *  샘플도 코드에 실려 있어야 한다(skins.ts).
 *
 *  올린 그림은 이미 dataURL 이므로 그 규칙에 걸리지 않는다. 덕분에
 *  샘플과 올린 것이 한 갈래로 흐른다 — 고르는 쪽은 둘을 구별하지 않는다.
 */
import { BLUE_STAR, CLOVER, SKY_STAR } from './skins'

/** 고른 그림. null 이면 기본(먹 원 안의 사람)이다. */
export type Walker = {
  id: string
  name: string
  /** 마커에 쓸 그림. null 은 기본꼴을 뜻한다 */
  src: string | null
}

const KEY = 'route.walker'

/** 고를 수 있는 그림들. 첫째가 기본이다.
 *
 *  도자기 사진에서 바탕만 걷어낸 것들이라 원형으로 자르지 않는다 —
 *  별은 가로가 넓고 클로버는 정사각이라 틀에 맞추면 저마다의 꼴이 사라진다.
 *  마커 쪽에서 아래 가운데를 맞춰 앉히므로(gmap.ts) 비율이 달라도 발이
 *  놓일 자리는 한결같다.
 *
 *  함수인 까닭은 나중에 색을 화면에서 읽는 그림이 다시 들어올 수 있어서다 —
 *  모듈이 실려 오는 때에는 아직 .routeview 가 없다. */
export const samples = (): Walker[] => [
  { id: 'dot', name: '기본', src: null },
  { id: 'bluestar', name: '파란 별', src: BLUE_STAR },
  { id: 'clover', name: '클로버', src: CLOVER },
  { id: 'skystar', name: '하늘 별', src: SKY_STAR },
]

/* ── 기억해 두기 ──────────────────────────────────────
   그 브라우저에만 남는다. 폰에서 고른 것은 폰에서만 보인다 —
   서버가 없는 화면이라 그 이상은 할 수가 없고, 이 값은 잃어도
   아쉬울 것이 없는 취향이라 그 정도면 맞다. */

export function loadWalker(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null            // 사생활 보호 모드에서는 읽기부터 막힌다
  }
}

export function saveWalker(src: string | null): void {
  try {
    if (src) localStorage.setItem(KEY, src)
    else localStorage.removeItem(KEY)
  } catch {
    /* 못 적어도 이번 판에서는 쓰인다. 다음에 다시 고르면 될 일이다 */
  }
}

/** 올린 그림을 마커에 앉힐 크기로 줄인다.
 *
 *  줄이는 까닭이 둘이다. 곳간(localStorage)은 대개 5MB 인데 사진 한 장이
 *  그걸 넘고, 44px 로 그릴 그림에 4000px 짜리를 들고 있을 까닭도 없다.
 *
 *  비율은 지킨다. 마커 쪽에서 아래 가운데에 맞춰 넣으므로(xMidYMax)
 *  가로로 긴 그림이든 세로로 긴 그림이든 발이 놓일 자리는 한결같다.
 *
 *  PNG 로 굽는다 — 누끼 딴 그림의 투명한 자리를 지켜야 해서다.
 */
export function shrink(file: File, max = 128): Promise<string> {
  return new Promise((ok, no) => {
    const fr = new FileReader()
    fr.onerror = () => no(new Error('파일을 읽지 못했습니다'))
    fr.onload = () => {
      const img = new Image()
      img.onerror = () => no(new Error('그림이 아닌 것 같습니다'))
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height))
        const w = Math.max(1, Math.round(img.width * k))
        const h = Math.max(1, Math.round(img.height * k))
        const cv = document.createElement('canvas')
        cv.width = w
        cv.height = h
        const cx = cv.getContext('2d')
        if (!cx) return no(new Error('그림을 줄이지 못했습니다'))
        cx.drawImage(img, 0, 0, w, h)
        ok(cv.toDataURL('image/png'))
      }
      img.src = String(fr.result)
    }
    fr.readAsDataURL(file)
  })
}
