import { useEffect, useState } from 'react'

// 화면 전환은 주소의 # 부분으로 한다(라우터 라이브러리 없음). 링크 공유와 뒤로가기가 그대로 동작한다.
export type Route = 'map' | 'validation' | 'about'

export const ROUTE_HASH: Record<Route, string> = { map: '#/', validation: '#/validation', about: '#/about' }

export function parseRoute(hash: string): Route {
  const head = hash.replace(/^#\/?/, '').split(/[/?]/)[0]
  return head === 'validation' || head === 'about' ? head : 'map'
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash))
  useEffect(() => {
    const on = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}
