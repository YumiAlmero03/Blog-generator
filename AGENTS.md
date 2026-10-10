# AGENTS.md

## Project Overview

Auto Blog Generator is a local Python Flask web app for SEO content generation and content operations. The detected stack is Python, Flask, Jinja HTML templates, Tailwind CDN plus project CSS, browser JavaScript, SQLite, pytest, Docker, and AI provider adapters for Ollama, OpenAI, and Gemini.

The frontend originated from an existing design. Preserve its visual appearance unless the task explicitly requests a design change.

## Core Rule

Preserve the existing frontend design, layout, typography, spacing, colors, CSS variables, responsive behavior, and visual structure unless the task explicitly requests a design change. Do not unnecessarily rewrite working HTML, Jinja, CSS, or JavaScript.

## Repository Structure

- `/app/controllers`: Flask page handlers and form workflows.
- `/app/routes/web.py`: central route registration.
- `/app/services`: reusable business logic, SEO checks, image tools, background jobs, schedulers, provider selection, document exports.
- `/app/events` and `/app/views`: generation status event state and SSE views.
- `/database`: SQLite schema, migration, and data-access helpers.
- `/generators`: AI generation orchestration and validation.
- `/prompts`: prompt builders grouped by feature.
- `/providers`: Ollama, OpenAI, and Gemini provider adapters.
- `/templates`: Jinja pages and shared partials. `templates/index.html` is the main blog generator page.
- `/static/assets/css` and `/static/assets/js`: shared frontend styles and page scripts.
- `/data`: SQLite database, WAL files, backups/recovered DBs, and uploads.
- `/tests`: pytest coverage.
- `/docs`: existing project documentation.
- `/admin`, `/api`, `/blog`, `/game`, `/includes`, `/scripts`: Not present in this repository.

## Editing Rules

- Read relevant files before editing.
- Make the smallest safe change possible.
- Do not refactor unrelated code.
- Do not rename routes without instruction.
- Do not break existing URLs.
- Preserve current Jinja/HTML structure when possible.
- Reuse existing CSS classes, templates, services, and database helpers.
- Avoid duplicating functionality.
- Keep controllers, services, generators, prompts, and database modules in their current roles.
- Do not replace working implementations simply because another approach is preferred.

## Python And Flask Rules

- Validate and normalize all request data.
- Escape output through Jinja defaults; be careful with generated HTML and `|safe`.
- Use existing controller/service/database boundaries.
- Keep provider credentials in environment variables or settings, not public files.
- Do not expose stack traces, API keys, OAuth tokens, service account JSON, or social tokens.
- Add CSRF protection for new state-changing web actions where practical; existing POST forms may not currently implement it.

## SQLite Rules

- Database location is `data/app.db`; preserve it.
- Do not delete, recreate, or move databases unless explicitly requested.
- Understand `database/schema.py` and related data helper modules before schema changes.
- Use `database/common.py:get_connection()`.
- Use parameterized queries.
- Use transactions for related writes.
- Preserve WAL behavior from `get_connection()`.
- Avoid destructive migrations; create backups/migrations when schema changes are necessary.

## Frontend Rules

- Maintain the current Tailwind/Jinja visual theme from `templates/base.html` and `static/assets/css/app.css`.
- Preserve responsive layouts and dark-mode behavior.
- Avoid unnecessary CSS rewrites and inline styles.
- Do not introduce frontend frameworks unless requested.
- Retain semantic HTML and accessibility attributes.

## SEO Rules

- Preserve existing tool routes and generated-output behavior.
- Preserve generated title/meta/canonical/OG/Twitter/schema handling unless the task requests changes.
- Do not accidentally add `noindex` to generated or inspected content.
- Preserve internal links and required URL logic.
- Use descriptive alt text when adding image UI.
- Avoid duplicate H1s in templates and generated page output.
- Sitemap/robots files are not present in this checkout; SEO tools inspect external sites and generate submissions.

## Python Utilities

- Treat root scripts such as `ui.py` and `main.py` as application/CLI entrypoints.
- Preserve existing environment variables and CLI prompts.
- Preserve current behavior of generators and services.
- Log useful errors via `logger.py`.
- Avoid silently swallowing exceptions in batch or provider workflows.

## Validation

Use commands that exist in this repo:

```bash
python -m compileall app database generators prompts
pytest
python ui.py
docker compose up --build
```

Before completing changes, check syntax, affected routes, logs in `logs/app.log`, SQLite query behavior, and responsive layout when frontend changes are made.

## Agent Behavior

When instructions conflict, use this priority:

1. Explicit user/task instructions
2. Repository-specific documentation
3. Existing architecture and patterns
4. General best practices

Prefer consistency with the existing project over unnecessary modernization.
