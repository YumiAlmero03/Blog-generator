(function () {
  const minimumEditorWords = 800;
  const contentForm = document.getElementById("contentForm");
  const previewForm = document.getElementById("previewForm");
  const downloadForm = document.getElementById("downloadForm");
  const contentHtmlInput = document.getElementById("contentHtmlInput");
  const previewContentHtml = document.getElementById("previewContentHtml");
  const downloadContentHtml = document.getElementById("downloadContentHtml");
  const previewSelectedTitle = document.getElementById("previewSelectedTitle");
  const previewMetaDescription = document.getElementById("previewMetaDescription");
  const downloadSelectedTitle = document.getElementById("downloadSelectedTitle");
  const downloadMetaDescription = document.getElementById("downloadMetaDescription");
  const customTitleInput = document.getElementById("customTitleInput");
  const customTitleRadio = document.getElementById("customTitleRadio");
  const editorContainer = document.getElementById("contentEditor");
  const editorWordCount = document.getElementById("editorWordCount");
  const existingLinksElement = document.getElementById("existingLinksData");
  const linksContainer = document.getElementById("linksContainer");
  const addLinkButton = document.getElementById("addLinkButton");
  const generateContentButton = document.getElementById("generateContentButton");
  const saveGeneratedButton = document.getElementById("saveGeneratedButton");
  const contentActionInput = document.getElementById("contentActionInput");
  const postLinkInput = document.getElementById("post_link");
  const previewButton = document.getElementById("previewDocButton");
  const downloadButton = document.getElementById("downloadDocButton");
  const outputViewButtons = Array.from(document.querySelectorAll("[data-output-view-button]"));
  const outputViewPanels = Array.from(document.querySelectorAll("[data-output-view-panel]"));
  let quill = null;
  let linkFieldCounter = 0;

  function getSelectedTitle() {
    if (customTitleInput && customTitleRadio && customTitleRadio.checked) {
      const customTitle = customTitleInput.value.trim();
      return customTitle ? { value: customTitle } : null;
    }
    return document.querySelector('input[name="selected_title"]:checked');
  }

  function syncCustomTitleRadio() {
    if (!customTitleInput || !customTitleRadio) {
      return;
    }
    customTitleRadio.value = customTitleInput.value.trim();
    if (customTitleInput.value.trim()) {
      customTitleRadio.checked = true;
    }
  }

  function getSelectedMetaDescription() {
    return document.querySelector('input[name="meta_description_choice"]:checked');
  }

  function prepareContentForm() {
    if (quill && contentHtmlInput) {
      contentHtmlInput.value = quill.root.innerHTML;
    }
  }

  function normalizePostLink(value) {
    const cleaned = (value || "").trim();
    if (!cleaned) {
      return "";
    }
    if (/^https?:\/\//i.test(cleaned)) {
      return cleaned;
    }
    if (/^(www\.|[a-z0-9-]+\.[a-z]{2,})(\S*)$/i.test(cleaned)) {
      return "https://" + cleaned;
    }
    return cleaned;
  }

  function getValidationMessageBox() {
    if (!contentForm) {
      return null;
    }
    let box = document.getElementById("generatorValidationMessage");
    if (box) {
      return box;
    }
    box = document.createElement("div");
    box.id = "generatorValidationMessage";
    box.className = "hidden rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-700";
    contentForm.insertBefore(box, contentForm.firstChild);
    return box;
  }

  function showValidationMessage(message, focusElement) {
    const box = getValidationMessageBox();
    if (box) {
      box.textContent = message;
      box.classList.remove("hidden");
      box.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (focusElement && typeof focusElement.focus === "function") {
      focusElement.focus();
    }
  }

  function clearValidationMessage() {
    const box = document.getElementById("generatorValidationMessage");
    if (box) {
      box.textContent = "";
      box.classList.add("hidden");
    }
  }

  function countWordsFromHtml(html) {
    const temp = document.createElement("div");
    temp.innerHTML = html;
    const text = (temp.textContent || temp.innerText || "").trim();
    if (!text) {
      return 0;
    }
    return text.split(/\s+/).filter(Boolean).length;
  }

  function updateEditorWordCount() {
    if (!editorWordCount || !quill) {
      return;
    }
    const wordCount = countWordsFromHtml(quill.root.innerHTML);
    editorWordCount.textContent = "Word count: " + wordCount;
    editorWordCount.classList.toggle("low", wordCount < minimumEditorWords);
  }

  function convertMarkdownToHtml(text) {
    let html = text;
    html = html.replace(/^###\s+(.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^##\s+(.*)$/gm, "<h2>$1</h2>");
    html = html.replace(/^#\s+(.*)$/gm, "<h1>$1</h1>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\[(.*?)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2">$1</a>');
    return html;
  }

  function htmlToMarkdown(html) {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html || "";
    const chunks = [];

    function inlineMarkdown(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent || "";
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return "";
      }
      const tag = node.tagName.toLowerCase();
      const inner = Array.from(node.childNodes).map(inlineMarkdown).join("");
      if (tag === "a") {
        const href = node.getAttribute("href") || "";
        return href ? "[" + inner + "](" + href + ")" : inner;
      }
      if (tag === "strong" || tag === "b") {
        return "**" + inner + "**";
      }
      if (tag === "em" || tag === "i") {
        return "*" + inner + "*";
      }
      return inner;
    }

    Array.from(wrapper.childNodes).forEach(function (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.trim();
        if (text) {
          chunks.push(text);
        }
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return;
      }
      const tag = node.tagName.toLowerCase();
      const text = inlineMarkdown(node).trim();
      if (!text) {
        return;
      }
      if (tag === "h1") {
        chunks.push("# " + text);
      } else if (tag === "h2") {
        chunks.push("## " + text);
      } else if (tag === "h3") {
        chunks.push("### " + text);
      } else if (tag === "li") {
        chunks.push("- " + text);
      } else if (tag === "ul" || tag === "ol") {
        const items = Array.from(node.querySelectorAll(":scope > li")).map(function (item) {
          return "- " + inlineMarkdown(item).trim();
        });
        chunks.push(items.join("\n"));
      } else if (tag === "blockquote") {
        chunks.push("> " + text);
      } else {
        chunks.push(text);
      }
    });
    return chunks.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function htmlToGutenberg(html) {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html || "";
    const parts = [];
    Array.from(wrapper.children).forEach(function (node) {
      const tag = node.tagName.toLowerCase();
      const outer = node.outerHTML;
      if (tag === "p") {
        parts.push("<!-- wp:paragraph -->" + outer + "<!-- /wp:paragraph -->");
      } else if (tag === "h2") {
        parts.push("<!-- wp:heading -->" + outer + "<!-- /wp:heading -->");
      } else if (tag === "h3") {
        parts.push('<!-- wp:heading {"level":3} -->' + outer + "<!-- /wp:heading -->");
      } else if (tag === "ul" || tag === "ol") {
        parts.push("<!-- wp:list -->" + outer + "<!-- /wp:list -->");
      } else if (tag === "blockquote") {
        parts.push("<!-- wp:quote -->" + outer + "<!-- /wp:quote -->");
      } else {
        parts.push(outer);
      }
    });
    return parts.join("");
  }

  function refreshOutputViews() {
    if (!quill) {
      return;
    }
    const html = quill.root.innerHTML;
    const markdown = htmlToMarkdown(html);
    const markdownView = document.getElementById("markdownOutputView");
    const htmlView = document.getElementById("htmlOutputView");
    const gutenbergView = document.getElementById("gutenbergOutputView");
    if (markdownView) {
      markdownView.value = markdown;
    }
    if (htmlView) {
      htmlView.value = html;
    }
    if (gutenbergView) {
      gutenbergView.value = htmlToGutenberg(html);
    }
  }

  function setOutputView(mode) {
    const selectedMode = mode || "visual";
    const editorWrapper = document.getElementById("editorContainer");
    if (editorWrapper) {
      editorWrapper.classList.toggle("hidden", selectedMode !== "visual");
    }
    outputViewPanels.forEach(function (panel) {
      panel.classList.toggle("hidden", panel.dataset.outputViewPanel !== selectedMode);
    });
    outputViewButtons.forEach(function (button) {
      const active = button.dataset.outputViewButton === selectedMode;
      button.classList.toggle("bg-sand-600", active);
      button.classList.toggle("text-sand-50", active);
      button.classList.toggle("border", !active);
      button.classList.toggle("border-sand-200", !active);
      button.classList.toggle("bg-white", !active);
      button.classList.toggle("text-sand-700", !active);
    });
    refreshOutputViews();
  }

  function containsHtmlTags(text) {
    return /<\/?(h[1-6]|p|a|strong|em|ul|ol|li|br|b|i)>/i.test(text);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function addLinkField(link) {
    if (!linksContainer) {
      return;
    }
    const currentLink = link || {};
    const linkType = currentLink.type === "external" ? "external" : "internal";
    const linkText = currentLink.text || "";
    const linkUrl = currentLink.url || "";

    linkFieldCounter += 1;
    const linkField = document.createElement("div");
    linkField.className = "flex flex-wrap items-end gap-3 rounded-[22px] border border-sand-200 bg-white/80 p-4";
    linkField.id = "linkField_" + linkFieldCounter;
    linkField.innerHTML = [
      '<div class="w-full sm:w-[150px]">',
      '  <label for="link_type_' + linkFieldCounter + '" class="mb-2 block text-sm font-bold text-sand-900">Link Type</label>',
      '  <select id="link_type_' + linkFieldCounter + '" name="link_type[]" class="w-full rounded-2xl border border-sand-200 bg-white px-4 py-3 text-sand-900 outline-none transition focus:border-sand-500 focus:ring-2 focus:ring-sand-200">',
      '    <option value="internal"' + (linkType === "internal" ? " selected" : "") + ">Internal</option>",
      '    <option value="external"' + (linkType === "external" ? " selected" : "") + ">External</option>",
      "  </select>",
      "</div>",
      '<div class="min-w-[220px] flex-1">',
      '  <label for="link_text_' + linkFieldCounter + '" class="mb-2 block text-sm font-bold text-sand-900">Link Text</label>',
      '  <input type="text" id="link_text_' + linkFieldCounter + '" name="link_text[]" value="' + escapeHtml(linkText) + '" placeholder="e.g. Best Practices" class="w-full rounded-2xl border border-sand-200 bg-white px-4 py-3 text-sand-900 outline-none transition focus:border-sand-500 focus:ring-2 focus:ring-sand-200" />',
      "</div>",
      '<div class="min-w-[260px] flex-[1.4]">',
      '  <label for="link_url_' + linkFieldCounter + '" class="mb-2 block text-sm font-bold text-sand-900">URL</label>',
      '  <input type="url" id="link_url_' + linkFieldCounter + '" name="link_url[]" value="' + escapeHtml(linkUrl) + '" placeholder="https://example.com" class="w-full rounded-2xl border border-sand-200 bg-white px-4 py-3 text-sand-900 outline-none transition focus:border-sand-500 focus:ring-2 focus:ring-sand-200" />',
      "</div>",
      '<button type="button" class="inline-flex min-h-11 items-center justify-center rounded-full bg-red-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-red-700" data-remove-link="' + linkFieldCounter + '">Remove</button>',
    ].join("");
    linksContainer.appendChild(linkField);
  }

  document.addEventListener("click", function (event) {
    const removeButton = event.target.closest("[data-remove-link]");
    if (!removeButton) {
      return;
    }
    const target = document.getElementById("linkField_" + removeButton.dataset.removeLink);
    if (target) {
      target.remove();
    }
  });

  if (generateContentButton && contentForm) {
    generateContentButton.addEventListener("click", function () {
      if (contentActionInput) {
        contentActionInput.value = "generate_content";
      }
      syncCustomTitleRadio();
      const selectedTitle = getSelectedTitle();
      if (!selectedTitle) {
        showValidationMessage("Please select a title first.");
        return;
      }
      clearValidationMessage();
      prepareContentForm();
      window.AppUi.startFormLoading(contentForm, "Generating article content...");
      contentForm.submit();
    });
  }

  if (saveGeneratedButton && contentForm) {
    saveGeneratedButton.addEventListener("click", function () {
      if (contentActionInput) {
        contentActionInput.value = "save_generated_blog";
      }
      syncCustomTitleRadio();
      const selectedTitle = getSelectedTitle();
      if (!selectedTitle) {
        showValidationMessage("Please select a title before saving.");
        return;
      }
      if (postLinkInput) {
        postLinkInput.value = normalizePostLink(postLinkInput.value);
      }
      if (postLinkInput && !/^https?:\/\/\S+/i.test(postLinkInput.value.trim())) {
        showValidationMessage("Please enter a valid post link before saving.", postLinkInput);
        return;
      }
      clearValidationMessage();
      prepareContentForm();
      contentForm.submit();
    });
  }

  function syncPreviewFields() {
    syncCustomTitleRadio();
    const selectedTitle = getSelectedTitle();
    const selectedMetaDescription = getSelectedMetaDescription();

    if (previewSelectedTitle && selectedTitle) {
      previewSelectedTitle.value = selectedTitle.value;
    }
    if (downloadSelectedTitle && selectedTitle) {
      downloadSelectedTitle.value = selectedTitle.value;
    }
    if (previewMetaDescription && selectedMetaDescription) {
      previewMetaDescription.value = selectedMetaDescription.value;
    }
    if (downloadMetaDescription && selectedMetaDescription) {
      downloadMetaDescription.value = selectedMetaDescription.value;
    }
  }

  if (previewButton && previewForm) {
    previewButton.addEventListener("click", function () {
      syncPreviewFields();
      if (quill) {
        previewContentHtml.value = quill.root.innerHTML;
      }
      previewForm.submit();
    });
  }

  if (downloadButton && downloadForm) {
    downloadButton.addEventListener("click", function () {
      syncPreviewFields();
      if (quill) {
        downloadContentHtml.value = quill.root.innerHTML;
      }
      downloadForm.submit();
    });
  }

  if (contentForm) {
    contentForm.addEventListener("submit", function () {
      syncCustomTitleRadio();
      prepareContentForm();
    });
  }

  if (customTitleInput) {
    customTitleInput.addEventListener("input", syncCustomTitleRadio);
    customTitleInput.addEventListener("focus", syncCustomTitleRadio);
  }

  if (editorContainer && window.Quill) {
    const rawHtml = editorContainer.innerHTML;
    const cleanHtml = containsHtmlTags(rawHtml)
      ? rawHtml
      : convertMarkdownToHtml(editorContainer.textContent || editorContainer.innerText || rawHtml);

    quill = new window.Quill("#contentEditor", {
      theme: "snow",
      modules: {
        toolbar: [
          ["bold", "italic", "underline"],
          ["blockquote", "code-block"],
          [{ header: [1, 2, 3, false] }],
          ["link", "image"],
          ["clean"],
        ],
      },
    });

    quill.root.innerHTML = cleanHtml;
    updateEditorWordCount();
    refreshOutputViews();
    quill.on("text-change", function () {
      updateEditorWordCount();
      refreshOutputViews();
    });
  }

  outputViewButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setOutputView(button.dataset.outputViewButton);
    });
  });

  if (addLinkButton) {
    addLinkButton.addEventListener("click", function () {
      addLinkField({});
    });
  }

  if (existingLinksElement) {
    try {
      const existingLinks = JSON.parse(existingLinksElement.textContent || "[]");
      if (Array.isArray(existingLinks)) {
        existingLinks.forEach(function (link) {
          addLinkField(link);
        });
      }
    } catch (error) {
      console.error("Could not parse existing links JSON.", error);
    }
  }
})();
