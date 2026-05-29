"""Constants for Instagram parser plugin."""

DOMAIN = "instagram"

# Platform info
PLATFORM_CODE = "ig"
PLATFORM_NAME = "Instagram"
PLATFORM_URL = "https://www.instagram.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/Instagram.png"

# URL pattern — group(1) captures the shortcode.
# Matches /p/, /tv/, /reel/, /reels/ paths, with optional username prefix.
# Example: https://www.instagram.com/p/ABC123/
#          https://www.instagram.com/username/reel/ABC123
URL_PATTERN = (
    r"https?://(?:www\.)?instagram\.com"
    r"(?:/(?!share/)[^/?#]+)?"
    r"/(?:p|tv|reels?(?!/audio/))"
    r"/([^/?#&]+)"
)

# Instagram app ID (same as yt-dlp / official web client)
APP_ID = "936619743392459"
ASBD_ID = "198387"

# Private API base (requires sessionid cookie)
API_BASE = "https://i.instagram.com/api/v1"

# Public GraphQL endpoint (no sessionid required, but CSRF token needed)
GRAPHQL_URL = "https://www.instagram.com/graphql/query/"
GRAPHQL_DOC_ID = "8845758582119845"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Private API media_type values
MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_CAROUSEL = 8
