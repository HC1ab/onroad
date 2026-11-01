import type { MetaResponse } from '../api/types'
import { pct1 } from '../lib/format'

// meta 를 못 받아도 한계 고지는 항상 보이게 한다(F9).
const FALLBACK_LIMITS =
  '한계: 녹색신호시간 정의(점멸 포함 여부) 확정 전 · 읍면동 평균은 개별 이용자 구성이 아님 · 인과 미검증 · "점검 우선순위 후보"이며 위험·위반 판정이 아님'

const DEF_LABEL: Record<MetaResponse['green_def_status'], string> = {
  unconfirmed: '확정 전 (점멸 포함 여부 확인 중)',
  includes_flash: '점멸 포함으로 확인',
  excludes_flash: '점멸 제외로 확인',
}

const REPO = 'https://github.com/HC1ab/onroad'

/** About (피드백 16번): 하단 바에 있던 한계 고지·출처와, 화면 용어 설명을 한곳에 모은다(F9). */
export function AboutPage({ meta, minSample }: { meta: MetaResponse | null; minSample: number | null }) {
  return (
    <div className="about-page">
      <section className="card">
        <h2>한 박자 — 무엇을 보나</h2>
        <p>
          전국 횡단보도마다 공공데이터에 기록된 녹색신호시간을 기준식 <b>7초 + 연장 ÷ 보행 속도</b>와 비교합니다.
          보행 속도는 일반 1.0 m/s, 보행약자 0.8 m/s, 노인 0.7 m/s 세 가지로 바꿔 볼 수 있습니다.
          기록값이 기준식보다 짧은 횡단보도 중 노인이 오가는 목적지 가까이에 있는 곳을 <b>점검 우선순위 후보</b>로 보여줍니다.
        </p>
      </section>

      <section className="card">
        <h3>한계</h3>
        <p>{meta?.limits_text ?? FALLBACK_LIMITS}</p>
        <ul>
          <li>녹색신호시간 필드에 점멸 시간이 들어 있는지 확정되기 전에는 "짧음"의 크기를 확정된 값으로 읽지 않습니다.</li>
          <li>읍면동 평균은 그 동의 개별 횡단보도 이용자 구성을 뜻하지 않습니다.</li>
          <li>모든 검증은 연관성이며 인과가 아닙니다. 보행량 자료가 없습니다.</li>
          <li>노출 플래그가 없다고 노인 통행이 없다는 뜻은 아닙니다. 다발지역이 아니라고 사고가 없다는 뜻도 아닙니다.</li>
        </ul>
      </section>

      <section className="card">
        <h3>화면 용어</h3>
        <dl className="about-terms">
          <dt>기준식보다 짧은 비율</dt>
          <dd>읍면동 안 분석한 횡단보도 중 기록값이 기준식보다 짧은 곳의 비율. 지도 채색과 사분면 가로축.</dd>
          <dt>짧은 초 (점 색)</dt>
          <dd>기준식 필요 시간 − 기록 녹색신호시간. 양수(빨강)면 기록값이 짧고, 음수(파랑)면 여유가 있습니다.</dd>
          <dt>점검 우선순위 후보</dt>
          <dd>기록값이 기준식보다 짧으면서 노출이 1개 이상인 횡단보도. 판정이 아니라 먼저 살펴볼 곳의 목록입니다.</dd>
          <dt>노출 반경</dt>
          <dd>
            횡단보도에서 이 거리 안에 경로당·마을회관, 전통시장, 노인·장애인 보호구역, 노인 보행사고 다발지역(과거 연도)이 있으면 노출로 봅니다.
            기본 300m(노인보호구역 지정 범위 법령 기준), 200·500m는 비교용. 바꾸면 후보만 바뀌고 채색·사분면은 그대로입니다.
          </dd>
          <dt>표본 부족</dt>
          <dd>
            분석 횡단보도가 {minSample ? `${minSample}곳` : '표본 하한'} 미만인 읍면동. 비율이 크게 흔들려 회색 빗금으로 표시하고 순위에서 뺍니다.
          </dd>
          <dt>분석 제외</dt>
          <dd>녹색신호시간·연장 기록이 없거나 정제 범위 밖이라 기준식과 비교하지 못한 횡단보도. 지도에서 속 빈 점으로 켜 볼 수 있습니다.</dd>
          <dt>내 입력 (검토 전)</dt>
          <dd>
            지도에서 횡단보도를 눌러 넣은 녹색신호시간·현장 실측. 이 브라우저에만 저장되고 서버로 보내지 않습니다.
            공식 결과와 섞지 않고, 검증 V1에서 "내 입력"으로 따로 보며 CSV로 내보내 팀 검토를 거칩니다.
          </dd>
        </dl>
      </section>

      <section className="card">
        <h3>데이터 기준</h3>
        {meta ? (
          <dl className="about-terms">
            <dt>고령 인구 기준 월</dt><dd>{meta.ref_month}</dd>
            <dt>분석 실행 시각</dt><dd>{meta.built_at.replace('T', ' ').slice(0, 16)}</dd>
            <dt>좌표가 있어 분석 가능한 비율</dt><dd>{pct1(meta.coverage_ratio)}</dd>
            <dt>녹색신호시간 정의</dt><dd>{DEF_LABEL[meta.green_def_status]}</dd>
          </dl>
        ) : (
          <p className="muted">불러오는 중…</p>
        )}
        {meta?._sample && <p className="note warn">지금 화면은 샘플 데이터입니다. 실제 분석 결과가 아닙니다.</p>}
      </section>

      <section className="card">
        <h3>출처</h3>
        <ul>
          {meta
            ? meta.sources.map((s) => (
                <li key={s.url}>
                  <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                  {s.license && s.license !== '확인 필요' ? ` (${s.license})` : ''}
                  {s.modified ? ` · ${s.modified}` : ''}
                </li>
              ))
            : <li>전국횡단보도표준데이터, admdongkor(CC BY 4.0), 행정안전부 등</li>}
          <li>배경 지도: OpenFreeMap · © OpenMapTiles · © OpenStreetMap 기여자</li>
        </ul>
        <p className="muted small">
          기준식·반경·연도 분할 등 판단 근거는 <a href={`${REPO}/tree/main/docs/decisions`} target="_blank" rel="noreferrer">결정 기록</a>에 있습니다.
        </p>
      </section>
    </div>
  )
}
