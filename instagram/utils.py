"""Instagram plugin utility functions."""

# Base-64 alphabet used by Instagram shortcodes (same as yt-dlp)
_ENCODING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_DECODE_MAP: dict[str, int] = {c: i for i, c in enumerate(_ENCODING_CHARS)}


def shortcode_to_pk(shortcode: str) -> str:
    """Convert an Instagram shortcode to its numeric media pk.

    Instagram long-form shortcodes (>28 chars) include a 28-char private suffix;
    strip it before decoding to get the public pk.
    Source: https://stackoverflow.com/questions/24437823/getting-instagram-post-url-from-media-id
    """
    if len(shortcode) > 28:
        shortcode = shortcode[:-28]
    pk = 0
    for char in shortcode:
        if char not in _DECODE_MAP:
            raise ValueError(f"Invalid shortcode character: {char!r}")
        pk = pk * 64 + _DECODE_MAP[char]
    return str(pk)


def parse_cookie_string(raw: str) -> dict[str, str]:
    """Parse a browser cookie string (e.g. 'k1=v1; k2=v2') into a dict."""
    if not raw or not isinstance(raw, str):
        return {}
    result: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            result[key.strip()] = value.strip()
    return result


def serialize_cookie_dict(cookies: dict[str, str]) -> str:
    """Serialize a cookie dict back to a browser cookie string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if k)
