(function () {
  const htmlCopyButton = document.getElementById("copyHtmlButton");
  if (htmlCopyButton) {
    htmlCopyButton.addEventListener("click", function () {
      window.AppUi.copyField("htmlOutput", "HTML copied. You can now paste it into WordPress Gutenberg.");
    });
  }
})();
