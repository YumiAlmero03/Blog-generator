# Architecture

## 1. System Overview

Auto Blog Generator is a local Flask workspace for creating and managing SEO-oriented content. It provides browser pages for blog generation, page generation, backlink/medium content, social posts, image tools, website planning, SEO checks, IndexNow/Google indexing workflows, brand records, checklists, and generation history.

Main request shape:

```text
Browser
  -> Flask app from ui.py
  -> app/routes/web.py
  -> controller in app/controllers/
  -> service/generator/database helper
  -> Jinja template in templates/
  -> browser response
```

AI generation is separated into `generators/`, `prompts/`, and `providers/`. Persistent state is SQLite in `data/app.db`. Uploads and generated files are stored under `data/uploads/`. Background jobs and generation progress run in process using threads, SSE, and a WebSocket status server.

There is no PHP application, `/admin`, `/api`, `/blog`, `/game`, `/includes`, `/scripts`, `.htaccess`, `robots.txt`, or sitemap file in this checkout.

## 2. Technology Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | Jinja HTML templates, Tailwind CDN, `static/assets/css/app.css`, vanilla JS | Browser UI, forms, dark mode, generation progress, page-specific interactions |
| Backend | Python Flask | Web routes, form handling, downloads, uploads, background-job endpoints |
| Database | SQLite via `sqlite3` | Brands, keywords, content records, settings, backlinks, checklists, social profiles, SEO history, website index, image bank |
| AI Providers | Ollama, OpenAI, Gemini | Content, title, metadata, keyword, and planning generation |
| Utilities | Python modules and root scripts | CLI title generation, image processing, SEO crawling, DOCX exports, schedulers |
| Server | Flask dev server, Docker Compose | Local runtime on port `3444`; WebSocket status on `3445` by default |
| Tests | pytest, compileall, GitHub Actions | Unit/syntax validation |

## 3. Directory Architecture

```text
/
+-- app/
|   +-- controllers/     Flask request handlers
|   +-- routes/web.py    URL registration
|   +-- services/        Reusable logic and integrations
|   +-- events/          Generation status pub/sub state
|   +-- views/           SSE/status view functions
+-- database/            SQLite schema, migration, data helpers
+-- generators/          AI generation orchestration
+-- prompts/             Prompt construction
+-- providers/           AI provider adapters
+-- templates/           Jinja pages and partials
+-- static/assets/       CSS and JavaScript
+-- data/                app.db, WAL files, legacy JSON DB, uploads, backups
+-- tests/               pytest tests
+-- docs/                existing architecture/testing notes
+-- logs/                app.log
+-- external-images/     image working area
+-- optimized-images/    image optimization working area
```

`cmd/` and `internal/` directories exist but contain no files detected by `find`; their purpose is Not determined from repository.

## 4. Public Page Architecture

All visible application pages are Flask routes registered in `app/routes/web.py`. They render Jinja templates from `templates/` and usually share `templates/base.html`.

Important routes include:

```text
/                              -> templates/index.html, blog generator
/dashboard                     -> templates/dashboard.html
/generation-history            -> templates/generation_history.html
/generation-history/<id>       -> templates/generation_history_detail.html
/blog-rework-generator         -> templates/blog_rework_generator.html
/news-generator                -> templates/news_generator.html
/medium-blog-generator         -> templates/backlink_blog_generator.html
/backlink-blog-generator       -> same backlink generator
/tier-2-blog-generator         -> templates/tier2_blog_generator.html
/page-generator                -> templates/page_generator.html
/simple-page-generator         -> templates/simple_page_generator.html
/meta-generator                -> templates/meta_generator.html
/keyword-suggestions           -> templates/keyword_suggestions.html
/seo-checker                   -> templates/seo_checker.html
/seo-checker-v2                -> templates/seo_checker_v2.html
/indexnow and /website-index   -> templates/indexnow.html
/website-index-dashboard       -> templates/website_index_dashboard.html
/website-pages                 -> templates/website_pages.html
/website-planner               -> templates/website_planner.html
/website-planner-v2            -> templates/website_planner_v2.html
/gsc-planner                   -> templates/gsc_planner.html
/image-tools                   -> templates/image_tools.html
/bulk-image-downloader         -> templates/bulk_image_downloader.html
/image-bank                    -> templates/image_bank.html
/folder-image-optimizer        -> templates/folder_image_optimizer.html
/brands                        -> templates/brands.html
/mediums and /backlinks        -> templates/backlinks.html
/brand-medium-table            -> templates/brand_medium_table.html
/social-scheduler              -> templates/social_scheduler.html
/generated-social-post         -> templates/generated_social_post.html
/bio-generator                 -> templates/bio_generator.html
/settings                      -> templates/settings.html
/checklists                    -> templates/checklists.html
/banned-words                  -> templates/banned_words.html
/find-replace-settings         -> templates/find_replace_settings.html
/background-jobs-dashboard     -> templates/background_jobs_dashboard.html
/uploads/<path>                -> files below data/uploads/
```

