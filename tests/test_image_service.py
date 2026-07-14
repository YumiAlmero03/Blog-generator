from PIL import Image

from app.services.image_service import crop_image_to_box, format_file_size, normalize_image_quality, save_optimized_image


def test_crop_image_to_box_clamps_oversized_rounding():
    image = Image.new("RGBA", (100, 200), "white")

    cropped = crop_image_to_box(image, "0", "0", "101", "201")

    assert cropped.size == (100, 200)


def test_normalize_image_quality_clamps_values():
    assert normalize_image_quality("20") == 35
    assert normalize_image_quality("101") == 100
    assert normalize_image_quality("bad") == 82


def test_save_optimized_image_writes_smaller_webp(tmp_path):
    image = Image.new("RGB", (320, 180), "white")
    output_path = tmp_path / "optimized.webp"

    save_optimized_image(image, output_path, "webp", quality=70, optimize=True)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert format_file_size(output_path.stat().st_size).endswith(("B", "KB"))
