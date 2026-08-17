import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from flask import abort, render_template, request, send_file

from database import (
    get_brand_record,
    list_brand_names,
    list_folder_image_optimizer_runs,
    list_folder_image_optimizer_seen_folders,
    list_image_bank_items,
    save_folder_image_optimizer_run,
)
from logger import logger

from app.controllers.helpers import base_template_context, image_url
from app.services.image_bank_service import (
    image_bank_view_item,
    parse_bulk_image_queries,
    save_remote_image_to_bank,
    search_google_images_for_queries,
)
from app.services.image_service import (
    FOLDER_IMAGE_OPTIMIZER_DIR,
    FOLDER_IMAGE_OPTIMIZER_ZIP_DIR,
    IMAGE_TOOL_DIR,
    UPLOAD_ROOT,
    apply_logo_watermark,
    calculate_output_dimensions,
    crop_image_to_box,
    format_file_size,
    normalize_image_dimension_limit,
    normalize_image_quality,
    optimize_images_in_folder,
    optimize_uploaded_folder_images,
    save_optimized_image,
    save_uploaded_image,
)


def bulk_image_downloader():
    state = {
        "image_requests": "",
        "manual_image_url": "",
        "manual_query": "",
        "search_groups": [],
        "saved_item": None,
        "error": None,
        "success": None,
    }
    if request.method == "POST":
        action = request.form.get("action", "search").strip()
        if action == "save":
            _handle_bulk_image_save(state)
        elif action == "download_first_5":
            _handle_bulk_image_download_first_5(state)
        else:
            _handle_bulk_image_search(state)
    return render_template("bulk_image_downloader.html", **base_template_context(), **state)


def image_bank():
    items = [image_bank_view_item(item) for item in list_image_bank_items()]
    return render_template("image_bank.html", **base_template_context(), items=items)


def folder_image_optimizer():
    state = {
        "folder_path": "",
        "output_folder": "",
        "output_format": "webp",
        "image_quality": "82",
        "max_width": "1600",
        "max_height": "",
        "recursive": False,
        "overwrite_original": False,
        "result": None,
        "error": None,
        "success": None,
        "mode": "server_folder",
        "optimizer_history": list_folder_image_optimizer_runs(),
        "seen_folders": list_folder_image_optimizer_seen_folders(),
    }
    if request.method == "POST":
        state["mode"] = request.form.get("action", "server_folder").strip() or "server_folder"
        state["folder_path"] = request.form.get("folder_path", "").strip()
        state["output_folder"] = request.form.get("output_folder", "").strip()
        state["output_format"] = request.form.get("output_format", "webp").strip().lower() or "webp"
        state["image_quality"] = str(normalize_image_quality(request.form.get("image_quality", "82")))
        state["max_width"] = str(normalize_image_dimension_limit(request.form.get("max_width", "")) or "")
        state["max_height"] = str(normalize_image_dimension_limit(request.form.get("max_height", "")) or "")
        state["recursive"] = request.form.get("recursive") == "1"
        state["overwrite_original"] = request.form.get("overwrite_original") == "1"
        try:
            if state["mode"] == "upload_folder":
                state["result"] = optimize_uploaded_folder_images(
                    request.files.getlist("folder_files"),
                    output_format=state["output_format"],
                    quality=state["image_quality"],
                    max_width=state["max_width"],
                    max_height=state["max_height"],
                )
                _hydrate_folder_optimizer_download_urls(state["result"])
                state["success"] = f"Optimized {state['result']['optimized_count']} uploaded image(s)."
                save_folder_image_optimizer_run(state["result"], status="success", message=state["success"])
            else:
                state["result"] = optimize_images_in_folder(
                    state["folder_path"],
                    output_folder=state["output_folder"],
                    output_format=state["output_format"],
                    quality=state["image_quality"],
                    recursive=state["recursive"],
                    overwrite_original=state["overwrite_original"],
                    max_width=state["max_width"],
                    max_height=state["max_height"],
                )
                _hydrate_folder_optimizer_download_urls(state["result"])
                if state["overwrite_original"]:
                    state["success"] = f"Optimized and overwrote {state['result']['optimized_count']} original image(s)."
                else:
                    state["success"] = (
                        f"Optimized {state['result']['optimized_count']} image(s) into "
                        f"{state['result']['output_folder']}."
                    )
                save_folder_image_optimizer_run(state["result"], status="success", message=state["success"])
        except Exception as exc:
            logger.exception("folder image optimizer failed")
            state["error"] = str(exc) or "Could not optimize that folder."
            save_folder_image_optimizer_run(
                {
                    "mode": state["mode"],
                    "source_folder": state["folder_path"] if state["mode"] != "upload_folder" else "Selected browser folder",
                    "output_folder": state["output_folder"],
                    "output_format": state["output_format"],
                    "quality": state["image_quality"],
                    "max_width": state["max_width"],
                    "max_height": state["max_height"],
                    "recursive": state["recursive"],
                    "overwrite_original": state["overwrite_original"],
                    "seen_folders": [state["folder_path"]] if state["folder_path"] else [],
                },
                status="error",
                message=state["error"],
            )
        state["optimizer_history"] = list_folder_image_optimizer_runs()
        state["seen_folders"] = list_folder_image_optimizer_seen_folders()
    return render_template("folder_image_optimizer.html", **base_template_context(), **state)


