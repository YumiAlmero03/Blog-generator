import json
import re

from logger import logger
from prompts import build_social_media_post_prompt
from prompts.shared import build_language_instruction
from utils import extract_json_string
from word_bank import find_banned_terms_in_text


MAX_SOCIAL_POST_CHARACTERS = 1000
MAX_BLOG_MEDIUM_CHARACTERS = 6000
SOCIAL_POST_CHARACTER_LIMITS = {
    "facebook": 63206,
    "instagram": 2200,
    "linkedin": 3000,
    "pinterest": 500,
    "tiktok": 4000,
    "twitter": 280,
    "twitter/x": 280,
    "x": 280,
    "x/twitter": 280,
    "youtube": 5000,
    "wordpress": 6000,
    "blogger": 6000,
    "tumblr": 6000,
}
BLOG_MEDIUM_TYPES = {"wordpress", "blogger", "tumblr"}
GAMBLING_RELATED_TERMS = (
    "slot",
    "slots",
    "casino",
    "casinos",
    "gambling",
    "gamble",
    "bet",
    "bets",
    "betting",
    "wager",
    "wagering",
    "jackpot",
    "poker",
    "roulette",
    "blackjack",
    "sportsbook",
    "lottery",
    "bingo",
)


def generate_social_media_post(
    provider,
    focus_word: str,
    brand_name: str,
    social_type: str,
    brand_context: str = "",
    reference_link: str = "",
    research_context: str = "",
    max_characters: int | None = None,
    progress_callback=None,
) -> dict:
    max_characters = int(max_characters or get_social_post_character_limit(social_type))
    prompt = build_social_media_post_prompt(
        focus_word=focus_word,
        brand_name=brand_name,
        social_type=social_type,
        brand_context=brand_context,
        reference_link=reference_link,
        research_context=research_context,
        max_characters=max_characters,
    )
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- The post_content must be {max_characters} characters or fewer for {social_type}.\n"
                "- Choose one allowed random topic category: technical, sports, video games, or non-gambling online games.\n"
                "- Avoid every term in the forbidden word bank from the original prompt.\n"
                "- Do not use slot, casino, gambling, betting, jackpot, wager, poker, roulette, sportsbook, lottery, or related terms anywhere.\n"
                "- Return fresh valid JSON only.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)
        try:
            data = json.loads(extract_json_string(raw))
            post_content = str(data.get("post_content", "")).strip()
            image_description = str(data.get("image_description", "")).strip()
            tags = data.get("tags", [])
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            tags = [str(tag).strip() for tag in tags if str(tag).strip()]

            if len(post_content) > max_characters:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: post has {len(post_content)} characters, maximum is {max_characters}. Retrying...",
                )
                logger.warning(
                    "Social media post exceeded %d characters on attempt %d: %d",
                    max_characters,
                    attempt,
                    len(post_content),
                )
                continue

            restricted_terms = _find_gambling_related_terms(
                " ".join([post_content, image_description, " ".join(tags)])
            )
            banned_terms = find_banned_terms_in_text(
                " ".join([post_content, image_description, " ".join(tags)])
            )
            if restricted_terms:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: restricted terms found ({', '.join(restricted_terms)}). Retrying...",
                )
                logger.warning(
                    "Social media post used restricted terms %s on attempt %d",
                    ", ".join(restricted_terms),
                    attempt,
                )
                continue
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Social media post used banned terms %s on attempt %d",
                    ", ".join(banned_terms),
                    attempt,
                )
                continue

            return {
                "post_content": post_content,
                "image_description": image_description,
                "tags": tags[:8],
                "character_count": len(post_content),
                "character_limit": max_characters,
            }
        except Exception as exc:
            logger.exception("generate_social_media_post failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(f"Generated social media post could not satisfy the {max_characters} character limit.")


def get_social_post_character_limit(social_type: str) -> int:
    cleaned = (social_type or "").strip().lower()
    platform_limit = SOCIAL_POST_CHARACTER_LIMITS.get(cleaned)
    if platform_limit is None:
        for key, value in SOCIAL_POST_CHARACTER_LIMITS.items():
            if key and key in cleaned:
                platform_limit = value
                break
    if platform_limit is None:
        platform_limit = MAX_SOCIAL_POST_CHARACTERS
    if cleaned in BLOG_MEDIUM_TYPES:
        return min(platform_limit, MAX_BLOG_MEDIUM_CHARACTERS)
    return min(platform_limit, MAX_SOCIAL_POST_CHARACTERS)


def generate_neutral_blog_article(
    provider,
    topic: str,
    medium: dict,
    suggested_content: str = "",
    language: str = "English",
    progress_callback=None,
) -> dict:
    from app.services.content_format_service import markdown_to_html

    _publish_progress(progress_callback, "Generating neutral title...")
    title = generate_neutral_blog_title(
        provider,
        topic=topic,
        suggested_content=suggested_content,
        medium=medium,
        language=language,
        progress_callback=progress_callback,
    )
    _publish_progress(progress_callback, "Title passed validation. Generating meta description...")
    meta_description = generate_neutral_blog_meta_description(
        provider,
        title=title,
        topic=topic,
        suggested_content=suggested_content,
        medium=medium,
        language=language,
        progress_callback=progress_callback,
    )
    _publish_progress(progress_callback, "Meta description passed validation. Generating 2 visual ideas...")
    visual = "\n\n".join(
        generate_neutral_blog_visuals(
            provider,
            title=title,
            topic=topic,
            suggested_content=suggested_content,
            medium=medium,
            language=language,
            progress_callback=progress_callback,
        )
    )
    _publish_progress(progress_callback, "Visual ideas passed validation. Generating content...")
    content_result = generate_neutral_blog_content(
        provider,
        title=title,
        topic=topic,
        suggested_content=suggested_content,
        medium=medium,
        meta_description=meta_description,
        visual=visual,
        language=language,
        progress_callback=progress_callback,
    )
    _publish_progress(progress_callback, "Content passed validation. Generating tags...")
    tags = generate_neutral_blog_tags(
        provider,
        title=title,
        topic=topic,
        suggested_content=suggested_content,
        medium=medium,
        content=content_result["markdown_content"],
        language=language,
        progress_callback=progress_callback,
    )
    _publish_progress(progress_callback, "Tags passed validation.")

    return {
        "title": title,
        "meta_description": meta_description,
        "visual": visual,
        "tags": tags,
        "reference_links": content_result["reference_links"],
        "content": markdown_to_html(content_result["markdown_content"]),
        "markdown_content": content_result["markdown_content"],
        "word_count": content_result["word_count"],
    }


def generate_neutral_blog_title(provider, topic: str, medium: dict, suggested_content: str = "", language: str = "English", progress_callback=None) -> str:
    prompt = _build_neutral_blog_title_prompt(topic=topic, suggested_content=suggested_content, medium=medium, language=language)
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Return fresh valid JSON only.\n"
                "- Provide one clean title that avoids banned and restricted gambling terms.\n"
                "- Respect the medium title character limit when supplied.\n"
            )

        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
            title = str(data.get("title", "")).strip()
        except Exception as exc:
            logger.exception("generate_neutral_blog_title failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

        title_max = _int_or_zero(medium.get("title_max_characters", 0))
        restricted_terms = _find_gambling_related_terms(title)
        banned_terms = find_banned_terms_in_text(title)
        if not title:
            _publish_progress(progress_callback, f"Neutral title attempt {attempt}: missing title. Retrying...")
            continue
        if title_max and len(title) > title_max:
            _publish_progress(
                progress_callback,
                f"Neutral title attempt {attempt}: {len(title)} characters, maximum is {title_max}. Retrying...",
            )
            continue
        if restricted_terms or banned_terms:
            found = restricted_terms or banned_terms
            _publish_progress(
                progress_callback,
                f"Neutral title attempt {attempt}: restricted terms found ({', '.join(found)}). Retrying...",
            )
            logger.warning("Neutral title used restricted terms %s on attempt %d", ", ".join(found), attempt)
            continue
        return title


def generate_neutral_blog_meta_description(provider, title: str, topic: str, medium: dict, suggested_content: str = "", language: str = "English", progress_callback=None) -> str:
    prompt = _build_neutral_blog_meta_prompt(title=title, topic=topic, suggested_content=suggested_content, medium=medium, language=language)
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Return fresh valid JSON only.\n"
                "- Meta description must be 130-160 characters.\n"
                "- Use the selected title as context and avoid banned or restricted terms.\n"
            )

        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
            meta_description = str(data.get("meta_description", "")).strip()
        except Exception as exc:
            logger.exception("generate_neutral_blog_meta_description failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

        restricted_terms = _find_gambling_related_terms(meta_description)
        banned_terms = find_banned_terms_in_text(meta_description)
        if not 10 <= len(meta_description) <= 140:
            _publish_progress(
                progress_callback,
                f"Neutral meta attempt {attempt}: {len(meta_description)} characters, target is 130-160. Retrying...",
            )
            continue
        if restricted_terms or banned_terms:
            found = restricted_terms or banned_terms
            _publish_progress(
                progress_callback,
                f"Neutral meta attempt {attempt}: restricted terms found ({', '.join(found)}). Retrying...",
            )
            logger.warning("Neutral meta used restricted terms %s on attempt %d", ", ".join(found), attempt)
            continue
        return meta_description


def generate_neutral_blog_visuals(provider, title: str, topic: str, medium: dict, suggested_content: str = "", language: str = "English", progress_callback=None) -> list[str]:
    prompt = _build_neutral_blog_visual_prompt(title=title, topic=topic, suggested_content=suggested_content, medium=medium, language=language)
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Return fresh valid JSON only.\n"
                "- Return exactly 2 usable visual ideas.\n"
                "- Use the selected title as context and avoid banned or restricted imagery.\n"
            )

        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
            visuals = data.get("visuals", [])
            if isinstance(visuals, str):
                visuals = [visuals]
            cleaned = [str(item).strip() for item in visuals if str(item).strip()]
        except Exception as exc:
            logger.exception("generate_neutral_blog_visuals failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

        combined = " ".join(cleaned)
        restricted_terms = _find_gambling_related_terms(combined)
        banned_terms = find_banned_terms_in_text(combined)
        if len(cleaned) < 2:
            _publish_progress(
                progress_callback,
                f"Neutral visual attempt {attempt}: returned {len(cleaned)} idea(s), need 2. Retrying...",
            )
            continue
        if restricted_terms or banned_terms:
            found = restricted_terms or banned_terms
            _publish_progress(
                progress_callback,
                f"Neutral visual attempt {attempt}: restricted terms found ({', '.join(found)}). Retrying...",
            )
            logger.warning("Neutral visuals used restricted terms %s on attempt %d", ", ".join(found), attempt)
            continue
        return cleaned[:2]


def generate_neutral_blog_content(
    provider,
    title: str,
    topic: str,
    medium: dict,
    meta_description: str,
    visual: str,
    suggested_content: str = "",
    language: str = "English",
    progress_callback=None,
) -> dict:
    min_words = _int_or_zero(medium.get("min_words", 0))
    max_words = _int_or_zero(medium.get("max_characters", 0))
    prompt_min_words = min_words + 100 if min_words else 0
    prompt = _build_neutral_blog_content_prompt(
        title=title,
        topic=topic,
        suggested_content=suggested_content,
        medium=medium,
        meta_description=meta_description,
        visual=visual,
        min_words=prompt_min_words,
        max_words=max_words,
        language=language,
    )
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Return fresh valid JSON only.\n"
                "- Respect the medium word limits.\n"
                "- Avoid banned words and restricted gambling terms.\n"
                "- Include complete article content in Markdown source.\n"
                "- If you provide reference_links, every reference URL must also appear naturally inside the content using Markdown links.\n"
                "- Spread reference links across relevant paragraphs or sections. Do not place them all together in a references list.\n"
            )
            if min_words:
                retry_instruction += f"- The article must be at least {min_words} words.\n"
            if max_words:
                retry_instruction += f"- Keep the article close to {max_words} words when possible.\n"

        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
        except Exception as exc:
            logger.exception("generate_neutral_blog_content failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

        markdown_content = str(data.get("content", "")).strip()
        reference_links = _clean_reference_links(data.get("reference_links", []))
        reference_error = _reference_link_presence_error(markdown_content, reference_links)
        if reference_error:
            _publish_progress(
                progress_callback,
                f"Neutral blog attempt {attempt}: {reference_error} Retrying...",
            )
            logger.warning("Neutral blog reference link validation failed on attempt %d: %s", attempt, reference_error)
            continue

        combined = " ".join([title, meta_description, visual, markdown_content])
        restricted_terms = _find_gambling_related_terms(combined)
        banned_terms = find_banned_terms_in_text(combined)
        if restricted_terms or banned_terms:
            found = restricted_terms or banned_terms
            _publish_progress(
                progress_callback,
                f"Neutral blog attempt {attempt}: restricted terms found ({', '.join(found)}). Retrying...",
            )
            logger.warning("Neutral blog used restricted terms %s on attempt %d", ", ".join(found), attempt)
            continue

        word_count = _count_markdown_words(markdown_content)
        if min_words and word_count < min_words:
            _publish_progress(
                progress_callback,
                f"Neutral blog attempt {attempt}: {word_count} words, minimum is {min_words}. Retrying...",
            )
            logger.warning("Neutral blog was too short on attempt %d: %d words", attempt, word_count)
            continue
        if max_words and word_count > max_words + 120:
            _publish_progress(
                progress_callback,
                f"Neutral blog attempt {attempt}: {word_count} words, target max is {max_words}. Retrying...",
            )
            logger.warning("Neutral blog was too long on attempt %d: %d words", attempt, word_count)
            continue

        return {
            "reference_links": reference_links,
            "markdown_content": markdown_content,
            "word_count": word_count,
        }


def generate_neutral_blog_tags(provider, title: str, topic: str, medium: dict, content: str, suggested_content: str = "", language: str = "English", progress_callback=None) -> list[str]:
    prompt = _build_neutral_blog_tags_prompt(title=title, topic=topic, suggested_content=suggested_content, medium=medium, content=content, language=language)
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Return fresh valid JSON only.\n"
                "- Return 8-12 clean tags.\n"
                "- Use the selected title and generated content as context.\n"
                "- Avoid banned or restricted terms.\n"
            )

        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
            tags = _clean_tags(data.get("tags", []))
        except Exception as exc:
            logger.exception("generate_neutral_blog_tags failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

        combined = " ".join(tags)
        restricted_terms = _find_gambling_related_terms(combined)
        banned_terms = find_banned_terms_in_text(combined)
        if len(tags) < 3:
            _publish_progress(progress_callback, f"Neutral tags attempt {attempt}: returned too few tags. Retrying...")
            continue
        if restricted_terms or banned_terms:
            found = restricted_terms or banned_terms
            _publish_progress(
                progress_callback,
                f"Neutral tags attempt {attempt}: restricted terms found ({', '.join(found)}). Retrying...",
            )
            logger.warning("Neutral tags used restricted terms %s on attempt %d", ", ".join(found), attempt)
            continue
        return tags


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("generation progress callback failed")


def _neutral_medium_prompt_context(topic: str, medium: dict) -> dict:
    return {
        "medium_name": medium.get("website_name", ""),
        "publication": medium.get("blog_name", "") or medium.get("account_name", ""),
        "website_type": (medium.get("website_type", "") or "blog").replace("_", " "),
        "post_type": medium.get("post_type", "html") or "html",
        "title_max": _int_or_zero(medium.get("title_max_characters", 0)),
        "rules": medium.get("content_guidelines", ""),
        "topic": (topic or "").strip() or "Choose a random topic from technology, sports, video games, or non-gambling online games.",
    }


def _banned_words_prompt_section() -> str:
    try:
        from word_bank import build_banned_words_prompt_section

        return build_banned_words_prompt_section()
    except Exception:
        return ""


def _suggestion_prompt_section(suggested_content: str) -> str:
    cleaned = (suggested_content or "").strip()
    if not cleaned:
        return ""
    return f"""
User suggestion:
{cleaned}

Use this suggestion as optional direction for angle, facts, points, or style when it fits the neutral topic and medium rules. Keep the final output original and editorial.
"""


def _build_neutral_blog_title_prompt(topic: str, medium: dict, suggested_content: str = "", language: str = "English") -> str:
    context = _neutral_medium_prompt_context(topic, medium)
    language_section = build_language_instruction(language)
    title_rule = (
        f"- Keep the title under {context['title_max']} characters."
        if context["title_max"]
        else "- Keep the title concise and natural."
    )
    return f"""
You are creating a neutral editorial title for a publishing medium.

Topic:
{context["topic"]}

{_suggestion_prompt_section(suggested_content)}

Publishing medium:
- Medium name: {context["medium_name"]}
- Publication/account: {context["publication"]}
- Medium type: {context["website_type"]}
- Preferred post type: {context["post_type"]}
- Medium rules: {context["rules"]}

{language_section}
{_banned_words_prompt_section()}

Rules:
- Return valid JSON only.
- Create one neutral title.
{title_rule}
- Do not include a target, brand, money-site, or required promotional link.
- Do not create gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused content.
- If the topic suggests those areas, reframe toward neutral product design, digital safety, UX, technology, entertainment, or responsible play.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "title": "Generated title"
}}
"""


def _build_neutral_blog_meta_prompt(title: str, topic: str, medium: dict, suggested_content: str = "", language: str = "English") -> str:
    context = _neutral_medium_prompt_context(topic, medium)
    language_section = build_language_instruction(language)
    return f"""
You are writing a meta description for a neutral editorial blog/post.

Selected title:
{title}

Topic:
{context["topic"]}

{_suggestion_prompt_section(suggested_content)}

Publishing medium:
- Medium name: {context["medium_name"]}
- Publication/account: {context["publication"]}
- Medium type: {context["website_type"]}
- Medium rules: {context["rules"]}

{language_section}
{_banned_words_prompt_section()}

Rules:
- Return valid JSON only.
- Use the selected title as the anchor context.
- Write exactly one meta description.
- Meta description must be 130-160 characters.
- Keep it neutral, editorial, and natural.
- Do not include a target, brand, money-site, or required promotional link.
- Avoid gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused terms.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "meta_description": "130 to 160 character meta description."
}}
"""


def _build_neutral_blog_visual_prompt(title: str, topic: str, medium: dict, suggested_content: str = "", language: str = "English") -> str:
    context = _neutral_medium_prompt_context(topic, medium)
    language_section = build_language_instruction(language)
    return f"""
You are creating image directions for a neutral editorial blog/post.

Selected title:
{title}

Topic:
{context["topic"]}

{_suggestion_prompt_section(suggested_content)}

Publishing medium:
- Medium name: {context["medium_name"]}
- Publication/account: {context["publication"]}
- Medium type: {context["website_type"]}
- Medium rules: {context["rules"]}

{language_section}
{_banned_words_prompt_section()}

Rules:
- Return valid JSON only.
- Generate exactly 2 distinct visual or image descriptions.
- Use the selected title as the anchor for both visual ideas.
- Make each idea useful for a designer, AI image tool, or publisher selecting a featured image.
- Keep each idea to 1-2 sentences.
- Keep the ideas neutral and editorial, not promotional.
- Do not include text overlays, logos, watermarks, brand marks, or UI screenshots unless the article specifically requires them.
- Avoid gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused imagery.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "visuals": ["First clear image or visual idea for the post.", "Second clear image or visual idea for the post."]
}}
"""


def _build_neutral_blog_content_prompt(
    title: str,
    topic: str,
    medium: dict,
    meta_description: str,
    visual: str,
    min_words: int,
    max_words: int,
    suggested_content: str = "",
    language: str = "English",
) -> str:
    context = _neutral_medium_prompt_context(topic, medium)
    language_section = build_language_instruction(language)
    word_rule = "- Write a complete article."
    if min_words and max_words:
        word_rule = f"- Write at least {min_words} words and keep the article near {max_words} words where possible."
    elif min_words:
        word_rule = f"- Write at least {min_words} words."
    elif max_words:
        word_rule = f"- Keep the post near {max_words} words where possible."

    return f"""
You are a neutral editorial writer creating content for a publishing medium.

Create the article content for the selected title. The title, meta description, and visual ideas are already approved; use them as fixed context.

Selected title:
{title}

Topic:
{context["topic"]}

{_suggestion_prompt_section(suggested_content)}

Approved meta description:
{meta_description}

Approved visual ideas:
{visual}

Publishing medium:
- Medium name: {context["medium_name"]}
- Publication/account: {context["publication"]}
- Medium type: {context["website_type"]}
- Preferred post type: {context["post_type"]}
- Medium rules: {context["rules"]}

{language_section}
{_banned_words_prompt_section()}

Rules:
- Return valid JSON only.
- Do not include a target, brand, money-site, or required promotional link.
- Use reference links only as supporting editorial sources.
- Include 2-3 reference links in the article when reliable real source URLs are known or available.
- Put those same references in the reference_links array.
- Every URL in reference_links must also appear inside the content value as a Markdown link.
- Spread reference links naturally across the article where they support the nearby claim or explanation.
- Do not group all reference links in one paragraph, one bullet list, a "References" section, or at the very end.
- Use descriptive anchor text for each reference link, not raw URLs as the visible link text.
- Use this Markdown link format inside content: [descriptive source phrase](https://real-source-url).
- Never invent fake URLs, placeholder URLs, or example.com URLs.
- If you cannot verify a real URL, omit that reference link and write the article from general knowledge.
- Do not create gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused content.
- If the topic suggests those areas, reframe toward neutral product design, digital safety, UX, technology, entertainment, or responsible play.
{word_rule}
- Write content in Markdown source.
- Use Markdown headings, compact paragraphs, and lists when helpful.
- Do not use raw HTML in content.
- Match the structure to the selected medium type. Social mediums should be shorter and punchier; blog mediums can be fuller.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "reference_links": [
    {{"title": "Source title", "url": "https://real-source.example/path"}}
  ],
  "content": "Markdown article content with reference links spread naturally across relevant sections"
}}
"""


def _build_neutral_blog_tags_prompt(title: str, topic: str, medium: dict, content: str, suggested_content: str = "", language: str = "English") -> str:
    context = _neutral_medium_prompt_context(topic, medium)
    language_section = build_language_instruction(language)
    return f"""
Create publishing tags for a neutral editorial blog/post.

Selected title:
{title}

Topic:
{context["topic"]}

{_suggestion_prompt_section(suggested_content)}

Publishing medium:
- Medium name: {context["medium_name"]}
- Publication/account: {context["publication"]}
- Medium type: {context["website_type"]}
- Medium rules: {context["rules"]}

{language_section}
Generated content:
{(content or "")[:6000]}

{_banned_words_prompt_section()}

Rules:
- Return valid JSON only.
- Use the selected title as the main context.
- Return 8-12 short tags.
- Keep tags natural, useful for publishing, and lower case when possible.
- Avoid duplicate tags, banned terms, promotional hype, and generic filler.
- Do not include gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused terms.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "tags": ["tag one", "tag two"]
}}
"""


def _clean_tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",")]
    if not isinstance(tags, list):
        return []
    cleaned = []
    for tag in tags:
        value = str(tag).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[:12]


