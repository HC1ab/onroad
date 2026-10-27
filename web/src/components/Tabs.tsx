import { ROUTE_HASH, type Route } from '../lib/route'

const TABS: { route: Route; label: string }[] = [
  { route: 'map', label: '지도' },
  { route: 'validation', label: '검증' },
]

/** 헤더 탭. 주소의 # 부분을 바꿔 화면을 전환한다. */
export function Tabs({ route }: { route: Route }) {
  return (
    <nav className="tabs" aria-label="화면">
      {TABS.map((t) => (
        <a key={t.route} href={ROUTE_HASH[t.route]} className={t.route === route ? 'tab on' : 'tab'} aria-current={t.route === route ? 'page' : undefined}>
          {t.label}
        </a>
      ))}
    </nav>
  )
}
