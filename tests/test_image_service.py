from PIL import Image

from app.services.image_service import crop_image_to_box


def test_crop_image_to_box_clamps_oversized_rounding():
    image = Image.new("RGBA", (100, 200), "white")

    cropped = crop_image_to_box(image, "0", "0", "101", "201")

    assert cropped.size == (100, 200)
