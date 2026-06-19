from app.services.content_quality_service import analyze_generated_content, repeated_content_issue


def test_analyze_generated_content_counts_basic_html():
    report = analyze_generated_content(
        """
        <h1>Sample Page</h1>
        <h2>Overview</h2>
        <p>This sample keyword content has enough structure for a quick report.</p>
        <p>It includes a <a href='https://example.com'>sample link</a>.</p>
        """,
        keyword="sample keyword",
        meta_description="A useful sample meta description for testing content quality checks.",
        min_words=5,
        max_words=50,
    )

    assert report["word_count"] >= 10
    assert report["h1_count"] == 1
    assert report["h2_count"] == 1
    assert report["link_count"] == 1
    assert report["keyword_count"] == 1
    assert any(check["name"] == "Word count" for check in report["checks"])


def test_analyze_generated_content_checks_required_url_once():
    report = analyze_generated_content(
        "<p>Read more at <a href='https://example.com'>this guide</a>.</p>",
        required_url="https://example.com",
    )

    link_check = next(check for check in report["checks"] if check["name"] == "Links")
    assert "required URL appears 1 time" in link_check["detail"]


def test_repeated_content_issue_detects_duplicate_sentence_and_report_check():
    repeated = "This paragraph explains a detailed idea with enough words to count as a meaningful repeated sentence."
    content = f"<p>{repeated}</p><p>{repeated}</p>"

    assert "Repeated paragraph" in repeated_content_issue(content)

    report = analyze_generated_content(content)
    repeat_check = next(check for check in report["checks"] if check["name"] == "Repeated content")
    assert repeat_check["status"] == "fail"
