"""Constants for Twitter parser plugin."""

DOMAIN = "twitter"

# Platform info
PLATFORM_CODE = "x"
PLATFORM_NAME = "X"
PLATFORM_URL = "https://x.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/X.png"

# URL pattern — group(3) captures the numeric tweet ID.
# Matches twitter.com and x.com status URLs, with optional www prefix,
# query parameters, and path suffixes (e.g. /photo/1).
URL_PATTERN = r"https?://(www\.)?(twitter\.com|x\.com)/.+/status/(\d+)"

# Request headers — desktop Chrome UA to avoid App Store redirects
# that mobile UAs can trigger on some Twitter configurations.
REQUEST_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "accept-language": "en-US,en;q=0.9",
}

# JS invalid token cleanup — Twitter may embed JS-only values in the state JSON.
JS_INVALID_TOKENS = r'\b(?:undefined|NaN|Infinity)\b'

# Avatar image size suffix to replace for higher-resolution profile images.
AVATAR_NORMAL_SUFFIX = "_normal"
AVATAR_HQ_SUFFIX = "_400x400"
