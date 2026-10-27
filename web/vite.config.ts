import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 루트 .env 를 읽는다(VITE_ 로 시작하는 값만 브라우저에 노출된다).
// 개발 서버는 /api 와 /healthz 를 로컬 API(:8000)로 프록시한다.
export default defineConfig({
  plugins: [react()],
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
