"""
Threads Parser Plugin for ContentHive
Parses Threads content for ContentHive.
"""

from typing import cast

from contenthive.plugins.context import PluginContext

from .config import CONFIG_SCHEMA, ConfigSchema
from .const import DOMAIN

__all__ = ["CONFIG_SCHEMA"]


def _parse_cookie_string(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            result[k.strip()] = v.strip()
    return result


async def async_setup(context: PluginContext) -> bool:
    context.logger.info(f"{DOMAIN} plugin setup")
    return True


async def async_setup_entry(context: PluginContext, entry) -> bool:
    config = cast(ConfigSchema, context.get_config(DOMAIN)) if context.get_config else ConfigSchema()
    cookies = _parse_cookie_string(config.cookies)
    context.data[DOMAIN] = {"cookies": cookies, "config": config}

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
        context.data.pop(DOMAIN, None)
        context.logger.info(f"{DOMAIN} plugin entry unloaded")
    return success
