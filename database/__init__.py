from database.backlinks import delete_backlink, get_backlink, list_backlinks, save_backlink, update_backlink_notes
from database.banned_words import list_custom_banned_words, replace_custom_banned_words
from database.brands import delete_brand, get_brand_context, get_brand_record, list_brand_names, list_brand_records, upsert_brand, update_brand_notes
from database.common import DB_PATH, LEGACY_DB_PATH, normalize_brand_name, normalize_keyword, split_keywords
from database.generation_history import (
    count_sent_posts_for_date,
    delete_generation_history_item,
    generation_dashboard_stats,
    get_generation_history_item,
    list_brand_posts_for_planner_date,
    list_generation_history,
    list_generation_history_medium_names,
    list_posts_for_planner_date,
    list_sent_posts_export_for_date,
    list_sent_posts_for_date,
    mark_generation_history_draft,
    planner_medium_key,
    record_generation,
    update_generation_history_post_link,
)
from database.keywords import get_or_create_keyword
from database.migration import migrate_from_tinydb_json_if_needed
from database.pages import (
    check_keyword_usage,
    delete_brand_page,
    get_blog_keywords,
    get_brand_blogs,
    get_brand_pages,
    get_brand_related_keywords,
    get_page_keywords,
    record_blog,
    record_page,
    record_used_keyword,
    update_brand_page,
)
from database.schema import init_db
from database.settings import get_setting, list_settings, set_setting
from database.social_media import delete_social_profile, get_social_profile, list_social_profiles, save_social_profile


init_db()
migrate_from_tinydb_json_if_needed()
