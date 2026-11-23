"""Settings: defaults, environment overrides, and the JSON-list parsing the docs promise."""

from mcpserver.settings import Settings


def test_defaults_are_safe_to_start_locally() -> None:
    settings = Settings(_env_file=None)

    assert settings.mcp_port == 8000
    assert settings.mcp_name == "McpSquelette"
    assert settings.mcp_transport == "http"
    assert settings.rate_limit_max_requests == 100
    assert settings.allowed_origins == []
    assert settings.http_timeout_seconds == 10.0


def test_the_transport_is_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")

    assert Settings(_env_file=None).mcp_transport == "stdio"


def test_lists_are_read_from_json_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", '["mcp.example.com"]')
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com"]')
    settings = Settings(_env_file=None)

    assert settings.allowed_hosts == ["mcp.example.com"]
    assert settings.allowed_origins == ["https://app.example.com"]


def test_unknown_variables_are_ignored() -> None:
    settings = Settings(_env_file=None, SOMETHING_ELSE="1")

    assert settings.mcp_port == 8000
