from pathlib import Path

from flask import render_template, request

from database import get_brand_record, list_brand_names
from logger import logger

from app.controllers.helpers import base_template_context, image_url
from app.services.image_service import (
    IMAGE_TOOL_DIR,
    UPLOAD_ROOT,
    apply_logo_watermark,
    calculate_output_dimensions,
    crop_image_to_box,
    save_uploaded_image,
)


def image_tools():
    state = {
        "brand": "",
        "brand_logo_url": "",
        "source_image_url": "",
        "source_image_name": "",
        "result_image_url": "",
        "result_download_name": "",
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
        from PIL import Image

        if uploaded_image and uploaded_image.filename:
            source_filename = save_uploaded_image(uploaded_image, IMAGE_TOOL_DIR, "source")
        if not source_filename:
            raise ValueError("Please upload the image you want to process.")

        source_path = IMAGE_TOOL_DIR / source_filename
        if not source_path.exists():
            raise ValueError("The last uploaded image could not be found. Please upload it again.")

        state["source_image_name"] = Path(source_filename).name
        state["source_image_url"] = image_url(f"image_tools/{source_filename}")
        clean_base_name = Path(state["output_filename"]).stem.replace("_", " ").strip() or "watermarked-image"

        normalized_format = "jpg" if state["output_format"] == "jpeg" else state["output_format"]

        with Image.open(source_path) as source_image:
            working_image = source_image.convert("RGBA")
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
                        logo_image,
                        state["watermark_position"],
                        state["watermark_opacity"],
                        state["logo_scale"],
                        state["watermark_x"],
                        state["watermark_y"],
                        state["watermark_rotation"],
                    )

            if normalized_format in {"jpg", "webp"}:
                working_image = working_image.convert("RGB")

            output_name = f"{clean_base_name}.{normalized_format}"
            output_path = IMAGE_TOOL_DIR / output_name
            save_format = "JPEG" if normalized_format == "jpg" else normalized_format.upper()
            save_kwargs = {"format": save_format}
            if save_format in {"JPEG", "WEBP"}:
                save_kwargs["quality"] = 92
            working_image.save(output_path, **save_kwargs)

        state["result_image_url"] = image_url(f"image_tools/{output_name}")
        state["result_download_name"] = f"{clean_base_name}.{normalized_format}"
        state["success"] = f"Image processed as {state['result_download_name']}."
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
    if state["output_format"] not in {"png", "jpg", "jpeg", "webp"}:
        return "Please choose PNG, JPG, JPEG, or WEBP as the export format."
    if state["use_watermark"] and not state["brand"]:
        return "Please select or enter a brand to use a watermark."
    if state["use_watermark"] and not brand_record:
        return "That brand is not saved yet. Add it first on the Brands page."
    if state["use_watermark"] and not brand_record.get("logo_path"):
        return "This brand does not have a logo yet. Upload one on the Brands page first."
    return None
