import json
import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from logger import logger


INDEXNOW_BATCH_LIMIT = 10000
DEFAULT_INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
GOOGLE_INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
GOOGLE_URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
GOOGLE_INDEXING_SCOPE = "https://www.googleapis.com/auth/indexing"
GOOGLE_WEBMASTERS_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
URL_PATTERN = re.compile(r"https?://[^\s,\"'<>]+", re.IGNORECASE)
KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


@dataclass
class IndexNowBatchResult:
    batch_number: int
    submitted_count: int
    status_code: int | None
    status: str
    detail: str


@dataclass
class IndexNowSubmissionResult:
    host: str
    submitted_count: int
    duplicate_count: int
    skipped: list[str]
    batches: list[IndexNowBatchResult]

    @property
    def ok(self) -> bool:
        return bool(self.batches) and all(batch.status in {"ok", "accepted"} for batch in self.batches)


@dataclass
class GoogleIndexingItemResult:
    url: str
    status_code: int | None
    status: str
    detail: str


@dataclass
class GoogleIndexingSubmissionResult:
    submitted_count: int
    skipped: list[str]
    items: list[GoogleIndexingItemResult]

    @property
    def ok(self) -> bool:
        return bool(self.items) and all(item.status == "ok" for item in self.items)


@dataclass
class GoogleInspectionItemResult:
    url: str
    status_code: int | None
    status: str
    verdict: str
    coverage_state: str
    robots_txt_state: str
    indexing_state: str
    last_crawl_time: str
    detail: str


@dataclass
class GoogleInspectionResult:
    inspected_count: int
    skipped: list[str]
    items: list[GoogleInspectionItemResult]


def extract_urls(*texts: str) -> list[str]:
    urls = []
    for text in texts:
        for match in URL_PATTERN.findall(text or ""):
            urls.append(match.rstrip(").,;]"))
    return urls


def normalize_host(host: str) -> str:
    cleaned = (host or "").strip()
    if not cleaned:
        return ""
    if "://" in cleaned:
        cleaned = urlparse(cleaned).netloc
    return cleaned.strip("/").lower()


def infer_host(urls: Iterable[str]) -> str:
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return parsed.netloc.lower()
    return ""


def validate_key(key: str) -> str:
    cleaned = (key or "").strip()
    if not KEY_PATTERN.match(cleaned):
        raise ValueError("IndexNow key must be 8-128 characters and use only letters, numbers, or dashes.")
    return cleaned


def filter_host_urls(urls: list[str], host: str) -> tuple[list[str], list[str]]:
    seen = set()
    valid = []
    skipped = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            skipped.append(f"{url} - not a valid http or https URL")
            continue
        if parsed.netloc.lower() != host:
            skipped.append(f"{url} - host does not match {host}")
            continue
        valid.append(url)
    return valid, skipped


def submit_indexnow_urls(
    urls: list[str],
    key: str,
    host: str = "",
    key_location: str = "",
    endpoint: str = DEFAULT_INDEXNOW_ENDPOINT,
    timeout: int = 30,
) -> IndexNowSubmissionResult:
    key = validate_key(key)
    submitted_host = normalize_host(host) or infer_host(urls)
    if not submitted_host:
        raise ValueError("Enter a host or include at least one valid URL so the host can be detected.")

    valid_urls, skipped = filter_host_urls(urls, submitted_host)
    if not valid_urls:
        raise ValueError("No URLs matched the selected host.")

    duplicate_count = len(urls) - len(set(urls))
    batches = []
    endpoint = (endpoint or DEFAULT_INDEXNOW_ENDPOINT).strip()

    for start in range(0, len(valid_urls), INDEXNOW_BATCH_LIMIT):
        url_batch = valid_urls[start : start + INDEXNOW_BATCH_LIMIT]
        payload = {
            "host": submitted_host,
            "key": key,
            "urlList": url_batch,
        }
        if key_location.strip():
            payload["keyLocation"] = key_location.strip()

        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        batch_number = (start // INDEXNOW_BATCH_LIMIT) + 1
        try:
            with urlopen(request, timeout=timeout) as response:
                status_code = response.getcode()
                status = "ok" if status_code == 200 else "accepted" if status_code == 202 else "check"
                detail = _status_detail(status_code)
        except HTTPError as exc:
            status_code = exc.code
            status = "error"
            detail = _status_detail(exc.code)
        except URLError as exc:
            status_code = None
            status = "error"
            detail = str(exc.reason) if getattr(exc, "reason", None) else "Could not reach IndexNow endpoint."

        batches.append(
            IndexNowBatchResult(
                batch_number=batch_number,
                submitted_count=len(url_batch),
                status_code=status_code,
                status=status,
                detail=detail,
            )
        )

    return IndexNowSubmissionResult(
        host=submitted_host,
        submitted_count=len(valid_urls),
        duplicate_count=duplicate_count,
        skipped=skipped,
        batches=batches,
    )


def submit_google_indexing_urls(
    urls: list[str],
    access_token: str,
    service_account_json: str = "",
    notification_type: str = "URL_UPDATED",
    endpoint: str = GOOGLE_INDEXING_ENDPOINT,
    timeout: int = 30,
) -> GoogleIndexingSubmissionResult:
    token = (access_token or "").strip() or google_access_token_from_service_account_json(service_account_json)
    if not token:
        raise ValueError("Enter a Google OAuth access token or paste/upload a service account JSON key for the Indexing API.")
    if notification_type not in {"URL_UPDATED", "URL_DELETED"}:
        raise ValueError("Google notification type must be URL_UPDATED or URL_DELETED.")

    valid_urls = []
    skipped = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            skipped.append(f"{url} - not a valid http or https URL")
            continue
        valid_urls.append(url)

    if not valid_urls:
        raise ValueError("No valid URLs were found.")

    items = []
    for url in valid_urls:
        payload = {"url": url, "type": notification_type}
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout) as response:
                status_code = response.getcode()
                status = "ok" if 200 <= status_code < 300 else "check"
                detail = "Google received the indexing notification." if status == "ok" else "Google returned an unexpected response."
        except HTTPError as exc:
            status_code = exc.code
            status = "error"
            detail = _google_status_detail(exc.code)
        except URLError as exc:
            status_code = None
            status = "error"
            detail = str(exc.reason) if getattr(exc, "reason", None) else "Could not reach Google Indexing API."

        items.append(
            GoogleIndexingItemResult(
                url=url,
                status_code=status_code,
                status=status,
                detail=detail,
            )
        )

    return GoogleIndexingSubmissionResult(
        submitted_count=len(valid_urls),
        skipped=skipped,
        items=items,
    )


