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

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Avatar image size suffix to replace for higher-resolution profile images.
AVATAR_NORMAL_SUFFIX = "_normal"
AVATAR_HQ_SUFFIX = "_400x400"

# API endpoints
API_BASE = "https://api.x.com/1.1/"
GRAPHQL_API_BASE = "https://x.com/i/api/graphql/"
SYNDICATION_API_URL = "https://cdn.syndication.twimg.com/tweet-result"

# GraphQL tweet query endpoint ID (from yt-dlp)
GRAPHQL_ENDPOINT = "2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId"

# Public Bearer token used by the Twitter web client (same token as yt-dlp)
AUTH_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# GraphQL variable defaults for TweetResultByRestId
GRAPHQL_VARIABLES_DEFAULTS = {
    "withCommunity": False,
    "includePromotedContent": False,
    "withVoice": False,
}

# GraphQL field toggles for TweetResultByRestId
GRAPHQL_FIELD_TOGGLES = {
    "withArticleRichContentState": False,
}

# GraphQL feature flags required by the TweetResultByRestId endpoint
GRAPHQL_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
