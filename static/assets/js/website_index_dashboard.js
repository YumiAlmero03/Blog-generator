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
  const pageSize = 50;
  let currentPage = 1;

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

  applyFilters();
})();
