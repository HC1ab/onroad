-- 노출 반경별 결과 (계약 #46). 후보 수·노출 플래그가 반경(200/300/500m)에 따라 달라진다.
-- 기존 행은 반경 정보가 없던 시기의 기본값 300m 로 본다.
ALTER TABLE area_vulnerability DROP CONSTRAINT area_vulnerability_speed_fkey;

ALTER TABLE area_summary ADD COLUMN radius_m integer NOT NULL DEFAULT 300 CHECK (radius_m IN (200, 300, 500));
ALTER TABLE area_summary DROP CONSTRAINT area_summary_pkey, ADD PRIMARY KEY (speed, radius_m);

ALTER TABLE area_vulnerability ADD COLUMN radius_m integer NOT NULL DEFAULT 300 CHECK (radius_m IN (200, 300, 500));
ALTER TABLE area_vulnerability DROP CONSTRAINT area_vulnerability_pkey, ADD PRIMARY KEY (speed, radius_m, adm_cd);
ALTER TABLE area_vulnerability ADD FOREIGN KEY (speed, radius_m) REFERENCES area_summary(speed, radius_m);

ALTER TABLE crosswalk_gap ADD COLUMN radius_m integer NOT NULL DEFAULT 300 CHECK (radius_m IN (200, 300, 500));
ALTER TABLE crosswalk_gap DROP CONSTRAINT crosswalk_gap_pkey, ADD PRIMARY KEY (speed, radius_m, cw_id);
DROP INDEX crosswalk_gap_candidate_idx;
CREATE INDEX crosswalk_gap_candidate_idx ON crosswalk_gap(speed, radius_m, cw_id) WHERE is_candidate;

ALTER TABLE area_detail ADD COLUMN radius_m integer NOT NULL DEFAULT 300 CHECK (radius_m IN (200, 300, 500));
ALTER TABLE area_detail DROP CONSTRAINT area_detail_pkey, ADD PRIMARY KEY (adm_cd, speed, radius_m);

-- 이후 적재는 반경을 항상 명시한다.
ALTER TABLE area_summary ALTER COLUMN radius_m DROP DEFAULT;
ALTER TABLE area_vulnerability ALTER COLUMN radius_m DROP DEFAULT;
ALTER TABLE crosswalk_gap ALTER COLUMN radius_m DROP DEFAULT;
ALTER TABLE area_detail ALTER COLUMN radius_m DROP DEFAULT;