def download_folder_image_optimizer_zip(run_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id or ""):
        abort(404)
    saved_zip_path = FOLDER_IMAGE_OPTIMIZER_ZIP_DIR / f"optimized-images-{run_id[:8]}.zip"
    if saved_zip_path.exists() and saved_zip_path.is_file():
        return send_file(
            saved_zip_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=saved_zip_path.name,
            conditional=False,
        )

    output_dir = FOLDER_IMAGE_OPTIMIZER_DIR / run_id
    if not output_dir.exists() or not output_dir.is_dir():
        abort(404)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for image_path in sorted(output_dir.rglob("*")):
            if image_path.is_file():
                archive.write(image_path, image_path.relative_to(output_dir).as_posix())
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"optimized-images-{run_id[:8]}.zip",
    )


def image_tools():
    state = {
        "brand": "",
        "brand_logo_url": "",
        "source_image_url": "",
        "source_image_name": "",
        "result_image_url": "",
        "result_download_name": "",
        "result_file_size": "",
        "result_original_file_size": "",
        "error": None,
        "success": None,
        "pixel_width": "800",
        "pixel_height": "450",
        "snap_ratio": "16:9",
        "watermark_position": "bottom-right",
        "watermark_opacity": "100",
        "logo_scale": "20",
        "output_filename": "watermarked-image",
        "output_format": "webp",
        "optimize_image": True,
        "image_quality": "82",
        "crop_x": "0",
        "crop_y": "0",
        "crop_width": "",
        "crop_height": "",
        "crop_scale": "70",
        "watermark_x": "85",
        "watermark_y": "85",
        "watermark_rotation": "0",
        "use_watermark": True,
        "brand_names": list_brand_names(),
    }

    if request.method == "POST":
        _handle_image_tools_post(state)

    return render_template("image_tools.html", **base_template_context(), **state)


def _hydrate_folder_optimizer_download_urls(result: dict | None) -> None:
    if not result:
        return
    zip_file_path = result.get("zip_file_path", "")
    if zip_file_path:
        result["zip_url"] = image_url(zip_file_path)
    for item in result.get("items", []):
        output_file_path = item.get("output_file_path", "")
        if output_file_path:
            item["output_url"] = image_url(output_file_path)


def _handle_bulk_image_search(state: dict) -> None:
    state["image_requests"] = request.form.get("image_requests", "").strip()
    queries = parse_bulk_image_queries(state["image_requests"])
    if not queries:
        state["error"] = "List at least one icon or featured image to search."
        return
    try:
        state["search_groups"] = search_google_images_for_queries(queries)
        if not any(group.get("results") for group in state["search_groups"]):
            state["error"] = "Google did not return direct image URLs. Open the Google Images links or paste a direct image URL below."
    except Exception as exc:
        logger.exception("bulk image search failed")
        state["error"] = str(exc) or "Could not search Google Images. Try a direct image URL."


