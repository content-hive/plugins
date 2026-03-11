"""Constants for Xiaohongshu parser plugin."""

DOMAIN = "xiaohongshu"

# Platform info
PLATFORM_CODE = "xhs"
PLATFORM_NAME = "Xiaohongshu"
PLATFORM_URL = "https://www.xiaohongshu.com/"
PLATFORM_ICON = "https://raw.githubusercontent.com/content-hive/assets/main/IconSet/小红书.png"

# URL patterns
URL_PATTERN = [
    "xhslink.com", 
    "xiaohongshu.com/explore/"
]

# Parser constants
STREAM_CODEC_PRIORITY = ("h264", "h265", "h266", "av1")

REQUEST_HEADERS = {
	"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
	"referer": "https://www.xiaohongshu.com/"
}

JS_INVALID_TOKENS = r'\b(?:undefined|NaN|Infinity)\b'

IMAGE_CDN_URL = "https://sns-img-bd.xhscdn.com"
VIDEO_CDN_URL = "https://sns-bak-v8.xhscdn.com"