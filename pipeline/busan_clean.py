"""부산 F1 정제 + F2 읍면동 배정 (이슈: 부산 F1·F2).

흐름
    부산 횡단보도 엑셀(첫 시트) → F1 정제(행 단위 제외, 처음 걸린 사유 하나만 기록)
    → F2 좌표를 R2 읍면동 경계와 공간 결합해 adm_cd2 부여 → 건수표와 산출물 저장

원칙 (pipeline/CLAUDE.md, 루트 CLAUDE.md)
    - 설정값(이상치 상한, 좌표계)은 config.yaml 에서만 읽는다.
    - 원본 엑셀은 읽기만 한다. 결측 채우기·지오코딩 없음.
    - 보행시간은 반올림하지 않는다 (소수점 값이 0.7m/s 기준식 값인지 분류에 쓰인다).
    - 제외·매칭 실패는 건수를 표로 출력한다 (F1, F2 인수 조건).
    - 수치 표기는 "gap>0 비율, 정의 미확정" 규칙(R5)과 무관한 단계라 gap 은 다루지 않는다.

사용
    python pipeline/busan_clean.py --xlsx <부산 엑셀> --boundary <R2 geojson> [--out data/interim]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

# 엑셀 열 이름 → 내부 이름. 엑셀 형식이 바뀌면 여기만 고친다.
COLUMNS = {
    "순번": "seq",
    "행정구역(구)": "gu_raw",
    "행정구역(동)": "dong_raw",
    "지번": "jibun",
    "교차로": "crossing",
    "신호등존재유무": "signal_yn",
    "세로길이": "length_m",  # 횡단보도 연장(m). 판정식의 L
    "보행시간": "green_s",  # 현재 운영 시간(초). contracts 필드명 green_s 를 따른다
    "경도": "lon",
    "위도": "lat",
}

# 제외 사유 코드와 사람이 읽는 설명. 판정 순서가 곧 이 순서다.
REASONS = {
    "coord_missing": "좌표 없음",
    "coord_range": "좌표가 한국 범위 밖",
    "length_invalid": "세로길이 없음 또는 0 이하",
    "green_invalid": "보행시간 없음 또는 0 이하",
    "duplicate": "중복 행 (구·동·지번·좌표·길이·보행시간 동일, 순번이 빠른 행만 남김)",
    "outlier_length": "세로길이 > outlier.max_length_m",
    "outlier_green": "보행시간 > outlier.max_green_s",
}

# 한국 영역의 대략적 경계(도). 분석 설정이 아니라 좌표 오입력을 걸러내는 물리적 한계다.
KOREA_LAT = (33.0, 39.0)
KOREA_LON = (124.0, 132.0)

# 동 이름 비교에서 지우는 글자: 엑셀은 법정동('우동'), R2 는 행정동('우2동')이라 번호를 뗀다.
_DONG_STRIP = str.maketrans("", "", "0123456789·.")

DUP_KEY = ["gu_raw", "dong_raw", "jibun", "lat", "lon", "length_m", "green_s"]


def load_config(path: Path) -> dict:
    """config.yaml 을 읽어 필요한 키가 있는지 확인한다."""
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("outlier", "crs_storage", "crs_compute"):
        if key not in cfg:
            raise KeyError(f"config.yaml 에 '{key}' 가 없다")
    for key in ("max_length_m", "max_green_s"):
        if key not in cfg["outlier"]:
            raise KeyError(f"config.yaml outlier 에 '{key}' 가 없다")
    return cfg


def load_input(xlsx: Path) -> pd.DataFrame:
    """엑셀 첫 시트만 읽는다. 필요한 열이 없으면 바로 실패한다 (조용한 오류 방지)."""
    raw = pd.read_excel(xlsx, sheet_name=0)
    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise KeyError(f"엑셀에 필요한 열이 없다: {missing}")
    df = raw[list(COLUMNS)].rename(columns=COLUMNS).copy()
    for col in ("length_m", "green_s", "lat", "lon"):
        df[col] = pd.to_numeric(df[col], errors="coerce")  # 숫자가 아니면 결측으로 본다
    return df


def clean(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """F1: 행마다 처음 걸린 제외 사유 하나를 붙이고, 남은 행과 제외된 행을 나눠 돌려준다."""
    out = df.copy()
    out["reason"] = ""

    def mark(mask: pd.Series, code: str) -> None:
        # 아직 사유가 없는 행에만 붙인다 (처음 걸린 사유만 기록)
        out.loc[mask & (out["reason"] == ""), "reason"] = code

    mark(out["lat"].isna() | out["lon"].isna(), "coord_missing")
    mark(~out["lat"].between(*KOREA_LAT) | ~out["lon"].between(*KOREA_LON), "coord_range")
    mark(~(out["length_m"] > 0), "length_invalid")  # NaN 도 여기에 걸린다
    mark(~(out["green_s"] > 0), "green_invalid")

    # 중복은 지금까지 통과한 행끼리만 비교한다 (앞 사유로 빠진 행과 비교하지 않는다)
    alive = out[out["reason"] == ""].sort_values("seq")
    dup = alive.duplicated(subset=DUP_KEY, keep="first")
    mark(out.index.isin(alive.index[dup]), "duplicate")

    mark(out["length_m"] > cfg["outlier"]["max_length_m"], "outlier_length")
    mark(out["green_s"] > cfg["outlier"]["max_green_s"], "outlier_green")

    kept = out[out["reason"] == ""].drop(columns="reason").copy()
    excluded = out[out["reason"] != ""].copy()
    # 식별자: 원본 순번 기반. 같은 엑셀이면 항상 같은 값이 나온다.
    kept.insert(0, "cw_id", kept["seq"].map(lambda s: f"busan-{int(s):05d}"))
    return kept.reset_index(drop=True), excluded.reset_index(drop=True)


def load_boundary(path: Path, sido_prefix: str, cfg: dict) -> gpd.GeoDataFrame:
    """R2 경계 중 지정한 시도(adm_cd2 앞자리)만 남긴다. adm_cd2 는 문자열로 둔다."""
    gdf = gpd.read_file(path)
    gdf["adm_cd2"] = gdf["adm_cd2"].astype(str)
    gdf = gdf[gdf["adm_cd2"].str.startswith(sido_prefix)].copy()
    if gdf.crs is None:
        gdf = gdf.set_crs(cfg["crs_storage"])  # 이 파일은 CRS84(= 경도·위도)
    return gdf.to_crs(cfg["crs_storage"])


def assign(kept: pd.DataFrame, bnd: gpd.GeoDataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """F2: 점이 속한 읍면동을 찾는다. 경계 위의 점은 adm_cd2 가 가장 작은 동 하나로 고정한다.

    매칭 실패 행은 가장 가까운 경계까지의 거리(m, EPSG:5179)를 계산해 원인 확인용으로만 돌려준다.
    자동으로 고치지 않는다.
    """
    pts = gpd.GeoDataFrame(
        kept.copy(),
        geometry=gpd.points_from_xy(kept["lon"], kept["lat"]),
        crs=cfg["crs_storage"],
    )
    cols = ["adm_cd2", "adm_nm", "sggnm", "geometry"]
    joined = gpd.sjoin(pts, bnd[cols], how="left", predicate="within")
    # 점이 여러 경계에 걸리면 행이 늘어난다. 하나로 고정하고 몇 곳이었는지 센다.
    joined = joined.sort_values(["cw_id", "adm_cd2"])
    tie_ids = set(joined.loc[joined.duplicated("cw_id", keep=False), "cw_id"])
    joined = joined.drop_duplicates("cw_id", keep="first").drop(columns="index_right")
    joined["boundary_tie"] = joined["cw_id"].isin(tie_ids)

    matched = joined["adm_cd2"].notna()
    # 동 이름은 R2 행정동 이름의 마지막 단어 (예: '부산광역시 중구 중앙동' → '중앙동')
    joined["dong_r2"] = joined["adm_nm"].str.split().str[-1]
    joined["gu_match"] = joined["gu_raw"].str.strip() == joined["sggnm"]
    joined["dong_match"] = (joined["dong_raw"].str.strip().str.translate(_DONG_STRIP)
                            == joined["dong_r2"].str.translate(_DONG_STRIP))
    joined["gu_dist_m"] = pd.NA  # 구 이름이 다른 행만 채운다 (엑셀이 적은 구까지의 거리, m)

    # 실패 행: 가장 가까운 동까지 거리. 거리는 미터 좌표계에서 잰다.
    bad = joined[~matched].copy()
    if len(bad):
        near = gpd.sjoin_nearest(
            bad[["cw_id", "geometry"]].to_crs(cfg["crs_compute"]),
            bnd[["adm_cd2", "adm_nm", "geometry"]].to_crs(cfg["crs_compute"]),
            how="left",
            distance_col="dist_m",
        ).drop_duplicates("cw_id")
        bad = bad.drop(columns=["adm_cd2", "adm_nm"]).merge(
            near[["cw_id", "adm_cd2", "adm_nm", "dist_m"]].rename(
                columns={"adm_cd2": "nearest_adm_cd2", "adm_nm": "nearest_adm_nm"}),
            on="cw_id", how="left")
    # 구 이름이 다른 행: 엑셀에 적힌 구의 경계까지 거리를 잰다. 경계 근처면 좌표 오차, 멀면 입력 오류 후보.
    gu_polys = bnd.dissolve(by="sggnm").to_crs(cfg["crs_compute"]).geometry
    off = joined[matched & ~joined["gu_match"]]
    for idx, row in off.iterrows():
        gu = str(row["gu_raw"]).strip()
        if gu in gu_polys.index:
            pt = gpd.GeoSeries([row.geometry], crs=cfg["crs_storage"]).to_crs(cfg["crs_compute"]).iloc[0]
            joined.at[idx, "gu_dist_m"] = float(pt.distance(gu_polys[gu]))
    joined["gu_dist_m"] = pd.to_numeric(joined["gu_dist_m"], errors="coerce")
    assigned = pd.DataFrame(joined[matched].drop(columns="geometry"))
    unmatched = pd.DataFrame(bad.drop(columns="geometry")) if len(bad) else pd.DataFrame()
    return assigned.reset_index(drop=True), unmatched.reset_index(drop=True)


def reason_table(excluded: pd.DataFrame, total: int) -> pd.DataFrame:
    """제외 사유별 건수표 (F1 인수 조건). 건수 0인 사유도 보여 준다."""
    counts = excluded["reason"].value_counts()
    rows = [{"reason": c, "설명": d, "건수": int(counts.get(c, 0))} for c, d in REASONS.items()]
    t = pd.DataFrame(rows)
    t["비율(%)"] = (t["건수"] / total * 100).round(2)
    return t


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(xlsx: Path, boundary: Path, out_dir: Path, config: Path, sido_prefix: str) -> dict:
    cfg = load_config(config)
    df = load_input(xlsx)
    kept, excluded = clean(df, cfg)
    bnd = load_boundary(boundary, sido_prefix, cfg)
    assigned, unmatched = assign(kept, bnd, cfg)

    out_dir.mkdir(parents=True, exist_ok=True)
    table = reason_table(excluded, len(df))
    kept.to_csv(out_dir / "busan_f1_clean.csv", index=False, encoding="utf-8-sig")
    excluded.to_csv(out_dir / "busan_f1_exclusions.csv", index=False, encoding="utf-8-sig")
    table.to_csv(out_dir / "busan_f1_reasons.csv", index=False, encoding="utf-8-sig")
    assigned.to_csv(out_dir / "busan_f2_assigned.csv", index=False, encoding="utf-8-sig")
    unmatched.to_csv(out_dir / "busan_f2_unmatched.csv", index=False, encoding="utf-8-sig")

    n_kept, n_ok = len(kept), len(assigned)
    meta = {
        "input_file": xlsx.name,
        "input_sha256": sha256(xlsx),
        "boundary_file": boundary.name,
        "config": {"outlier": cfg["outlier"], "crs_storage": cfg["crs_storage"],
                   "crs_compute": cfg["crs_compute"]},
        "f1": {"input_rows": len(df), "kept": n_kept, "excluded": len(excluded),
               "signal_yn_not_yes": int((df["signal_yn"].fillna("") != "유").sum())},
        "f2": {"boundary_dongs": int(len(bnd)), "assigned": n_ok,
               "unmatched": len(unmatched),
               "unmatched_rate_pct": round(len(unmatched) / n_kept * 100, 3) if n_kept else None,
               "boundary_ties": int(assigned["boundary_tie"].sum()),
               "gu_name_match_pct": round(float(assigned["gu_match"].mean() * 100), 2) if n_ok else None,
               "dong_name_match_pct": round(float(assigned["dong_match"].mean() * 100), 2) if n_ok else None,
               "gu_name_mismatch": int((~assigned["gu_match"]).sum()),
               "gu_name_mismatch_dist_m_median": (round(float(assigned["gu_dist_m"].median()), 1)
                                                  if assigned["gu_dist_m"].notna().any() else None)},
    }
    (out_dir / "busan_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[F1] 제외 사유별 건수")
    print(table.to_string(index=False))
    print(f"\n입력 {len(df):,} → 남음 {n_kept:,} / 제외 {len(excluded):,}")
    print(f"[F2] 동 배정 {n_ok:,} / 경계 밖 {len(unmatched):,} ({meta['f2']['unmatched_rate_pct']}%)")
    print(f"     구 이름 일치 {meta['f2']['gu_name_match_pct']}% (불일치 {meta['f2']['gu_name_mismatch']}곳,"
          f" 엑셀이 적은 구까지 거리 중앙값 {meta['f2']['gu_name_mismatch_dist_m_median']} m)")
    print(f"     동 이름 일치 {meta['f2']['dong_name_match_pct']}% (번호 제거 후, 법정동·행정동 차이)"
          f"  경계 위 동점 {meta['f2']['boundary_ties']}곳")
    if len(unmatched):
        d = unmatched["dist_m"].describe()[["min", "50%", "max"]].round(1).to_dict()
        print(f"     경계 밖 곳의 가장 가까운 동까지 거리(m): {d}")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", type=Path, required=True, help="부산 횡단보도 엑셀 (원본, 수정 금지)")
    ap.add_argument("--boundary", type=Path, required=True, help="R2 admdongkor geojson")
    ap.add_argument("--out", type=Path, default=Path("data/interim"), help="산출물 폴더 (git 제외)")
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--sido-prefix", default="26", help="adm_cd2 앞자리. 부산 = 26")
    a = ap.parse_args(argv)
    run(a.xlsx, a.boundary, a.out, a.config, a.sido_prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
