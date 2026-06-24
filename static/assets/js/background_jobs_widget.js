(function () {
  const widget = document.querySelector("[data-background-jobs-widget]");
  if (!widget) {
    return;
  }

  const toggle = widget.querySelector("[data-background-jobs-toggle]");
  const panel = widget.querySelector("[data-background-jobs-panel]");
  const body = widget.querySelector("[data-background-jobs-body]");
  const summary = widget.querySelector("[data-background-jobs-summary]");
  const count = widget.querySelector("[data-background-jobs-count]");
  const indicator = widget.querySelector("[data-background-jobs-indicator]");
  const live = widget.querySelector("[data-background-jobs-live]");
  const storageKey = "backgroundJobsWidgetExpanded";
  let isLoading = false;

  const escapeHtml = function (value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  const statusClass = function (status) {
    if (status === "running") {
      return "bg-blue-100 text-blue-700";
    }
    if (status === "queued") {
      return "bg-amber-100 text-amber-700";
    }
    if (status === "complete") {
      return "bg-green-100 text-green-700";
    }
    if (status === "cancelled") {
      return "bg-sand-100 text-sand-700";
    }
    return "bg-red-100 text-red-700";
  };

  const jobLabel = function (path) {
    const cleaned = String(path || "").replace(/^\//, "") || "background-job";
    return cleaned
      .split("?")[0]
      .replace(/-/g, " ")
      .replace(/\b\w/g, function (letter) {
        return letter.toUpperCase();
      });
  };

  const setExpanded = function (expanded) {
    widget.dataset.widgetState = expanded ? "expanded" : "collapsed";
    if (panel) {
      panel.classList.toggle("hidden", !expanded);
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
    try {
      window.localStorage.setItem(storageKey, expanded ? "1" : "0");
    } catch (error) {}
  };

  const renderSummary = function (stats) {
    const running = Number(stats.running || 0);
    const queued = Number(stats.queued || 0);
    const active = running + queued;
    const total = Number(stats.total || 0);
    if (count) {
      count.textContent = String(active || total || 0);
    }
    if (summary) {
      if (active) {
        summary.textContent = running + " running, " + queued + " queued";
      } else if (total) {
        summary.textContent = "No active jobs. " + total + " stored.";
      } else {
        summary.textContent = "No background jobs.";
      }
    }
    if (indicator) {
      indicator.className = "inline-flex h-3 w-3 rounded-full " + (active ? "bg-blue-500" : total ? "bg-green-500" : "bg-sand-300");
    }
  };

  const renderJobs = function (jobs) {
    if (!body) {
      return;
    }
    const items = Array.isArray(jobs) ? jobs.slice(0, 12) : [];
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="3" class="px-3 py-4 text-center text-sm text-sand-600">No background jobs yet.</td></tr>';
      return;
    }
    body.innerHTML = items.map(function (job) {
      const status = String(job.status || "unknown");
      const message = job.error || job.message || "";
      return [
        "<tr>",
        '<td class="whitespace-nowrap px-3 py-2 align-top">',
        '<span class="rounded-full px-2 py-1 text-[11px] font-extrabold uppercase tracking-[0.08em] ' + statusClass(status) + '">' + escapeHtml(status) + "</span>",
        "</td>",
        '<td class="max-w-[120px] px-3 py-2 align-top font-bold text-sand-900">' + escapeHtml(jobLabel(job.path)) + "</td>",
        '<td class="max-w-[220px] px-3 py-2 align-top text-sand-700">' + escapeHtml(message) + (job.repeat_reason ? '<div class="mt-1 text-[11px] font-bold text-amber-700">Retry: ' + escapeHtml(job.repeat_reason) + "</div>" : "") + "</td>",
        "</tr>",
      ].join("");
    }).join("");
  };

  const refresh = function () {
    if (isLoading) {
      return;
    }
    isLoading = true;
    fetch("/background-jobs-dashboard/data", { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Background jobs update failed.");
        }
        return response.json();
      })
      .then(function (payload) {
        renderSummary(payload.stats || {});
        renderJobs(payload.jobs || []);
        if (live) {
          live.textContent = "Live updates on";
        }
      })
      .catch(function () {
        if (live) {
          live.textContent = "Live update paused";
        }
      })
      .then(function () {
        isLoading = false;
      });
  };

  if (toggle) {
    toggle.addEventListener("click", function () {
      setExpanded(widget.dataset.widgetState !== "expanded");
    });
  }

  try {
    setExpanded(window.localStorage.getItem(storageKey) === "1");
  } catch (error) {
    setExpanded(false);
  }
  refresh();
  window.setInterval(refresh, 5000);
})();
