import { createReadStream, existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const BOUNDARIES = fileURLToPath(new URL('./public/data/boundaries.json', import.meta.url))
const SAMPLE_BOUNDARIES = fileURLToPath(new URL('../contracts/samples/boundaries.json', import.meta.url))
const STATIC_MANIFEST = fileURLToPath(new URL('./public/static/manifest.json', import.meta.url))

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

/**
 * static 빌드 전용(F18): 정적 묶음이 있어야 하고, 경계 파일도 함께 들어가야 데모가 된다.
 * 실제 경계가 없을 때 샘플 묶음이면 샘플 경계를 넣고, 실제 묶음이면 빌드를 멈춘다(부산 일부만 보이는 데모 방지).
 */
function staticBundleCheck(): Plugin {
  return {
    name: 'onroad-static-bundle',
    apply: (_config, env) => env.command === 'build' && env.mode === 'static',
    buildStart() {
      if (!existsSync(STATIC_MANIFEST)) {
        this.error('web/public/static/manifest.json 이 없습니다. 서버에서 내보낸 정적 묶음을 먼저 넣으세요(web/README.md).')
      }
      if (existsSync(BOUNDARIES)) return
      const manifest = JSON.parse(readFileSync(STATIC_MANIFEST, 'utf8'))
      if (!manifest._sample) {
        this.error('web/public/data/boundaries.json 이 없습니다. 실제 묶음에는 실제 경계가 필요합니다(D6).')
      }
      this.warn('샘플 묶음이라 샘플 경계(contracts/samples/boundaries.json)를 넣습니다.')
      this.emitFile({ type: 'asset', fileName: 'data/boundaries.json', source: readFileSync(SAMPLE_BOUNDARIES) })
    },
  }
}

// 루트 .env 를 읽는다(VITE_ 로 시작하는 값만 브라우저에 노출된다).
// 개발 서버는 /api 와 /healthz 를 로컬 API(:8000)로 프록시한다.
export default defineConfig({
  plugins: [react(), sampleBoundariesFallback(), staticBundleCheck()],
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
