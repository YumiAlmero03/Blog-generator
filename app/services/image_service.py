from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"
BRAND_LOGO_DIR = UPLOAD_ROOT / "brand_logos"
IMAGE_TOOL_DIR = UPLOAD_ROOT / "image_tools"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

for directory in (BRAND_LOGO_DIR, IMAGE_TOOL_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def allowed_image_file(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return suffix in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file_storage, destination_dir: Path, prefix: str) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename or not allowed_image_file(filename):
        raise ValueError("Please upload a PNG, JPG, JPEG, or WEBP image.")

    suffix = Path(filename).suffix.lower() or ".png"
    saved_name = f"{prefix}_{uuid4().hex}{suffix}"
    output_path = destination_dir / saved_name
    file_storage.save(output_path)
    return saved_name


def parse_ratio_dimensions(snap_ratio: str, fallback_width: int, fallback_height: int) -> tuple[int, int]:
    ratio_map = {
        "1:1": (1, 1),
        "4:5": (4, 5),
        "16:9": (16, 9),
        "9:16": (9, 16),
        "3:2": (3, 2),
        "original": (fallback_width, fallback_height),
    }
    ratio = ratio_map.get(snap_ratio)
    if not ratio or ratio[0] <= 0 or ratio[1] <= 0:
        return fallback_width, fallback_height
    return ratio


def calculate_output_dimensions(
    pixel_width: str,
    pixel_height: str,
    snap_ratio: str,
    fallback_width: int,
    fallback_height: int,
) -> tuple[int, int]:
    width_value = int(str(pixel_width or "").strip() or 0)
    height_value = int(str(pixel_height or "").strip() or 0)
    ratio_width, ratio_height = parse_ratio_dimensions(snap_ratio, fallback_width, fallback_height)

    if width_value <= 0 and height_value <= 0:
        raise ValueError("Enter a width or height for the final exported image.")
    if width_value > 0:
        return width_value, max(1, round(width_value * (ratio_height / ratio_width)))
    return max(1, round(height_value * (ratio_width / ratio_height))), height_value


def crop_image_to_box(image, crop_x: str, crop_y: str, crop_width: str, crop_height: str):
    crop_width_value = int(float(crop_width or 0))
    crop_height_value = int(float(crop_height or 0))
    if crop_width_value <= 0 or crop_height_value <= 0:
        raise ValueError("Set a crop area before processing the image.")
    if crop_width_value > image.width or crop_height_value > image.height:
        raise ValueError("The crop size is larger than the source image. Reduce the target crop size.")

    crop_x_value = int(float(crop_x or 0))
    crop_y_value = int(float(crop_y or 0))
    max_x = image.width - crop_width_value
    max_y = image.height - crop_height_value
    crop_x_value = min(max(crop_x_value, 0), max_x)
    crop_y_value = min(max(crop_y_value, 0), max_y)

    return image.crop(
        (
            crop_x_value,
            crop_y_value,
            crop_x_value + crop_width_value,
            crop_y_value + crop_height_value,
        )
    )


def apply_logo_watermark(
    base_image,
    logo_image,
    position: str,
    opacity_percent: str,
    logo_scale_percent: str,
    watermark_x_percent: str = "",
    watermark_y_percent: str = "",
    watermark_rotation: str = "0",
):
    from PIL import Image

    base = base_image.convert("RGBA")
    logo = logo_image.convert("RGBA")

    opacity = max(0, min(100, int(opacity_percent or 45)))
    scale = max(1, int(logo_scale_percent or 20))

    target_logo_width = max(1, round(base.width * (scale / 100.0)))
    resize_ratio = target_logo_width / logo.width
    target_logo_height = max(1, round(logo.height * resize_ratio))
    logo = logo.resize((target_logo_width, target_logo_height), resample=Image.Resampling.LANCZOS)

    alpha = logo.getchannel("A")
    alpha = alpha.point(lambda value: round(value * (opacity / 100.0)))
    logo.putalpha(alpha)

    padding = max(16, round(min(base.width, base.height) * 0.03))

    rotation = float(str(watermark_rotation or "0").strip() or 0)
    if rotation:
        logo = logo.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)

    if str(watermark_x_percent).strip() and str(watermark_y_percent).strip():
        center_x = round(base.width * (float(watermark_x_percent) / 100.0))
        center_y = round(base.height * (float(watermark_y_percent) / 100.0))
        x = center_x - (logo.width // 2)
        y = center_y - (logo.height // 2)
    else:
        positions = {
            "top-left": (padding, padding),
            "top-right": (base.width - logo.width - padding, padding),
            "bottom-left": (padding, base.height - logo.height - padding),
            "center": ((base.width - logo.width) // 2, (base.height - logo.height) // 2),
            "bottom-right": (base.width - logo.width - padding, base.height - logo.height - padding),
        }
        x, y = positions.get(position, positions["bottom-right"])

    x = min(max(0, x), max(0, base.width - logo.width))
    y = min(max(0, y), max(0, base.height - logo.height))
    overlay = base.copy()
    overlay.alpha_composite(logo, (max(0, x), max(0, y)))
    return overlay
