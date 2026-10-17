import re

file_path = "app/controllers/tool_controller.py"
with open(file_path, "r") as f:
    content = f.read()

# We are fixing the f-string quote nesting issue.
# Use single quotes for dictionary keys inside f-strings.

# Target 1: f"Broken link to {link["url"]}"
# Replace with: f"Broken link to {link['url']}"
content = content.replace('f"Broken link to {link["url"]}"', "f\"Broken link to {link['url']}\"")

# Target 2: f"Check anchor text "{link["text"] or link["image_alt"] or "No anchor text"}" if URL exists"
# Replace with: f"Check anchor text \"{link['text'] or link['image_alt'] or 'No anchor text'}\" if URL exists"
# Note: The original had "Check anchor text " (double quotes) then {link...} then " if URL exists"
# I will use a regex to be safe.

pattern = r'f"Check anchor text "\{link\["text"\] or link\["image_alt"\] or "No anchor text"\}" if URL exists"'
replacement = 'f"Check anchor text \\"{link[\'text\'] or link[\'image_alt\'] or \'No anchor text\'}\\" if URL exists"'
content = re.sub(pattern, replacement, content)

with open(file_path, "w") as f:
    f.write(content)
