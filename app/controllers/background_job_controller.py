from flask import current_app, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.controllers.helpers import base_template_context
from app.services.background_job_service import background_job_stats, get_background_job, list_background_jobs, start_background_post
from logger import logger


def create_background_job():
    try:
        path = request.form.get("_background_path", "").strip() or request.path
        if not path.startswith("/") or path.startswith("/background-jobs"):
            return jsonify({"error": "Invalid background job path."}), 400

        form_data = {
            key: values
            for key, values in request.form.to_dict(flat=False).items()
            if key != "_background_path"
        }
        file_data = _background_file_data()
        job = start_background_post(current_app._get_current_object(), path, form_data, file_data)
        return jsonify(job.to_dict()), 202
    except RequestEntityTooLarge:
        return jsonify({
            "error": (
                "The upload is too large. Capture a smaller browser area, upload a compressed screenshot, "
                "or lower the screenshot resolution before generating the report."
            )
        }), 413
    except Exception as exc:
        logger.exception("could not start background job")
        return jsonify({"error": str(exc) or "Could not start background job."}), 500


def background_job_status(job_id: str):
    job = get_background_job(job_id)
    if not job:
        return jsonify({"error": "Background job not found."}), 404
    return jsonify(job)


def background_jobs_dashboard():
    jobs = list_background_jobs()
    return render_template(
        "background_jobs_dashboard.html",
        **base_template_context(),
        jobs=jobs,
        stats=background_job_stats(jobs),
    )


def background_jobs_dashboard_data():
    jobs = list_background_jobs()
    return jsonify({"jobs": jobs, "stats": background_job_stats(jobs)})


def _background_file_data() -> dict[str, list[dict]]:
    file_data: dict[str, list[dict]] = {}
    for field_name, uploads in request.files.lists():
        saved_uploads = []
        for upload in uploads:
            if not upload or not upload.filename:
                continue
            saved_uploads.append(
                {
                    "filename": upload.filename,
                    "content_type": upload.content_type or "application/octet-stream",
                    "content": upload.read(),
                }
            )
        if saved_uploads:
            file_data[field_name] = saved_uploads
    return file_data
