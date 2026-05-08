from database.backlinks import get_backlink, list_backlinks, save_backlink
from database.brands import get_brand_context, get_brand_record, list_brand_names, list_brand_records, upsert_brand
from database.common import DB_PATH, LEGACY_DB_PATH, normalize_brand_name, normalize_keyword, split_keywords
from database.generation_history import (
    generation_dashboard_stats,
    get_generation_history_item,
    list_generation_history,
    record_generation,
)
from database.keywords import get_or_create_keyword
from database.migration import migrate_from_tinydb_json_if_needed
from database.pages import (
    check_keyword_usage,
    get_blog_keywords,
    get_brand_blogs,
    get_brand_pages,
    get_brand_related_keywords,
    get_page_keywords,
    record_blog,
    record_page,
    record_used_keyword,
)
from database.schema import init_db
from database.settings import get_setting, list_settings, set_setting
from database.social_media import delete_social_profile, get_social_profile, list_social_profiles, save_social_profile


init_db()
migrate_from_tinydb_json_if_needed()
