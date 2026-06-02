"""Threads plugin configuration schema."""

from pydantic import Field

from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="Cookie",
        description="Optional. Threads account cookie string for accessing restricted content.",
        json_schema_extra={"secret": True},
    )


CONFIG_SCHEMA = ConfigSchema
