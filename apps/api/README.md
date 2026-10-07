# apps/api

Python package `aip`: FastAPI app, platform services and business modules (ADR 0001, 0004).

```bash
uv sync --all-packages --frozen
uv run uvicorn aip.main:create_app --factory --reload
uv run pytest
python tools/new_module.py <snake_case_name>   # scaffold a module from aip/modules/_template
```
