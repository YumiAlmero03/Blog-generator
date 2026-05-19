Tables and Schema
-----------------

brands

-   `id` INTEGER PRIMARY KEY
-   `name` TEXT NOT NULL
-   `normalized_name` TEXT NOT NULL UNIQUE
-   `website` TEXT NOT NULL DEFAULT ''
-   `money_site` TEXT NOT NULL DEFAULT ''
-   `tone` TEXT NOT NULL DEFAULT ''
-   `notes` TEXT NOT NULL DEFAULT ''
-   `niche` TEXT NOT NULL DEFAULT ''
-   `main_keywords` TEXT NOT NULL DEFAULT ''
-   `logo_path` TEXT NOT NULL DEFAULT ''
-   `brand_color` TEXT NOT NULL DEFAULT ''
-   `include_in_posting_planner` INTEGER NOT NULL DEFAULT 0

keywords

-   `id` INTEGER PRIMARY KEY
-   [keyword](vscode-file://vscode-app/Applications/Visual%20Studio%20Code.app/Contents/Resources/app/out/vs/code/electron-browser/workbench/workbench.html) TEXT NOT NULL
-   `normalized_keyword` TEXT NOT NULL UNIQUE

pages

-   `id` INTEGER PRIMARY KEY
-   `brand_id` INTEGER
-   `brand_normalized_name` TEXT NOT NULL
-   `page_title` TEXT NOT NULL DEFAULT ''
-   `page_type` TEXT NOT NULL DEFAULT ''
-   `primary_keyword` TEXT NOT NULL DEFAULT ''
-   `supporting_keywords` TEXT NOT NULL DEFAULT ''
-   `expectations` TEXT NOT NULL DEFAULT ''

blogs

-   `id` INTEGER PRIMARY KEY
-   `brand_id` INTEGER
-   `brand_normalized_name` TEXT NOT NULL
-   `title` TEXT NOT NULL DEFAULT ''
-   `primary_keyword` TEXT NOT NULL DEFAULT ''
-   `supporting_keyword` TEXT NOT NULL DEFAULT ''

page_keywords

-   `id` INTEGER PRIMARY KEY
-   `page_id` INTEGER NOT NULL (FK to pages.id)
-   `keyword_id` INTEGER NOT NULL (FK to keywords.id)
-   `is_primary` INTEGER NOT NULL DEFAULT 0

blog_keywords

-   `id` INTEGER PRIMARY KEY
-   `blog_id` INTEGER NOT NULL (FK to blogs.id)
-   `keyword_id` INTEGER NOT NULL (FK to keywords.id)
-   `is_primary` INTEGER NOT NULL DEFAULT 0

legacy_used_keywords

-   `id` INTEGER PRIMARY KEY
-   `brand_id` INTEGER
-   `brand_normalized_name` TEXT NOT NULL DEFAULT ''
-   [keyword](vscode-file://vscode-app/Applications/Visual%20Studio%20Code.app/Contents/Resources/app/out/vs/code/electron-browser/workbench/workbench.html) TEXT NOT NULL DEFAULT ''
-   `normalized_keyword` TEXT NOT NULL DEFAULT ''
-   `content_type` TEXT NOT NULL DEFAULT ''
-   `title` TEXT NOT NULL DEFAULT ''

settings

-   `key` TEXT PRIMARY KEY
-   `value` TEXT NOT NULL DEFAULT ''

backlinks

-   `id` INTEGER PRIMARY KEY
-   `website_name` TEXT NOT NULL DEFAULT ''
-   `blog_url` TEXT NOT NULL DEFAULT ''
-   `tier_level` TEXT NOT NULL DEFAULT 'Tier 1'
-   `posts_per_day` INTEGER NOT NULL DEFAULT 0
-   `notes` TEXT NOT NULL DEFAULT ''
-   `account_name` TEXT NOT NULL DEFAULT ''
-   `blog_name` TEXT NOT NULL DEFAULT ''
-   `writer_name` TEXT NOT NULL DEFAULT ''
-   `website_type` TEXT NOT NULL DEFAULT 'blog'
-   `max_characters` INTEGER NOT NULL DEFAULT 0
-   `title_max_characters` INTEGER NOT NULL DEFAULT 0
-   `content_guidelines` TEXT NOT NULL DEFAULT ''
-   `min_words` INTEGER NOT NULL DEFAULT 0
-   `post_type` TEXT NOT NULL DEFAULT 'html'

social_profiles

-   `id` INTEGER PRIMARY KEY
-   `brand_name` TEXT NOT NULL DEFAULT ''
-   `social_type` TEXT NOT NULL DEFAULT ''
-   `posts_per_day` INTEGER NOT NULL DEFAULT 0

generation_history

-   `id` INTEGER PRIMARY KEY
-   `created_at` TEXT NOT NULL DEFAULT (datetime('now'))
-   `content_type` TEXT NOT NULL DEFAULT ''
-   `brand_id` INTEGER
-   `title` TEXT NOT NULL DEFAULT ''
-   `primary_keyword` TEXT NOT NULL DEFAULT ''
-   `medium_name` TEXT NOT NULL DEFAULT ''
-   `word_count` INTEGER NOT NULL DEFAULT 0
-   `meta_description` TEXT NOT NULL DEFAULT ''
-   `post_link` TEXT NOT NULL DEFAULT ''
-   `tags` TEXT NOT NULL DEFAULT ''
-   `prompt_inputs` TEXT NOT NULL DEFAULT ''
-   `content` TEXT NOT NULL DEFAULT ''
-   `quality_report` TEXT NOT NULL DEFAULT ''

banned_words

-   `id` INTEGER PRIMARY KEY
-   `term` TEXT NOT NULL
-   `normalized_term` TEXT NOT NULL UNIQUE
