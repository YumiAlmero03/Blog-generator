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

  function syncSaveContext() {
    if (!generatorForm || !saveForm) {
      return;
    }
    ["history_id", "brand", "language", "keyword", "supporting_keywords", "page_type", "expectations", "image_count"].forEach(function (name) {
      const source = generatorForm.querySelector("[name='" + name + "']");
      const target = saveForm.querySelector("[name='" + name + "']");
      if (source && target) {
        target.value = source.value;
      }
    });
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

  document.addEventListener("submit", function (event) {
    if (event.target && event.target.id === "savePageForm") {
      syncSaveContext();
      syncTitle();
      syncMeta();
      if (htmlOutput) {
        setContent(htmlOutput.value, { live: false });
      } else if (liveHtmlOutput) {
        setContent(liveHtmlOutput.value, { live: true });
      }
    }
  });

  syncTitle();
  syncMeta();
})();
