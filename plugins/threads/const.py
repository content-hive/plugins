"""Constants for Threads parser plugin."""

DOMAIN = "threads"

# Platform info
PLATFORM_CODE = "threads"
PLATFORM_NAME = "Threads"
PLATFORM_URL = "https://www.threads.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/Threads.png"

# URL pattern
URL_PATTERN = r"https?://(?:www\.)?threads\.(?:com|net)/@[\w.]+/post/[\w-]+"

# HTTP request headers matching a real Safari browser page navigation (from HAR)
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/26.5 Mobile/15E148 Safari/604.1"
)
REQUEST_HEADERS = {
    "user-agent": USER_AGENT,
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

# Relay preloader name prefixes used to locate the correct Relay data script.
# Each Threads page embeds multiple JSON scripts; the target one has a
# RelayPrefetchedStreamCache item whose preloader name starts with these.
# With the mobile UA, both logged-in and logged-out pages use this same preloader.
# Data path: data['data']['edges'][n]['node']['thread_items'][n]['post']
RELAY_POST_KEY = "adp_BarcelonaPostPageDirectQueryRelayPreloader"
RELAY_PROFILE_KEY = "adp_BarcelonaProfilePageDirectQueryRelayPreloader"

# Media type codes
MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_CAROUSEL = 8