def _clean_reference_links(reference_links) -> list[dict]:
    if not isinstance(reference_links, list):
        return []
    cleaned = []
    for item in reference_links:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title or not re.match(r"^https?://", url):
            continue
        if "example.com" in url.lower():
            continue
        cleaned.append({"title": title, "url": url})
    return cleaned[:3]


def _reference_link_presence_error(markdown_content: str, reference_links: list[dict]) -> str:
    if not reference_links:
        return ""
    content = markdown_content or ""
    missing = [
        item["url"]
        for item in reference_links
        if item.get("url") and item["url"] not in content
    ]
    if missing:
        return "Reference URLs were listed but not placed inside the article content."

    positions = sorted(content.find(item["url"]) for item in reference_links if item.get("url"))
    if len(positions) >= 2 and positions[-1] - positions[0] < 200:
        return "Reference links are too close together; spread them naturally across the article."
    return ""


def _count_markdown_words(markdown: str) -> int:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", markdown or "")
    text = re.sub(r"[#*_>`~-]+", " ", text)
    return len(re.findall(r"\b[\w'-]+\b", text))


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _find_gambling_related_terms(text: str) -> list[str]:
    lowered = f" {text or ''} ".lower()
    found = []
    for term in GAMBLING_RELATED_TERMS:
        if f" {term} " in lowered or f"#{term}" in lowered:
            found.append(term)
    return found
