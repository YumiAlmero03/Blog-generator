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
  const editorContainer = document.getElementById("contentEditor");
  const editorWordCount = document.getElementById("editorWordCount");
  const existingLinksElement = document.getElementById("existingLinksData");
  const linksContainer = document.getElementById("linksContainer");
  const addLinkButton = document.getElementById("addLinkButton");
  const generateContentButton = document.getElementById("generateContentButton");
  const previewButton = document.getElementById("previewDocButton");
  const downloadButton = document.getElementById("downloadDocButton");
  let quill = null;
  let linkFieldCounter = 0;

  function getSelectedTitle() {
    return document.querySelector('input[name="selected_title"]:checked');
  }

  function getSelectedMetaDescription() {
    return document.querySelector('input[name="meta_description_choice"]:checked');
  }

  function prepareContentForm() {
    if (quill && contentHtmlInput) {
      contentHtmlInput.value = quill.root.innerHTML;
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
      const selectedTitle = getSelectedTitle();
      if (!selectedTitle) {
        window.alert("Please select a title first.");
        return;
      }
      prepareContentForm();
      window.AppUi.showLoading("Generating article content...");
      contentForm.submit();
    });
  }

  function syncPreviewFields() {
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
    contentForm.addEventListener("submit", prepareContentForm);
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
    quill.on("text-change", updateEditorWordCount);
  }

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
