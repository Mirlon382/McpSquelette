"""Every value this server can be configured with.

Names are read from the environment in upper case (`MCP_PORT`) and from `.env` beside the working
directory. Unknown variables are ignored, so a stale key never prevents the server from starting.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MCP server -------------------------------------------------------------------------------------------------------
    # Sent to the client in the handshake, and shown in most inspector UIs.
    mcp_name: str = "McpSquelette"
    # stdio: a client launches the process and talks over pipes -- what Claude Desktop and most
    # editors expect. http: a long-running server answering on /mcp. The console script defaults to
    # http so the quickstart works without a client; a container must keep it.
    mcp_transport: Literal["http", "stdio"] = "http"

    # HTTP server ------------------------------------------------------------------------------------------------------
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    # JSON list of the hostnames clients use to reach this server, checked against the Host
    # header. "*" accepts any host, which disables the check.
    allowed_hosts: list[str] = ["*"]
    # JSON list of browser origins allowed to call the server. Empty rejects every cross-origin
    # browser request, which is right until a browser-based client needs in.
    allowed_origins: list[str] = []
    # Peers whose X-Forwarded-For header is believed; anything else keeps its real socket address.
    # Accepts addresses, CIDR networks and literals. Widening this lets callers forge their own address.
    trusted_proxy_hosts: list[str] = ["127.0.0.1"]

    # Outbound HTTP ----------------------------------------------------------------------------------------------------
    # Applied to the single client the lifespan opens (lifespan.py): every tool inherits both.
    http_timeout_seconds: float = 10.0
    # Many public APIs reject the default Python user agent. Set yours here, once.
    http_user_agent: str = "McpSquelette/0.1 (+https://github.com/Mirlon382/McpSquelette)"

    # Rate limiting ----------------------------------------------------------------------------------------------------
    rate_limit_max_requests: int = 100
    rate_limit_window_minutes: int = 1

    # Logging ----------------------------------------------------------------------------------------------------------
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


def load_settings() -> Settings:
    return Settings()
