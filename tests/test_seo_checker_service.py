from app.services.seo_checker_service import PageSeoParser


def test_page_seo_parser_collects_core_seo_fields():
    parser = PageSeoParser()
    parser.feed(
        """
        <html>
          <head>
            <title>Example Title</title>
            <meta name="description" content="Example meta description">
            <meta property="og:title" content="Open Graph Title">
            <meta name="twitter:card" content="summary">
            <link rel="canonical" href="https://example.com/page">
          </head>
          <body>
            <h1>Main Heading</h1>
            <h2>Section Heading</h2>
            <img src="/image.jpg">
            <a href="/internal">Internal</a>
          </body>
        </html>
        """
    )

    assert parser.title == "Example Title"
    assert parser.meta_description == "Example meta description"
    assert parser.canonical == "https://example.com/page"
    assert parser.open_graph["og:title"] == "Open Graph Title"
    assert parser.twitter_cards["twitter:card"] == "summary"
    assert len(parser.headings["h1"]) == 1
    assert len(parser.images) == 1
    assert not parser.images[0]["has_alt"]