Only one `index.html` file exists: `templates/index.html`.

## 5. Request Flow

### Static/public page

```text
Request
  -> Flask route in app/routes/web.py
  -> controller creates state
  -> templates/base.html plus page template
  -> static/assets/css/app.css and static/assets/js/*.js
  -> browser response
```

### Dynamic content generation page

```text
Form POST
  -> controller reads request.form/request.files
  -> database helpers load settings, brands, backlinks, checklists
  -> provider_service.get_provider()
  -> generator builds prompt using prompts/
  -> provider returns text/JSON
  -> generator validates/parses output
  -> optional quality report and generation_history write
  -> controller renders updated template state
```

### Blog page

`/` is handled by `app/controllers/blog_controller.py:index()`. It supports title generation, meta descriptions, visual ideas, content generation, tag generation, history editing, and saving generated blogs. It uses `database` helpers for brand context, settings, checklist items, and generation history; `generators/content_generator.py`, `generators/title_generator.py`, and `generators/meta_description_generator.py` for AI output; and `templates/index.html` for rendering.

There is no separate `/blog` route directory in this repository.

### Admin action

There is no distinct authenticated admin area. Admin-like state-changing actions are ordinary Flask POST routes such as `/settings`, `/brands`, `/mediums`, `/checklists`, `/generation-history/<id>/delete`, `/website-index-dashboard`, and `/background-jobs`.

```text
Local UI form/fetch
  -> Flask controller
  -> validation/normalization in controller or service
  -> database helper or file helper
  -> redirect, JSON, download, or rendered HTML response
```

Authentication and CSRF protection are Not determined from repository.

## 6. Database Architecture

SQLite state is stored at `data/app.db`. The connection helper is `database/common.py:get_connection()`, which sets:

- `PRAGMA foreign_keys = ON`
- `PRAGMA busy_timeout = 30000`
- `PRAGMA journal_mode = WAL`
- `PRAGMA synchronous = NORMAL`

`database/__init__.py` imports helpers and initializes the database by calling `init_db()`, `seed_default_checklist_items()`, and `migrate_from_tinydb_json_if_needed()`.

Important tables from `database/schema.py`:

- `brands`: brand profile, website, tone, notes, logo path, color, planner/checklist flags.
- `keywords`: normalized keyword library.
- `pages`, `page_keywords`: brand page records and page-keyword relationships.
- `blogs`, `blog_keywords`, `legacy_used_keywords`: used blog/page keywords and legacy tracking.
- `settings`: app-wide configuration values.
- `banned_words`: custom banned term list.
- `find_replace_rules`: text replacement rules.
- `backlinks`: medium/backlink profiles and posting constraints.
- `checklist_items`, `checklist_item_states`: checklist definitions and per-subject state.
- `social_profiles`: social account records and tokens.
- `generation_history`: generated content, prompt inputs, quality reports, post links, saved status.
- `website_index_urls`: discovered/submitted URLs and indexing status fields.
- `seo_check_history`: saved SEO audit summaries and full JSON results.
- `image_bank`: saved remote images.
- `folder_image_optimizer_runs`: image optimization run summaries.

`data/app.db-wal` and `data/app.db-shm` are present. Several malformed/recovered/backup DB files are also present under `data/`, so database edits require extra care.

## 7. Blog System

Blog generation is a generator workflow, not a public blog CMS route. Main files:

- `app/controllers/blog_controller.py`: root `/` workflow.
- `templates/index.html`: blog generator UI.
- `generators/title_generator.py`, `generators/meta_description_generator.py`, `generators/content_generator.py`: title/meta/content/tag/visual generation.
- `prompts/blog.py` and `prompts/shared.py`: prompt text.
- `database/generation_history.py`: generated output history.
- `database/pages.py`: `record_blog()` and keyword usage helpers.

