"""Constants for Xiaohongshu parser plugin."""

DOMAIN = "xiaohongshu"

# Platform info
PLATFORM_CODE = "xhs"
PLATFORM_NAME = "小红书"
PLATFORM_URL = "https://www.xiaohongshu.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/小红书.png"

# URL pattern — matches short-links (xhslink.com/o/<path>) and direct note URLs
# (xiaohongshu.com/explore/<noteId>, xiaohongshu.com/discovery/item/<noteId>).
# Uses re.match() so the host must appear at the very start of the string,
# preventing false positives from query-string values that contain these hostnames.
URL_PATTERN = r'https?://(?:www\.)?xhslink\.com/o/\S+|https?://(?:www\.)?xiaohongshu\.com/(?:explore|discovery/item)/\w+'

# Parser constants
STREAM_CODEC_PRIORITY = ("h265", "av1", "h264", "h266")

REQUEST_HEADERS = {
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.4 Mobile/15E148 Safari/604.1"
}

JS_INVALID_TOKENS = r'\b(?:undefined|NaN|Infinity)\b'

IMAGE_CDN_URL = "https://sns-img-bd.xhscdn.com"
VIDEO_CDN_URL = "https://sns-bak-v8.xhscdn.com"