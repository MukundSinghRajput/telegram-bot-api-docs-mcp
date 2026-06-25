# Telegram Bot API Docs MCP

It gives AI clients access to the current
[Telegram Bot API documentation](https://core.telegram.org/bots/api). The server scrapes the official docs on
startup, validates the method/type graph, and serves the result through MCP
tools and JSON resources.

## Run

Run the published package over stdio, which is the usual transport for local AI
client bindings:

```sh
uvx telegram-bot-api-docs-mcp
```

Or run as an HTTP MCP server:

```sh
uvx telegram-bot-api-docs-mcp --transport http --host 127.0.0.1 --port 8080
```

Startup requires internet access because the server fetches
`https://core.telegram.org/bots/api` every time it starts.

For local development from a checkout, use `uv run python main.py` with the same
arguments.

## Codex

This repo includes a project-scoped Codex config at `.codex/config.toml`:

```toml
[mcp_servers.telegram-bot-api-docs]
command = "uvx"
args = ["telegram-bot-api-docs-mcp"]
```

Start a new Codex session from this trusted repo and run `/mcp` to confirm that
`telegram-bot-api-docs` is connected.

## Tools

- `get_bot_api_overview`: version, release date, changelog URL, and counts.
- `list_methods` / `list_types`: paginated method/type discovery with optional search.
- `get_method` / `get_type`: full docs for a method or type.
- `get_field`: docs for a specific method parameter or type field.
- `search_bot_api`: search names, descriptions, fields, return types, and relationships.
- `get_related_types`: subtype and usage graph for a type.
- `dump_bot_api_spec`: raw full spec or a single section.

## Resources

- `telegram-bot-api://overview`
- `telegram-bot-api://methods`
- `telegram-bot-api://types`
- `telegram-bot-api://spec`

## Scraper

`scrape.py` contains the parser and schema validation used by the MCP server.

Thanks to [PaulSonOfLars](https://github.com/PaulSonOfLars) for such wonderful [project](https://github.com/PaulSonOfLars/telegram-bot-api-spec)

> Made by Mukund