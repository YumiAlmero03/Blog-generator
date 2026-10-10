# Post saving and downloads

Blog Generator, Blog Rework, and News Generator share the same post controls.

- Categories default to **Auto**, which uses title and keyword rules (no AI request) when saving or downloading. Explicit login/signup intent takes precedence over topic matches; unmatched news uses News and other unmatched posts use General. A manually selected category is preserved. Available manual categories: General, Casino, Slots, Navigational, Transactional, Informational, Commercial, or News.
- Select a meta description to automatically save the current draft. This also works before article content has been generated. Later choices update the same history entry.
- **Save Post** requires a title, category, meta description, and readable article content. It saves the current editor contents to generation history.
- **Download Post · WordPress XML** exports a WXR 1.2 file. In WordPress, use Tools → Import → WordPress and upload the XML. Imported posts are drafts. Categories, tags, HTML content, title, slug, and description are included. Descriptions are stored as the excerpt and in generic, Yoast, and Rank Math metadata; SEO output depends on the destination's theme/plugin configuration.
- **Download Post · JSON** exports the fields below as compact UTF-8 JSON, without formatting whitespace, for a lightweight custom blog-admin download. A custom admin may need an importer or field mapping; the repository does not include that admin.

Both formats export current edits. Downloading alone does not save additional edits to history. Use Save Post to persist them.

## JSON schema (version 1)

| Field | Type | Meaning |
| --- | --- | --- |
| schema_version | integer | `1` |
| generator | string | `blog`, `rework`, or `news` |
| status | string | `draft` |
| title | string | Selected post title |
| slug | string | Slug derived from the title |
| content_html | string | Current article HTML |
| meta_description | string | Selected description |
| category | string | Selected category |
| tags | string array | Generated tags |
| primary_keyword | string | Primary keyword |
| brand | string | Brand, when supplied |
| language | string | Article language |

No images are uploaded or bundled by these exports; existing image URLs remain in the article HTML. Categories are stored in existing history prompt metadata, with no database schema change.
