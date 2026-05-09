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

  let loadingEventSource = null;
  let loadingStatusPoll = null;
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
    if (loadingStatusPoll) {
      window.clearInterval(loadingStatusPoll);
      loadingStatusPoll = null;
    }
    setLoadingStatus("");
    setLoadingPrompt("");
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
    loadingEventSource = new EventSource("/events/generation/" + encodeURIComponent(token));
    loadingEventSource.onmessage = function (event) {
      try {
        const payload = JSON.parse(event.data || "{}");
        if (payload && payload.message) {
          setLoadingStatus(payload.message);
        }
        if (payload && typeof payload.prompt === "string") {
          setLoadingPrompt(payload.prompt);
        }
      } catch (error) {}
    };
    loadingEventSource.onerror = function () {};
    startStatusPolling(token);
  }

  function startStatusPolling(token) {
    if (loadingStatusPoll) {
      window.clearInterval(loadingStatusPoll);
    }

    const poll = function () {
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
          }
          if (typeof payload.prompt === "string" && payload.prompt) {
            setLoadingPrompt(payload.prompt);
          }
        })
        .catch(function () {});
    };

    poll();
    loadingStatusPoll = window.setInterval(poll, 1500);
  }

  function startFormLoading(form, message) {
    if (!form) {
      showLoading(message);
      return "";
    }
    const token = ensureStatusToken(form);
    showLoading(message || form.dataset.loadingMessage);
    startStatusEvents(token);
    return token;
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

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("form[data-loading-message]");
    if (!form) {
      return;
    }
    startFormLoading(form, form.dataset.loadingMessage);
  });

  document.addEventListener("click", function (event) {
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
    copyField: copyField,
    copyText: copyText,
  };

  window.addEventListener("load", hideLoading);
})();
