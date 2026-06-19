import os
import time

from app.services.image_tool_cleanup_scheduler import cleanup_old_image_tool_files


def test_cleanup_old_image_tool_files_deletes_only_old_images(tmp_path):
    old_image = tmp_path / "old.webp"
    recent_image = tmp_path / "recent.webp"
    old_text = tmp_path / "old.txt"
    for path in (old_image, recent_image, old_text):
        path.write_text("x", encoding="utf-8")

    old_timestamp = time.time() - (16 * 24 * 60 * 60)
    os.utime(old_image, (old_timestamp, old_timestamp))
    os.utime(old_text, (old_timestamp, old_timestamp))

    deleted_count = cleanup_old_image_tool_files(max_age_days=15, image_tool_dir=tmp_path)

    assert deleted_count == 1
    assert not old_image.exists()
    assert recent_image.exists()
    assert old_text.exists()
