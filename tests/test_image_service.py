from io import BytesIO
from zipfile import ZipFile

from PIL import Image
from werkzeug.datastructures import FileStorage

from app.services.image_service import (
    UPLOAD_ROOT,
    crop_image_to_box,
    format_file_size,
    normalize_image_dimension_limit,
    normalize_image_quality,
    optimize_images_in_folder,
    optimize_uploaded_folder_images,
    save_optimized_image,
)


def test_crop_image_to_box_clamps_oversized_rounding():
    image = Image.new("RGBA", (100, 200), "white")

    cropped = crop_image_to_box(image, "0", "0", "101", "201")

    assert cropped.size == (100, 200)


def test_normalize_image_quality_clamps_values():
    assert normalize_image_quality("20") == 35
    assert normalize_image_quality("101") == 100
    assert normalize_image_quality("bad") == 82


def test_normalize_image_dimension_limit_clamps_values():
    assert normalize_image_dimension_limit("1600") == 1600
    assert normalize_image_dimension_limit("-1") == 0
    assert normalize_image_dimension_limit("20000") == 10000
    assert normalize_image_dimension_limit("bad") == 0


def test_save_optimized_image_writes_smaller_webp(tmp_path):
    image = Image.new("RGB", (320, 180), "white")
    output_path = tmp_path / "optimized.webp"

    save_optimized_image(image, output_path, "webp", quality=70, optimize=True)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert format_file_size(output_path.stat().st_size).endswith(("B", "KB"))


def test_optimize_images_in_folder_writes_output_files(tmp_path):
    Image.new("RGB", (120, 80), "red").save(tmp_path / "hero.png")
    (tmp_path / "icons").mkdir()
    Image.new("RGB", (80, 80), "blue").save(tmp_path / "icon.jpg")
    Image.new("RGB", (80, 80), "yellow").save(tmp_path / "icons" / "badge.png")
    (tmp_path / "notes.txt").write_text("not an image", encoding="utf-8")

    result = optimize_images_in_folder(str(tmp_path), output_format="webp", quality=75, recursive=True)

    assert result["optimized_count"] == 3
    assert result["error_count"] == 0
    assert (tmp_path / "optimized-images" / "hero.webp").exists()
    assert (tmp_path / "optimized-images" / "icon.webp").exists()
    assert (tmp_path / "optimized-images" / "icons" / "badge.webp").exists()
    assert result["run_id"]
    assert (UPLOAD_ROOT / f"folder_image_optimizer/{result['run_id']}/icons/badge.webp").exists()
    assert result["zip_file_path"].endswith(f"optimized-images-{result['run_id'][:8]}.zip")
    with ZipFile(UPLOAD_ROOT / result["zip_file_path"]) as archive:
        assert "icons/badge.webp" in archive.namelist()
    assert any(item["output_file_path"].endswith("icons/badge.webp") for item in result["items"])
    assert result["original_total"] > 0
    assert result["optimized_total"] > 0


def test_optimize_images_in_folder_can_overwrite_original_files(tmp_path):
    source_path = tmp_path / "hero.jpg"
    Image.new("RGB", (900, 600), "purple").save(source_path, format="JPEG", quality=100)
    original_size = source_path.stat().st_size

    result = optimize_images_in_folder(str(tmp_path), output_format="webp", quality=35, overwrite_original=True)

    assert result["optimized_count"] == 1
    assert result["overwrite_original"] is True
    assert result["items"][0]["output"] == str(source_path)
    assert source_path.exists()
    assert not (tmp_path / "optimized-images").exists()
    assert source_path.stat().st_size > 0
    assert source_path.stat().st_size <= original_size


def test_optimize_images_in_folder_resizes_for_delivery(tmp_path):
    source_path = tmp_path / "large.jpg"
    Image.new("RGB", (2400, 1200), "orange").save(source_path, format="JPEG", quality=95)

    result = optimize_images_in_folder(str(tmp_path), output_format="webp", quality=75, max_width=1200)

    output_path = tmp_path / "optimized-images" / "large.webp"
    with Image.open(output_path) as image:
        assert image.size == (1200, 600)
    assert result["max_width"] == 1200
    assert result["max_height"] == 0


def test_optimize_uploaded_folder_images_preserves_relative_paths():
    image_buffer = BytesIO()
    Image.new("RGB", (120, 80), "green").save(image_buffer, format="PNG")
    image_buffer.seek(0)
    upload = FileStorage(stream=image_buffer, filename="icons/hero.png", content_type="image/png")

    result = optimize_uploaded_folder_images([upload], output_format="webp", quality=75)

    assert result["optimized_count"] == 1
    assert result["run_id"]
    item = result["items"][0]
    assert item["output_file_path"].startswith(f"folder_image_optimizer/{result['run_id']}/")
    assert item["output_file_path"].endswith("icons/hero.webp")
    assert (UPLOAD_ROOT / item["output_file_path"]).exists()
    with ZipFile(UPLOAD_ROOT / result["zip_file_path"]) as archive:
        assert "icons/hero.webp" in archive.namelist()
