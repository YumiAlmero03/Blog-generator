import json
import re
from logger import logger


def extract_json_string(raw: str) -> str:
    """Extract a JSON string from raw model output.
    Handles incomplete/truncated JSON by attempting to match braces."""
    if not raw:
        logger.error("Empty response from model.")
        raise ValueError("Empty response from model.")

    cleaned = raw.strip()

    # Remove surrounding code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Try direct parse first
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    # Try to locate the first {...} or [...] block
    brace_start = cleaned.find("{")
    bracket_start = cleaned.find("[")
    start = -1
    if brace_start != -1 and (bracket_start == -1 or brace_start < bracket_start):
        start = brace_start
    elif bracket_start != -1:
        start = bracket_start

    if start != -1:
        candidate = cleaned[start:]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            # Try to repair incomplete JSON by matching braces
            repaired = attempt_repair_json(candidate)
            if repaired:
                try:
                    json.loads(repaired)
                    logger.info("Successfully repaired truncated JSON response")
                    return repaired
                except json.JSONDecodeError:
                    pass

    # Try JSONDecoder raw_decode from the first brace
    decoder = json.JSONDecoder()
    for idx in range(len(cleaned)):
        if cleaned[idx] in '{[':
            try:
                obj, end = decoder.raw_decode(cleaned[idx:])
                return cleaned[idx:idx+end]
            except json.JSONDecodeError:
                continue

    logger.error("Unable to extract JSON from model output. Response length: %d, starts with: %s", 
                 len(raw), raw[:100] if len(raw) > 100 else raw)
    raise ValueError("Unable to extract JSON from model output.")


def attempt_repair_json(candidate: str) -> str:
    """Attempt to repair truncated/incomplete JSON by matching braces and closing strings."""
    if not candidate:
        return None
    
    repaired = candidate.strip()
    
    # Check if we have unclosed quotes (string value)
    # Count unescaped quotes to detect incomplete strings
    quote_count = 0
    escape = False
    for char in repaired:
        if char == '\\' and not escape:
            escape = True
            continue
        if char == '"' and not escape:
            quote_count += 1
        escape = False
    
    # If odd number of quotes, we have an unclosed string
    if quote_count % 2 == 1:
        # Close the unclosed string
        repaired += '"'
    
    # Remove incomplete patterns that indicate truncation
    incomplete_patterns = [
        r',\s*$',  # Trailing comma
        r':\s*$',  # Trailing colon
    ]
    
    for pattern in incomplete_patterns:
        repaired = re.sub(pattern, '', repaired)
    
    # Count opening and closing braces/brackets
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    
    # Add missing closing brackets/braces
    if open_braces > 0:
        repaired += "}" * open_braces
    if open_brackets > 0:
        repaired += "]" * open_brackets
    
    return repaired if repaired != candidate else None
