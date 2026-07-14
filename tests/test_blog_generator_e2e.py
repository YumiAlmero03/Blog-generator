import json

from generators.content_generator import generate_content
from generators.meta_description_generator import generate_meta_descriptions
from generators.title_generator import generate_titles


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("FakeProvider ran out of responses")
        return json.dumps(self.responses.pop(0))


def test_blog_generator_retries_filters_and_returns_complete_blog():
    valid_meta = (
        "Learn how modern gaming platforms improve account safety, player trust, and usability with clear design choices that help users."
    )
    complete_content = _html_article(95)
    provider = FakeProvider(
        [
            {"titles": ["Guaranteed Gaming Platform Safety Tips"]},
            {"titles": ["How Gaming Platforms Improve Account Safety"]},
            {
                "meta_descriptions": [
                    {"text": "Too short"},
                    {"text": "Guaranteed access tips for gaming platforms with enough words to trigger the banned word filter in validation."},
                    {"text": valid_meta},
                ]
            },
            {"content": "<p>Too short for the configured article length.</p>", "word_count": 7},
            {"content": complete_content, "word_count": 95},
        ]
    )
    progress_messages = []

    titles = generate_titles(
        provider,
        keyword="gaming platform safety",
        supporting_keyword="account protection",
        count=1,
        progress_callback=progress_messages.append,
    )
    meta_descriptions = generate_meta_descriptions(
        provider,
        title=titles[0],
        keyword="gaming platform safety",
        count=3,
        progress_callback=progress_messages.append,
    )
    content = generate_content(
        provider,
        title=titles[0],
        keyword="gaming platform safety",
        supporting_keyword="account protection",
        suggested_h2s="Account Protection Basics\nSafer Session Habits",
        min_words=80,
        max_words=130,
        progress_callback=progress_messages.append,
    )

    assert titles == ["How Gaming Platforms Improve Account Safety"]
    assert meta_descriptions == [{"text": valid_meta, "character_count": len(valid_meta)}]
    assert content == complete_content
    assert len(provider.prompts) == 5
    assert "IMPORTANT RETRY REQUIREMENT" in provider.prompts[1]
    assert "IMPORTANT RETRY REQUIREMENT" in provider.prompts[4]
    assert "valid HTML content" not in provider.prompts[4]
    assert "Suggested H2 headings from the user" in provider.prompts[3]
    assert "Account Protection Basics" in provider.prompts[3]
    assert "Safer Session Habits" in provider.prompts[3]
    assert any("Title attempt 1" in message and "banned terms" in message for message in progress_messages)
    assert any("Meta attempt 1" in message and "ignored descriptions" in message for message in progress_messages)
    assert any("Content attempt 1" in message and "minimum is 80" in message for message in progress_messages)
    assert provider.responses == []


def _html_article(target_words):
    sentence_templates = [
        "Modern game platforms use careful account design to help players understand choices and manage sessions with less confusion.",
        "Clear menus, plain alerts, privacy controls, and practical reminders support safer habits during everyday play.",
        "Teams can explain settings, payment checks, device access, and recovery steps without turning the article into promotion.",
        "Helpful guidance gives readers examples they can compare with their own digital routines and preferences.",
    ]
    repeated_words = []
    cycle = 1
    while len(repeated_words) < target_words:
        for sentence in sentence_templates:
            varied_sentence = sentence.replace(".", f" for scenario {cycle}.")
            repeated_words.extend(varied_sentence.split())
            cycle += 1
    article_words = repeated_words[: max(1, target_words - 2)]
    midpoint = max(1, len(article_words) // 2)
    intro_text = " ".join(article_words[:midpoint])
    body_text = " ".join(article_words[midpoint:])
    return f"<p>{intro_text}</p><h2>Safety Basics</h2><p>{body_text}</p>"
