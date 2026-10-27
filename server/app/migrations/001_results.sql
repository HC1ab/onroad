CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE dataset (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    is_sample boolean NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE admin_area (
    adm_cd text PRIMARY KEY CHECK (adm_cd ~ '^[0-9]{8,10}$'),
    adm_name text NOT NULL, sido text NOT NULL, sigungu text NOT NULL
);
CREATE INDEX admin_area_region_idx ON admin_area(sido, sigungu);
CREATE TABLE area_summary (
    speed numeric PRIMARY KEY CHECK (speed IN (0.7, 0.8, 1.0)),
    thresholds jsonb NOT NULL
);
CREATE TABLE area_vulnerability (
    speed numeric REFERENCES area_summary(speed),
    adm_cd text REFERENCES admin_area(adm_cd),
    payload jsonb NOT NULL,
    PRIMARY KEY(speed, adm_cd)
);
CREATE TABLE crosswalk (
    cw_id text PRIMARY KEY,
    adm_cd text NOT NULL REFERENCES admin_area(adm_cd),
    geom geometry(Point,4326),
    payload jsonb NOT NULL
);
CREATE INDEX crosswalk_area_idx ON crosswalk(adm_cd);
CREATE INDEX crosswalk_geom_idx ON crosswalk USING gist(geom);
CREATE TABLE crosswalk_gap (
    cw_id text REFERENCES crosswalk(cw_id),
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    is_candidate boolean NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY(speed,cw_id)
);
CREATE INDEX crosswalk_gap_candidate_idx ON crosswalk_gap(speed,cw_id) WHERE is_candidate;
-- Candidate contract is an independent, possibly partial, exported point layer.
CREATE TABLE candidate (
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    radius_m integer NOT NULL CHECK (radius_m IN (200,300,500)),
    cw_id text NOT NULL,
    adm_cd text NOT NULL REFERENCES admin_area(adm_cd),
    geom geometry(Point,4326) NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY(speed,radius_m,cw_id)
);
CREATE TABLE candidate_layer (
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    radius_m integer NOT NULL CHECK (radius_m IN (200,300,500)),
    PRIMARY KEY(speed,radius_m)
);
CREATE INDEX candidate_geom_idx ON candidate USING gist(geom);
CREATE INDEX candidate_area_idx ON candidate(speed,adm_cd);
CREATE TABLE result_document (
    kind text PRIMARY KEY CHECK (kind IN ('meta','validation')),
    payload jsonb NOT NULL
);
