# Python — Ailey Code-Referenz

> Best Practices, Patterns & häufige Stolperfallen für Python 3.10+

## Projekt-Struktur
```
project/
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── main.py
│       └── utils.py
├── tests/
│   ├── __init__.py
│   └── test_main.py
├── pyproject.toml          # Modern config (ersetzt setup.py)
├── requirements.txt
├── .env
└── README.md
```

## pyproject.toml (modern, PEP 621)
```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["flask>=3.0", "pydantic>=2.0"]

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Type Hints (IMMER verwenden ab Python 3.10+)
```python
# Modern syntax (3.10+) — kein `from typing import` nötig
def process(items: list[str], config: dict[str, int] | None = None) -> bool: ...
def fetch(url: str) -> tuple[int, str]: ...
type UserID = int  # Type alias (3.12+)
```

## Datenklassen
```python
from dataclasses import dataclass, field
from pydantic import BaseModel  # Für API/Validation

# Einfache Daten
@dataclass
class User:
    name: str
    email: str
    age: int = 0
    tags: list[str] = field(default_factory=list)

# API/Validation — Pydantic v2
class UserCreate(BaseModel):
    name: str
    email: str
    age: int = 0
    model_config = {"strict": True}
```

## Async / Await
```python
import asyncio
import aiohttp

async def fetch_url(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def main():
    results = await asyncio.gather(
        fetch_url("https://api.example.com/a"),
        fetch_url("https://api.example.com/b"),
    )

asyncio.run(main())
```

## Flask (REST API)
```python
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.get("/api/items")
def get_items():
    return jsonify({"items": [], "count": 0})

@app.post("/api/items")
def create_item():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name fehlt"}), 400
    return jsonify({"success": True, "item": {"name": name}}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

## FastAPI (async, auto-docs)
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    return {"item_id": item_id}

@app.post("/items/", status_code=201)
async def create_item(item: Item):
    return item
```

## Error Handling
```python
# Custom exceptions
class AppError(Exception):
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code

# Context managers
from contextlib import contextmanager

@contextmanager
def managed_resource():
    resource = acquire()
    try:
        yield resource
    finally:
        resource.release()
```

## Testing (pytest)
```python
import pytest

def test_basic():
    assert 1 + 1 == 2

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_api(client):
    r = client.get("/api/items")
    assert r.status_code == 200
    assert r.json["count"] == 0

@pytest.mark.parametrize("input,expected", [
    ("hello", 5), ("", 0), ("abc", 3)
])
def test_length(input, expected):
    assert len(input) == expected
```

## Häufige Stolperfallen
- `list` als Default-Parameter: `def f(items=[])` → IMMER `def f(items=None)` + `items = items or []`
- f-Strings mit Dicts: `f"{d['key']}"` — Anführungszeichen beachten
- `is` vs `==`: `is` für None/True/False, `==` für Werte
- `import` Zyklen: Lazy imports oder TYPE_CHECKING verwenden
- GIL: Für CPU-bound → `multiprocessing`, für I/O-bound → `asyncio`/`threading`
