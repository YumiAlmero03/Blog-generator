import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database import get_setting


FACEBOOK_GRAPH_VERSION_KEY = "facebook_graph_api_version"
DEFAULT_FACEBOOK_GRAPH_VERSION = "v20.0"


@dataclass
class SocialPublishResult:
    platform: str
    success: bool
    remote_post_id: str = ""
    url: str = ""
    message: str = ""
    raw_response: dict | None = None


def get_facebook_graph_api_version() -> str:
    version = (get_setting(FACEBOOK_GRAPH_VERSION_KEY, DEFAULT_FACEBOOK_GRAPH_VERSION) or "").strip()
    if not version:
        return DEFAULT_FACEBOOK_GRAPH_VERSION
    return version if version.startswith("v") else f"v{version}"


def publish_facebook_page_post(
    profile: dict,
    message: str,
    link: str = "",
    graph_version: str | None = None,
    timeout: int = 30,
) -> SocialPublishResult:
    page_id = _facebook_page_id(profile)
    access_token = (profile.get("access_token") or "").strip()
    cleaned_message = (message or "").strip()
    cleaned_link = (link or "").strip()
    if not page_id:
        raise ValueError("Add the Facebook Page ID in the social account API settings before posting.")
    if not access_token:
        raise ValueError("Add a Facebook Page access token before posting.")
    if not cleaned_message:
        raise ValueError("Generate or enter post content before posting.")

    version = graph_version or get_facebook_graph_api_version()
    endpoint = f"https://graph.facebook.com/{version}/{page_id}/feed"
    payload = {
        "message": cleaned_message,
        "access_token": access_token,
    }
    if cleaned_link:
        payload["link"] = cleaned_link

    request = Request(
        endpoint,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
    except HTTPError as exc:
        detail = _facebook_error_detail(exc)
        raise ValueError(detail or f"Facebook Graph API returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(str(exc.reason) if getattr(exc, "reason", None) else "Could not reach Facebook Graph API.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Facebook Graph API returned unreadable data.") from exc

    post_id = str(data.get("id", "") or "")
    if not post_id:
        raise ValueError("Facebook Graph API did not return a post ID.")
    return SocialPublishResult(
        platform="facebook",
        success=True,
        remote_post_id=post_id,
        url=f"https://www.facebook.com/{post_id}",
        message="Posted to Facebook Page.",
        raw_response=data,
    )


def _facebook_page_id(profile: dict) -> str:
    return (profile.get("platform_account_id") or profile.get("account_name") or "").strip()


def _facebook_error_detail(exc: HTTPError) -> str:
    try:
        raw = exc.read(1_000_000).decode("utf-8", errors="replace")
        data = json.loads(raw or "{}")
    except Exception:
        return ""
    error = data.get("error") if isinstance(data, dict) else {}
    if not isinstance(error, dict):
        return ""
    message = error.get("message") or "Facebook Graph API request failed."
    code = error.get("code")
    error_type = error.get("type")
    parts = [str(message)]
    if error_type:
        parts.append(f"type={error_type}")
    if code:
        parts.append(f"code={code}")
    return " ".join(parts)
