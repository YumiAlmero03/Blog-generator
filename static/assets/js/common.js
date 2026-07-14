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
      actions.innerHTML = '<button type="button" class="inline-flex min-h-10 items-center justify-center rounded-full border border-red-200 bg-red-50 px-4 py-2 text-xs font-bold text-red-700 transition hover:bg-red-100" data-loading-stop>Skip Generating</button>';
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
  let activeLoadingForm = null;
  const lockedButtons = new WeakSet();
  let activeGenerationControlLocks = [];
  const temporaryButtonLockMs = 1200;
  const generationStatusPollDelay = 1500;
  let latestLoadingPrompt = "";
  let generationLogEntries = readInitialGenerationLog();

  function generationLogBoxes() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-generation-log]"));
  }

  function generationLogFields() {
    return Array.prototype.slice.call(document.querySelectorAll("textarea[name='generation_log_json'], input[name='generation_log_json']"));
  }

  function readInitialGenerationLog() {
    const box = document.querySelector("[data-generation-log]");
    if (!box || !box.dataset.generationLog) {
      return [];
    }
    try {
      const parsed = JSON.parse(box.dataset.generationLog);
      return Array.isArray(parsed) ? parsed.filter(function (item) {
        return item && typeof item === "object" && item.message;
      }).slice(-80) : [];
    } catch (error) {
      return [];
    }
  }

  function syncGenerationLogFields() {
    const value = JSON.stringify(generationLogEntries.slice(-80));
    generationLogFields().forEach(function (field) {
      field.value = value;
    });
  }

  function renderGenerationLog() {
    generationLogBoxes().forEach(function (box) {
      box.innerHTML = "";
      if (!generationLogEntries.length) {
        const empty = document.createElement("p");
        empty.className = "text-sm font-semibold leading-6 text-sand-500";
        empty.textContent = "No generation log yet.";
        box.appendChild(empty);
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
        box.appendChild(wrapper);
      });
      box.scrollTop = box.scrollHeight;
    });
  }

  function appendGenerationLog(kind, message) {
    const cleanedMessage = String(message || "").trim();
    if (!cleanedMessage || !generationLogBoxes().length) {
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

  function floatingStatusPanels() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-floating-generation-status]"));
  }

  function valueFromSelector(selector) {
    if (!selector) {
      return "";
    }
    const fields = Array.prototype.slice.call(document.querySelectorAll(selector));
    for (let index = 0; index < fields.length; index += 1) {
      const field = fields[index];
      if (!field) {
        continue;
      }
      let value = "";
      if (field.tagName === "SELECT") {
        const option = field.options[field.selectedIndex];
        value = option ? option.textContent : field.value;
      } else if ("value" in field) {
        value = field.value;
      } else {
        value = field.textContent || "";
      }
      value = String(value || "").replace(/\s+/g, " ").trim();
      if (value) {
        return value;
      }
    }
    return "";
  }

  function setFloatingStatus(panel, message) {
    const status = panel.querySelector("[data-floating-status-value]");
    const indicator = panel.querySelector("[data-floating-status-indicator]");
    const cleaned = String(message || panel.dataset.initialStatus || "Idle").trim() || "Idle";
    if (status) {
      status.textContent = cleaned;
    }
    if (indicator) {
      const normalized = cleaned.toLowerCase();
      indicator.classList.remove("bg-sand-300", "bg-blue-500", "bg-amber-500", "bg-green-500", "bg-red-500");
      if (normalized.includes("error") || normalized.includes("failed")) {
        indicator.classList.add("bg-red-500");
      } else if (normalized.includes("complete") || normalized.includes("loading generated result")) {
        indicator.classList.add("bg-green-500");
      } else if (normalized.includes("queued") || normalized.includes("generating") || normalized.includes("starting") || normalized.includes("running")) {
        indicator.classList.add("bg-blue-500");
      } else if (normalized.includes("skip") || normalized.includes("cancel")) {
        indicator.classList.add("bg-amber-500");
      } else {
        indicator.classList.add("bg-sand-300");
      }
    }
  }

  function refreshFloatingGenerationStatus() {
    floatingStatusPanels().forEach(function (panel) {
      const keyword = panel.querySelector("[data-floating-keyword-value]");
      const brand = panel.querySelector("[data-floating-brand-value]");
      const language = panel.querySelector("[data-floating-language-value]");
      const keywordLabel = panel.querySelector("[data-floating-keyword-label]");
      if (keywordLabel && panel.dataset.keywordLabel) {
        keywordLabel.textContent = panel.dataset.keywordLabel;
      }
      if (keyword) {
        keyword.textContent = valueFromSelector(panel.dataset.keywordSelector) || "Not set";
      }
      if (brand) {
        brand.textContent = valueFromSelector(panel.dataset.brandSelector) || "Not set";
      }
      if (language) {
        language.textContent = valueFromSelector(panel.dataset.languageSelector) || "Not set";
      }
      setFloatingStatus(panel, panel.dataset.currentStatus || panel.dataset.initialStatus || "Idle");
    });
  }

  function updateFloatingGenerationStatus(message) {
    floatingStatusPanels().forEach(function (panel) {
      panel.dataset.currentStatus = String(message || "").trim() || panel.dataset.initialStatus || "Idle";
      setFloatingStatus(panel, panel.dataset.currentStatus);
    });
  }

  function usesInlineLoading() {
    return activeLoadingForm && activeLoadingForm.hasAttribute("data-inline-loading");
  }

  function getInlineTarget(attributeName) {
    if (!activeLoadingForm) {
      return null;
    }
    const selector = activeLoadingForm.dataset[attributeName] || "";
    if (!selector) {
      return null;
    }
    return document.querySelector(selector);
  }

  function setLoadingStatus(message) {
    const cleanedMessage = String(message || "");
    if (cleanedMessage) {
      document.dispatchEvent(new CustomEvent("app:generation-status", { detail: { message: cleanedMessage } }));
      appendGenerationLog("status", cleanedMessage);
    }
    if (usesInlineLoading() && ["Queued in background...", "Generating..."].includes(cleanedMessage)) {
      return;
    }
    if (usesInlineLoading()) {
      const status = getInlineTarget("inlineStatusTarget");
      if (status) {
        status.textContent = cleanedMessage;
        status.classList.toggle("hidden", !cleanedMessage);
      }
      return;
    }
    const status = getOverlayStatus();
    if (status) {
      status.textContent = cleanedMessage;
    }
  }

  function setLoadingError(message) {
    const cleanedMessage = String(message || "");
    if (usesInlineLoading()) {
      const error = getInlineTarget("inlineErrorTarget");
      if (error) {
        error.textContent = cleanedMessage;
        error.classList.toggle("hidden", !cleanedMessage);
      } else if (cleanedMessage) {
        setLoadingStatus(cleanedMessage);
      }
      return;
    }
    if (cleanedMessage) {
      setLoadingStatus(cleanedMessage);
    }
  }

  function setLoadingPrompt(prompt) {
    latestLoadingPrompt = prompt || "";
    if (latestLoadingPrompt) {
      document.dispatchEvent(new CustomEvent("app:generation-prompt", { detail: { prompt: latestLoadingPrompt } }));
      appendGenerationLog("prompt", latestLoadingPrompt);
    }
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
    if (usesInlineLoading()) {
      setLoadingStatus(message || "Generating...");
      setLoadingPrompt("");
      const actions = getInlineTarget("inlineActionsTarget");
      if (actions) {
        actions.classList.remove("hidden");
      }
      return;
    }
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
    const actions = getInlineTarget("inlineActionsTarget");
    if (actions) {
      actions.classList.add("hidden");
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
    unlockGenerationControls();
    updateFloatingGenerationStatus("Idle");
    setLoadingStatus("");
    activeLoadingForm = null;
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
      activeLoadingForm = null;
      showLoading(message);
      return "";
    }
    activeLoadingForm = form;
    const token = ensureStatusToken(form);
    currentGenerationToken = token;
    loadingResultHandled = false;
    loadingUsesBackgroundJob = false;
    showLoading(message || form.dataset.loadingMessage);
    startStatusEvents(token);
    return token;
  }

  function isButtonLike(element) {
    return element && element.matches && element.matches("button, input[type='submit'], input[type='button'], input[type='reset'], a[role='button']");
  }

  function isSubmitControl(element) {
    if (!element || !element.matches) {
      return false;
    }
    if (element.matches("input[type='submit']")) {
      return true;
    }
    if (!element.matches("button")) {
      return false;
    }
    const type = (element.getAttribute("type") || "submit").toLowerCase();
    return type === "submit";
  }

  function shouldSkipClickLock(element) {
    if (!element || !element.matches) {
      return true;
    }
    return element.matches([
      "[data-loading-stop]",
      "[data-loading-prompt-toggle]",
      "[data-loading-prompt-copy]",
      "[data-generation-log-clear]",
      "[data-copy-target]",
      "[data-background-jobs-toggle]",
      "[data-output-view-button]",
      "[data-keyword-suggestion]",
      "[data-generate-action]",
      "#generateContentButton",
      "#generateMetaDescriptionsButton",
      "[data-no-click-lock]",
    ].join(","));
  }

  function lockButton(button, label, disableControl) {
    if (!isButtonLike(button) || lockedButtons.has(button)) {
      return false;
    }
    const shouldDisable = disableControl !== false;
    lockedButtons.add(button);
    button.dataset.clickLocked = "1";
    if (label && "textContent" in button && !button.dataset.originalText) {
      button.dataset.originalText = button.textContent;
      button.textContent = label;
    }
    if (shouldDisable && "disabled" in button) {
      button.disabled = true;
    }
    button.setAttribute("aria-disabled", "true");
    button.classList.add("pointer-events-none", "cursor-not-allowed", "opacity-60");
    return true;
  }

  function unlockButton(button) {
    if (!isButtonLike(button)) {
      return;
    }
    lockedButtons.delete(button);
    delete button.dataset.clickLocked;
    if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
      delete button.dataset.originalText;
    }
    if ("disabled" in button) {
      button.disabled = false;
    }
    button.removeAttribute("aria-disabled");
    button.classList.remove("pointer-events-none", "cursor-not-allowed", "opacity-60");
  }

  function lockButtonTemporarily(button) {
    if (!lockButton(button)) {
      return false;
    }
    window.setTimeout(function () {
      unlockButton(button);
    }, temporaryButtonLockMs);
    return true;
  }

  function generationControlSelector() {
    return [
      "form[data-background-submit] button[type='submit']",
      "form[data-background-submit] input[type='submit']",
      "form[data-background-submit] button:not([type])",
      "[data-generate-action]",
      "#generateContentButton",
      "#generateMetaDescriptionsButton",
    ].join(",");
  }

  function lockGenerationControls(activeForm, activeSubmitter) {
    unlockGenerationControls();
    const controls = Array.prototype.slice.call(document.querySelectorAll(generationControlSelector()));
    const seen = new Set();
    controls.forEach(function (control) {
      if (!isButtonLike(control) || seen.has(control)) {
        return;
      }
      if (control.matches("[data-loading-stop], [data-no-generation-lock]")) {
        return;
      }
      seen.add(control);
      activeGenerationControlLocks.push({
        control: control,
        disabled: "disabled" in control ? control.disabled : null,
        ariaDisabled: control.getAttribute("aria-disabled"),
        text: control.textContent,
      });
      const isActive = control === activeSubmitter || (activeForm && activeForm.contains(control) && isSubmitControl(control));
      if (isActive && control.textContent && !control.dataset.originalGeneratingText) {
        control.dataset.originalGeneratingText = control.textContent;
        control.textContent = "Generating...";
      }
      if ("disabled" in control) {
        control.disabled = true;
      }
      control.setAttribute("aria-disabled", "true");
      control.classList.add("pointer-events-none", "cursor-not-allowed", "opacity-60");
    });
  }

  function unlockGenerationControls() {
    activeGenerationControlLocks.forEach(function (entry) {
      const control = entry.control;
      if (!isButtonLike(control)) {
        return;
      }
      if ("disabled" in control && entry.disabled !== null) {
        control.disabled = entry.disabled;
      }
      if (entry.ariaDisabled === null) {
        control.removeAttribute("aria-disabled");
      } else {
        control.setAttribute("aria-disabled", entry.ariaDisabled);
      }
      if (control.dataset.originalGeneratingText) {
        control.textContent = control.dataset.originalGeneratingText;
        delete control.dataset.originalGeneratingText;
      } else if (entry.text != null) {
        control.textContent = entry.text;
      }
      control.classList.remove("pointer-events-none", "cursor-not-allowed", "opacity-60");
    });
    activeGenerationControlLocks = [];
  }

  function lockFormSubmit(form, submitter) {
    if (!form || form.dataset.submitting === "1") {
      return false;
    }
    form.dataset.submitting = "1";
    const button = isButtonLike(submitter) ? submitter : form.querySelector("button[type='submit'], input[type='submit']");
    if (button) {
      lockButton(button, null, false);
    }
    return true;
  }

  function unlockFormSubmit(form, submitter) {
    if (form) {
      delete form.dataset.submitting;
    }
    if (isButtonLike(submitter)) {
      unlockButton(submitter);
    } else if (form) {
      form.querySelectorAll("button[type='submit'], input[type='submit']").forEach(unlockButton);
    }
  }

  function setLoadingDraft(html) {
    document.dispatchEvent(new CustomEvent("app:generation-draft", { detail: { html: html } }));
    if (usesInlineLoading()) {
      return;
    }
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
      setLoadingStatus("No running generation to skip.");
      return;
    }
    setLoadingStatus("Skipping current generation...");
    document.querySelectorAll("[data-loading-stop]").forEach(function (button) {
      button.disabled = true;
      button.classList.add("cursor-not-allowed", "opacity-60");
      button.textContent = "Skip requested";
    });
    fetch("/generation-status/" + encodeURIComponent(currentGenerationToken) + "/cancel", {
      method: "POST",
      headers: { Accept: "application/json" },
    }).catch(function () {
      setLoadingStatus("Could not send skip request.");
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
    const message = submitter && submitter.dataset && submitter.dataset.loadingMessage
      ? submitter.dataset.loadingMessage
      : form.dataset.loadingMessage;
    const token = startFormLoading(form, message);
    loadingUsesBackgroundJob = true;
    lockGenerationControls(form, submitter);
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
    lockButton(submitter);
    formData.set("generation_status_token", token);
    formData.set("_background_path", form.getAttribute("action") || window.location.pathname + window.location.search);

    fetch("/background-jobs", {
      method: "POST",
      body: formData,
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () {
            return {};
          }).then(function (payload) {
            throw new Error(payload.error || "Could not start background job.");
          });
        }
        return response.json();
      })
      .then(function (payload) {
        if (!payload || !payload.id) {
          throw new Error(payload && payload.error ? payload.error : "Background job did not return an id.");
        }
        pollBackgroundJob(payload.id);
      })
      .catch(function (error) {
        setLoadingError(error.message || "Could not start background job.");
        unlockGenerationControls();
        unlockFormSubmit(form, submitter);
        if (!usesInlineLoading()) {
          window.setTimeout(hideLoading, 1800);
        }
      });
  }

  function pollBackgroundJob(jobId) {
    if (!jobId) {
      setLoadingStatus("Background job did not return an id.");
      unlockGenerationControls();
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
            setLoadingError(payload.error || "Background generation failed.");
            unlockGenerationControls();
            unlockFormSubmit(activeLoadingForm, null);
            if (!usesInlineLoading()) {
              window.setTimeout(hideLoading, 2200);
            }
            return;
          }
          if (payload.status === "cancelled") {
            setLoadingStatus(payload.error || payload.message || "Generation stopped.");
            unlockGenerationControls();
            unlockFormSubmit(activeLoadingForm, null);
            return;
          }
          window.setTimeout(poll, 1200);
        })
        .catch(function (error) {
          setLoadingError(error.message || "Background job status failed.");
          unlockGenerationControls();
          unlockFormSubmit(activeLoadingForm, null);
          if (!usesInlineLoading()) {
            window.setTimeout(hideLoading, 2200);
          }
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
    const form = event.target.closest("form");
    if (!form) {
      return;
    }
    if (form.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    if (form.hasAttribute("data-background-submit")) {
      event.preventDefault();
      form.dataset.submitting = "1";
      submitFormInBackground(form, event.submitter || null);
      return;
    }
    lockFormSubmit(form, event.submitter || null);
    if (!form.hasAttribute("data-loading-message")) {
      return;
    }
    const message = event.submitter && event.submitter.dataset && event.submitter.dataset.loadingMessage
      ? event.submitter.dataset.loadingMessage
      : form.dataset.loadingMessage;
    startFormLoading(form, message);
  });

  document.addEventListener("input", refreshFloatingGenerationStatus);
  document.addEventListener("change", refreshFloatingGenerationStatus);
  document.addEventListener("app:generation-status", function (event) {
    updateFloatingGenerationStatus(event.detail && event.detail.message ? event.detail.message : "");
    refreshFloatingGenerationStatus();
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshFloatingGenerationStatus);
  } else {
    refreshFloatingGenerationStatus();
  }

  document.addEventListener("click", function (event) {
    const clickedButton = event.target.closest("button, input[type='button'], input[type='reset'], a[role='button']");
    if (clickedButton && lockedButtons.has(clickedButton)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (clickedButton && !isSubmitControl(clickedButton) && !shouldSkipClickLock(clickedButton)) {
      lockButtonTemporarily(clickedButton);
    }
  }, true);

  document.addEventListener("click", function (event) {
    const clearLogButton = event.target.closest("[data-generation-log-clear]");
    if (clearLogButton) {
      event.preventDefault();
      generationLogEntries = [];
      renderGenerationLog();
      syncGenerationLogFields();
      return;
    }

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
