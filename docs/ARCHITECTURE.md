# Architecture

This app is a Flask content workspace. Most pages follow the same path:

1. A route in `app/routes/web.py` points to a controller.
2. The controller reads form inputs, loads saved brand/settings context, and calls a generator or service.
3. A generator builds a prompt from `prompts/`, calls the selected provider, parses JSON, and validates the result.
4. The controller renders a template in `templates/`.
5. Important outputs are saved to SQLite through `database/`.

## Main Folders

- `app/controllers/`: request handling and page state.
- `app/services/`: reusable app logic that is not tied to one page.
- `database/`: SQLite schema and data access helpers.
- `generators/`: AI generation orchestration and validation.
- `prompts/`: prompt builders grouped by feature.
- `templates/`: Jinja pages and shared partials.
- `static/`: CSS and browser-side JavaScript.
- `tests/`: unit tests for services and pure logic.

## Navigation

The grouped sidebar lives in `templates/base.html`. Pages only need to set:

```jinja
{% set active_page = "page-key" %}
```

Use existing page keys when adding a page, or add a new key to the sidebar group where it belongs.

## Generator Pattern

Use this pattern for new AI generators:

1. Add or update a prompt builder in `prompts/`.
2. Add generator orchestration in `generators/`.
3. Add controller handling in `app/controllers/`.
4. Store generated outputs with `record_generation()` when the output is useful later.
5. Add a quality report with `analyze_generated_content()` when the output is HTML or article-like.

Keep provider calls inside `generators/` or provider-specific services. Controllers should stay focused on form state and rendering.

## Settings And Personalization

Global app settings use the `settings` table through `database/settings.py`.

For new personalization settings:

1. Add a key constant near the code that owns the setting, or create a small service in `app/services/`.
2. Read the value with `get_setting(key, default)`.
3. Save it from `app/controllers/settings_controller.py`.
4. Add the form field to `templates/settings.html`.
5. Thread the setting into prompts or validators explicitly.

Brand-level personalization belongs in `database/brands.py` and the Brands page. Use brand context when the value should affect only one brand.

## History

Generated output history is stored in `generation_history`.

Use `record_generation()` for:

- blog posts
- medium blog posts
- pages
- simple pages
- social media posts
- future generated assets that users may want to review

History detail pages show prompt inputs, quality reports, and raw output, which makes debugging easier.
