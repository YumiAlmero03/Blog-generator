# Testing

The project now has a small pytest foundation and a GitHub Actions workflow.

## Run Tests Locally

```bash
source venv/bin/activate
pip install -r requirements.txt
pytest
```

For a quick syntax check:

```bash
python -m compileall app database generators prompts
```

## What To Test First

Prefer tests around pure logic and validation before testing full AI flows.

Good candidates:

- content quality reports
- word-limit normalization
- SEO parser behavior
- prompt helper formatting
- SQLite data helpers with a temporary database
- controller state handling with Flask test clients

Avoid calling live AI providers in unit tests. For generator tests, use a fake provider with a `generate_json()` method that returns fixed JSON.

## CI

`.github/workflows/tests.yml` runs:

- dependency install
- `compileall`
- `pytest`

Future CI additions can include linting, formatting, Playwright UI checks, and Docker build checks.

## Suggested Next Test Layer

When the app gets more personalization settings, add tests that assert:

- settings save correctly
- controllers pass settings into generators
- prompts include the expected settings text
- invalid settings fall back safely
