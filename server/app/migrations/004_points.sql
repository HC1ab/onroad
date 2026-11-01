-- 전체 횡단보도 점(분석·분석 제외, 계약 #60). 후보 점(candidate)과 따로 둔다.
-- 묶음에 점 파일이 없을 수 있어(선택 항목) 적재된 속도·반경 조합을 point_layer 로 구분한다.
CREATE TABLE point_layer (
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    radius_m integer NOT NULL CHECK (radius_m IN (200,300,500)),
    PRIMARY KEY (speed, radius_m)
);
CREATE TABLE crosswalk_point (
    speed numeric NOT NULL,
    radius_m integer NOT NULL,
    cw_id text NOT NULL,
    adm_cd text NOT NULL,
    status text NOT NULL CHECK (status IN ('analyzed','excluded')),
    geom geometry(Point,4326) NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (speed, radius_m, cw_id),
    FOREIGN KEY (speed, radius_m) REFERENCES point_layer(speed, radius_m)
);
CREATE INDEX crosswalk_point_geom_idx ON crosswalk_point USING gist (geom);

-- 표본 하한(min_sample)은 areas 응답의 최상위 값이라 집계 행에 둔다. 예전 묶음에는 없으므로 null 허용.
ALTER TABLE area_summary ADD COLUMN min_sample integer CHECK (min_sample >= 1);
