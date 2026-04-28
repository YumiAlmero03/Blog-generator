from flask import Blueprint, send_from_directory

from app.controllers import backlink_blog_controller, backlink_controller, blog_controller, brand_controller, image_controller, page_controller, settings_controller, tool_controller
from app.services.image_service import UPLOAD_ROOT


web = Blueprint("web", __name__)


web.add_url_rule("/", view_func=blog_controller.index, methods=["GET", "POST"])
web.add_url_rule("/backlink-blog-generator", view_func=backlink_blog_controller.backlink_blog_generator, methods=["GET", "POST"])
web.add_url_rule("/page-generator", view_func=page_controller.page_generator, methods=["GET", "POST"])
web.add_url_rule("/simple-page-generator", view_func=page_controller.simple_page_generator, methods=["GET", "POST"])
web.add_url_rule("/text-tools", view_func=tool_controller.text_tools, methods=["GET"])
web.add_url_rule("/image-tools", view_func=image_controller.image_tools, methods=["GET", "POST"])
web.add_url_rule("/brands", view_func=brand_controller.brands, methods=["GET", "POST"])
web.add_url_rule("/backlinks", view_func=backlink_controller.backlinks, methods=["GET", "POST"])
web.add_url_rule("/settings", view_func=settings_controller.settings, methods=["GET", "POST"])
web.add_url_rule("/preview", view_func=tool_controller.preview, methods=["POST"])
web.add_url_rule("/download_doc", view_func=tool_controller.download_doc, methods=["POST"])


@web.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_ROOT, filename)
