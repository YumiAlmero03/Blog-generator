from flask import render_template, request

from database import (
    delete_social_profile,
    get_brand_context,
    record_generation,
    get_social_profile,
    list_brand_names,
    list_social_profiles,
    save_social_profile,
)
from generators.social_media_generator import generate_social_media_post
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.provider_service import generation_error_message, get_provider


SOCIAL_MEDIA_TYPES = (
    "Twitter/X",
    "Facebook",
    "Instagram",
    "LinkedIn",
    "TikTok",
    "Pinterest",
    "YouTube",
)


def social_media_list():
    state = {
        "profile_id": "",
        "brand_name": "",
        "social_type": "Twitter/X",
        "success": None,
        "error": None,
        "brand_names": list_brand_names(),
        "social_media_types": SOCIAL_MEDIA_TYPES,
    }

    edit_id = request.args.get("edit", "").strip()
    if request.method == "GET" and edit_id.isdigit():
        _populate_social_profile_for_edit(state, int(edit_id))

    if request.method == "POST":
        action = request.form.get("action", "save_profile").strip()
        if action == "delete_profile":
            _handle_delete_social_profile(state)
        else:
            _handle_save_social_profile(state)

    return render_template(
        "social_media_list.html",
        **base_template_context(),
        **state,
        profiles=list_social_profiles(),
    )


def social_media_activator():
    state = {
        "focus_word": "",
        "reference_link": "",
        "selected_profile_id": "",
        "selected_profile": None,
        "result": None,
        "error": None,
        "success": None,
        "profiles": list_social_profiles(),
    }

    if request.method == "POST":
        action = request.form.get("action", "generate_post").strip()
        if action == "save_generated_blog":
            _handle_save_social_media_post(state)
        else:
            _handle_generate_social_media_post(state)

    return render_template("social_media_activator.html", **base_template_context(), **state)


def _populate_social_profile_for_edit(state: dict, profile_id: int):
    profile = get_social_profile(profile_id)
    if not profile:
        return
    state["profile_id"] = str(profile.get("id", ""))
    state["brand_name"] = profile.get("brand_name", "")
    state["social_type"] = profile.get("social_type", "Twitter/X") or "Twitter/X"


def _handle_save_social_profile(state: dict):
    state["profile_id"] = request.form.get("profile_id", "").strip()
    state["brand_name"] = request.form.get("brand_name", "").strip()
    state["social_type"] = request.form.get("social_type", "Twitter/X").strip() or "Twitter/X"

    if not state["brand_name"]:
        state["error"] = "Please select a brand."
        return
    if state["social_type"] not in SOCIAL_MEDIA_TYPES:
        state["social_type"] = "Twitter/X"

    profile_id = int(state["profile_id"]) if state["profile_id"].isdigit() else None
    save_social_profile(
        brand_name=state["brand_name"],
        social_type=state["social_type"],
        profile_id=profile_id,
    )
    state.update(
        {
            "profile_id": "",
            "brand_name": "",
            "social_type": "Twitter/X",
            "success": "Social media profile saved.",
        }
    )


def _handle_delete_social_profile(state: dict):
    profile_id = request.form.get("profile_id", "").strip()
    if profile_id.isdigit():
        delete_social_profile(int(profile_id))
        state["success"] = "Social media profile deleted."


