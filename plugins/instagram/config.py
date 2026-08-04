"""Instagram plugin configuration schema."""

from pydantic import Field

from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="Cookie",
        description="Required. Instagram account cookie string. The 'sessionid' key is required.",
        json_schema_extra={"secret": True},
    )


CONFIG_SCHEMA = ConfigSchema
