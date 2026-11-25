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
- Provider support for OpenRouter, Ollama, OpenAI, and Gemini

## Run Locally

```bash
source venv/bin/activate
pip install -r requirements.txt
python ui.py
```

For browser-rendered link fetching, install the Playwright browser and Linux dependencies once:

```bash
python -m playwright install --with-deps chromium
```

Then open:

```text
http://localhost:3444
```

## Configuration

Provider and model configuration lives in `config.py` and environment variables, depending on your local setup.

The app supports:

- `openrouter` (default model: `baidu/ernie-5.5-flash-preview:free`)
- `ollama`
- `openai`
- `gemini`

Example `.env` configuration for OpenRouter:

```env
PROVIDER=openrouter
MODEL=baidu/ernie-5.5-flash-preview:free
OPENROUTER_API_KEY=your_openrouter_api_key
TAVILY_API_KEY=your_tavily_api_key
TAVILY_SEARCH_MAX_RESULTS=5
TAVILY_SEARCH_TIME_RANGE=week
```

For cloud providers (`openrouter`, `openai`, `gemini`), set the required API keys (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`) in your environment or `.env` file. Never commit real API keys to git.

News Generator uses Tavily Search to find recent sources, then passes their URLs,
publication dates, and excerpts to the selected writing model. The default search
uses the `news` topic, `basic` depth, five results, and the past week. Set
`TAVILY_SEARCH_TIME_RANGE=day` for the past day. Basic search uses one Tavily credit
per request; no automatic advanced searches or retries are enabled. See
[Tavily's Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
and [credit pricing](https://docs.tavily.com/documentation/api-credits).

When reference URLs are supplied, the existing HTTP/browser reader supplies the
source text and Tavily is skipped. Without reference URLs, missing credentials,
failed searches, or empty results stop news generation with an actionable error
instead of writing current news without sources. Other generators retain their
existing Ollama search configuration. After updating code, restart the app to
load the Tavily integration; `.env` model and Tavily settings refresh on the next
request.

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

## Reset Docker

If theres additional packages

```bash
docker compose down -v
docker compose up -d --build
```
