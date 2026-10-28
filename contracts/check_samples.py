"""contracts/samples/*.json 이 같은 이름의 스키마를 통과하는지 검사한다.

사용: pip install jsonschema referencing && python contracts/check_samples.py
CI(.github/workflows/contracts.yml)에서도 같은 명령으로 실행한다.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

# 샘플 파일 이름 → 스키마 파일 이름
PAIRS = {
    "areas.json": "areas.schema.json",
    "area_crosswalks.json": "area_crosswalks.schema.json",
    "candidates.json": "candidates.schema.json",
    "validation.json": "validation.schema.json",
    "meta.json": "meta.schema.json",
    "error.json": "error.schema.json",
    "boundaries.json": "boundaries.schema.json",
    "static_manifest.json": "static_manifest.schema.json",
}


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    schemas = {p.name: load(p) for p in ROOT.glob("*.schema.json")}
    registry = Registry().with_resources(
        (name, Resource.from_contents(s)) for name, s in schemas.items()
    )
    failed = 0
    for sample_name, schema_name in PAIRS.items():
        sample_path = SAMPLES / sample_name
        if not sample_path.exists():
            print(f"MISSING  samples/{sample_name}")
            failed += 1
            continue
        schema = schemas[schema_name]
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, registry=registry)
        errors = sorted(validator.iter_errors(load(sample_path)), key=lambda e: list(e.path))
        if errors:
            failed += 1
            print(f"FAIL     samples/{sample_name}")
            for e in errors[:10]:
                where = "/".join(str(p) for p in e.path) or "(root)"
                print(f"         {where}: {e.message}")
        else:
            print(f"OK       samples/{sample_name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