def inspect_google_index_status(
    urls: list[str],
    site_url: str,
    access_token: str = "",
    service_account_json: str = "",
    language_code: str = "en-US",
    endpoint: str = GOOGLE_URL_INSPECTION_ENDPOINT,
    timeout: int = 30,
) -> GoogleInspectionResult:
    token = (access_token or "").strip() or google_access_token_from_service_account_json(
        service_account_json,
        scopes=[GOOGLE_WEBMASTERS_READONLY_SCOPE],
    )
    if not token:
        raise ValueError("Enter a Google OAuth access token or service account JSON for Search Console URL inspection.")

    cleaned_site_url = (site_url or "").strip()
    if not cleaned_site_url:
        raise ValueError("Enter the Search Console property URL, such as https://www.example.com/ or sc-domain:example.com.")

    valid_urls = []
    skipped = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            skipped.append(f"{url} - not a valid http or https URL")
            continue
        valid_urls.append(url)

    if not valid_urls:
        raise ValueError("No valid URLs were found.")

    started_at = time.perf_counter()
    logger.info("Google URL Inspection request batch started: urls=%d site_url=%s", len(valid_urls), cleaned_site_url)
    items = []
    for index, url in enumerate(valid_urls, start=1):
        url_started_at = time.perf_counter()
        payload = {
            "inspectionUrl": url,
            "siteUrl": cleaned_site_url,
            "languageCode": language_code or "en-US",
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout) as response:
                status_code = response.getcode()
                raw = response.read().decode("utf-8", errors="replace")
                data = json.loads(raw or "{}")
                index_status = data.get("inspectionResult", {}).get("indexStatusResult", {})
                verdict = index_status.get("verdict", "")
                coverage_state = index_status.get("coverageState", "")
                status = "indexed" if verdict == "PASS" else "not-indexed" if verdict else "check"
                detail = coverage_state or "Google returned URL inspection data."
                logger.info(
                    "Google URL Inspection item finished: index=%d/%d url=%s status=%s status_code=%s elapsed=%.2fs",
                    index,
                    len(valid_urls),
                    url,
                    status,
                    status_code,
                    time.perf_counter() - url_started_at,
                )
                items.append(
                    GoogleInspectionItemResult(
                        url=url,
                        status_code=status_code,
                        status=status,
                        verdict=verdict,
                        coverage_state=coverage_state,
                        robots_txt_state=index_status.get("robotsTxtState", ""),
                        indexing_state=index_status.get("indexingState", ""),
                        last_crawl_time=index_status.get("lastCrawlTime", ""),
                        detail=detail,
                    )
                )
        except HTTPError as exc:
            logger.error(
                "Google URL Inspection HTTP error: index=%d/%d url=%s status_code=%s detail=%s elapsed=%.2fs",
                index,
                len(valid_urls),
                url,
                exc.code,
                _google_inspection_status_detail(exc.code),
                time.perf_counter() - url_started_at,
            )
            items.append(_google_inspection_error(url, exc.code, _google_inspection_status_detail(exc.code)))
        except URLError as exc:
            detail = str(exc.reason) if getattr(exc, "reason", None) else "Could not reach Google URL Inspection API."
            logger.error(
                "Google URL Inspection URL error: index=%d/%d url=%s detail=%s elapsed=%.2fs",
                index,
                len(valid_urls),
                url,
                detail,
                time.perf_counter() - url_started_at,
            )
            items.append(_google_inspection_error(url, None, detail))
        except json.JSONDecodeError:
            logger.error(
                "Google URL Inspection JSON decode error: index=%d/%d url=%s elapsed=%.2fs",
                index,
                len(valid_urls),
                url,
                time.perf_counter() - url_started_at,
            )
            items.append(_google_inspection_error(url, None, "Google returned an unreadable URL inspection response."))

    logger.info("Google URL Inspection request batch finished: urls=%d elapsed=%.2fs", len(valid_urls), time.perf_counter() - started_at)
    return GoogleInspectionResult(
        inspected_count=len(valid_urls),
        skipped=skipped,
        items=items,
    )


