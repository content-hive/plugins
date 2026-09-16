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

# Instagram Android app identifiers (matches instagrapi defaults)
APP_ID = "567067343352427"
APP_VERSION = "428.0.0.47.67"
VERSION_CODE = "961145276"
BLOKS_VERSIONING_ID = "7189b949425f9bf80ea8bd880cf5a3080b292d9b1c4b38a18d112f7c4b71e7a8"

# Private API base (requires sessionid cookie)
API_BASE = "https://i.instagram.com/api/v1"

# Android User-Agent simulating Pixel 8 Pro / Android 14
USER_AGENT = (
    "Instagram 428.0.0.47.67 "
    "Android (34/14; 480dpi; 1344x2992; Google/google; "
    "Pixel 8 Pro; husky; husky; en_US; 961145276)"
)

# Private API media_type values
MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_CAROUSEL = 8
