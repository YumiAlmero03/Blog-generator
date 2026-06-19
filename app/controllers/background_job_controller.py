from flask import current_app, jsonify, render_template, request

from app.controllers.helpers import base_template_context
from app.services.background_job_service import background_worker_count, get_background_job, list_background_jobs, start_background_post


def create_background_job():
    path = request.form.get("_background_path", "").strip() or request.path
    if not path.startswith("/") or path.startswith("/background-jobs"):
        return jsonify({"error": "Invalid background job path."}), 400

    form_data = {
        key: values
        for key, values in request.form.to_dict(flat=False).items()
        if key != "_background_path"
    }
    job = start_background_post(current_app._get_current_object(), path, form_data)
    return jsonify(job.to_dict()), 202


def background_job_status(job_id: str):
    job = get_background_job(job_id)
    if not job:
        return jsonify({"error": "Background job not found."}), 404
    return jsonify(job)


def background_jobs_dashboard():
    jobs = list_background_jobs()
    stats = {
        "queued": sum(1 for job in jobs if job.get("status") == "queued"),
        "running": sum(1 for job in jobs if job.get("status") == "running"),
        "complete": sum(1 for job in jobs if job.get("status") == "complete"),
        "failed": sum(1 for job in jobs if job.get("status") == "failed"),
        "total": len(jobs),
        "slots": background_worker_count(),
    }
    return render_template(
        "background_jobs_dashboard.html",
        **base_template_context(),
        jobs=jobs,
        stats=stats,
    )
