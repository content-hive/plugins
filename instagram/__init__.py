"""
Instagram Parser Plugin for ContentHive
Parses Instagram posts, reels, and IGTV for ContentHive.

Requires authentication via cookies (sessionid) configured in the plugin settings.
"""

from typing import cast

from contenthive.plugins.context import PluginContext

from .api_client import InstagramAPIClient
from .config import CONFIG_SCHEMA, ConfigSchema
from .const import DOMAIN
from .utils import parse_cookie_string, serialize_cookie_dict

__all__ = ["CONFIG_SCHEMA", "ConfigSchema"]


async def async_setup(context: PluginContext) -> bool:
    context.logger.info(f"{DOMAIN} plugin setup")
    return True


async def async_setup_entry(context: PluginContext, entry) -> bool:
    config = cast(ConfigSchema, context.get_config(DOMAIN)) if context.get_config else ConfigSchema()
    cookies = parse_cookie_string(config.cookies)
    if not cookies:
        raise ValueError(f"{DOMAIN} plugin setup failed: 'cookies' is not configured")

    def _on_cookies_updated(updated: dict[str, str]) -> None:
        if context.save_config and context.get_config:
            cfg = context.get_config(DOMAIN)
            context.save_config(DOMAIN, cfg.model_copy(update={"cookies": serialize_cookie_dict(updated)}))
            context.logger.debug(f"{DOMAIN} cookies persisted")

    client = InstagramAPIClient(context.logger, cookies=cookies, on_cookies_updated=_on_cookies_updated)
    await client.async_setup()
    context.data[DOMAIN] = {"client": client, "config": config}

    if context.async_forward_entry_setup:
        await context.async_forward_entry_setup(entry, "parser")
    context.logger.info(f"{DOMAIN} plugin entry setup completed")
    return True


async def async_unload_entry(context: PluginContext, entry) -> bool:
    if context.async_unload_platforms:
        success = await context.async_unload_platforms(entry, ["parser"])
    else:
        success = True
    if success:
        entry_data = context.data.pop(DOMAIN, {})
        client: InstagramAPIClient | None = entry_data.get("client")
        if client:
            await client.async_teardown()
        context.logger.info(f"{DOMAIN} plugin entry unloaded")
    return success
