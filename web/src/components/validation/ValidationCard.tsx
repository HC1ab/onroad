import type { ReactNode } from 'react'

interface Props {
  id: string
  title: string
  /** 이 검증이 묻는 것 (PRD 7장) */
  question: string
  /** 해석할 때 주의할 점. 인과로 읽히지 않게 한다. */
  caution: string
  /** null 이면 "아직 계산 전"을 보여준다 */
  ready: boolean
  pendingText?: string
  metrics?: ReactNode
  children?: ReactNode
}

/** 검증 카드 공통 틀: 묻는 것 → 그림 → 보고 수치 → 해석 주의 */
export function ValidationCard({ id, title, question, caution, ready, pendingText, metrics, children }: Props) {
  return (
    <section className="card v-card" aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`}>{title}</h3>
      <p className="v-question"><span className="muted">묻는 것</span> {question}</p>
      {ready ? (
        <>
          <div className="v-figure">{children}</div>
          {metrics && <div className="v-metrics">{metrics}</div>}
        </>
      ) : (
        <div className="v-pending">{pendingText ?? '아직 계산 전입니다. 결과가 나오면 이 자리에 그대로 표시합니다.'}</div>
      )}
      <p className="v-caution"><span className="muted">해석 주의</span> {caution}</p>
    </section>
  )
}

/** 보고 수치 한 칸 */
export function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="v-metric">
      <span className="muted">{label}</span>
      <b>{value}</b>
      {sub && <small className="muted">{sub}</small>}
    </div>
  )
}
