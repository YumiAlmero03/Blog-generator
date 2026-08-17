from io import BytesIO
from zipfile import ZipFile

from app import create_app
from app.controllers import image_controller
from app.services.image_bank_service import _extract_google_image_urls, parse_bulk_image_queries
from app.services.image_service import FOLDER_IMAGE_OPTIMIZER_ZIP_DIR


def test_parse_bulk_image_queries_deduplicates_lines_and_commas():
    queries = parse_bulk_image_queries("casino icon\nfootball hero, casino icon\nmobile app")

    assert queries == ["casino icon", "football hero", "mobile app"]


def test_google_image_parser_uses_img_tag_thumbnails():
    urls = _extract_google_image_urls(
        """
        <html>
          <body>
            <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:abc123">
            <img data-src="https://example.com/photo.jpg">
          </body>
        </html>
        """
    )

    assert "https://example.com/photo.jpg" in urls
    assert "https://encrypted-tbn0.gstatic.com/images?q=tbn:abc123" in urls


def test_google_image_parser_uses_stackoverflow_rg_meta_pattern():
    urls = _extract_google_image_urls(
        """
        <div class="rg_meta">{"ou":"https://example.com/original-photo.jpg","ity":"jpg"}</div>
        <script>var item = {"ou":"https://example.com/second-photo.png"};</script>
        """
    )

    assert urls[:2] == [
        "https://example.com/original-photo.jpg",
        "https://example.com/second-photo.png",
    ]