def inspect_google_index_status_by_url_domain(
    urls: list[str],
    access_token: str = "",
    service_account_json: str = "",
    language_code: str = "en-US",
    endpoint: str = GOOGLE_URL_INSPECTION_ENDPOINT,
    timeout: int = 30,
) -> GoogleInspectionResult:
    grouped_urls: dict[str, list[str]] = {}
    skipped = []
    seen = set()

    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        property_url = search_console_property_for_url(url)
        if not property_url:
            skipped.append(f"{url} - not a valid http or https URL")
            continue
        grouped_urls.setdefault(property_url, []).append(url)

    if not grouped_urls:
        raise ValueError("No valid URLs were found.")

    all_items = []
    inspected_count = 0
    for property_url, property_urls in grouped_urls.items():
        logger.info(
            "Google URL Inspection derived Search Console property: site_url=%s urls=%d",
            property_url,
            len(property_urls),
        )
        result = inspect_google_index_status(
            urls=property_urls,
            site_url=property_url,
            access_token=access_token,
            service_account_json=service_account_json,
            language_code=language_code,
            endpoint=endpoint,
            timeout=timeout,
        )
        inspected_count += result.inspected_count
        skipped.extend(result.skipped)
        all_items.extend(result.items)

    return GoogleInspectionResult(
        inspected_count=inspected_count,
        skipped=skipped,
        items=all_items,
    )


def search_console_property_for_url(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"https://{parsed.netloc.lower()}/"


def google_access_token_from_service_account_json(service_account_json: str, scopes: list[str] | None = None) -> str:
    cleaned = (service_account_json or "").strip()
    if not cleaned:
        return ""

    try:
        service_account_info = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("Google service account JSON could not be parsed.") from exc

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ValueError("Google auth libraries are required for service account JSON. Install google-auth.") from exc

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes or [GOOGLE_INDEXING_SCOPE],
    )
    credentials.refresh(GoogleAuthRequest())
    return credentials.token or ""


def build_sitemap_xml(urls: list[str]) -> str:
    valid_urls = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            valid_urls.append(url)

    url_items = "\n".join(f"  <url><loc>{escape(url)}</loc></url>" for url in valid_urls)
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            url_items,
            "</urlset>",
            "",
        ]
    )


def _status_detail(status_code: int) -> str:
    return {
        200: "URL set submitted successfully.",
        202: "URL set received; key validation is pending.",
        400: "Invalid request format.",
        403: "IndexNow key is not valid or the key file could not be verified.",
        422: "URLs do not belong to the host or the key does not match the protocol.",
        429: "Too many requests. Wait before submitting again.",
    }.get(status_code, "IndexNow returned an unexpected response.")


def _google_status_detail(status_code: int) -> str:
    return {
        400: "Invalid Google Indexing API request.",
        401: "Google access token is missing, expired, or invalid.",
        403: "Google rejected the request. Check Search Console ownership, API access, quota, and whether the page type is eligible.",
        404: "Google Indexing API endpoint or URL was not found.",
        429: "Google quota or rate limit was reached.",
    }.get(status_code, "Google returned an error for this URL.")


def _google_inspection_error(url: str, status_code: int | None, detail: str) -> GoogleInspectionItemResult:
    return GoogleInspectionItemResult(
        url=url,
        status_code=status_code,
        status="error",
        verdict="",
        coverage_state="",
        robots_txt_state="",
        indexing_state="",
        last_crawl_time="",
        detail=detail,
    )


def _google_inspection_status_detail(status_code: int) -> str:
    return {
        400: "Invalid URL inspection request. Check that the URL is under the Search Console property.",
        401: "Google access token is missing, expired, or invalid.",
        403: "Google rejected the inspection request. Check Search Console ownership and URL Inspection API access.",
        404: "Google URL Inspection API endpoint or property was not found.",
        429: "Google URL Inspection API quota or rate limit was reached.",
    }.get(status_code, "Google returned an error for this URL inspection request.")
