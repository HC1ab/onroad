import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { AreasResponse } from '../api/types'
import { pct0 as pct, pct1 } from '../lib/format'
import { buildPoints, countPriority, effectiveThresholds, niceMax, ticks, type PlotPoint, type Thresholds } from '../lib/quadrant'
import { regionLabel } from '../lib/region'
import { useAppState } from '../state/AppState'
import { LOW_SAMPLE_COLOR } from './mapStyle'

// SVG 좌표계(viewBox). 실제 크기는 CSS 로 패널 너비에 맞춘다.
const W = 320
const H = 260
const PAD = { left: 40, right: 12, top: 14, bottom: 34 }
const PW = W - PAD.left - PAD.right
const PH = H - PAD.top - PAD.bottom

type Axis = 'x' | 'y'

/** 읍면동 사분면 (F5). 가로 = 기준식보다 짧은 비율, 세로 = 65세 이상 비율. */
export function QuadrantChart({ data }: { data: AreasResponse | null }) {
  const { selectedAdmCd, select, customThresholds: custom, setCustomThresholds: setCustom, region } = useAppState()
  const svgRef = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<Axis | null>(null)
  const [hover, setHover] = useState<PlotPoint | null>(null)

  // 사용자가 경계선을 옮기기 전에는 API 기본값(중앙값)을 따른다. 경계선은 상위 N 목록과 공유한다.
  const t: Thresholds | null = effectiveThresholds(data, custom)

  const view = useMemo(() => {
    if (!data || !t) return null
    const { points, excluded } = buildPoints(data.items, t)
    const xMax = niceMax(points.map((p) => p.x))
    const yMax = niceMax(points.map((p) => p.y))
    return { points, excluded, xMax, yMax, priority: countPriority(points) }
  }, [data, t])

  if (!data || !t || !view) {
    return (
      <section className="card quadrant">
        <h3>읍면동 사분면</h3>
        <p className="muted">불러오는 중…</p>
      </section>
    )
  }

  const { points, excluded, xMax, yMax, priority } = view
  const sx = (v: number) => PAD.left + (Math.min(v, xMax) / xMax) * PW
  const sy = (v: number) => PAD.top + PH - (Math.min(v, yMax) / yMax) * PH
  const tx = sx(t.x)
  const ty = sy(t.y)

  // 화면 좌표 → 비율 값 (경계선 드래그)
  const toValue = (e: ReactPointerEvent, axis: Axis): number => {
    const svg = svgRef.current!
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    const v = axis === 'x' ? ((p.x - PAD.left) / PW) * xMax : ((PAD.top + PH - p.y) / PH) * yMax
    const max = axis === 'x' ? xMax : yMax
    return Math.round(Math.min(max, Math.max(0, v)) * 1000) / 1000
  }
  const onMove = (e: ReactPointerEvent) => {
    if (!drag) return
    const v = toValue(e, drag)
    setCustom({ ...t, [drag]: v })
  }
  const startDrag = (axis: Axis) => (e: ReactPointerEvent) => {
    ;(e.target as Element).setPointerCapture(e.pointerId)
    setDrag(axis)
  }

  // 표본 부족 → 일반 → 선택 순으로 그려 선택 점이 위에 오게 한다.
  const ordered = [...points].sort((a, b) => Number(b.low_sample) - Number(a.low_sample) || Number(a.adm_cd === selectedAdmCd) - Number(b.adm_cd === selectedAdmCd))

  return (
    <section className="card quadrant">
      <div className="card-head">
        <h3>읍면동 사분면{region ? ` · ${regionLabel(region)}` : ''}</h3>
        <span className="priority-count">점검 우선순위 후보 {priority}곳</span>
      </div>
      <div className="quadrant-plot">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`읍면동 ${points.length}곳의 짧음 비율과 65세 이상 비율 산점도. 점검 우선순위 후보 ${priority}곳`}
          onPointerMove={onMove}
          onPointerUp={() => setDrag(null)}
          onPointerLeave={() => setDrag(null)}
        >
          {/* 오른쪽 위 칸 */}
          <rect x={tx} y={PAD.top} width={Math.max(0, PAD.left + PW - tx)} height={Math.max(0, ty - PAD.top)} className="q-priority" />
          <text x={PAD.left + PW - 4} y={PAD.top + 12} className="q-priority-label" textAnchor="end">
            점검 우선순위 후보
          </text>

          {/* 축과 눈금 */}
          <line x1={PAD.left} y1={PAD.top + PH} x2={PAD.left + PW} y2={PAD.top + PH} className="q-axis" />
          <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + PH} className="q-axis" />
          {ticks(xMax).map((v) => (
            <text key={`x${v}`} x={sx(v)} y={PAD.top + PH + 13} textAnchor="middle" className="q-tick">{pct(v)}</text>
          ))}
          {ticks(yMax).map((v) => (
            <text key={`y${v}`} x={PAD.left - 5} y={sy(v) + 3} textAnchor="end" className="q-tick">{pct(v)}</text>
          ))}
          <text x={PAD.left + PW / 2} y={H - 4} textAnchor="middle" className="q-label">기준식보다 짧은 비율 →</text>
          <text transform={`translate(11 ${PAD.top + PH / 2}) rotate(-90)`} textAnchor="middle" className="q-label">65세 이상 비율 →</text>

          {/* 점 */}
          {ordered.map((p) => {
            const sel = p.adm_cd === selectedAdmCd
            const cls = p.low_sample ? 'q-pt low' : p.quadrant === 'high_high' ? 'q-pt hh' : 'q-pt'
            return (
              <g
                key={p.adm_cd}
                className="q-pt-wrap"
                style={{ transform: `translate(${sx(p.x)}px, ${sy(p.y)}px)` }}
                onClick={() => select(p.adm_cd, 'chart')}
                onPointerEnter={() => setHover(p)}
                onPointerLeave={() => setHover(null)}
              >
                {sel && <circle r={8} className="q-sel" />}
                <circle r={4} className={cls} style={p.low_sample ? { stroke: LOW_SAMPLE_COLOR } : undefined} />
              </g>
            )
          })}

          {/* 경계선: 넓은 투명 선으로 잡기 쉽게 */}
          <line x1={tx} y1={PAD.top} x2={tx} y2={PAD.top + PH} className="q-th" />
          <line x1={tx} y1={PAD.top} x2={tx} y2={PAD.top + PH} className="q-th-hit x" onPointerDown={startDrag('x')} />
          <line x1={PAD.left} y1={ty} x2={PAD.left + PW} y2={ty} className="q-th" />
          <line x1={PAD.left} y1={ty} x2={PAD.left + PW} y2={ty} className="q-th-hit y" onPointerDown={startDrag('y')} />
        </svg>
        {hover && (
          <div
            className="q-tip"
            style={{ left: `${(sx(hover.x) / W) * 100}%`, top: `${(sy(hover.y) / H) * 100}%` }}
          >
            <b>{hover.adm_name}</b> <span className="muted">{hover.sigungu}</span>
            <br />짧음 {pct1(hover.x)} · 65세 이상 {pct1(hover.y)}
            {hover.low_sample && <><br />표본 부족 (순위 제외)</>}
          </div>
        )}
      </div>
      <div className="quadrant-foot">
        <span>
          경계선: {custom ? '직접 조절' : '전국 중앙값'} (짧음 {pct1(t.x)} · 65세 {pct1(t.y)}) · 선을 끌어 조절
        </span>
        {custom && (
          <button type="button" className="link-btn" onClick={() => setCustom(null)}>중앙값으로</button>
        )}
      </div>
      <div className="quadrant-foot muted">
        <span><i className="q-legend-low" /> 표본 부족(후보 제외)</span>
        {excluded > 0 && <span> · 값 없음 {excluded}곳 제외</span>}
      </div>
    </section>
  )
}
