/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** real: 서버 API 사용, mock: contracts/samples 사용. 없으면 mock */
  readonly VITE_API_MODE?: 'real' | 'mock' | 'static'
  /** 배경 지도 스타일 URL. 없으면 OpenFreeMap positron */
  readonly VITE_BASEMAP_STYLE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
