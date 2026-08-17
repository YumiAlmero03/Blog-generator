from io import BytesIO
from pathlib import Path
from shutil import copy2
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = BASE_DIR / "data" / "uploads"
BRAND_LOGO_DIR = UPLOAD_ROOT / "brand_logos"
IMAGE_TOOL_DIR = UPLOAD_ROOT / "image_tools"
IMAGE_BANK_DIR = UPLOAD_ROOT / "image_bank"
GSC_PLANNER_DIR = UPLOAD_ROOT / "gsc_planner"
FOLDER_IMAGE_OPTIMIZER_DIR = UPLOAD_ROOT / "folder_image_optimizer"
FOLDER_IMAGE_OPTIMIZER_ZIP_DIR = UPLOAD_ROOT / "folder_image_optimizer_zips"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".avif"}
FOLDER_IMAGE_OPTIMIZER_DEFAULT_OUTPUT = "optimized-images"

for directory in (
    BRAND_LOGO_DIR,
    IMAGE_TOOL_DIR,
    IMAGE_BANK_DIR,
    GSC_PLANNER_DIR,
    FOLDER_IMAGE_OPTIMIZER_DIR,
    FOLDER_IMAGE_OPTIMIZER_ZIP_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)


def allowed_image_file(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return suffix in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file_storage, destination_dir: Path, prefix: str) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename or not allowed_image_file(filename):
        raise ValueError("Please upload a PNG, JPG, JPEG, WEBP, or AVIF image.")

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
    crop_width_value = min(crop_width_value, image.width)
    crop_height_value = min(crop_height_value, image.height)

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


def normalize_image_quality(value: str, default: int = 82) -> int:
    try:
        quality = int(str(value or "").strip() or default)
    except (TypeError, ValueError):
        quality = default
    return max(35, min(100, quality))


def normalize_image_dimension_limit(value: str | int, default: int = 0) -> int:
    try:
        limit = int(str(value or "").strip() or default)
    except (TypeError, ValueError):
        limit = default
    return max(0, min(10000, limit))


def save_optimized_image(image, output_path: Path, normalized_format: str, quality: int = 82, optimize: bool = True) -> None:
    save_format = "JPEG" if normalized_format == "jpg" else normalized_format.upper()
    save_kwargs = {"format": save_format}
    if save_format == "JPEG":
        save_kwargs.update(
            {
                "quality": normalize_image_quality(str(quality)),
                "optimize": bool(optimize),
                "progressive": bool(optimize),
                "subsampling": "4:2:0",
            }
        )
    elif save_format == "WEBP":
        save_kwargs.update(
            {
                "quality": normalize_image_quality(str(quality)),
                "method": 6 if optimize else 4,
            }
        )
    elif save_format == "AVIF":
        save_kwargs.update(
            {
                "quality": normalize_image_quality(str(quality)),
                "speed": 4 if optimize else 6,
            }
        )
    elif save_format == "PNG":
        save_kwargs.update(
            {
                "optimize": bool(optimize),
                "compress_level": 9 if optimize else 6,
            }
        )
    image.save(output_path, **save_kwargs)


