from flask import Blueprint, send_from_directory

from app.controllers import background_job_controller, backlink_blog_controller, backlink_controller, blog_controller, brand_controller, brand_medium_controller, checklist_controller, dashboard_controller, image_controller, news_controller, page_controller, posting_planner_controller, settings_controller, social_media_controller, tier2_blog_controller, tool_controller
from app.views import generation_events_view
from app.services.image_service import UPLOAD_ROOT


web = Blueprint("web", __name__)


web.add_url_rule("/dashboard", view_func=dashboard_controller.dashboard, methods=["GET"])
web.add_url_rule("/website-checklist-dashboard", view_func=checklist_controller.website_checklist_dashboard, methods=["GET", "POST"])
web.add_url_rule("/website-index-dashboard", view_func=tool_controller.website_index_dashboard, methods=["GET"])
web.add_url_rule("/posting-planner", view_func=posting_planner_controller.posting_planner, methods=["GET", "POST"])
web.add_url_rule("/brand-medium-table", view_func=brand_medium_controller.brand_medium_table, methods=["GET", "POST"])
web.add_url_rule("/generation-history", view_func=dashboard_controller.generation_history, methods=["GET"])
web.add_url_rule("/generation-history/<int:history_id>", view_func=dashboard_controller.generation_history_detail, methods=["GET", "POST"])
web.add_url_rule("/generation-history/<int:history_id>/edit", view_func=dashboard_controller.edit_generation_history, methods=["GET"])
web.add_url_rule("/generation-history/<int:history_id>/mark-draft", view_func=dashboard_controller.mark_generation_history_as_draft, methods=["POST"])
web.add_url_rule("/generation-history/<int:history_id>/delete", view_func=dashboard_controller.delete_generation_history, methods=["POST"])
web.add_url_rule("/", view_func=blog_controller.index, methods=["GET", "POST"])
web.add_url_rule("/news-generator", view_func=news_controller.news_generator, methods=["GET", "POST"])
web.add_url_rule("/medium-blog-generator", view_func=backlink_blog_controller.backlink_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/backlink-blog-generator", view_func=backlink_blog_controller.backlink_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/tier-2-blog-generator", view_func=tier2_blog_controller.tier2_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/tier2-blog-generator", view_func=tier2_blog_controller.tier2_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/page-generator", view_func=page_controller.page_generator, methods=["GET", "POST"])
web.add_url_rule("/simple-page-generator", view_func=page_controller.simple_page_generator, methods=["GET", "POST"])
web.add_url_rule("/keyword-suggestions", view_func=tool_controller.keyword_suggestions, methods=["GET", "POST"])
web.add_url_rule("/text-tools", view_func=tool_controller.text_tools, methods=["GET"])
web.add_url_rule("/seo-checker", view_func=tool_controller.seo_checker, methods=["GET", "POST"])
web.add_url_rule("/indexnow", view_func=tool_controller.indexnow, methods=["GET", "POST"])
web.add_url_rule("/website-index", view_func=tool_controller.indexnow, methods=["GET", "POST"])
web.add_url_rule("/image-tools", view_func=image_controller.image_tools, methods=["GET", "POST"])
web.add_url_rule("/brands", view_func=brand_controller.brands, methods=["GET", "POST"])
web.add_url_rule("/neutral-blog-generator", view_func=social_media_controller.neutral_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/mediums", view_func=backlink_controller.backlinks, methods=["GET", "POST"])
web.add_url_rule("/backlinks", view_func=backlink_controller.backlinks, methods=["GET", "POST"])
web.add_url_rule("/settings", view_func=settings_controller.settings, methods=["GET", "POST"])
web.add_url_rule("/checklists", view_func=checklist_controller.checklist_manager, methods=["GET", "POST"])
web.add_url_rule("/banned-words", view_func=settings_controller.banned_words, methods=["GET", "POST"])
web.add_url_rule("/preview", view_func=tool_controller.preview, methods=["POST"])
web.add_url_rule("/download_doc", view_func=tool_controller.download_doc, methods=["POST"])
web.add_url_rule("/generation-status/<token>", view_func=generation_events_view.generation_status, methods=["GET"])
web.add_url_rule("/generation-status/<token>/cancel", view_func=generation_events_view.cancel_generation_status, methods=["POST"])
web.add_url_rule("/events/generation/<token>", view_func=generation_events_view.generation_events, methods=["GET"])
web.add_url_rule("/background-jobs", view_func=background_job_controller.create_background_job, methods=["POST"])
web.add_url_rule("/background-jobs-dashboard", view_func=background_job_controller.background_jobs_dashboard, methods=["GET"])
web.add_url_rule("/background-jobs-dashboard/data", view_func=background_job_controller.background_jobs_dashboard_data, methods=["GET"])
web.add_url_rule("/background-jobs/<job_id>", view_func=background_job_controller.background_job_status, methods=["GET"])


@web.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_ROOT, filename)
