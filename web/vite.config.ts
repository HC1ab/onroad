import { createReadStream, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const BOUNDARIES = fileURLToPath(new URL('./public/data/boundaries.json', import.meta.url))
const SAMPLE_BOUNDARIES = fileURLToPath(new URL('../contracts/samples/boundaries.json', import.meta.url))

/**
 * 개발 서버 전용: 실제 경계 파일(D6 #9가 web/public/data 에 생성)이 아직 없으면
 * contracts 의 샘플 경계(부산 일부)를 대신 내준다. 빌드·배포에는 영향이 없다.
 */
function sampleBoundariesFallback(): Plugin {
  return {
    name: 'onroad-sample-boundaries',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/data/boundaries.json', (_req, res, next) => {
        if (existsSync(BOUNDARIES)) return next()
        res.setHeader('Content-Type', 'application/geo+json; charset=utf-8')
        res.setHeader('X-Onroad-Sample', 'boundaries')
        createReadStream(SAMPLE_BOUNDARIES).pipe(res)
      })
    },
  }
}

// 루트 .env 를 읽는다(VITE_ 로 시작하는 값만 브라우저에 노출된다).
// 개발 서버는 /api 와 /healthz 를 로컬 API(:8000)로 프록시한다.
export default defineConfig({
  plugins: [react(), sampleBoundariesFallback()],
  envDir: '..',
  resolve: {
    alias: {
      '@contracts': fileURLToPath(new URL('../contracts', import.meta.url)),
    },
  },
  build: {
    // MapLibre 는 크기가 커서 별도 파일로 나눈다(캐시 효율).
    rollupOptions: { output: { manualChunks: { maplibre: ['maplibre-gl'] } } },
    chunkSizeWarningLimit: 1100,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
    fs: { allow: ['..'] },
  },
})
