"""Constants for Jike parser plugin."""

DOMAIN = "jike"

# Platform info
PLATFORM_CODE = "jike"
PLATFORM_NAME = "即刻"
PLATFORM_URL = "https://m.okjike.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/即刻.png"

# URL pattern — matches mobile share links (m.okjike.com/originalPosts/<id> or /reposts/<id>)
# and web share links (web.okjike.com/u/<username>/post/<id>).
# Uses re.match() so the host must appear at the very start of the string.
URL_PATTERN = (
    r"https?://m\.okjike\.com/(?:originalPosts|reposts)/\w+"
    r"|https?://web\.okjike\.com/u/[^/]+/post/\w+"
)

# Captures the post ID from a web.okjike.com share URL.
WEB_POST_ID_RE = r"web\.okjike\.com/u/[^/]+/post/(\w+)"

REQUEST_HEADERS = {
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.4 Mobile/15E148 Safari/604.1"
}

# Signed video URL API — POST with query params, no auth required.
MEDIA_PLAY_API = "https://api.ruguoapp.com/1.0/mediaMeta/play"
MEDIA_PLAY_HEADERS = {
    "Platform": "MobileWeb",
    "Origin": "https://m.okjike.com",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.5 Safari/605.1.15",
}