def _handle_bulk_image_save(state: dict) -> None:
    state["image_requests"] = request.form.get("image_requests", "").strip()
    image_src = request.form.get("image_url", "").strip() or request.form.get("manual_image_url", "").strip()
    query = request.form.get("query", "").strip() or request.form.get("manual_query", "").strip()
    title = request.form.get("title", "").strip() or query
    state["manual_image_url"] = request.form.get("manual_image_url", "").strip()
    state["manual_query"] = request.form.get("manual_query", "").strip()
    if not image_src:
        state["error"] = "Choose an image result or paste a direct image URL."
        return
    try:
        item = save_remote_image_to_bank(image_src, query=query, title=title)
        state["saved_item"] = image_bank_view_item(item)
        state["success"] = f"Saved {state['saved_item']['download_name']} to Image Bank."
    except Exception as exc:
        logger.exception("bulk image save failed")
        state["error"] = str(exc) or "Could not save that image."


def _handle_bulk_image_download_first_5(state: dict) -> None:
    state["image_requests"] = request.form.get("image_requests", "").strip()
    queries = parse_bulk_image_queries(state["image_requests"])
    if not queries:
        state["error"] = "List at least one icon or featured image to download."
        return
    saved_count = 0
    failed_count = 0
    try:
        state["search_groups"] = search_google_images_for_queries(queries, per_query=5)
        for group in state["search_groups"]:
            for item in group.get("results", [])[:5]:
                try:
                    save_remote_image_to_bank(
                        item.get("image_url", ""),
                        query=group.get("query", ""),
                        title=item.get("title", "") or group.get("query", ""),
                    )
                    saved_count += 1
                except Exception:
                    failed_count += 1
                    logger.exception("bulk image first 5 save failed: query=%s", group.get("query", ""))
        if saved_count:
            state["success"] = f"Downloaded {saved_count} image(s) to Image Bank."
            if failed_count:
                state["success"] += f" {failed_count} image(s) could not be downloaded."
        else:
            state["error"] = "Python searched Google, but no images could be downloaded. Try Regenerate or paste a direct image URL."
    except Exception as exc:
        logger.exception("bulk image first 5 download failed")
        state["error"] = str(exc) or "Could not download images from Google results."


