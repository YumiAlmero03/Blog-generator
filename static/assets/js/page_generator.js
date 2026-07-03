(function () {
  const pageTitleEditor = document.getElementById("pageTitleEditor");
  const pageMetaEditor = document.getElementById("pageMetaEditor");
  const pageTitleHidden = document.getElementById("pageTitleHidden");
  const pageMetaHidden = document.getElementById("pageMetaHidden");
  const pageContentHidden = document.getElementById("pageContentHidden");
  const savePageTitle = document.getElementById("savePageTitle");
  const savePageMeta = document.getElementById("savePageMeta");
  const savePageContent = document.getElementById("savePageContent");
  const titleOutput = document.getElementById("titleOutput");
  const pageTitleCharacterCount = document.getElementById("pageTitleCharacterCount");
  const pageGeneratedHeading = document.getElementById("pageGeneratedHeading");
  const metaOutput = document.getElementById("metaOutput");
  const metaOutputFull = document.getElementById("metaOutputFull");
  const htmlOutput = document.getElementById("htmlOutput");
  const htmlOutputMirror = document.getElementById("htmlOutputMirror");
  const markdownOutput = document.getElementById("markdownOutput");
  const gutenbergOutput = document.getElementById("gutenbergOutput");
  const previewArea = document.getElementById("previewArea");
  const liveWorkspace = document.getElementById("pageLiveDraftWorkspace");
  const livePreviewArea = document.getElementById("pageLivePreviewArea");
  const liveHtmlOutput = document.getElementById("pageLiveHtmlOutput");
  const generatorForm = document.getElementById("pageGeneratorForm");
  const saveForm = document.getElementById("savePageForm");
  const generationLogBox = document.getElementById("pageGenerationLogBox");
  const generationLogJson = document.getElementById("pageGenerationLogJson");
  const saveGenerationLogJson = document.getElementById("savePageGenerationLogJson");
  const clearGenerationLog = document.getElementById("clearPageGenerationLog");
  let generationLogEntries = readInitialGenerationLog();

  function syncSaveContext() {
    if (!generatorForm || !saveForm) {
      return;
    }
    ["history_id", "brand", "language", "keyword", "supporting_keywords", "expectations", "image_count"].forEach(function (name) {
      const source = generatorForm.querySelector("[name='" + name + "']");
      const target = saveForm.querySelector("[name='" + name + "']");
      if (source && target) {
        target.value = source.value;
      }
    });
    const keyword = generatorForm.querySelector("[name='keyword']");
    const pageType = saveForm.querySelector("[name='page_type']");
    if (keyword && pageType) {
      pageType.value = keyword.value;
    }
    syncGenerationLogFields();
  }

  function readInitialGenerationLog() {
    if (!generationLogBox || !generationLogBox.dataset.generationLog) {
      return [];
    }
    try {
      const parsed = JSON.parse(generationLogBox.dataset.generationLog);
      return Array.isArray(parsed) ? parsed.filter(function (item) {
        return item && typeof item === "object" && item.message;
      }) : [];
    } catch (error) {
      return [];
    }
  }

  function syncGenerationLogFields() {
    const value = JSON.stringify(generationLogEntries.slice(-80));
    if (generationLogJson) {
      generationLogJson.value = value;
    }
    if (saveGenerationLogJson) {
      saveGenerationLogJson.value = value;
    }
  }

  function appendGenerationLog(kind, message) {
    const cleanedMessage = String(message || "").trim();
    if (!cleanedMessage) {
      return;
    }
    const cleanedKind = String(kind || "status").trim() || "status";
    const previous = generationLogEntries[generationLogEntries.length - 1];
    if (previous && previous.kind === cleanedKind && previous.message === cleanedMessage) {
      return;
    }
    generationLogEntries.push({ kind: cleanedKind, message: cleanedMessage });
    generationLogEntries = generationLogEntries.slice(-80);
    renderGenerationLog();
    syncGenerationLogFields();
  }

  function renderGenerationLog() {
    if (!generationLogBox) {
      return;
    }
    generationLogBox.innerHTML = "";
    if (!generationLogEntries.length) {
      const empty = document.createElement("p");
      empty.className = "text-sm font-semibold leading-6 text-sand-500";
      empty.textContent = "No generation log yet.";
      generationLogBox.appendChild(empty);
      return;
    }
    generationLogEntries.forEach(function (item) {
      const wrapper = document.createElement("div");
      wrapper.className = "mb-3 rounded-xl bg-sand-50 px-3 py-2";
      const label = document.createElement("div");
      label.className = "mb-1 font-bold uppercase tracking-[0.08em] text-sand-500";
      label.textContent = item.kind || "status";
      const body = document.createElement("pre");
      body.className = "whitespace-pre-wrap font-sans text-xs leading-5 text-sand-800";
      body.textContent = item.message || "";
      wrapper.appendChild(label);
      wrapper.appendChild(body);
      generationLogBox.appendChild(wrapper);
    });
    generationLogBox.scrollTop = generationLogBox.scrollHeight;
  }

  function syncTitle() {
    const value = pageTitleEditor ? pageTitleEditor.value : (pageTitleHidden ? pageTitleHidden.value : "");
    [pageTitleHidden, savePageTitle, titleOutput].forEach(function (element) {
      if (element) {
        element.value = value;
      }
    });
    if (pageGeneratedHeading) {
      pageGeneratedHeading.textContent = value || "Generated Page";
    }
    if (pageTitleCharacterCount) {
      const length = value.length;
      const isTarget = length >= 50 && length <= 60;
      pageTitleCharacterCount.textContent = "Title length: " + length + " characters. Target: 50-60.";
      pageTitleCharacterCount.classList.toggle("text-moss-700", isTarget);
      pageTitleCharacterCount.classList.toggle("text-amber-700", Boolean(value) && !isTarget);
      pageTitleCharacterCount.classList.toggle("text-sand-600", !value);
    }
  }

  function syncMeta() {
    const value = pageMetaEditor ? pageMetaEditor.value : (pageMetaHidden ? pageMetaHidden.value : "");
    [pageMetaHidden, savePageMeta, metaOutput, metaOutputFull].forEach(function (element) {
      if (element) {
        element.value = value;
      }
    });
  }

  function setContent(html, options) {
    const shouldShowLive = options && options.live;
    if (shouldShowLive && liveWorkspace) {
      liveWorkspace.classList.remove("hidden");
    }
    if (shouldShowLive && liveHtmlOutput) {
      liveHtmlOutput.value = html;
    }
    if (htmlOutput && !shouldShowLive) {
      htmlOutput.value = html;
    }
    [pageContentHidden, savePageContent, htmlOutputMirror, gutenbergOutput].forEach(function (element) {
      if (element) {
        element.value = html;
      }
    });
    if (previewArea && !shouldShowLive) {
      previewArea.innerHTML = html;
    }
    if (livePreviewArea && shouldShowLive) {
      livePreviewArea.innerHTML = html;
    }
    if (markdownOutput && !shouldShowLive) {
      markdownOutput.value = html;
    }
  }

  const htmlCopyButton = document.getElementById("copyHtmlButton");
  if (htmlCopyButton) {
    htmlCopyButton.addEventListener("click", function () {
      window.AppUi.copyField("htmlOutput", "HTML copied. You can now paste it into WordPress Gutenberg.");
    });
  }

  if (pageTitleEditor) {
    pageTitleEditor.addEventListener("input", syncTitle);
  }
  if (pageMetaEditor) {
    pageMetaEditor.addEventListener("input", syncMeta);
  }
  if (htmlOutput) {
    htmlOutput.addEventListener("input", function () {
      setContent(htmlOutput.value, { live: false });
    });
  }
  if (liveHtmlOutput) {
    liveHtmlOutput.addEventListener("input", function () {
      setContent(liveHtmlOutput.value, { live: true });
    });
  }
  document.addEventListener("app:generation-draft", function (event) {
    const html = event.detail && event.detail.html ? event.detail.html : "";
    if (!html) {
      return;
    }
    setContent(html, { live: true });
  });
  document.addEventListener("app:generation-status", function (event) {
    appendGenerationLog("status", event.detail && event.detail.message);
  });
  document.addEventListener("app:generation-prompt", function (event) {
    appendGenerationLog("prompt", event.detail && event.detail.prompt);
  });
  if (clearGenerationLog) {
    clearGenerationLog.addEventListener("click", function () {
      generationLogEntries = [];
      renderGenerationLog();
      syncGenerationLogFields();
    });
  }

  document.addEventListener("submit", function (event) {
    if (event.target && event.target.id === "savePageForm") {
      syncSaveContext();
      syncTitle();
      syncMeta();
      syncGenerationLogFields();
      if (htmlOutput) {
        setContent(htmlOutput.value, { live: false });
      } else if (liveHtmlOutput) {
        setContent(liveHtmlOutput.value, { live: true });
      }
    }
  });

  syncTitle();
  syncMeta();
  syncGenerationLogFields();
})();
