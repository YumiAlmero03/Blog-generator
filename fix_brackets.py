import re

file_path = "app/controllers/tool_controller.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Target: ... {link['text'] or link['image_alt'] or 'No anchor text'] } ...
# Fix: ... {link['text'] or link['image_alt'] or 'No anchor text'} ...

content = content.replace("link['text'] or link['image_alt'] or 'No anchor text']}", "link['text'] or link['image_alt'] or 'No anchor text'}")

with open(file_path, "w") as f:
    f.write(content)
