import sys

file_path = 'app/controllers/tool_controller.py'
with open(file_path, 'r') as f:
    content = f.read()

# Fix the issue type for 404s from "404" to "error"
content = content.replace(' "type": "404", ', ' "type": "error", ')

with open(file_path, 'w') as f:
    f.write(content)
