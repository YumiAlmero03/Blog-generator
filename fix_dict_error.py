import sys

file_path = 'app/controllers/tool_controller.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Replace .pages with ['pages']
    if '.pages' in line and 'audit_result' in line:
        line = line.replace('audit_result.pages', "audit_result['pages']")
    
    # Replace .status with ['status']
    if '.status' in line and 'page' in line:
        # This is tricky because 'page' might be used elsewhere.
        # In the loop: for page in audit_result['pages']:
        #    if page.status != "checked":
        # We need to check if it's inside the seo_checker_v2 function block
        pass
    
    new_lines.append(line)

# Better to use a targeted replacement for the block
content = "".join(lines)

# Fix 1: audit_result.pages -> audit_result['pages']
content = content.replace('audit_result.pages', "audit_result['pages']")

# Fix 2: page.url -> page['url']
# We need to be careful not to replace all .url. 
# Let's target the specific loop block.

old_loop = """                for page in audit_result.pages:
                    url = page.url
                    if page.status != "checked":
                        all_issues.append({"url": url, "type": "error", "title": "Page unreachable", "fix": "Check server logs or URL"})
                        continue
                    
                    res = page.result
                    for check in res.checks:
                        if check["status"] != "pass":
                            type_str = "error" if check["status"] == "fail" else "warning"
                            all_issues.append({
                                "url": url,
                                "type": type_str,
                                "title": check["name"],
                                "fix": check["recommendation"]
                            })"""

new_loop = """                for page in audit_result['pages']:
                    url = page['url']
                    if page['status'] != "checked":
                        all_issues.append({"url": url, "type": "error", "title": "Page unreachable", "fix": "Check server logs or URL"})
                        continue
                    
                    res = page['result']
                    for check in res['checks']:
                        if check["status"] != "pass":
                            type_str = "error" if check["status"] == "fail" else "warning"
                            all_issues.append({
                                "url": url,
                                "type": type_str,
                                "title": check["name"],
                                "fix": check["recommendation"]
                            })"""

# Since I just changed audit_result.pages to audit_result['pages'], I need to adjust the old_loop match.
old_loop_updated = old_loop.replace('audit_result.pages', "audit_result['pages']")
content = content.replace(old_loop_updated, new_loop)

with open(file_path, 'w') as f:
    f.write(content)
