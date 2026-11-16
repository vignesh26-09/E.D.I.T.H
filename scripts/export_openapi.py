"""Export OpenAPI schema specification to docs/openapi.json."""

import json
import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from edith_brain.api.app import create_app


def export_openapi() -> None:
    app = create_app()
    openapi_schema = app.openapi()
    output_path = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    print(f"Exported OpenAPI specification successfully to {output_path}")


if __name__ == "__main__":
    export_openapi()
