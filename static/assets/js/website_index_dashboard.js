(function () {
  const rows = Array.from(document.querySelectorAll("[data-website-index-row]"));
  const searchInput = document.getElementById("websiteIndexSearch");
  const domainFilter = document.getElementById("websiteIndexDomainFilter");
  const weeklyFilter = document.getElementById("websiteIndexWeeklyFilter");
  const googleFilter = document.getElementById("websiteIndexGoogleFilter");
  const bingFilter = document.getElementById("websiteIndexBingFilter");
  const yahooFilter = document.getElementById("websiteIndexYahooFilter");
  const countText = document.getElementById("websiteIndexFilterCount");
  const emptyMessage = document.getElementById("websiteIndexEmptyFilter");
  const prevPageButton = document.getElementById("websiteIndexPrevPage");
  const nextPageButton = document.getElementById("websiteIndexNextPage");
  const pageStatus = document.getElementById("websiteIndexPageStatus");
  const downloadCsvButton = document.getElementById("websiteIndexDownloadCsv");
  const pageSize = 50;
  let currentPage = 1;
  let matchedRowsCache = [];

  if (!rows.length) {
    return;
  }

  function value(element) {
    return element ? element.value.trim().toLowerCase() : "";
  }

  function applyFilters() {
    const query = value(searchInput);
    const domain = value(domainFilter);
    const weekly = value(weeklyFilter);
    const google = value(googleFilter);
    const bing = value(bingFilter);
    const yahoo = value(yahooFilter);
    const matchedRows = [];

    rows.forEach(function (row) {
      const matches = (!query || row.dataset.search.includes(query))
        && (!domain || row.dataset.domain === domain)
        && (!weekly || row.dataset.weekly === weekly)
        && (!google || row.dataset.google === google)
        && (!bing || row.dataset.bing === bing)
        && (!yahoo || row.dataset.yahoo === yahoo);
      if (matches) {
        matchedRows.push(row);
      }
    });

    matchedRows.sort(function (first, second) {
      const firstPriority = Number(first.dataset.priority || "1");
      const secondPriority = Number(second.dataset.priority || "1");
      if (firstPriority !== secondPriority) {
        return firstPriority - secondPriority;
      }
      const firstChecked = first.dataset.lastChecked || "";
      const secondChecked = second.dataset.lastChecked || "";
      if (!firstChecked && secondChecked) {
        return -1;
      }
      if (firstChecked && !secondChecked) {
        return 1;
      }
      return firstChecked.localeCompare(secondChecked);
    });
    matchedRowsCache = matchedRows;

    const totalPages = Math.max(1, Math.ceil(matchedRows.length / pageSize));
    currentPage = Math.min(Math.max(1, currentPage), totalPages);
    const start = (currentPage - 1) * pageSize;
    const pagedRows = new Set(matchedRows.slice(start, start + pageSize));

    rows.forEach(function (row) {
      row.classList.toggle("hidden", !pagedRows.has(row));
    });

    if (countText) {
      countText.textContent = matchedRows.length + " of " + rows.length + " URL" + (rows.length === 1 ? "" : "s") + " match filters";
    }
    if (emptyMessage) {
      emptyMessage.classList.toggle("hidden", matchedRows.length !== 0);
    }
    if (pageStatus) {
      pageStatus.textContent = matchedRows.length ? "Page " + currentPage + " of " + totalPages + " · 50 per page" : "No results";
    }
    if (prevPageButton) {
      prevPageButton.disabled = currentPage <= 1;
      prevPageButton.classList.toggle("opacity-50", currentPage <= 1);
    }
    if (nextPageButton) {
      nextPageButton.disabled = currentPage >= totalPages;
      nextPageButton.classList.toggle("opacity-50", currentPage >= totalPages);
    }
    if (downloadCsvButton) {
      downloadCsvButton.disabled = matchedRows.length === 0;
      downloadCsvButton.classList.toggle("opacity-50", matchedRows.length === 0);
    }
  }

  function csvCell(value) {
    const text = String(value || "");
    if (/[",\n\r]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function rowToCsvRecord(row) {
    return [
      row.dataset.url || "",
      row.dataset.domain || "",
      row.dataset.status || "",
      row.dataset.weekly || "",
      row.dataset.google || "",
      row.dataset.bing || "",
      row.dataset.yahoo || "",
      row.dataset.coverage || "",
      row.dataset.lastChecked || "",
      row.dataset.lastCrawl || "",
    ];
  }

  function downloadFilteredCsv() {
    const headers = [
      "url",
      "domain",
      "check_status",
      "due_status",
      "google_status",
      "bing_status",
      "yahoo_status",
      "coverage",
      "last_checked_at",
      "google_last_crawl_time",
    ];
    const lines = [headers].concat(matchedRowsCache.map(rowToCsvRecord)).map(function (record) {
      return record.map(csvCell).join(",");
    });
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 10);
    link.href = URL.createObjectURL(blob);
    link.download = "website-index-dashboard-" + stamp + ".csv";
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(link.href);
    link.remove();
  }

  [searchInput, domainFilter, weeklyFilter, googleFilter, bingFilter, yahooFilter].forEach(function (element) {
    if (!element) {
      return;
    }
    element.addEventListener("input", function () {
      currentPage = 1;
      applyFilters();
    });
    element.addEventListener("change", function () {
      currentPage = 1;
      applyFilters();
    });
  });

  if (prevPageButton) {
    prevPageButton.addEventListener("click", function () {
      currentPage -= 1;
      applyFilters();
    });
  }
  if (nextPageButton) {
    nextPageButton.addEventListener("click", function () {
      currentPage += 1;
      applyFilters();
    });
  }
  if (downloadCsvButton) {
    downloadCsvButton.addEventListener("click", downloadFilteredCsv);
  }

  applyFilters();
})();
