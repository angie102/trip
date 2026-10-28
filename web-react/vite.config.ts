import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  /* 바깥에서도 붙을 수 있게 연다.
   *
   *  전에는 127.0.0.1 에만 묶어 두었다 — Windows 의 기본 바인딩이 IPv6([::1])
   *  만 잡아 브라우저가 127.0.0.1 로 붙으면 끊겼기 때문이다. host:true 는
   *  모든 자리에 묶으므로 그 문제도 없고, 같은 와이파이의 폰에서도 열린다.
   *
   *  뜰 때 「Network: http://192.168.x.x:5180」 이 함께 찍힌다. 폰에서 그
   *  주소로 들어가면 된다 — 다만 지도 열쇠에 referer 제한이 걸려 있으면
   *  그 주소도 허용 목록에 넣어야 지도가 뜬다. */
  server: { host: true, port: 5180, strictPort: true, open: true },
  build: { outDir: 'dist' },
})
