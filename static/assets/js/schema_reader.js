(() => {
  "use strict";
  const core = window.SchemaReader;
  const input = document.getElementById("schemaCode");
  const status = document.getElementById("schemaStatus");
  const results = document.getElementById("schemaResults");
  const fields = [...document.querySelectorAll('[data-schema-field]')];
  const fieldValues = () => Object.fromEntries(fields.map(field => [field.dataset.schemaField, field.value]));
  const storageKey = "schemaReaderDraft";
  try { const saved = localStorage.getItem(storageKey); if (saved !== null) input.value = saved; } catch (_) {}
  const editor = window.CodeMirror ? CodeMirror.fromTextArea(input, {
    mode: { name: "javascript", json: true }, theme: "material-darker",
    lineNumbers: true, lineWrapping: true, foldGutter: true,
    gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"],
    matchBrackets: true, autoCloseBrackets: true, indentUnit: 2, tabSize: 2,
    extraKeys: {
      Tab: cm => cm.somethingSelected() ? cm.indentSelection("add") : cm.replaceSelection("  ", "end", "+input"),
      "Shift-Tab": cm => cm.indentSelection("subtract"),
      Esc: cm => { cm.setOption("extraKeys", { ...cm.getOption("extraKeys"), Tab: false }); },
      "Ctrl-Q": cm => cm.foldCode(cm.getCursor()),
      "Ctrl-Enter": () => validate(), "Cmd-Enter": () => validate()
    }
  }) : null;
  if (editor) {
    editor.getInputField().setAttribute("aria-label", "JSON-LD code editor");
    editor.getInputField().setAttribute("aria-describedby", "schemaEditorHelp");
  }
  const read = () => editor ? editor.getValue() : input.value;
  const write = value => {
    const text = JSON.stringify(value, null, 2);
    if (editor) editor.setValue(text); else { input.value = text; changed(); }
    validate();
  };
  let markedLine = null;
  function validate() {
    if (editor && markedLine !== null) editor.removeLineClass(markedLine, "background", "schema-error-line");
    markedLine = null;
    results.replaceChildren();
    try {
      const value = core.parse(read());
      const report = core.check(value);
      const messages = [...report.errors.map(message => ({ message, error: true })), ...report.warnings.map(message => ({ message: `Notice: ${message}`, error: false }))];
      if (!messages.length) messages.push({ message: "No JSON syntax or basic structure errors found.", error: false });
      for (const item of messages) {
        const paragraph = document.createElement("p");
        paragraph.textContent = item.message;
        if (item.error) paragraph.className = "schema-error";
        results.append(paragraph);
      }
      return report.errors.length ? null : value;
    } catch (error) {
      const paragraph = document.createElement("p");
      paragraph.className = "schema-error";
      paragraph.textContent = `JSON syntax error: ${error.message}`;
      results.append(paragraph);
      const match = error.message.match(/position (\d+)/i);
      const lineMatch = error.message.match(/line (\d+)/i);
      // Wrapped script input uses different offsets; keep its parser message without a misleading marker.
      if (editor && !read().trim().startsWith("<")) {
        const line = match ? read().slice(0, Number(match[1])).split("\n").length - 1 : lineMatch ? Number(lineMatch[1]) - 1 : null;
        if (line !== null) markedLine = editor.addLineClass(line, "background", "schema-error-line");
      }
      return null;
    }
  }
  let timer;
  function changed() {
    try { localStorage.setItem(storageKey, read()); status.textContent = "Draft saved in this browser."; }
    catch (_) { status.textContent = "Browser storage is unavailable. Copy or download your draft to keep it."; }
    clearTimeout(timer);
    timer = setTimeout(validate, 350);
  }
  if (editor) editor.on("change", changed); else input.addEventListener("input", changed);
  const buttons = document.getElementById("schemaTemplates");
  Object.keys(core.templates).forEach(type => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "min-h-10 rounded-full border border-sand-300 bg-sand-50 px-4 py-2 text-sm font-bold text-sand-700";
    button.textContent = `+ ${type}`;
    button.addEventListener("click", () => {
      const value = read().trim() ? validate() : { "@context": "https://schema.org", "@graph": [] };
      if (value === null) { status.textContent = "Fix the code errors before adding a template. Your code has been kept."; return; }
      try { write(core.add(value, type, fieldValues())); status.textContent = `${type} block added. Review remaining placeholders in Code check.`; }
      catch (error) { status.textContent = error.message; }
    });
    buttons.append(button);
  });
  document.getElementById("schemaApply").addEventListener("click", () => {
    const value = validate();
    if (value === null) { status.textContent = "Fix code errors before filling placeholders."; return; }
    try { write(core.apply(value, fieldValues())); status.textContent = "Available values applied to named placeholders. Review remaining notices."; }
    catch (error) { status.textContent = error.message; }
  });
  document.getElementById("schemaExtract").addEventListener("click", async event => {
    const button = event.currentTarget;
    try {
      const requestedFields = fieldValues();
      if (!requestedFields.PAGE_URL.trim()) throw new Error("Enter a Page URL or path first.");
      const pageUrl = core.replacements({ DOMAIN_URL: requestedFields.DOMAIN_URL, PAGE_URL: requestedFields.PAGE_URL }).PAGE_URL;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      status.textContent = "Fetching page metadata…";
      const response = await fetch(`/schema-reader/metadata?${new URLSearchParams({ url: pageUrl })}`, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(failure.error || "Could not fetch that page. Try again.");
      }
      const fetched = await response.json();
      if (fields.some(field => ['DOMAIN_URL', 'PAGE_URL'].includes(field.dataset.schemaField) && field.value !== requestedFields[field.dataset.schemaField])) {
        status.textContent = "The page URL changed. Extract metadata again for the new URL.";
        return;
      }
      const source = fetched.html;
      // A template keeps page scripts, images and frames inert and detached from the page.
      const template = document.createElement("template");
      template.innerHTML = source;
      const doc = template.content;
      const meta = (...names) => {
        for (const name of names) {
          const element = [...doc.querySelectorAll('meta')].find(item => (item.getAttribute('name') || item.getAttribute('property') || '').toLowerCase() === name);
          if (element && element.content.trim()) return element.content.trim();
        }
        return '';
      };
      const extracted = {
        PAGE_URL: pageUrl,
        META_TITLE: doc.querySelector('title')?.textContent.trim() || meta('og:title', 'twitter:title'),
        META_DESCRIPTION: meta('description', 'og:description', 'twitter:description'),
        META_IMAGE: meta('og:image', 'twitter:image'), SITE_NAME: meta('og:site_name'),
        AUTHOR_NAME: meta('author'), DATE_PUBLISHED: meta('article:published_time'), DATE_MODIFIED: meta('article:modified_time'),
        PAGE_LANGUAGE: source.match(/<html\b[^>]*\blang\s*=\s*["']([^"']+)["']/i)?.[1] || meta('og:locale').replace(/_/g, '-')
      };
      if (extracted.META_IMAGE) extracted.META_IMAGE = new URL(extracted.META_IMAGE, fetched.final_url || pageUrl).href;
      const merged = Object.fromEntries(fields.map(field => [field.dataset.schemaField, field.value.trim() || extracted[field.dataset.schemaField] || '']));
      const normalized = core.replacements(merged);
      let count = 0;
      fields.forEach(field => {
        const key = field.dataset.schemaField;
        if (!field.value.trim() && normalized[key]) { field.value = normalized[key]; count++; }
      });
      status.textContent = count ? `Filled ${count} empty fields from the page. Review them, then add a block or fill existing placeholders.` : "No new metadata found. Existing fields were kept.";
    } catch (error) {
      status.textContent = `Metadata was not applied: ${error.message}`;
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  });
  document.getElementById("schemaCheck").addEventListener("click", validate);
  document.getElementById("schemaFormat").addEventListener("click", () => {
    const value = validate();
    if (value !== null) { write(value); status.textContent = "JSON-LD formatted."; }
  });
  for (const [id, command] of [["schemaFold", "foldAll"], ["schemaUnfold", "unfoldAll"]]) {
    document.getElementById(id).addEventListener("click", () => {
      if (editor) editor.execCommand(command); else status.textContent = "Reload the page to load code folding.";
    });
  }
  document.getElementById("schemaCopy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(read()); status.textContent = "Copied to clipboard."; }
    catch (_) { status.textContent = "Clipboard unavailable. Select the code and copy it with Ctrl+C or Cmd+C."; }
  });
  document.getElementById("schemaDownload").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([read()], { type: "application/ld+json" }));
    const link = document.createElement("a");
    link.href = url; link.download = "schema.jsonld";
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "JSON-LD downloaded.";
  });
  validate();
})();
