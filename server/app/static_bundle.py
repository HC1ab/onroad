"""정적 묶음 내보내기(F18). 적재된 결과를 contracts/README.md "정적 묶음" 구성으로 파일에 쓴다.

    python -m app.static_bundle --out /out

한 읽기 트랜잭션에서 내보내므로 적재 중 결과가 섞이지 않는다. 요청 시 계산하지 않고 DB 값을 그대로 쓴다.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from fastapi import HTTPException

from . import export, routes
from .errors import NOT_LOADED

SPEEDS = (0.7, 0.8, 1.0)
RADII = (200, 300, 500)


def _loaded(load, *args):
    """미적재(not_loaded)면 None. 다른 오류는 그대로 올린다."""
    try:
        return load(*args)
    except HTTPException as exc:
        if exc.detail == NOT_LOADED:
            return None
        raise


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding='utf-8')
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def build(conn, out):
    """묶음을 out 에 쓰고 manifest 를 돌려준다."""
    sample = bool(routes.sample_flag(conn))
    _write(out / 'meta.json', routes.load_document(conn, 'meta'))
    _write(out / 'validation.json', routes.load_document(conn, 'validation'))
    results = []
    for speed in SPEEDS:
        for radius in RADII:
            key = f'{speed:.1f}_{radius}'
            areas = _loaded(routes.load_areas, conn, speed, radius)
            candidates = _loaded(routes.load_candidates, conn, speed, radius)
            if areas is None or candidates is None:
                if areas is not None or candidates is not None:
                    print(f'skip {key}: areas·candidates 중 하나만 적재됨')
                continue
            _write(out / 'areas' / f'{key}.json', areas)
            _write(out / 'candidates' / f'{key}.json', candidates)
            _write(out / 'export' / export.csv_name('areas', speed, radius),
                   export.to_csv(export.AREA_COLUMNS, areas['items']))
            details = [r[0] for r in conn.execute(
                'SELECT adm_cd FROM area_detail WHERE speed=%s AND radius_m=%s ORDER BY adm_cd',
                (speed, radius)).fetchall()]
            for adm_cd in details:
                _write(out / 'crosswalks' / key / f'{adm_cd}.json', routes.load_crosswalks(conn, adm_cd, speed, radius))
            if details:
                _write(out / 'export' / export.csv_name('crosswalks', speed, radius),
                       export.to_csv(export.CROSSWALK_COLUMNS, routes.load_candidate_rows(conn, speed, radius)))
            results.append({'speed': speed, 'radius_m': radius, 'details': details})
    manifest = {**({'_sample': True} if sample else {}),
                'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'results': results}
    _write(out / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='비어 있거나 없는 폴더')
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.exit(1, f'{args.out} 가 비어 있지 않습니다. 이전 묶음과 섞이지 않게 빈 폴더를 지정하세요.\n')
    try:
        with routes.reader() as conn:
            manifest = build(conn, args.out)
    except (HTTPException, psycopg.Error, OSError) as exc:
        parser.exit(1, f'Export failed ({type(exc).__name__}).\n')
    combos = ', '.join(f"{r['speed']:.1f}/{r['radius_m']}m(상세 {len(r['details'])})" for r in manifest['results'])
    print(f'Exported {len(manifest["results"])} combinations: {combos or "없음"}; sample={"_sample" in manifest}')


if __name__ == '__main__':
    main()
