# Blog Generator in Python

A simple command-line blog title generator written in Python. It uses various AI providers (Ollama, OpenAI, Gemini) to generate SEO-friendly blog title variants based on a keyword/topic and tone.

## Features

- Generate multiple blog title variants (default: 10)
- Support for multiple AI providers: Ollama (local), OpenAI, and Google Gemini
- Configurable tone (e.g., natural, professional)
- Easy provider switching via configuration
- JSON-based prompt responses for structured output

## Installation

Clone or download the project files. Install dependencies based on the provider you plan to use:

### For Ollama (local)
```bash
pip install ollama
```
Ensure Ollama is running locally with the desired model (e.g., `gemma3:4b`).

### For OpenAI
```bash
pip install openai
```
Set your OpenAI API key as an environment variable.

### For Gemini
```bash
pip install google-genai
```
Set your Gemini API key as an environment variable: `GEMINI_API_KEY`.

## Usage

1. Configure the provider and model in `config.py`.
2. Run the application:
   ```bash
   python main.py
   ```
3. Enter a keyword/topic and optional tone when prompted.
4. The app will output 10 title variants.

Example output:
```
Enter keyword/topic: Python programming
Enter tone (default natural): natural

10 title variants:

1. Master Python Programming: A Beginner's Complete Guide
2. Unlock Python's Power: Tips for Efficient Coding
...
```

## Configuration

Edit `config.py` to switch providers and models:

- **Ollama**:
  ```python
  PROVIDER = "ollama"
  MODEL = "gemma3:4b"
  ```

- **OpenAI**:
  ```python
  PROVIDER = "openai"
  MODEL = "gpt-4o-mini"  # or similar
  ```

- **Gemini**:
  ```python
  PROVIDER = "gemini"
  MODEL = "gemini-1.5-flash"  # or similar
  ```

## File Structure and Descriptions

### main.py
The entry point of the application. Handles user input (keyword and tone), initializes the selected provider, generates titles, and prints the results.

### config.py
Contains configuration constants for the AI provider and model. Allows easy switching between providers without code changes.

### prompts.py
Defines the `build_title_prompt` function, which constructs a detailed prompt for generating blog titles. Includes rules for SEO-friendliness, variety, and JSON output format.

### providers/base.py
Abstract base class defining the common interface for all AI providers. Requires implementing the `generate_json(prompt: str) -> str` method.

### providers/ollama_provider.py
Concrete implementation for Ollama. Uses the `ollama` library to interact with a local Ollama server, requesting JSON-formatted responses.

### providers/openai_provider.py
Concrete implementation for OpenAI. Uses the `openai` library to call the OpenAI API for generating responses.

### providers/gemini_provider.py
Concrete implementation for Google Gemini. Uses the `google-genai` library to interact with the Gemini API, requiring an API key.

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