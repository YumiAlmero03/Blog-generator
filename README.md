# Auto Blog Generator

Auto Blog Generator is a local Flask workspace for creating and managing SEO content. It supports blog posts, medium/backlink posts, WordPress pages, simple pages, social posts, image tools, text tools, brand profiles, medium profiles, and website SEO checks.

## Features

- Blog title, meta description, tag, and article generation
- Medium Blog Generator with platform-specific rules
- Page Generator and Simple Page Generator
- Social Media Activator and Social Media List
- Brand library with logos, colors, presets, and keyword history
- Medium library with post type, title, min-word, and max-word rules
- Website SEO Checker for on-page checks, robots.txt, sitemap, headings, social cards, links, and image alt text
- Generation dashboard and history
- Quality reports for generated content
- Provider support for Ollama, OpenAI, and Gemini

## Run Locally

```bash
source venv/bin/activate
pip install -r requirements.txt
python ui.py
```

Then open:

```text
http://localhost:3444
```

## Configuration

Provider and model configuration lives in `config.py` and environment variables, depending on your local setup.

The app supports:

- `ollama`
- `openai`
- `gemini`

For cloud providers, set the required API keys in your environment.

## Project Structure

- `app/controllers/`: Flask page handlers
- `app/services/`: reusable app logic
- `app/routes/web.py`: route registration
- `database/`: SQLite schema and data helpers
- `generators/`: AI generation orchestration
- `prompts/`: prompt builders grouped by feature
- `templates/`: Jinja pages and shared layout
- `static/`: CSS and JavaScript
- `tests/`: unit tests
- `docs/`: architecture and testing notes

Read more in:

- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`

## Testing

```bash
pytest
```

Syntax check:

```bash
python -m compileall app database generators prompts
```

GitHub Actions is configured in `.github/workflows/tests.yml`.

## Personalization Notes

Use global settings for app-wide defaults such as word limits and shared URLs. Use brand records for brand-specific personalization such as niche, tone, notes, colors, logo, website, and main keywords.

When adding a new setting:

1. Add the setting key and defaults in a service.
2. Save it from `app/controllers/settings_controller.py`.
3. Add the field in `templates/settings.html`.
4. Pass the setting into prompts or validators explicitly.
5. Add a unit test for fallback behavior.

## Docker

If Docker files are present in your checkout:

```bash
cp .env.example .env
docker compose up --build
```

Then open `http://localhost:3444`.