def optimize_images_in_folder(
    folder_path: str,
    output_folder: str = "",
    output_format: str = "webp",
    quality: int | str = 82,
    recursive: bool = False,
    overwrite_original: bool = False,
    max_width: int | str = 0,
    max_height: int | str = 0,
) -> dict:
    source_dir = Path(folder_path or "").expanduser()
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError("Enter an existing folder path.")

    normalized_format = "jpg" if str(output_format or "webp").strip().lower() == "jpeg" else str(output_format or "webp").strip().lower()
    if normalized_format not in {"png", "jpg", "webp", "avif"}:
        raise ValueError("Choose PNG, JPG, WEBP, or AVIF as the output format.")

    if overwrite_original:
        output_dir = source_dir
    else:
        if output_folder:
            output_dir = Path(output_folder).expanduser()
            if not output_dir.is_absolute():
                output_dir = source_dir / output_dir
        else:
            output_dir = source_dir / FOLDER_IMAGE_OPTIMIZER_DEFAULT_OUTPUT
        output_dir.mkdir(parents=True, exist_ok=True)

    quality_value = normalize_image_quality(str(quality))
    max_width_value = normalize_image_dimension_limit(max_width)
    max_height_value = normalize_image_dimension_limit(max_height)
    source_files = _folder_image_files(source_dir, None if overwrite_original else output_dir, recursive=recursive)
    run_id = uuid4().hex
    archive_dir = FOLDER_IMAGE_OPTIMIZER_DIR / run_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    results = []
    optimized_count = 0
    skipped_count = 0
    error_count = 0
    original_total = 0
    optimized_total = 0

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ValueError("Folder Image Optimizer needs Pillow. Install it with: pip install pillow") from exc

    for source_path in source_files:
        relative = source_path.relative_to(source_dir)
        target_format = _image_format_from_path(source_path) if overwrite_original else normalized_format
        output_name = relative if overwrite_original else relative.with_suffix(f".{normalized_format}")
        output_path = output_dir / output_name
        temp_output_path = (
            output_path.with_name(f"{output_path.stem}.{uuid4().hex}.tmp.{target_format}")
            if overwrite_original
            else output_path
        )
        temp_output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            original_size = source_path.stat().st_size
            with Image.open(source_path) as source_image:
                working_image = ImageOps.exif_transpose(source_image)
                working_image = resize_image_for_delivery(working_image, max_width_value, max_height_value)
                if target_format in {"jpg", "webp", "avif"}:
                    working_image = working_image.convert("RGB")
                save_optimized_image(working_image, temp_output_path, target_format, quality=quality_value, optimize=True)
            if overwrite_original:
                temp_output_path.replace(output_path)
            optimized_size = output_path.stat().st_size
            archive_path = archive_dir / output_name
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(output_path, archive_path)
            optimized_count += 1
            original_total += original_size
            optimized_total += optimized_size
            results.append(
                {
                    "source": str(source_path),
                    "output": str(output_path),
                    "output_file_path": f"folder_image_optimizer/{run_id}/{output_name.as_posix()}",
                    "status": "optimized",
                    "original_size": original_size,
                    "optimized_size": optimized_size,
                    "original_size_label": format_file_size(original_size),
                    "optimized_size_label": format_file_size(optimized_size),
                    "saved_size_label": format_file_size(max(0, original_size - optimized_size)),
                    "message": "",
                }
            )
        except Exception as exc:
            error_count += 1
            results.append(
                {
                    "source": str(source_path),
                    "output": str(output_path),
                    "output_file_path": "",
                    "status": "error",
                    "original_size": 0,
                    "optimized_size": 0,
                    "original_size_label": "",
                    "optimized_size_label": "",
                    "saved_size_label": "",
                    "message": str(exc) or "Could not optimize this image.",
                }
            )

    if not source_files:
        skipped_count = 0
    zip_file_path = create_folder_optimizer_zip(run_id)

    return {
        "mode": "server_folder",
        "run_id": run_id,
        "source_folder": str(source_dir),
        "output_folder": str(output_dir),
        "output_format": normalized_format,
        "quality": quality_value,
        "recursive": bool(recursive),
        "overwrite_original": bool(overwrite_original),
        "max_width": max_width_value,
        "max_height": max_height_value,
        "total_count": len(source_files),
        "optimized_count": optimized_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "original_total": original_total,
        "optimized_total": optimized_total,
        "original_total_label": format_file_size(original_total),
        "optimized_total_label": format_file_size(optimized_total),
        "saved_total_label": format_file_size(max(0, original_total - optimized_total)),
        "zip_file_path": zip_file_path,
        "seen_folders": _folder_image_seen_folders(source_files, source_dir),
        "items": results,
    }


def optimize_uploaded_folder_images(
    uploaded_files,
    output_format: str = "webp",
    quality: int | str = 82,
    max_width: int | str = 0,
    max_height: int | str = 0,
) -> dict:
    files = [file for file in uploaded_files if getattr(file, "filename", "") and allowed_image_file(file.filename)]
    if not files:
        raise ValueError("Select a folder with PNG, JPG, JPEG, WEBP, or AVIF images.")

    normalized_format = "jpg" if str(output_format or "webp").strip().lower() == "jpeg" else str(output_format or "webp").strip().lower()
    if normalized_format not in {"png", "jpg", "webp", "avif"}:
        raise ValueError("Choose PNG, JPG, WEBP, or AVIF as the output format.")

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ValueError("Folder Image Optimizer needs Pillow. Install it with: pip install pillow") from exc

    run_id = uuid4().hex
    output_dir = FOLDER_IMAGE_OPTIMIZER_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    quality_value = normalize_image_quality(str(quality))
    max_width_value = normalize_image_dimension_limit(max_width)
    max_height_value = normalize_image_dimension_limit(max_height)
    results = []
    optimized_count = 0
    error_count = 0
    original_total = 0
    optimized_total = 0

    for upload in files:
        original_filename = upload.filename or "image"
        relative_path = _safe_uploaded_relative_path(original_filename)
        output_relative = relative_path.with_suffix(f".{normalized_format}")
        output_path = output_dir / output_relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw = upload.read()
        try:
            original_size = len(raw)
            with Image.open(BytesIO(raw)) as source_image:
                working_image = ImageOps.exif_transpose(source_image)
                working_image = resize_image_for_delivery(working_image, max_width_value, max_height_value)
                if normalized_format in {"jpg", "webp", "avif"}:
                    working_image = working_image.convert("RGB")
                save_optimized_image(working_image, output_path, normalized_format, quality=quality_value, optimize=True)
            optimized_size = output_path.stat().st_size
            optimized_count += 1
            original_total += original_size
            optimized_total += optimized_size
            results.append(
                {
                    "source": original_filename,
                    "output": str(output_path),
                    "output_file_path": f"folder_image_optimizer/{run_id}/{output_relative.as_posix()}",
                    "status": "optimized",
                    "original_size": original_size,
                    "optimized_size": optimized_size,
                    "original_size_label": format_file_size(original_size),
                    "optimized_size_label": format_file_size(optimized_size),
                    "saved_size_label": format_file_size(max(0, original_size - optimized_size)),
                    "message": "",
                }
            )
        except Exception as exc:
            error_count += 1
            results.append(
                {
                    "source": original_filename,
                    "output": str(output_path),
                    "output_file_path": "",
                    "status": "error",
                    "original_size": 0,
                    "optimized_size": 0,
                    "original_size_label": "",
                    "optimized_size_label": "",
                    "saved_size_label": "",
                    "message": str(exc) or "Could not optimize this image.",
                }
            )

    zip_file_path = create_folder_optimizer_zip(run_id)

    return {
        "mode": "upload_folder",
        "run_id": run_id,
        "source_folder": "Selected browser folder",
        "output_folder": str(output_dir),
        "output_format": normalized_format,
        "quality": quality_value,
        "recursive": True,
        "max_width": max_width_value,
        "max_height": max_height_value,
        "total_count": len(files),
        "optimized_count": optimized_count,
        "skipped_count": 0,
        "error_count": error_count,
        "original_total": original_total,
        "optimized_total": optimized_total,
        "original_total_label": format_file_size(original_total),
        "optimized_total_label": format_file_size(optimized_total),
        "saved_total_label": format_file_size(max(0, original_total - optimized_total)),
        "zip_file_path": zip_file_path,
        "seen_folders": _uploaded_folder_names(files),
        "items": results,
    }


