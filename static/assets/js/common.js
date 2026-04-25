(function () {
  function getOverlay() {
    return document.querySelector("[data-loading-overlay]");
  }

  function getOverlayText() {
    return document.querySelector("[data-loading-text]");
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
    overlay.classList.add("active");
  }

  function hideLoading() {
    const overlay = getOverlay();
    if (overlay) {
      overlay.classList.remove("active");
    }
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
    showLoading(form.dataset.loadingMessage);
  });

  document.addEventListener("click", function (event) {
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
    copyField: copyField,
    copyText: copyText,
  };

  window.addEventListener("load", hideLoading);
})();
