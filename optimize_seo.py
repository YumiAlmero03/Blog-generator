import re

file_path = "app/controllers/tool_controller.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_func = """def seo_checker_v2():
    checker_version = "v2"
    state = {
        "url": "",
        "ignore_ssl_errors": False,
        "allow_private_urls": False,
        "use_ai": False,
        "check_google_issues": False,
        "limit": 10,
        "result": None,
        "history": list_seo_check_history(checker_version=checker_version),
        "previous_check": None,
        "comparison": None,
        "loaded_history": None,
        "error": None,
        "generation_log": [],
        "generation_log_json": "[]",
    }

    history_id = request.args.get("history_id", "").strip()
    
    if history_id and request.method == "GET":
        try:
            snapshot = get_seo_check_history_result(int(history_id), checker_version=checker_version)
        except ValueError:
            snapshot = None
            
        if snapshot:
            state["loaded_history"] = snapshot
            state["result"] = snapshot["result"]
            state["url"] = snapshot.get("source_url", "") or state["result"].get("source_url", "")
            state["limit"] = int(snapshot.get("page_limit", 0) or state["result"].get("limit", 10) or 10)
            state["use_ai"] = bool(state["result"].get("use_ai", True))
            state["check_google_issues"] = bool(state["result"].get("check_google_issues", False))
            
            state["previous_check"] = get_previous_seo_check_history(
                state["result"].get("base_url", ""),
                snapshot["id"],
                checker_version=checker_version,
            )
            state["comparison"] = _seo_history_comparison(state["result"], state["previous_check"])
            
            state["history"] = list_seo_check_history(
                checker_version=checker_version,
                base_url=state["result"].get("base_url", ""),
            )
        else:
            state["error"] = "The saved V2 report could not be found or its JSON data is invalid."

    if request.method == "POST":
        state["url"] = request.form.get("url", "").strip()
        state["ignore_ssl_errors"] = request.form.get("ignore_ssl_errors") == "1"
        state["allow_private_urls"] = request.form.get("allow_private_urls") == "1" or _is_local_dev_url(state["url"])
        state["use_ai"] = request.form.get("use_ai") == "1"
        state["check_google_issues"] = request.form.get("check_google_issues") == "1"
        state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
        state["generation_log_json"] = generation_log_json(state["generation_log"])
        try:
            state["limit"] = max(1, min(100, int(request.form.get("limit", "10"))))
        except ValueError:
            state["limit"] = 10
        
        action = request.form.get("action", "check")
        
        try:
            if action == "check":
                progress = _seo_checker_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
                state["result"] = _run_site_seo_checks(
                    state["url"],
                    limit=state["limit"],
                    verify_ssl=not state["ignore_ssl_errors"],
                    allow_private=state["allow_private_urls"],
                    use_ai=state["use_ai"],
                    progress_callback=progress,
                )
                add_google_issues(
                    state["result"], enabled=state["check_google_issues"],
                    access_token=get_setting("google_oauth_access_token", ""),
                    service_account_json=get_setting("google_service_account_json", ""),
                )
                record_seo_check_history(
                    state["url"], 
                    state["result"], 
                    checker_version=checker_version, 
                    page_limit=state["limit"]
                )
            elif action == "issues":
                progress = _seo_checker_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
                audit_result = _run_site_seo_checks(
                    state["url"],
                    limit=state["limit"],
                    verify_ssl=not state["ignore_ssl_errors"],
                    allow_private=state["allow_private_urls"],
                    use_ai=state["use_ai"],
                    progress_callback=progress,
                )
                
                all_issues = []
                for page in audit_result.pages:
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
                            })
                
                for link in audit_result.link_health_details.get("not_found_links", []):
                    all_issues.append({
                        "url": link["source_page"],
                        "type": "404",
                        "title": f"Broken link to {link['url']}",
                        "fix": f"Check anchor text \\\"{link['text'] or link['image_alt'] or 'No anchor text']}\\\" if URL exists"
                    })
                
                state["result"] = {
                    "mode": "issues",
                    "issues": all_issues
                }
            else:
                state["error"] = "Invalid action."
                
        except Exception as exc:
            logger.exception("seo_checker_v2 action failed")
            state["error"] = str(exc) or "SEO Checker V2 action failed."

    return render_template("seo_checker_v2.html", **base_template_context(), **state)
"""

match = re.search(r"def seo_checker_v2\(\):.*?return render_template\(\"seo_checker_v2.html\", \*\*base_template_context\(\), \*\*state\)", content, re.DOTALL)
if match:
    content = content.replace(match.group(0), new_func)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