def test_bulk_image_downloader_search_renders_google_results(monkeypatch):
    monkeypatch.setattr(
        image_controller,
        "search_google_images_for_queries",
        lambda queries: [
            {
                "query": queries[0],
                "google_url": "https://www.google.com/search?tbm=isch&q=casino+icon",
                "results": [
                    {
                        "title": "casino icon",
                        "image_url": "https://example.com/casino-icon.jpg",
                        "thumbnail_url": "https://example.com/casino-icon.jpg",
                        "source": "example.com",
                    }
                ],
            }
        ],
    )

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/bulk-image-downloader",
        data={
            "action": "search",
            "image_requests": "casino icon",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Bulk Image Downloader" in html
    assert "casino icon" in html
    assert "https://example.com/casino-icon.jpg" in html
    assert "Save to Image Bank" in html
    assert "Regenerate Results" in html
    assert "Download First 5 to Bank" in html


def test_bulk_image_downloader_save_uses_image_bank(monkeypatch):
    saved = {}

    def fake_save_remote_image_to_bank(image_src, query="", title=""):
        saved.update({"image_src": image_src, "query": query, "title": title})
        return {
            "id": 1,
            "query": query,
            "title": title,
            "source_url": image_src,
            "file_path": "image_bank/casino-icon.webp",
            "file_name": "casino-icon.webp",
            "file_size": 1200,
            "width": 800,
            "height": 450,
        }

    monkeypatch.setattr(image_controller, "save_remote_image_to_bank", fake_save_remote_image_to_bank)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/bulk-image-downloader",
        data={
            "action": "save",
            "query": "casino icon",
            "title": "casino icon",
            "image_url": "https://example.com/casino-icon.jpg",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert saved == {
        "image_src": "https://example.com/casino-icon.jpg",
        "query": "casino icon",
        "title": "casino icon",
    }
    assert "Saved casino-icon.webp to Image Bank." in html
    assert "/uploads/image_bank/casino-icon.webp" in html


def test_bulk_image_downloader_downloads_first_five_to_bank(monkeypatch):
    saved_urls = []

    monkeypatch.setattr(
        image_controller,
        "search_google_images_for_queries",
        lambda queries, per_query=5: [
            {
                "query": queries[0],
                "google_url": "https://www.google.com/search?tbm=isch&q=casino+icon",
                "results": [
                    {
                        "title": f"casino icon {index}",
                        "image_url": f"https://example.com/casino-icon-{index}.jpg",
                        "thumbnail_url": f"https://example.com/casino-icon-{index}.jpg",
                        "source": "example.com",
                    }
                    for index in range(1, 6)
                ],
            }
        ],
    )

    def fake_save_remote_image_to_bank(image_src, query="", title=""):
        saved_urls.append(image_src)
        return {
            "id": len(saved_urls),
            "query": query,
            "title": title,
            "source_url": image_src,
            "file_path": f"image_bank/{len(saved_urls)}.webp",
            "file_name": f"{len(saved_urls)}.webp",
            "file_size": 1200,
            "width": 800,
            "height": 450,
        }

    monkeypatch.setattr(image_controller, "save_remote_image_to_bank", fake_save_remote_image_to_bank)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/bulk-image-downloader",
        data={
            "action": "download_first_5",
            "image_requests": "casino icon",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert len(saved_urls) == 5
    assert saved_urls[0] == "https://example.com/casino-icon-1.jpg"
    assert "Downloaded 5 image(s) to Image Bank." in html


def test_image_bank_page_renders_downloadable_images(monkeypatch):
    monkeypatch.setattr(
        image_controller,
        "list_image_bank_items",
        lambda: [
            {
                "id": 1,
                "query": "featured image",
                "title": "Featured Image",
                "source_url": "https://example.com/source.jpg",
                "file_path": "image_bank/featured.webp",
                "file_name": "featured.webp",
                "file_size": 1400,
                "width": 1200,
                "height": 675,
            }
        ],
    )

    app = create_app()
    app.testing = True
    response = app.test_client().get("/image-bank")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Image Bank" in html
    assert "Featured Image" in html
    assert "/uploads/image_bank/featured.webp" in html
    assert 'download="featured.webp"' in html


def test_folder_image_optimizer_page_optimizes_folder(monkeypatch):
    monkeypatch.setattr(
        image_controller,
        "optimize_images_in_folder",
        lambda folder_path, output_folder="", output_format="webp", quality=82, recursive=False, overwrite_original=False, max_width=0, max_height=0: {
            "source_folder": folder_path,
            "output_folder": f"{folder_path}/optimized-images",
            "output_format": output_format,
            "quality": int(quality),
            "max_width": int(max_width or 0),
            "max_height": int(max_height or 0),
            "recursive": recursive,
            "overwrite_original": overwrite_original,
            "total_count": 1,
            "optimized_count": 1,
            "skipped_count": 0,
            "error_count": 0,
            "original_total": 2000,
            "optimized_total": 1200,
            "original_total_label": "2.0 KB",
            "optimized_total_label": "1.2 KB",
            "saved_total_label": "800 B",
            "items": [
                {
                    "source": f"{folder_path}/hero.png",
                    "output": f"{folder_path}/optimized-images/hero.webp",
                    "status": "optimized",
                    "original_size_label": "2.0 KB",
                    "optimized_size_label": "1.2 KB",
                    "saved_size_label": "800 B",
                    "message": "",
                }
            ],
        },
    )

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/folder-image-optimizer",
        data={
            "folder_path": "/tmp/images",
            "output_format": "webp",
            "image_quality": "75",
            "recursive": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Folder Image Optimizer" in html
    assert "Optimized 1 image(s)" in html
    assert "/tmp/images/optimized-images/hero.webp" in html


def test_folder_image_optimizer_page_optimizes_selected_folder(monkeypatch):
    def fake_optimize_uploaded_folder_images(uploaded_files, output_format="webp", quality=82, max_width=0, max_height=0):
        assert len(uploaded_files) == 1
        return {
            "mode": "upload_folder",
            "run_id": "a" * 32,
            "source_folder": "Selected browser folder",
            "output_folder": "/tmp/optimized-upload",
            "output_format": output_format,
            "quality": int(quality),
            "max_width": int(max_width or 0),
            "max_height": int(max_height or 0),
            "recursive": True,
            "total_count": 1,
            "optimized_count": 1,
            "skipped_count": 0,
            "error_count": 0,
            "original_total": 2000,
            "optimized_total": 1200,
            "original_total_label": "2.0 KB",
            "optimized_total_label": "1.2 KB",
            "saved_total_label": "800 B",
            "items": [
                {
                    "source": "icons/hero.png",
                    "output": "/tmp/optimized-upload/icons/hero.webp",
                    "output_file_path": "folder_image_optimizer/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/icons/hero.webp",
                    "status": "optimized",
                    "original_size_label": "2.0 KB",
                    "optimized_size_label": "1.2 KB",
                    "saved_size_label": "800 B",
                    "message": "",
                }
            ],
        }

    monkeypatch.setattr(image_controller, "optimize_uploaded_folder_images", fake_optimize_uploaded_folder_images)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/folder-image-optimizer",
        data={
            "action": "upload_folder",
            "output_format": "webp",
            "image_quality": "75",
            "folder_files": (BytesIO(b"fake image"), "icons/hero.png"),
        },
        content_type="multipart/form-data",
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Optimized 1 uploaded image(s)" in html
    assert "Download Zip File" in html
    assert "/uploads/folder_image_optimizer/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/icons/hero.webp" in html


def test_folder_image_optimizer_download_zip_serves_saved_zip():
    run_id = "b" * 32
    FOLDER_IMAGE_OPTIMIZER_ZIP_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = FOLDER_IMAGE_OPTIMIZER_ZIP_DIR / f"optimized-images-{run_id[:8]}.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("icons/hero.webp", b"image")

    app = create_app()
    app.testing = True
    response = app.test_client().get(f"/folder-image-optimizer/download/{run_id}")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/zip")
    with ZipFile(BytesIO(response.data)) as archive:
        assert archive.namelist() == ["icons/hero.webp"]
