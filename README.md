# Invoice Filler

Initial project scaffold for the Invoice Filler MVP. The backend and frontend are
kept intentionally empty until their task is reached; no Google integration or
invoice behavior is included yet.

## Local development

The project currently has no third-party dependencies:

```sh
uv run python -m unittest discover -s backend/tests
cd frontend && npm test
```

The current smoke test can also be run with:

```sh
uv run python -m unittest discover -s backend/tests -t .
```
