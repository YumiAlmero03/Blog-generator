(function () {
  const copyButton = document.getElementById("copySimpleHtmlButton");
  if (copyButton) {
    copyButton.addEventListener("click", function () {
      window.AppUi.copyField("htmlOutput", "HTML copied. You can now paste it into WordPress Gutenberg.");
    });
  }
})();