def resize_image_for_delivery(image, max_width: int = 0, max_height: int = 0):
    width_limit = normalize_image_dimension_limit(max_width)
    height_limit = normalize_image_dimension_limit(max_height)
    if width_limit <= 0 and height_limit <= 0:
        return image
    current_width, current_height = image.size
    target_width = width_limit if width_limit > 0 else current_width
    target_height = height_limit if height_limit > 0 else current_height
    if current_width <= target_width and current_height <= target_height:
        return image
    resized = image.copy()
    try:
        from PIL import Image

        resized.thumbnail((target_width, target_height), resample=Image.Resampling.LANCZOS)
    except ImportError:
        resized.thumbnail((target_width, target_height))
    return resized


def create_folder_optimizer_zip(run_id: str) -> str:
    source_dir = FOLDER_IMAGE_OPTIMIZER_DIR / run_id
    zip_path = FOLDER_IMAGE_OPTIMIZER_ZIP_DIR / f"optimized-images-{run_id[:8]}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", ZIP_DEFLATED, allowZip64=True) as archive:
        for image_path in sorted(source_dir.rglob("*")):
            if image_path.is_file():
                archive.write(image_path, image_path.relative_to(source_dir).as_posix())
    return f"folder_image_optimizer_zips/{zip_path.name}"


def _folder_image_files(source_dir: Path, output_dir: Path | None, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    resolved_output_dir = output_dir.resolve() if output_dir else None
    files = []
    for path in source_dir.glob(pattern):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            continue
        if resolved_output_dir:
            try:
                if path.resolve().is_relative_to(resolved_output_dir):
                    continue
            except OSError:
                pass
        files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _image_format_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "jpg"
    if suffix == ".png":
        return "png"
    if suffix == ".avif":
        return "avif"
    return "webp"


def _folder_image_seen_folders(source_files: list[Path], source_dir: Path) -> list[str]:
    seen = []
    seen_keys = set()
    for path in source_files:
        folder = str(path.parent)
        if path.parent == source_dir:
            folder = str(source_dir)
        key = folder.lower()
        if key not in seen_keys:
            seen_keys.add(key)
            seen.append(folder)
    return seen


def _uploaded_folder_names(uploaded_files) -> list[str]:
    seen = []
    seen_keys = set()
    for upload in uploaded_files:
        relative_path = _safe_uploaded_relative_path(getattr(upload, "filename", ""))
        folder = relative_path.parent.as_posix()
        if folder == ".":
            folder = "Selected browser folder"
        key = folder.lower()
        if key not in seen_keys:
            seen_keys.add(key)
            seen.append(folder)
    return seen


def _safe_uploaded_relative_path(filename: str) -> Path:
    parts = []
    for part in Path(str(filename or "").replace("\\", "/")).parts:
        if part in {"", ".", ".."}:
            continue
        clean_part = secure_filename(part)
        if clean_part:
            parts.append(clean_part)
    if not parts:
        return Path(f"image_{uuid4().hex}.png")
    return Path(*parts)


def format_file_size(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes or 0)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


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
