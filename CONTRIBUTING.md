# Contributing

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the codebase is laid out,
including a walkthrough of adding a second task tracker or calendar backend.

## Setup

```bash
uv sync --locked
```

## Before opening a PR

Run the full local pipeline and make sure every step passes:

```bash
uv run python -m ruff check .
uv run python -m ruff format --check .
uv run python -m pytest -q
uv run python -m mypy src tests
```

Use `uv run ...` for all of these — do not invoke `python`, `pytest`, `ruff`, or `mypy`
directly, since that bypasses the locked environment in `uv.lock`.

## Conventions

- No code comments unless the change genuinely needs one to explain a non-obvious why;
  prefer clearer naming and structure instead.
- Keep `scheduler.py` free of any import from `providers/` or a concrete integration —
  see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for why that boundary matters.