Posts are stored as generated records in `generation_history` and keyword usage rows in `blogs`/`blog_keywords`; no rendered public article route was detected.

SEO metadata handling is part of generation output: title, meta description, tags, quality reports, and export/preview behavior are controlled by the generator/controller/template stack.

## 8. Game System

No `/game` directory, game table, game listing, iframe launch flow, or game-specific scripts were detected. Some uploaded image filenames mention games, but repository code does not define a game system.

## 9. Admin Architecture

Admin-like areas are local management pages:

- `/settings`: app/provider/indexing/social/planner/word-limit settings.
- `/brands`: brand CRUD, logos, colors, page imports, page records.
- `/mediums` and `/backlinks`: backlink/medium profile CRUD.
- `/brand-medium-table`: combined brand/medium planning table and CSV downloads.
- `/checklists` and `/website-checklist-dashboard`: checklist definitions and tracking.
- `/generation-history`: generated content review, edit links, post link status, deletion/export.
- `/background-jobs-dashboard`: background job monitoring.
- `/social-scheduler`: social account and posting scheduler UI.

Authentication is Not determined from repository. Treat these routes as sensitive because they can store credentials, tokens, uploaded files, and generated content.

## 10. API Architecture

There is no `/api` directory and no separate API blueprint. JSON/fetch-style endpoints are registered in `app/routes/web.py`:

Endpoint: `/generation-status/<token>`  
Purpose: read generation status.  
Method: GET.  
Reads: in-memory status from `app/events/generation_events.py`.  
Writes: none.  
Called by: `static/assets/js/common.js`.

Endpoint: `/generation-status/<token>/cancel`  
Purpose: cancel an active generation.  
Method: POST.  
Reads/Writes: in-memory generation status.  
Called by: `static/assets/js/common.js`.

Endpoint: `/events/generation/<token>`  
Purpose: server-sent generation progress stream.  
Method: GET.  
Reads: generation event subscriber queue.  
Writes: subscription lifecycle.  
Called by: `static/assets/js/common.js` fallback when WebSocket is unavailable.

Endpoint: WebSocket `/events/generation/<token>` on port `APP_PORT + 1` or `GENERATION_WEBSOCKET_PORT`  
Purpose: live generation progress.  
Reads/Writes: generation event subscriptions.  
Called by: `static/assets/js/common.js`.

Endpoint: `/background-jobs`  
Purpose: queue a background POST for a generation route.  
Method: POST.  
Reads: submitted form/file data.  
Writes: in-memory job queue.  
Called by: `static/assets/js/common.js`.

Endpoint: `/background-jobs/<job_id>`  
Purpose: get background job status and terminal HTML.  
Method: GET.  
Reads: in-memory background job store.  
Writes: none.  
Called by: `static/assets/js/common.js`.

Endpoint: `/background-jobs-dashboard/data`  
Purpose: dashboard JSON for background jobs.  
Method: GET.  
Reads: in-memory job state plus scheduled job state.  
Writes: cleanup of expired jobs may occur.  
Called by: `templates/background_jobs_dashboard.html` and `static/assets/js/background_jobs_widget.js`.

Download endpoints include `/download_doc`, `/website-pages/download.csv`, `/website-planner*/download-*`, `/seo-checker/download-*`, `/gsc-planner/download-summary`, `/folder-image-optimizer/download/<run_id>`, and CSV exports from brand/medium controllers. These return generated files from request payloads, database rows, or saved optimizer output.

## 11. Shared Components

- `templates/base.html`: global shell, Tailwind config, theme toggle, sidebar include, background-jobs widget, shared scripts.
- `templates/_sidebar.html`: navigation and active page grouping.
- `templates/_components.html`: reusable template macros/components.
- `templates/_output_views.html`, `_quality_report.html`, `_generation_log.html`, `_content_checklist.html`, `_floating_generation_status.html`, `_seo_history_compare.html`: shared rendering partials.
- `app/controllers/helpers.py`: base template context, provider/model display, output conversion helpers, uploaded image URL helper.
- `app/services/provider_service.py`: selected provider and JSON retry wrapper.
- `app/services/content_format_service.py`: Markdown/HTML/Gutenberg/text conversion.
- `app/services/generation_status_service.py`, `app/events/generation_events.py`, `app/views/generation_events_view.py`: progress publication, cancellation, SSE.
- `app/services/background_job_service.py`: in-process background queue.
- `database/common.py`: SQLite path and connection setup.
- `logger.py`: app logger writing to `logs/app.log`.