def _handle_generate_social_media_post(state: dict):
    state["focus_word"] = request.form.get("focus_word", "").strip()
    state["reference_link"] = request.form.get("reference_link", "").strip()
    state["selected_profile_id"] = request.form.get("selected_profile_id", "").strip()

    if not state["focus_word"]:
        state["error"] = "Please enter a focus word."
        return
    if not state["selected_profile_id"].isdigit():
        state["error"] = "Please select a social media profile."
        return

    state["selected_profile"] = get_social_profile(int(state["selected_profile_id"]))
    if not state["selected_profile"]:
        state["error"] = "The selected social media profile could not be found."
        return

    try:
        provider = get_provider()
        brand_name = state["selected_profile"].get("brand_name", "")
        progress = _progress_callback("Social activator", request.form.get("generation_status_token", ""))
        progress("Generating social media post...")
        state["result"] = generate_social_media_post(
            provider,
            focus_word=state["focus_word"],
            brand_name=brand_name,
            social_type=state["selected_profile"].get("social_type", ""),
            brand_context=get_brand_context(brand_name),
            reference_link=state["reference_link"],
            progress_callback=progress,
        )
        post_content = state["result"].get("post_content", "")
        tags = state["result"].get("tags", [])
        quality_report = {
            "word_count": len(post_content.split()),
            "checks": [
                {
                    "name": "Character count",
                    "status": "pass" if len(post_content) <= 220 else "fail",
                    "detail": f"{len(post_content)} of 220 characters",
                    "recommendation": "Keep social activator posts at or below 220 characters.",
                },
                {
                    "name": "Tags",
                    "status": "pass" if tags else "warn",
                    "detail": f"{len(tags)} tag(s)",
                    "recommendation": "Use a few platform-appropriate tags without cluttering the post.",
                },
            ],
        }
        record_generation(
            content_type="Social Post",
            brand_name=brand_name,
            title=f"{state['selected_profile'].get('social_type', '')} post for {state['focus_word']}",
            primary_keyword=state["focus_word"],
            medium_name=state["selected_profile"].get("social_type", ""),
            word_count=quality_report["word_count"],
            tags=tags,
            prompt_inputs={
                "focus_word": state["focus_word"],
                "reference_link": state["reference_link"],
                "social_type": state["selected_profile"].get("social_type", ""),
                "image_description": state["result"].get("image_description", ""),
            },
            content=post_content,
            quality_report=quality_report,
        )
        clear_generation_status(request.form.get("generation_status_token", ""))
    except Exception as exc:
        logger.exception("social_media_activator generation failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the social media post. Check logs/app.log for details.",
            exc,
        )


def _handle_save_social_media_post(state: dict):
    state["focus_word"] = request.form.get("focus_word", "").strip()
    state["reference_link"] = request.form.get("reference_link", "").strip()
    state["selected_profile_id"] = request.form.get("selected_profile_id", "").strip()
    post_content = request.form.get("post_content", "").strip()
    image_description = request.form.get("image_description", "").strip()
    tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]

    if state["selected_profile_id"].isdigit():
        state["selected_profile"] = get_social_profile(int(state["selected_profile_id"]))

    if not state["selected_profile"]:
        state["error"] = "The selected social media profile could not be found."
        return
    if not post_content:
        state["error"] = "There is no generated social post to save."
        return

    state["result"] = {
        "post_content": post_content,
        "image_description": image_description,
        "tags": tags,
        "character_count": len(post_content),
    }
    quality_report = {
        "word_count": len(post_content.split()),
        "checks": [
            {
                "name": "Character count",
                "status": "pass" if len(post_content) <= 220 else "fail",
                "detail": f"{len(post_content)} of 220 characters",
                "recommendation": "Keep social activator posts at or below 220 characters.",
            },
            {
                "name": "Tags",
                "status": "pass" if tags else "warn",
                "detail": f"{len(tags)} tag(s)",
                "recommendation": "Use a few platform-appropriate tags without cluttering the post.",
            },
        ],
    }
    record_generation(
        content_type="Social Post",
        brand_name=state["selected_profile"].get("brand_name", ""),
        title=f"{state['selected_profile'].get('social_type', '')} post for {state['focus_word']}",
        primary_keyword=state["focus_word"],
        medium_name=state["selected_profile"].get("social_type", ""),
        word_count=quality_report["word_count"],
        tags=tags,
        prompt_inputs={
            "focus_word": state["focus_word"],
            "reference_link": state["reference_link"],
            "social_type": state["selected_profile"].get("social_type", ""),
            "image_description": image_description,
            "manual_save": True,
        },
        content=post_content,
        quality_report=quality_report,
    )
    state["success"] = "Generated social post saved to history."


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
