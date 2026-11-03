import { api } from '../api/client'
import type { MetaResponse } from '../api/types'
import { SUMMARY } from '../components/validation/basis'
import { MeasureInput } from '../components/validation/MeasureInput'
import { V1Card } from '../components/validation/V1Card'
import { V2Card } from '../components/validation/V2Card'
import { V3Card } from '../components/validation/V3Card'
import { V4Card } from '../components/validation/V4Card'
import { V5Card } from '../components/validation/V5Card'
import { V6Card } from '../components/validation/V6Card'
import { V7Card } from '../components/validation/V7Card'
import { useApi } from '../hooks/useApi'

const DEF_LABEL: Record<MetaResponse['green_def_status'], string> = {
  unconfirmed: '녹색신호시간 정의(점멸 포함 여부) 확정 전',
  includes_flash: '녹색신호시간: 점멸 포함으로 확인',
  excludes_flash: '녹색신호시간: 점멸 제외로 확인',
}

/** 검증 화면 (F8). V1~V4 결과를 수치와 함께 한 페이지에 보여준다. */
export function ValidationPage({ meta }: { meta: MetaResponse | null }) {
  const v = useApi((s) => api.validation(s), [])

  return (
    <div className="v-page">
      <div className="v-head">
        <div>
          <h2>검증 결과</h2>
          <p className="muted">
            <b>부산 기준</b> · 지도의 지역 선택과 관계없습니다 · 결과가 기대와 다르게 나와도 그대로 표시합니다 · 모든 검증은 연관성이며 인과가 아닙니다
          </p>
        </div>
        {meta && (
          <span className={meta.green_def_status === 'unconfirmed' ? 'v-status warn' : 'v-status'}>
            {DEF_LABEL[meta.green_def_status]}
          </span>
        )}
      </div>

      <section className="card v-intro" aria-label="검증 안내">
        <p>
          지도는 횡단보도마다 기록된 녹색신호시간을 기준식(7초 + 연장 ÷ 보행 속도)과 비교한 결과입니다.
          이 결과를 그대로 믿어도 되는지, 다섯 가지로 확인합니다. 각 카드의 "쓴 데이터 · 방법 · 읽는 법"을 펼치면 자세히 볼 수 있습니다.
        </p>
        <ol className="v-summary">
          {SUMMARY.map((s) => (
            <li key={s.id}><b>{s.id} {s.label}</b> — {s.role}</li>
          ))}
        </ol>
      </section>

      <MeasureInput />

      {v.error ? (
        <div className="load-inline error" role="alert">
          {v.error.message}
          <button type="button" onClick={v.reload}>다시 시도</button>
        </div>
      ) : !v.data ? (
        <p className="muted">불러오는 중…</p>
      ) : (
        <div className="v-grid">
          <V1Card v1={v.data.v1} />
          <V2Card v2={v.data.v2} />
          <V3Card v3={v.data.v3} />
          <V4Card v4={v.data.v4} />
          <V6Card v6={v.data.v6} />
          <V7Card v7={v.data.v7} />
          <div className="v-wide"><V5Card v5={v.data.v5} /></div>
        </div>
      )}
    </div>
  )
}
