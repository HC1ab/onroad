import type { Speed } from '../api/types'
import { meter, sec1 } from '../lib/format'
import { richParts, v1Narrative, v2Narrative } from '../lib/narrative'
import { needSeconds } from '../lib/points'
import { fmtPct, TIER_DESC, TIER_LABEL } from '../lib/recommend'
import { ROUTE_HASH } from '../lib/route'
import { useAppState } from '../state/AppState'
import { useUserInputs } from '../state/UserInputs'

type Props = NonNullable<ReturnType<typeof useAppState>['point']>['props']

/** 오른쪽 패널: 지도에서 고른 횡단보도. 위는 수치(타일·비교 막대), 아래는 분석 요약 문장. */
export function CrosswalkDetail({ areaName }: { areaName: string | null }) {
  const { point, setPoint, basis, target, speed, radius } = useAppState()
  const { inputs } = useUserInputs()
  if (!point) return null
  const p = point.props
  const v2 = basis === 'v2'
  const narrative = v2 ? v2Narrative(p, target, radius) : v1Narrative(p, speed)
  const myCount = inputs.measurements.filter((m) => m.cw_id === p.cw_id).length

  const status = p.status === 'excluded' ? '분석 제외' : p.status === 'data_check' ? '기록 방식 확인 중' : null

  return (
    <section className="cw-detail" aria-label="선택한 횡단보도">
      <header className="cwd-head">
        <div>
          <p className="cwd-eyebrow">{areaName ?? p.adm_cd}</p>
          <h2>횡단보도 {p.cw_id.replace(/^busan-0*/, '')}</h2>
          <div className="cwd-chips">
            {status ? (
              <span className="chip muted-chip">{status}</span>
            ) : v2 && p.tier ? (
              <span className="chip" title={TIER_DESC[p.tier]}>{TIER_LABEL[p.tier]}</span>
            ) : p.is_candidate ? (
              <span className="chip accent-chip">점검 우선순위 후보</span>
            ) : null}
            {p.length_m != null && <span className="chip muted-chip">연장 {meter(p.length_m)}</span>}
          </div>
        </div>
        <button type="button" className="icon-btn" aria-label="횡단보도 상세 닫기" onClick={() => setPoint(null)}>✕</button>
      </header>

      {!status && (v2 ? <V2Numbers p={p} /> : <V1Numbers p={p} speed={speed} />)}

      <section className="cwd-narrative" aria-label="분석 요약">
        <h3>분석 요약 <span className="muted small">데이터 값으로 자동 작성</span></h3>
        {narrative.paragraphs.map((x) => (
          <div key={x.title} className="cwd-para">
            <h4>{x.title}</h4>
            <p>{richParts(x.text).map((t, i) => (i % 2 ? <strong key={i}>{t}</strong> : t))}</p>
          </div>
        ))}
        <p className="cwd-caveat">{narrative.caveat}</p>
      </section>

      <a className="cwd-link" href={ROUTE_HASH.validation}>
        현장 실측 입력하기{myCount > 0 && ` · 내 입력 ${myCount}건`} →
      </a>
    </section>
  )
}

/** 3단계 기준: 추가 초(대표 수치) · 현재 vs 기준 적용 시간 막대 · 적용 속도 · 고령 커버리지 */
function V2Numbers({ p }: { p: Props }) {
  if (p.t_required_s == null || p.green_s == null) return <p className="muted small">이 조합에서는 계산 값이 없습니다.</p>
  const add = p.add_s ?? 0
  const max = Math.max(p.t_required_s, p.green_s)
  return (
    <div className="cwd-numbers">
      <div className="hero">
        <span className="hero-label">기준 적용 시 추가 시간</span>
        <span className="hero-value">{add > 0 ? `+${add.toFixed(1)}` : '0'}<small>초</small></span>
        <span className="hero-sub">{add > 0 ? `${sec1(p.green_s)} → ${sec1(p.t_required_s)}` : '현재 기록이 기준 적용 시간 이상'}</span>
      </div>

      <figure className="cmp" aria-label="보행시간 비교">
        <CmpBar label="현재 기록" value={p.green_s} max={max} />
        <CmpBar label="기준 적용" value={p.t_required_s} max={max} strong />
      </figure>

      <dl className="tiles">
        <div className="tile">
          <dt>적용 속도</dt>
          <dd>{p.v_applied_mps != null ? p.v_applied_mps.toFixed(2) : '—'}<small>m/s</small></dd>
        </div>
        <div className="tile">
          <dt>주민 고령 비율</dt>
          <dd>{fmtPct(p.resident_elderly_ratio)}</dd>
        </div>
        <div className="tile wide">
          <dt>고령 보행자 커버리지</dt>
          <dd>{fmtPct(p.coverage_now)} <span className="arrow">→</span> {fmtPct(p.coverage_required)}</dd>
          <Meter now={p.coverage_now ?? 0} after={p.coverage_required ?? 0} />
        </div>
      </dl>
    </div>
  )
}

/** 기록값 기준: 짧은 초(대표 수치) · 기록 vs 기준식 막대 · 노출 수 */
function V1Numbers({ p, speed }: { p: Props; speed: Speed }) {
  const need = p.t_need_s ?? (p.length_m != null ? needSeconds(p.length_m, speed) : null)
  if (p.gap_s == null || need == null || p.green_s == null) return null
  const g = p.gap_s
  return (
    <div className="cwd-numbers">
      <div className="hero">
        <span className="hero-label">기준식({speed.toFixed(1)}m/s) 대비</span>
        <span className="hero-value">{g > 0 ? g.toFixed(1) : Math.abs(g).toFixed(1)}<small>초 {g > 0 ? '짧음' : '여유'}</small></span>
      </div>
      <figure className="cmp" aria-label="보행시간 비교">
        <CmpBar label="현재 기록" value={p.green_s} max={Math.max(need, p.green_s)} />
        <CmpBar label="기준식" value={need} max={Math.max(need, p.green_s)} strong />
      </figure>
      <dl className="tiles">
        <div className="tile"><dt>노출 시설</dt><dd>{p.exposure_cnt}<small>종</small></dd></div>
        <div className="tile"><dt>연장</dt><dd>{p.length_m != null ? Math.round(p.length_m) : '—'}<small>m</small></dd></div>
      </dl>
    </div>
  )
}

/** 같은 축(0~max) 위의 얇은 가로 막대. 값은 글자색으로 옆에 쓴다. */
function CmpBar({ label, value, max, strong }: { label: string; value: number; max: number; strong?: boolean }) {
  return (
    <div className="cmp-row">
      <span className="cmp-label">{label}</span>
      <span className="cmp-track"><span className={strong ? 'cmp-fill strong' : 'cmp-fill'} style={{ width: `${(value / max) * 100}%` }} /></span>
      <span className="cmp-value">{sec1(value)}</span>
    </div>
  )
}

/** 0~100% 트랙에 현재(연한 색)와 기준 적용 후(진한 색)를 겹쳐 그린다 */
function Meter({ now, after }: { now: number; after: number }) {
  return (
    <span className="meter" role="img" aria-label={`현재 ${Math.round(now * 100)}%, 기준 적용 시 ${Math.round(after * 100)}%`}>
      <span className="meter-after" style={{ width: `${after * 100}%` }} />
      <span className="meter-now" style={{ width: `${now * 100}%` }} />
    </span>
  )
}
