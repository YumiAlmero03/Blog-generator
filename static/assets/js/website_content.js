(function () {
  const form = document.getElementById('website-content-form');
  form.addEventListener('submit', function () {
    document.getElementById('collect-content').disabled = true;
    document.getElementById('crawl-status').hidden = false;
  });
  const download = document.getElementById('download-content-csv');
  if (!download) return;
  download.addEventListener('click', function () {
    const rows = JSON.parse(document.getElementById('website-content-rows').textContent);
    function cell(value) {
      let text = String(value || '');
      // Prevent spreadsheet formula execution in metadata from external sites.
      if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    }
    const csv = [['Post Date', 'Title', 'Meta Description'], ...rows]
      .map(row => row.map(cell).join(',')).join('\r\n') + '\r\n';
    const url = URL.createObjectURL(new Blob(['\ufeff', csv], {type: 'text/csv;charset=utf-8;'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'website-content-metadata.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