## 12. Python Utility Architecture

- `ui.py`: Flask runtime entrypoint. Reads `APP_HOST`, `APP_PORT`, and `FLASK_DEBUG`; defaults to `127.0.0.1:3444` with debug enabled.
- `main.py`: interactive CLI that asks for keyword/topic and tone, selects provider from `config.py`, then prints 10 title variants via `generators/title_generator.py`.
- `config.py`: `.env` loader and provider/model/web-search settings.
- `content_repetition.py`, `generation_retry_policy.py`, `utils.py`, `word_bank.py`: shared utility modules used by generation and validation logic.
- `database/migration.py`: migrates legacy `data/app_db.json` into SQLite when core tables are empty, then migrates `money_site` to settings.

No `/scripts` directory exists. Utilities are Python modules and root entrypoint files. CLI arguments are Not determined from repository for these root scripts; `main.py` is prompt-driven.

## 13. SEO Architecture

SEO is handled through generation tools and site-audit/indexing utilities rather than static sitemap/robots files in this repository.

- Titles/meta descriptions: generated by `generators/title_generator.py`, `generators/meta_description_generator.py`, `app/services/meta_generator_service.py`, and prompt modules under `prompts/`.
- Generated article/page SEO quality: `app/services/content_quality_service.py`.
- Website SEO crawler/auditor: `app/services/seo_checker_service.py`, controlled by `/seo-checker` and `/seo-checker-v2`.
- SEO history: `database/seo_check_history.py` and `seo_check_history` table.
- Sitemap/robots inspection: `seo_checker_service.py` fetches external `robots.txt` and sitemap data for audited URLs.
- Sitemap XML generation for submissions: `app/services/indexnow_service.py:build_sitemap_xml()`.
- IndexNow and Google indexing/inspection: `app/services/indexnow_service.py`, `app/services/website_index_scheduler.py`, and `database/website_index.py`.
- Website page discovery and page keyword extraction: `app/services/website_page_discovery_service.py`.
- GSC planning: `app/services/gsc_planner_service.py` and `/gsc-planner`.
- Internal linking/required link behavior: generator prompts and validation in `generators/content_generator.py`, plus planner outputs in `app/services/website_planner_service.py`.

Canonical tags, Open Graph tags, Twitter metadata, and structured data are inspected on external URLs by SEO tools and may be generated as content guidance, but static site-level files controlling them are Not determined from repository.

## 14. Routing

Routes are Flask URL rules in `app/routes/web.py`. There is no `.htaccess` or rewrite configuration in the repository.

Dynamic segments:

- `/generation-history/<int:history_id>`
- `/generation-history/<int:history_id>/edit`
- `/generation-history/<int:history_id>/mark-draft`
- `/generation-history/<int:history_id>/delete`
- `/generation-status/<token>`
- `/generation-status/<token>/cancel`
- `/events/generation/<token>`
- `/background-jobs/<job_id>`
- `/folder-image-optimizer/download/<run_id>`
- `/uploads/<path:filename>`

Query parameters are used for editing/filtering in places such as `edit_history_id`, `brand`, `history_id`, `domain`, `page`, `success`, and `error`.

## 15. Data Flow

```text
                         Browser
                            |
                Flask routes in app/routes/web.py
                            |
        +-------------------+-------------------+
        |                   |                   |
   Controllers          Static assets       Upload serving
        |                   |                   |
        v                   v                   v
 Services and generators   JS/CSS          data/uploads/
        |
        +--------------------+
        |                    |
   AI providers        Database helpers
 Ollama/OpenAI/Gemini        |
                             v
                         data/app.db
                             ^
                             |
              migration/init from database/__init__.py
```

Background flow:

```text
Browser fetch /background-jobs
  -> app/services/background_job_service.py queue
  -> Flask test_client posts original route in a worker thread
  -> generation events publish status
  -> WebSocket/SSE updates browser
```

## 16. Change Guidelines

