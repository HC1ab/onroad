-- v2 3단계 기준 결과(결정 009, 계약 C3). v1 표는 그대로 두고 목표 커버리지(target)·반경별로 따로 둔다.
-- 묶음에 없을 수 있어(선택 항목) 적재된 조합을 area_summary_v2·point_layer_v2 로 구분한다.
ALTER TABLE crosswalk_point DROP CONSTRAINT crosswalk_point_status_check;
ALTER TABLE crosswalk_point ADD CONSTRAINT crosswalk_point_status_check
    CHECK (status IN ('analyzed','excluded','data_check'));

CREATE TABLE area_summary_v2 (
    target numeric NOT NULL CHECK (target IN (0.85,0.9,0.95)),
    radius_m integer NOT NULL CHECK (radius_m IN (200,300,500)),
    thresholds jsonb NOT NULL,
    min_sample integer CHECK (min_sample >= 1),
    PRIMARY KEY (target, radius_m)
);
CREATE TABLE area_vulnerability_v2 (
    target numeric NOT NULL,
    radius_m integer NOT NULL,
    adm_cd text NOT NULL REFERENCES admin_area(adm_cd),
    payload jsonb NOT NULL,
    PRIMARY KEY (target, radius_m, adm_cd),
    FOREIGN KEY (target, radius_m) REFERENCES area_summary_v2(target, radius_m)
);

-- 점의 v1 필드(t_need_s·gap_s·flags)는 speed 하나로 계산돼 있어 조합마다 그 속도를 적어 둔다.
CREATE TABLE point_layer_v2 (
    target numeric NOT NULL CHECK (target IN (0.85,0.9,0.95)),
    radius_m integer NOT NULL CHECK (radius_m IN (200,300,500)),
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    PRIMARY KEY (target, radius_m)
);
CREATE TABLE crosswalk_point_v2 (
    target numeric NOT NULL,
    radius_m integer NOT NULL,
    cw_id text NOT NULL,
    adm_cd text NOT NULL,
    status text NOT NULL CHECK (status IN ('analyzed','excluded','data_check')),
    geom geometry(Point,4326) NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (target, radius_m, cw_id),
    FOREIGN KEY (target, radius_m) REFERENCES point_layer_v2(target, radius_m)
);
CREATE INDEX crosswalk_point_v2_geom_idx ON crosswalk_point_v2 USING gist (geom);
