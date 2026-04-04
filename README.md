# Auto Blog Generator

## Project Overview

This project is an automated blog content generator built in Python. It creates complete, SEO-friendly blog posts ready for WordPress publishing. The system accepts keyword inputs and generates titles, introductions, full articles, and featured images using AI providers. Designed for efficiency, it produces human-sounding content that adheres to Yoast SEO guidelines.

The architecture supports multiple AI providers (Ollama, OpenAI, Gemini) for flexibility in deployment and cost management.

## Requirements

- **Input Handling**: Accept single or multiple keywords (single keyword as default).
- **Output Formats**: Generate WordPress-ready HTML/markdown content.
- **AI Integration**: Modular provider system for easy switching between local (Ollama) and cloud (OpenAI, Gemini) models.
- **Validation**: Built-in checks for content length, SEO compliance, and image guidelines.
- **Extensibility**: Plugin-like structure for adding new generators (e.g., meta descriptions, internal links).

## Features

- Keyword-based content generation (single or multi-keyword support)
- Automated title generation with multiple options
- Introduction generation (≤450 characters, problem-focused)
- Full article generation (~800 words, SEO-optimized)
- Featured image generation (text-free, button-free visuals)
- Yoast-friendly content validation
- Provider abstraction for Ollama, OpenAI, and Gemini
- Command-line interface for easy integration
- Configurable prompts and generation rules

## Content Rules

1. **Introduction**: Must explain the user's problem clearly. Limited to 450 characters or less. Focus on engaging the reader and setting context.
2. **Main Article**: Approximately 800 words. Ensure natural, human-sounding language. Incorporate keywords naturally for SEO.
3. **Overall Tone**: Avoid robotic phrasing. Use varied sentence structures, active voice, and conversational style.
4. **SEO Compliance**: Follow Yoast guidelines – readable structure, keyword density, internal linking suggestions.
5. **Featured Image**: Generated based on the selected title. Must be visual-only (no text overlays or call-to-action buttons).
6. **WordPress Readiness**: Output formatted for direct copy-paste into WordPress editor, including headings, paragraphs, and image placeholders.

## Planned Workflow

1. **Input Collection**: User provides one or more keywords via CLI.
2. **Title Generation**: System generates 5-10 title variants using the configured AI provider.
3. **Title Selection**: User selects preferred title (or system auto-selects based on criteria).
4. **Introduction Generation**: Create a concise intro explaining the problem (≤450 chars).
5. **Article Generation**: Produce the full ~800-word article with SEO optimization.
6. **Image Generation**: Generate or prompt for a featured image based on the title.
7. **Validation & Formatting**: Check content against rules, format for WordPress.
8. **Output**: Display or save the complete blog post package.

## Future Improvements

- **Provider Extensions**: Add support for more AI services (e.g., Anthropic Claude, local models via transformers).
- **Advanced Validation**: Integrate Yoast API or similar for real-time SEO scoring.
- **WordPress Integration**: Direct publishing to WordPress via API.
- **Content Enhancement**: Add meta descriptions, alt text generation, internal/external linking.
- **Multi-language Support**: Generate content in multiple languages.
- **Batch Processing**: Handle multiple keywords/topics in a single run.
- **UI/UX**: Web interface or GUI for non-technical users.
- **Analytics**: Track generation success rates, SEO performance post-publishing.

### generators/title_generator.py
Contains the `generate_titles` function, which orchestrates title generation. Builds the prompt, calls the provider's `generate_json` method, parses the JSON response, and returns a list of titles.

## Dependencies

- `ollama` (for Ollama provider)
- `openai` (for OpenAI provider)
- `google-genai` (for Gemini provider)
- Standard library: `json`, `os`, `abc`

## Notes

- Ensure the selected model supports JSON output format.
- For OpenAI and Gemini, set the appropriate API keys in your environment.
- Titles are generated to be around 45-65 characters for SEO optimization.
MODEL = "gemini-3-flash-preview"

<!-- the plan -->
# Goals

## Project Overview
This project is a simple auto blog generator designed to create blog content that is easy to publish on WordPress. It should support title generation, introduction generation, full article generation, and featured image generation while keeping the output SEO-friendly and natural-sounding.

The system should be flexible enough to work with different AI providers such as Ollama, OpenAI, or Gemini.

## Requirements

### Input
- Accept one or multiple keywords
- One keyword is the default input case

### Content Rules
- Generate an introduction that explains the user problem
- The introduction must be 450 characters or less
- Generate a main article of around 800 words
- The article must sound human, natural, and SEO-friendly
- The output must be website-ready and easy to copy directly into WordPress
- The content should aim to follow Yoast-friendly writing rules

### Featured Image Rules
- Generate a featured image based on the selected blog title
- The image must contain no text
- The image must contain no buttons

## Core Features
- Keyword input: single or multiple
- Blog title generation
- Short introduction generation
- Full article generation
- Featured image generation
- Yoast-friendly content checks
- Provider-based model architecture for Ollama, OpenAI, and Gemini

## Planned Workflow
1. User enters one or more keywords
2. System generates multiple blog title options
3. User selects a preferred title
4. System generates a short introduction that explains the problem in 450 characters or less
5. System generates an SEO-friendly article of around 800 words
6. System formats the output so it is easy to paste into WordPress
7. System generates a featured image prompt or image based on the title
8. System validates the content against basic Yoast-friendly rules

## Yoast-Friendly Goals
The generated content should aim to follow these guidelines:
- Clear and readable structure
- Natural keyword placement
- Introduction includes the topic naturally
- Reasonable paragraph length
- Readable sentence length
- Low passive voice when possible
- Useful headings and subheadings
- Human and non-robotic tone

## Validation Rules
- Warn if introduction exceeds 450 characters
- Warn if the article is far below or above the 800-word target
- Support both single-keyword and multi-keyword input
- Ensure output is WordPress-ready
- Ensure image output avoids text and buttons

## Future Improvements
- Automatic WordPress draft publishing
- Title scoring and ranking
- Regenerate individual sections
- Internal linking suggestions
- Meta title and meta description generation
- Provider switching between Ollama, OpenAI, and Gemini