(function () {
  function getOverlay() {
    return document.querySelector("[data-loading-overlay]");
  }

  function getOverlayText() {
    return document.querySelector("[data-loading-text]");
  }

  function getOverlayStatus() {
    let status = document.querySelector("[data-loading-status]");
    const text = getOverlayText();
    if (!status && text && text.parentElement) {
      status = document.createElement("div");
      status.className = "loading-status mt-3 max-w-xl text-sm font-bold leading-6 text-sand-600";
      status.setAttribute("data-loading-status", "");
      text.parentElement.appendChild(status);
    }
    return status;
  }

  function getOverlayPrompt() {
    let promptPanel = document.querySelector("[data-loading-prompt-panel]");
    const text = getOverlayText();
    if (!promptPanel && text && text.parentElement) {
      const wrapper = document.createElement("div");
      wrapper.className = "mt-4 text-left";
      wrapper.setAttribute("data-loading-prompt-panel", "");
      wrapper.innerHTML = [
        '<div class="flex flex-wrap items-center gap-2">',
        '<button type="button" class="inline-flex min-h-9 items-center justify-center rounded-full border border-sand-200 bg-white px-3 py-2 text-xs font-bold text-sand-700 disabled:cursor-not-allowed disabled:opacity-50" disabled data-loading-prompt-toggle>Prompt loading...</button>',
        '<button type="button" class="inline-flex min-h-9 items-center justify-center rounded-full border border-sand-200 bg-white px-3 py-2 text-xs font-bold text-sand-700 disabled:cursor-not-allowed disabled:opacity-50" disabled data-loading-prompt-copy>Copy prompt</button>',
        '<span class="text-xs font-bold text-sand-500" data-loading-prompt-copy-status></span>',
        "</div>",
        '<pre class="mt-3 hidden max-h-[42vh] overflow-auto rounded-2xl border border-sand-200 bg-sand-50 p-4 text-xs leading-5 text-sand-900 whitespace-pre-wrap" data-loading-prompt-text></pre>',
      ].join("");
      text.parentElement.appendChild(wrapper);
      promptPanel = wrapper;
    }
    return promptPanel;
  }

  function getOverlayActions() {
    let actions = document.querySelector("[data-loading-actions]");
    const text = getOverlayText();
    if (!actions && text && text.parentElement) {
      actions = document.createElement("div");
      actions.className = "mt-4 flex flex-wrap items-center justify-center gap-2";
      actions.setAttribute("data-loading-actions", "");
      actions.innerHTML = '<button type="button" class="inline-flex min-h-10 items-center justify-center rounded-full border border-red-200 bg-red-50 px-4 py-2 text-xs font-bold text-red-700 transition hover:bg-red-100" data-loading-stop>Stop Generating</button>';
      text.parentElement.appendChild(actions);
    }
    return actions;
  }

  function getOverlayDraft() {
    let draft = document.querySelector("[data-loading-draft]");
    const text = getOverlayText();
    if (!draft && text && text.parentElement) {
      draft = document.createElement("div");
      draft.className = "mt-4 hidden w-full max-w-3xl text-left";
      draft.setAttribute("data-loading-draft", "");
      draft.innerHTML = [
        '<div class="mb-2 text-xs font-extrabold uppercase tracking-[0.14em] text-sand-500">Best draft so far</div>',
        '<iframe title="Best generated draft so far" class="h-[42vh] w-full rounded-2xl border border-sand-200 bg-white" data-loading-draft-frame></iframe>',
      ].join("");
      text.parentElement.appendChild(draft);
    }
    return draft;
  }

  let loadingEventSource = null;
  let loadingWebSocket = null;
  let loadingStatusPoll = null;
  let loadingStatusPollToken = "";
  let currentGenerationToken = "";
  let loadingCompletionFallback = null;
  let loadingResultHandled = false;
  let loadingUsesBackgroundJob = false;
  const generationStatusPollDelay = 1500;
  let latestLoadingPrompt = "";

  function setLoadingStatus(message) {
    const status = getOverlayStatus();
    if (status) {
      status.textContent = message || "";
    }
  }

  function setLoadingPrompt(prompt) {
    latestLoadingPrompt = prompt || "";
    const panel = getOverlayPrompt();
    const promptText = panel ? panel.querySelector("[data-loading-prompt-text]") : null;
    const promptToggle = panel ? panel.querySelector("[data-loading-prompt-toggle]") : null;
    const promptCopy = panel ? panel.querySelector("[data-loading-prompt-copy]") : null;
    const promptCopyStatus = panel ? panel.querySelector("[data-loading-prompt-copy-status]") : null;
    if (!panel || !promptText) {
      return;
    }
    panel.classList.toggle("hidden", !latestLoadingPrompt);
    promptText.textContent = latestLoadingPrompt;
    if (!latestLoadingPrompt) {
      promptText.classList.add("hidden");
      if (promptToggle) {
        promptToggle.textContent = "Prompt loading...";
        promptToggle.disabled = true;
      }
      if (promptCopy) {
        promptCopy.disabled = true;
      }
      if (promptCopyStatus) {
        promptCopyStatus.textContent = "";
      }
      return;
    }
    if (promptToggle) {
      promptToggle.textContent = promptText.classList.contains("hidden") ? "Show prompt" : "Hide prompt";
      promptToggle.disabled = false;
    }
    if (promptCopy) {
      promptCopy.disabled = false;
    }
  }

  function showLoading(message) {
    const overlay = getOverlay();
    const text = getOverlayText();
    if (!overlay) {
      return;
    }
    if (text && message) {
      text.textContent = message;
    }
    setLoadingStatus("Starting generation...");
    setLoadingPrompt("");
    getOverlayActions();
    overlay.classList.add("active");
  }

  function hideLoading() {
    const overlay = getOverlay();
    if (overlay) {
      overlay.classList.remove("active");
    }
    if (loadingEventSource) {
      loadingEventSource.close();
      loadingEventSource = null;
    }
    if (loadingWebSocket) {
      loadingWebSocket.close();
      loadingWebSocket = null;
    }
    if (loadingStatusPoll) {
      window.clearTimeout(loadingStatusPoll);
      loadingStatusPoll = null;
    }
    if (loadingCompletionFallback) {
      window.clearTimeout(loadingCompletionFallback);
      loadingCompletionFallback = null;
    }
    loadingStatusPollToken = "";
    currentGenerationToken = "";
    loadingResultHandled = false;
    loadingUsesBackgroundJob = false;
    setLoadingStatus("");
    setLoadingPrompt("");
    const draft = document.querySelector("[data-loading-draft]");
    if (draft) {
      draft.classList.add("hidden");
    }
  }

  function generationToken() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  }

  function ensureStatusToken(form) {
    let field = form.querySelector("input[name='generation_status_token']");
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "generation_status_token";
      form.appendChild(field);
    }
    field.value = generationToken();
    return field.value;
  }

  function startStatusEvents(token) {
    if (!token) {
      return;
    }
    if (loadingEventSource) {
      loadingEventSource.close();
    }
    if (loadingWebSocket) {
      loadingWebSocket.close();
      loadingWebSocket = null;
    }
    if (startStatusWebSocket(token)) {
      return;
    }
    startStatusEventSource(token);
  }

  function startStatusWebSocket(token) {
    if (!("WebSocket" in window)) {
      return false;
    }
    let didOpen = false;
    let didFallback = false;
    let fallbackTimer = null;
    const socket = new WebSocket(generationWebSocketUrl(token));
    loadingWebSocket = socket;

    const fallback = function () {
      if (didFallback || didOpen || loadingWebSocket !== socket) {
        return;
      }
      didFallback = true;
      try {
        socket.close();
      } catch (error) {}
      loadingWebSocket = null;
      startStatusEventSource(token);
    };

    fallbackTimer = window.setTimeout(fallback, 1500);

    socket.onopen = function () {
      didOpen = true;
      if (fallbackTimer) {
        window.clearTimeout(fallbackTimer);
      }
      socket.send(JSON.stringify({ token: token }));
    };
    socket.onmessage = function (event) {
      try {
        handleStatusPayload(JSON.parse(event.data || "{}"));
      } catch (error) {}
    };
    socket.onerror = fallback;
    socket.onclose = function () {
      if (!didOpen) {
        fallback();
        return;
      }
      if (loadingWebSocket === socket && !loadingResultHandled) {
        loadingWebSocket = null;
        startStatusEventSource(token);
      }
    };
    return true;
  }

  function startStatusEventSource(token) {
    loadingEventSource = new EventSource("/events/generation/" + encodeURIComponent(token));
    loadingEventSource.onmessage = function (event) {
      try {
        handleStatusPayload(JSON.parse(event.data || "{}"));
      } catch (error) {}
    };
    loadingEventSource.onerror = function () {};
    startStatusPolling(token);
  }

  function generationWebSocketUrl(token) {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const currentPort = Number(window.location.port || (window.location.protocol === "https:" ? 443 : 80));
    const wsPort = currentPort + 1;
    return scheme + "//" + window.location.hostname + ":" + wsPort + "/events/generation/" + encodeURIComponent(token);
  }

  function handleStatusPayload(payload) {
    if (!payload || payload.type === "keep-alive") {
      return;
    }
    if (payload.message) {
      setLoadingStatus(payload.message);
      maybeFinishFromStatus(payload.message);
    }
    if (typeof payload.prompt === "string") {
      setLoadingPrompt(payload.prompt);
    }
    if (typeof payload.draft_html === "string" && payload.draft_html) {
      setLoadingDraft(payload.draft_html);
    }
  }

  function startStatusPolling(token) {
    if (loadingStatusPoll) {
      window.clearTimeout(loadingStatusPoll);
    }
    loadingStatusPoll = null;
    loadingStatusPollToken = token;

    const poll = function () {
      if (loadingStatusPollToken !== token) {
        return;
      }
      fetch("/generation-status/" + encodeURIComponent(token), {
        headers: { Accept: "application/json" },
      })
        .then(function (response) {
          if (!response.ok) {
            return null;
          }
          return response.json();
        })
        .then(function (payload) {
          if (!payload) {
            return;
          }
          if (payload.message) {
            setLoadingStatus(payload.message);
            maybeFinishFromStatus(payload.message);
          }
          if (typeof payload.prompt === "string" && payload.prompt) {
            setLoadingPrompt(payload.prompt);
          }
          if (typeof payload.draft_html === "string" && payload.draft_html) {
            setLoadingDraft(payload.draft_html);
          }
        })
        .catch(function () {})
        .then(function () {
          if (loadingStatusPollToken === token) {
            loadingStatusPoll = window.setTimeout(poll, generationStatusPollDelay);
          }
        });
    };

    poll();
  }

  function startFormLoading(form, message) {
    if (!form) {
      showLoading(message);
      return "";
    }
    const token = ensureStatusToken(form);
    currentGenerationToken = token;
    loadingResultHandled = false;
    loadingUsesBackgroundJob = false;
    showLoading(message || form.dataset.loadingMessage);
    startStatusEvents(token);
    return token;
  }

  function setLoadingDraft(html) {
    const draft = getOverlayDraft();
    const frame = draft ? draft.querySelector("[data-loading-draft-frame]") : null;
    if (!draft || !frame || !html) {
      return;
    }
    draft.classList.remove("hidden");
    frame.setAttribute("srcdoc", html);
  }

  function stopCurrentGeneration() {
    if (!currentGenerationToken) {
      setLoadingStatus("No running generation to stop.");
      return;
    }
    setLoadingStatus("Stopping generation...");
    fetch("/generation-status/" + encodeURIComponent(currentGenerationToken) + "/cancel", {
      method: "POST",
      headers: { Accept: "application/json" },
    }).catch(function () {
      setLoadingStatus("Could not send stop request.");
    });
  }

  function maybeFinishFromStatus(message) {
    if (!message || loadingResultHandled) {
      return;
    }
    const normalized = String(message).toLowerCase();
    if (!normalized.includes("generation complete")) {
      return;
    }
    if (loadingStatusPoll) {
      window.clearTimeout(loadingStatusPoll);
      loadingStatusPoll = null;
    }
    loadingStatusPollToken = "";
    if (loadingUsesBackgroundJob) {
      return;
    }
    if (!loadingCompletionFallback) {
      loadingCompletionFallback = window.setTimeout(function () {
        if (!loadingResultHandled) {
          window.location.reload();
        }
      }, 2500);
    }
  }

  function renderBackgroundJobResult(payload) {
    if (loadingResultHandled) {
      return;
    }
    loadingResultHandled = true;
    if (loadingCompletionFallback) {
      window.clearTimeout(loadingCompletionFallback);
      loadingCompletionFallback = null;
    }
    if (payload.html) {
      document.open();
      document.write(payload.html);
      document.close();
      return;
    }
    window.location.reload();
  }

  function submitFormInBackground(form, submitter) {
    if (!form) {
      return;
    }
    const token = startFormLoading(form, form.dataset.loadingMessage);
    loadingUsesBackgroundJob = true;
    setLoadingStatus("Queued in background...");
    let formData;
    try {
      formData = submitter && typeof FormData === "function"
        ? new FormData(form, submitter)
        : new FormData(form);
    } catch (error) {
      formData = new FormData(form);
    }
    if (submitter && submitter.name && !formData.has(submitter.name)) {
      formData.append(submitter.name, submitter.value || "");
    }
    formData.set("generation_status_token", token);
    formData.set("_background_path", form.getAttribute("action") || window.location.pathname + window.location.search);

    fetch("/background-jobs", {
      method: "POST",
      body: formData,
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Could not start background job.");
        }
        return response.json();
      })
      .then(function (payload) {
        pollBackgroundJob(payload.id);
      })
      .catch(function (error) {
        setLoadingStatus(error.message || "Could not start background job.");
        window.setTimeout(hideLoading, 1800);
      });
  }

  function pollBackgroundJob(jobId) {
    if (!jobId) {
      setLoadingStatus("Background job did not return an id.");
      window.setTimeout(hideLoading, 1800);
      return;
    }

    const poll = function () {
      fetch("/background-jobs/" + encodeURIComponent(jobId), {
        headers: { Accept: "application/json" },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Could not read background job status.");
          }
          return response.json();
        })
        .then(function (payload) {
          if (payload.message) {
            setLoadingStatus(payload.message);
          }
          if (payload.status === "complete") {
            setLoadingStatus("Loading generated result...");
            renderBackgroundJobResult(payload);
            return;
          }
          if (payload.status === "failed") {
            setLoadingStatus(payload.error || "Background generation failed.");
            window.setTimeout(hideLoading, 2200);
            return;
          }
          if (payload.status === "cancelled") {
            setLoadingStatus(payload.error || payload.message || "Generation stopped.");
            return;
          }
          window.setTimeout(poll, 1200);
        })
        .catch(function (error) {
          setLoadingStatus(error.message || "Background job status failed.");
          window.setTimeout(hideLoading, 2200);
        });
    };

    window.setTimeout(poll, 800);
  }

  function copyText(value, message, onSuccess) {
    const fallback = function () {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "readonly");
      textarea.style.position = "absolute";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    };

    const done = function () {
      if (typeof onSuccess === "function") {
        onSuccess(message || "Copied.");
      } else if (message) {
        window.alert(message);
      }
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(function () {
        fallback();
        done();
      });
      return;
    }

    fallback();
    done();
  }

  function copyField(fieldId, message, onSuccess) {
    const element = document.getElementById(fieldId);
    if (!element) {
      return;
    }
    const value = "value" in element ? element.value : element.textContent || "";
    copyText(value, message, onSuccess);
  }

  function storageGet(key, fallback) {
    if (!key) {
      return fallback;
    }
    try {
      return window.localStorage.getItem(key) || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function storageSet(key, value) {
    if (!key) {
      return;
    }
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {}
  }

  function createPaginator(options) {
    const items = Array.from((options && options.items) || []);
    const pageSize = Number((options && options.pageSize) || 9);
    const controls = options ? options.controls : null;
    const empty = options ? options.empty : null;
    const storageKey = options ? options.storageKey : "";
    let currentPage = Number(storageGet(storageKey, "1")) || 1;

    function matchedItems() {
      return items.filter(function (item) {
        return item.dataset.filterVisible !== "0";
      });
    }

    function buttonClasses(isActive) {
      return [
        "inline-flex min-h-10 min-w-10 items-center justify-center rounded-full px-3 py-2 text-xs font-bold transition",
        isActive
          ? "bg-sand-600 text-sand-50"
          : "bg-white text-sand-700 ring-1 ring-sand-200 hover:bg-sand-50 hover:text-sand-950",
      ].join(" ");
    }

    function renderButton(label, page, disabled, active) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.className = buttonClasses(active);
      button.disabled = disabled;
      button.classList.toggle("cursor-not-allowed", disabled);
      button.classList.toggle("opacity-50", disabled);
      button.addEventListener("click", function () {
        if (disabled) {
          return;
        }
        currentPage = page;
        apply();
      });
      return button;
    }

    function renderControls(totalItems, totalPages) {
      if (!controls) {
        return;
      }
      controls.innerHTML = "";
      controls.classList.toggle("hidden", totalItems <= pageSize);
      if (totalItems <= pageSize) {
        return;
      }

      const summary = document.createElement("span");
      summary.className = "mr-2 text-sm font-bold text-sand-700";
      summary.textContent = "Page " + currentPage + " of " + totalPages;
      controls.appendChild(summary);

      controls.appendChild(renderButton("Prev", Math.max(1, currentPage - 1), currentPage <= 1, false));

      const startPage = Math.max(1, currentPage - 2);
      const endPage = Math.min(totalPages, currentPage + 2);
      if (startPage > 1) {
        controls.appendChild(renderButton("1", 1, false, currentPage === 1));
      }
      if (startPage > 2) {
        const spacer = document.createElement("span");
        spacer.className = "px-1 text-sm font-bold text-sand-500";
        spacer.textContent = "...";
        controls.appendChild(spacer);
      }
      for (let page = startPage; page <= endPage; page += 1) {
        controls.appendChild(renderButton(String(page), page, false, page === currentPage));
      }
      if (endPage < totalPages - 1) {
        const spacer = document.createElement("span");
        spacer.className = "px-1 text-sm font-bold text-sand-500";
        spacer.textContent = "...";
        controls.appendChild(spacer);
      }
      if (endPage < totalPages) {
        controls.appendChild(renderButton(String(totalPages), totalPages, false, currentPage === totalPages));
      }

      controls.appendChild(renderButton("Next", Math.min(totalPages, currentPage + 1), currentPage >= totalPages, false));
    }

    function apply() {
      const visibleItems = matchedItems();
      const totalPages = Math.max(1, Math.ceil(visibleItems.length / pageSize));
      currentPage = Math.min(Math.max(1, currentPage), totalPages);
      storageSet(storageKey, String(currentPage));

      const start = (currentPage - 1) * pageSize;
      const pagedItems = new Set(visibleItems.slice(start, start + pageSize));
      items.forEach(function (item) {
        item.classList.toggle("hidden", !pagedItems.has(item));
      });

      if (empty) {
        empty.classList.toggle("hidden", visibleItems.length !== 0);
      }
      renderControls(visibleItems.length, totalPages);
      return visibleItems.length;
    }

    return {
      refresh: apply,
      setPage: function (page) {
        currentPage = Number(page) || 1;
        return apply();
      },
      getPage: function () {
        return currentPage;
      },
    };
  }

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-loading-message]");
    if (!form) {
      return;
    }
    if (form.hasAttribute("data-background-submit")) {
      event.preventDefault();
      submitFormInBackground(form, event.submitter || null);
      return;
    }
    startFormLoading(form, form.dataset.loadingMessage);
  });

  document.addEventListener("click", function (event) {
    const stopButton = event.target.closest("[data-loading-stop]");
    if (stopButton) {
      event.preventDefault();
      stopCurrentGeneration();
      return;
    }

    const promptCopy = event.target.closest("[data-loading-prompt-copy]");
    if (promptCopy) {
      const panel = promptCopy.closest("[data-loading-prompt-panel]");
      const status = panel ? panel.querySelector("[data-loading-prompt-copy-status]") : null;
      copyText(latestLoadingPrompt, "Prompt copied.", function (message) {
        if (status) {
          status.textContent = message;
        }
      });
      return;
    }

    const promptToggle = event.target.closest("[data-loading-prompt-toggle]");
    if (promptToggle) {
      const panel = promptToggle.closest("[data-loading-prompt-panel]");
      const promptText = panel ? panel.querySelector("[data-loading-prompt-text]") : null;
      if (promptText) {
        const isHidden = promptText.classList.toggle("hidden");
        promptToggle.textContent = isHidden ? "Show prompt" : "Hide prompt";
      }
      return;
    }

    const button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }
    const statusId = button.dataset.copyStatus || "";
    const statusElement = statusId ? document.getElementById(statusId) : null;
    copyField(button.dataset.copyTarget, button.dataset.copyMessage, function (message) {
      if (statusElement) {
        statusElement.textContent = message;
      } else if (message) {
        window.alert(message);
      }
    });
  });

  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-print-trigger]");
    if (!button) {
      return;
    }
    window.print();
  });

  window.AppUi = {
    showLoading: showLoading,
    hideLoading: hideLoading,
    setLoadingStatus: setLoadingStatus,
    setLoadingPrompt: setLoadingPrompt,
    startFormLoading: startFormLoading,
    submitFormInBackground: submitFormInBackground,
    copyField: copyField,
    copyText: copyText,
    createPaginator: createPaginator,
  };

  window.addEventListener("load", hideLoading);
})();
