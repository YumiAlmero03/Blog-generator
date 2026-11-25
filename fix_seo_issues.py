import sys

file_path = 'app/controllers/tool_controller.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
for i in range(len(lines)):
    line = lines[i]
    # Fix the issue type for 404s from "404" to "error"
    if ' "type": "404", ' in line:
        line = line.replace(' "type": "404", ', ' "type": "error", ')
    
    # Inject link_health_details into the result dictionary for issues mode
    if ' "mode": "issues", ' in line:
        # We need to make sure we add the link_health_details.
        # The current block is:
        # state["result"] = {
        #     "mode": "issues",
        #     "issues": all_issues
        # }
        # We want:
        # state["result"] = {
        #     "mode": "issues",
        #     "issues": all_issues,
        #     "link_health_details": _site_link_health_details(audit_result.pages)
        # }
        
        # To be safe and avoid complex index logic, I'll replace the block.
        # But since I'm iterating, I'll just modify the current line and the next.
        pass

    new_lines.append(line)

# Because the replacement of the dictionary is multi-line, it's easier to use a string replace on the whole content
content = "".join(lines)
old_block = """                state["result"] = {
                    "mode": "issues",
                    "issues": all_issues
                }"""
new_block = """                state["result"] = {
                    "mode": "issues",
                    "issues": all_issues,
                    "link_health_details": _site_link_health_details(audit_result.pages)
                }"""
content = content.replace(old_block, new_block)

# Now apply the "404" -> "error" fix to the whole content
content = content.replace(' "type": "404", ', ' "type": "error", ')

with open(file_path, 'w') as f:
    f.write(content)
