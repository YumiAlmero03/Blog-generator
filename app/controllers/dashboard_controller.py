import json
import re
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Response, abort, redirect, render_template, request, url_for

from database import (
    delete_generation_history_item,
    generation_dashboard_stats,
    get_generation_history_item,
    list_generation_history,
    list_generation_history_medium_names,
    mark_generation_history_draft,
    update_generation_history_post_link,
)

from app.controllers.helpers import base_template_context


def dashboard():
    stats = generation_dashboard_stats()
    return render_template("dashboard.html", **base_template_context(), stats=stats)


def generation_history():
    filters = _history_filters()
    if request.args.get("export") == "xlsx":
        return _export_generation_history_xlsx(filters)
    return render_template(
        "generation_history.html",
        **base_template_context(),
        filters=filters,
        content_type_options=("Medium Blog", "Tier 2 Blog", "Neutral Post", "Blog", "Page", "Simple Page", "Social Post"),
        medium_options=list_generation_history_medium_names(),
        history_items=list_generation_history(
            200,
            content_type=filters["content_type"],
            status=filters["status"],
            selected_date=filters["date"],
            medium_name=filters["medium"],
            search=filters["search"],
        ),
    )


def _export_generation_history_xlsx(filters: dict):
    rows = list_generation_history(
        10000,
        content_type=filters["content_type"],
        status="saved",
        selected_date=filters["date"],
        medium_name=filters["medium"],
        search=filters["search"],
    )
    workbook = _build_history_workbook(rows)
    filename = "generation-history.xlsx"
    if filters["date"]:
        filename = f"generation-history-{filters['date']}.xlsx"
    return Response(
        workbook,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def delete_generation_history(history_id: int):
    delete_generation_history_item(history_id)
    return redirect(url_for("web.generation_history", **_history_filters()))


def edit_generation_history(history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        abort(404)
    content_type = (item.get("content_type") or "").strip().lower()
    routes = {
        "blog": "web.index",
        "medium blog": "web.backlink_blog_generator",
        "tier 2 blog": "web.tier2_blog_generator",
        "neutral post": "web.neutral_blog_generator",
        "page": "web.page_generator",
        "simple page": "web.simple_page_generator",
    }
    endpoint = routes.get(content_type)
    if not endpoint:
        return redirect(url_for("web.generation_history_detail", history_id=history_id))
    return redirect(url_for(endpoint, edit_history_id=history_id))


def mark_generation_history_as_draft(history_id: int):
    if not mark_generation_history_draft(history_id):
        abort(404)
    if request.form.get("return_to") == "detail":
        return redirect(url_for("web.generation_history_detail", history_id=history_id, draft="1"))
    return redirect(url_for("web.generation_history", **_history_filters()))


def generation_history_detail(history_id: int):
    error = None
    success = None
    if request.method == "POST":
        post_link = _normalize_post_link(request.form.get("post_link", ""))
        if not _valid_post_link(post_link):
            error = "Post link is required. Please enter a valid http or https URL."
        elif update_generation_history_post_link(history_id, post_link):
            return redirect(url_for("web.generation_history_detail", history_id=history_id, saved="1"))
        else:
            abort(404)

    if request.args.get("saved") == "1":
        success = "Post link saved. This item is now marked as saved."
    if request.args.get("draft") == "1":
        success = "Post link removed. This item is now marked as draft."

    item = get_generation_history_item(history_id)
    if not item:
        abort(404)
    item["prompt_inputs_data"] = _loads(item.get("prompt_inputs", "{}"))
    item["quality_report_data"] = _loads(item.get("quality_report", "{}"))
    return render_template("generation_history_detail.html", **base_template_context(), item=item, error=error, success=success)


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_history_workbook(rows: list[dict]) -> bytes:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(_history_sheet_name(row.get("content_type", "")), []).append(row)
    if not grouped:
        grouped["History"] = []

    sheet_names = _unique_sheet_names(grouped.keys())
    sheet_items = list(zip(sheet_names, grouped.values()))
    workbook_xml = _workbook_xml([name for name, _items in sheet_items])
    workbook_rels_xml = _workbook_rels_xml(len(sheet_items))
    content_types_xml = _content_types_xml(len(sheet_items))

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_name, items) in enumerate(sheet_items, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _history_sheet_xml(items))
    return buffer.getvalue()


def _history_sheet_name(content_type: str) -> str:
    labels = {
        "medium blog": "Tier 1",
        "tier 2 blog": "Tier 2",
        "blog": "Blog",
        "neutral post": "Neutral",
        "page": "Page",
        "simple page": "Simple Page",
    }
    cleaned = (content_type or "").strip()
    return labels.get(cleaned.lower(), cleaned or "History")


def _unique_sheet_names(names) -> list[str]:
    used = set()
    result = []
    for name in names:
        cleaned = re.sub(r"[\[\]\*:/\\?]", " ", str(name or "History")).strip() or "History"
        cleaned = re.sub(r"\s+", " ", cleaned)[:31]
        candidate = cleaned
        suffix = 2
        while candidate.lower() in used:
            suffix_text = f" {suffix}"
            candidate = f"{cleaned[:31 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        used.add(candidate.lower())
        result.append(candidate)
    return result


def _history_sheet_xml(rows: list[dict]) -> str:
    headers = [
        "Brand",
        "Medium",
        "Title",
        "Keyword / Anchor",
        "Post Link",
        "Date Saved",
    ]
    data_rows = [headers]
    for row in rows:
        data_rows.append(
            [
                row.get("brand_name", ""),
                row.get("medium_name", ""),
                row.get("title", ""),
                row.get("primary_keyword", ""),
                row.get("post_link", ""),
                row.get("saved_at", "") or row.get("created_at", ""),
            ]
        )

    rows_xml = []
    for row_index, values in enumerate(data_rows, start=1):
        cells = []
        for column_index, value in enumerate(values, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            style = ' s="1"' if row_index == 1 else ""
            cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{_cell_text(value)}</t></is></c>')
        rows_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>
    <col min="1" max="4" width="24" customWidth="1"/>
    <col min="5" max="5" width="55" customWidth="1"/>
    <col min="6" max="6" width="22" customWidth="1"/>
  </cols>
  <sheetData>
    {"".join(rows_xml)}
  </sheetData>
</worksheet>'''


def _cell_text(value) -> str:
    text = "" if value is None else str(value)
    text = text[:32767]
    return escape(text, {'"': "&quot;"})


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets}</sheets>
</workbook>'''


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    rels += f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'''


def _content_types_xml(sheet_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  {sheets}
</Types>'''


def _root_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>'''


def _history_filters() -> dict:
    return {
        "content_type": request.values.get("content_type", "").strip(),
        "status": request.values.get("status", "").strip(),
        "date": request.values.get("date", "").strip(),
        "medium": request.values.get("medium", "").strip(),
        "search": request.values.get("search", "").strip(),
    }


def _valid_post_link(value: str) -> bool:
    cleaned = (value or "").strip().lower()
    return cleaned.startswith("https://") or cleaned.startswith("http://")


def _normalize_post_link(value: str) -> str:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("http://", "https://")):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"
    return cleaned
