-- Distinguish an imported empty detail list from a missing detail export.
CREATE TABLE area_detail (
    adm_cd text REFERENCES admin_area(adm_cd),
    speed numeric NOT NULL CHECK (speed IN (0.7,0.8,1.0)),
    PRIMARY KEY(adm_cd,speed)
);
INSERT INTO area_detail
SELECT DISTINCT c.adm_cd,g.speed FROM crosswalk c JOIN crosswalk_gap g USING(cw_id);