def _handle_image_tools_post(state: dict):
    for key, default in (
        ("brand", ""),
        ("pixel_width", ""),
        ("pixel_height", ""),
        ("snap_ratio", "16:9"),
        ("watermark_position", "bottom-right"),
        ("watermark_opacity", "45"),
        ("logo_scale", "20"),
        ("output_filename", "watermarked-image"),
        ("output_format", "webp"),
        ("image_quality", "82"),
        ("crop_x", "0"),
        ("crop_y", "0"),
        ("crop_width", ""),
        ("crop_height", ""),
        ("crop_scale", "70"),
        ("watermark_x", "85"),
        ("watermark_y", "85"),
        ("watermark_rotation", "0"),
    ):
        state[key] = request.form.get(key, default).strip() or default

    state["output_format"] = state["output_format"].lower()
    state["image_quality"] = str(normalize_image_quality(state["image_quality"]))
    state["optimize_image"] = request.form.get("optimize_image") == "1"
    state["use_watermark"] = request.form.get("use_watermark") == "1"
    saved_source_image = request.form.get("saved_source_image", "").strip()

    brand_record = get_brand_record(state["brand"])
    if brand_record and brand_record.get("logo_path"):
        state["brand_logo_url"] = image_url(brand_record.get("logo_path", ""))

    uploaded_image = request.files.get("image_file")
    source_filename = saved_source_image
    if uploaded_image and uploaded_image.filename:
        source_filename = ""

    if source_filename:
        state["source_image_name"] = Path(source_filename).name
        state["source_image_url"] = image_url(f"image_tools/{source_filename}")

    validation_error = _validate_image_request(uploaded_image, source_filename, brand_record, state)
    if validation_error:
        state["error"] = validation_error
        return

    try:
        from PIL import Image, ImageOps

        if uploaded_image and uploaded_image.filename:
            source_filename = save_uploaded_image(uploaded_image, IMAGE_TOOL_DIR, "source")
        if not source_filename:
            raise ValueError("Please upload the image you want to process.")

        source_path = IMAGE_TOOL_DIR / source_filename
        if not source_path.exists():
            raise ValueError("The last uploaded image could not be found. Please upload it again.")
        source_size = source_path.stat().st_size

        state["source_image_name"] = Path(source_filename).name
        state["source_image_url"] = image_url(f"image_tools/{source_filename}")
        clean_base_name = Path(state["output_filename"]).stem.replace("_", " ").strip() or "watermarked-image"

        normalized_format = "jpg" if state["output_format"] == "jpeg" else state["output_format"]

        with Image.open(source_path) as source_image:
            working_image = ImageOps.exif_transpose(source_image).convert("RGBA")
            working_image = crop_image_to_box(
                working_image,
                state["crop_x"],
                state["crop_y"],
                state["crop_width"],
                state["crop_height"],
            )
            output_width, output_height = calculate_output_dimensions(
                state["pixel_width"],
                state["pixel_height"],
                state["snap_ratio"],
                working_image.width,
                working_image.height,
            )
            if (working_image.width, working_image.height) != (output_width, output_height):
                working_image = working_image.resize((output_width, output_height), resample=Image.Resampling.LANCZOS)
            if state["use_watermark"]:
                logo_path = UPLOAD_ROOT / brand_record["logo_path"]
                with Image.open(logo_path) as logo_image:
                    working_image = apply_logo_watermark(
                        working_image,
                        ImageOps.exif_transpose(logo_image),
                        state["watermark_position"],
                        state["watermark_opacity"],
                        state["logo_scale"],
                        state["watermark_x"],
                        state["watermark_y"],
                        state["watermark_rotation"],
                    )

            if normalized_format in {"jpg", "webp", "avif"}:
                working_image = working_image.convert("RGB")

            output_name = f"{clean_base_name}.{normalized_format}"
            output_path = IMAGE_TOOL_DIR / output_name
            save_optimized_image(
                working_image,
                output_path,
                normalized_format,
                quality=normalize_image_quality(state["image_quality"]),
                optimize=state["optimize_image"],
            )

        state["result_image_url"] = image_url(f"image_tools/{output_name}")
        state["result_download_name"] = f"{clean_base_name}.{normalized_format}"
        output_size = output_path.stat().st_size
        state["result_file_size"] = format_file_size(output_size)
        state["result_original_file_size"] = format_file_size(source_size)
        state["success"] = f"Image processed as {state['result_download_name']} ({state['result_file_size']})."
    except ImportError:
        state["error"] = "Image processing needs Pillow. Install it with: pip install pillow"
    except ValueError as exc:
        state["error"] = str(exc)
    except Exception:
        logger.exception("image_tools action failed")
        state["error"] = "An error occurred while processing the image. Check logs/app.log for details."


def _validate_image_request(uploaded_image, source_filename: str, brand_record, state: dict) -> str | None:
    if (not uploaded_image or not uploaded_image.filename) and not source_filename:
        return "Please upload the image you want to process."
    if state["output_format"] not in {"png", "jpg", "jpeg", "webp", "avif"}:
        return "Please choose PNG, JPG, JPEG, WEBP, or AVIF as the export format."
    if state["use_watermark"] and not state["brand"]:
        return "Please select or enter a brand to use a watermark."
    if state["use_watermark"] and not brand_record:
        return "That brand is not saved yet. Add it first on the Brands page."
    if state["use_watermark"] and not brand_record.get("logo_path"):
        return "This brand does not have a logo yet. Upload one on the Brands page first."
    return None
