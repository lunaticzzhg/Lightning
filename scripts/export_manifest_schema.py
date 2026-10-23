"""Keep the published ZIP manifest schema derived from its Pydantic source."""
import json
import sys
from pathlib import Path

from backend.features.strategies.manifest import Manifest

path = Path(__file__).resolve().parents[1] / 'contracts/strategy/strategy.schema.json'
content = json.dumps(Manifest.model_json_schema(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'
if '--check' in sys.argv:
    if path.read_text() != content:
        raise SystemExit('strategy.schema.json 已过期，请运行 python -m scripts.export_manifest_schema')
else:
    path.write_text(content)
