"""Instagram plugin configuration schema."""

from pydantic import Field

from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="Cookie",
        description=(
            "Optional. Instagram account cookie string. "
            "The 'sessionid' key is required for accessing restricted content via the private API. "
            "Without it, the plugin falls back to the public GraphQL endpoint."
        ),
        json_schema_extra={"secret": True},
    )


CONFIG_SCHEMA = ConfigSchema