- Change route mappings: `app/routes/web.py`.
- Change a page workflow: matching file in `app/controllers/`.
- Change global layout/navigation/theme: `templates/base.html`, `templates/_sidebar.html`, `static/assets/css/app.css`.
- Change page-specific behavior: corresponding template and JS file in `static/assets/js/`.
- Change provider selection/retry behavior: `config.py` and `app/services/provider_service.py`.
- Change AI prompt wording: `prompts/`.
- Change generation parsing/validation: `generators/`.
- Change SQLite access: use the relevant `database/*.py` helper and `database/common.py`.
- Change schema: `database/schema.py` plus migration/backward compatibility handling.
- Change history behavior: `database/generation_history.py` and `app/controllers/dashboard_controller.py`.
- Change image upload/optimization: `app/controllers/image_controller.py`, `app/services/image_service.py`, `database/image_bank.py`, `database/folder_image_optimizer.py`.
- Change SEO checks/indexing: `app/services/seo_checker_service.py`, `indexnow_service.py`, `website_index_scheduler.py`, `website_page_discovery_service.py`, and related controllers/templates.
- Change Docker runtime: `Dockerfile`, `docker-compose.yml`, `.env.example`.

## 17. Important Dependencies

```text
templates/base.html
  -> sidebar, dark mode, common.js, background job widget
  -> nearly every rendered page
```

```text
database/common.py DB_PATH/WAL settings
  -> every database helper
  -> app startup via database/__init__.py
```

```text
brands/settings/backlinks/checklists
  -> controllers
  -> prompts/generators
  -> generation_history and planner outputs
```

```text
generation_status_service/events
  -> common.js WebSocket/SSE progress
  -> background_job_service updates
```

```text
website_index_urls
  -> website pages discovery
  -> IndexNow/Google inspection/submission
  -> scheduler and dashboard
```

Changing these areas can affect multiple workflows, tests, and saved user data.

## 18. Deployment Notes

Local run from README:

```bash
source venv/bin/activate
pip install -r requirements.txt
python ui.py
```

Default URL is `http://localhost:3444`. `ui.py` reads:

- `APP_HOST`, default `127.0.0.1`
- `APP_PORT`, default `3444`
- `FLASK_DEBUG`, default `true`

Docker:

- `Dockerfile` uses `python:3.11-slim`, installs `requirements.txt`, installs Playwright Chromium dependencies, exposes `3444` and `3445`, and runs `python ui.py`.
- `docker-compose.yml` maps `3444:3444` and `3445:3445`, sets provider/model/API-key environment variables, mounts the repo to `/app`, and mounts `./data:/app/data`.

SQLite permissions must allow writing to `data/` and upload subdirectories. Apache, Nginx, aaPanel, PHP-FPM, and rewrite deployment configuration are Not determined from repository.

## 19. Security Boundaries

- Public/local UI routes are all on the single Flask blueprint; no authentication boundary was detected.
- Sensitive values can live in `.env`, settings, and `social_profiles` fields such as API keys, OAuth tokens, and service account JSON.
- Writable directories include `data/`, `data/uploads/`, `logs/`, `external-images/`, and `optimized-images/`.
- User-provided input enters through Flask forms, JSON/fetch endpoints, file uploads, URL fetchers, DOCX uploads, and social/indexing credentials.
- URL-fetching services (`seo_checker_service.py`, `reference_link_service.py`, `website_page_discovery_service.py`, `image_bank_service.py`) need SSRF/private URL care. Some flows expose `allow_private` toggles or local-dev exceptions.
- Upload and image processing flows need filename, path traversal, file type, and size-limit care. `app/__init__.py` configures upload size limits.
- Generated HTML can be displayed/exported; keep escaping and sanitization risks in mind.
- Background jobs replay submitted POSTs through Flask `test_client`; only queue paths intended for background execution.
- Social publishing and indexing endpoints can perform external state changes.

## 20. Architecture Principles

- Preserve existing URLs.
- Preserve the existing frontend design unless explicitly changing it.
- Keep changes localized.
- Reuse existing controllers, services, templates, generators, prompts, and database helpers.
- Protect `data/app.db` integrity and WAL files.
- Maintain backward compatibility with existing saved data.
- Keep generated content and SEO tooling SEO-safe.
- Follow existing project patterns before introducing new architecture.
