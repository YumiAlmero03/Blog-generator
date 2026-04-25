(function () {
  const textInput = document.getElementById("textInput");
  const statusText = document.getElementById("statusText");

  if (!textInput || !statusText) {
    return;
  }

  function setStatus(message) {
    statusText.textContent = message;
  }

  function applyTransform(transformer, message) {
    textInput.value = transformer(textInput.value);
    setStatus(message);
    textInput.focus();
  }

  function unhyphenText(value) {
    return value.replace(/-/g, " ");
  }

  function unsnakeText(value) {
    return value.replace(/_/g, " ");
  }

  function capitalizeText(value) {
    const trimmedStart = value.match(/^\s*/)[0];
    const rest = value.slice(trimmedStart.length);
    if (!rest) {
      return value;
    }
    return trimmedStart + rest.charAt(0).toUpperCase() + rest.slice(1);
  }

  function titleCaseText(value) {
    return value.toLowerCase().replace(/\b([a-z])/g, function (match) {
      return match.toUpperCase();
    });
  }

  function sentenceCaseText(value) {
    const lower = value.toLowerCase();
    return lower.replace(/(^\s*[a-z])|([.!?]\s+[a-z])/g, function (match) {
      return match.toUpperCase();
    });
  }

  document.querySelectorAll("[data-transform]").forEach(function (button) {
    button.addEventListener("click", function () {
      const action = button.dataset.transform;
      if (action === "unhyphen") {
        applyTransform(unhyphenText, "Hyphens replaced with spaces.");
      } else if (action === "unsnake") {
        applyTransform(unsnakeText, "Underscores replaced with spaces.");
      } else if (action === "capitalize") {
        applyTransform(capitalizeText, "First letter capitalized.");
      } else if (action === "upper") {
        applyTransform(function (value) { return value.toUpperCase(); }, "Changed to upper case.");
      } else if (action === "lower") {
        applyTransform(function (value) { return value.toLowerCase(); }, "Changed to lower case.");
      } else if (action === "title") {
        applyTransform(titleCaseText, "Changed to title case.");
      } else if (action === "sentence") {
        applyTransform(sentenceCaseText, "Changed to sentence case.");
      }
    });
  });

  const copyButton = document.getElementById("copyTextButton");
  if (copyButton) {
    copyButton.addEventListener("click", function () {
      window.AppUi.copyText(textInput.value, "Text copied.", setStatus);
    });
  }
})();
