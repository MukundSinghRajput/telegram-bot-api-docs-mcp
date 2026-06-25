from __future__ import annotations

import argparse
import contextlib
import json
import sys
from typing import Any, Literal

from fastmcp import FastMCP

from scrape import METHODS as METHODS_KEY
from scrape import TO_SCRAPE, TYPES as TYPES_KEY
from scrape import retrieve_info, verify_method_parameters, verify_type_parameters

Section = Literal["methods", "types"]

app = FastMCP(
    "telegram-bot-api-docs",
    instructions=(
        "Use this server to answer questions about the Telegram Bot API. "
        "The tools expose the scraped official Bot API method/type schema, "
        "including descriptions, parameters, return types, subtypes, and source URLs."
    ),
)


def scrape_spec() -> dict[str, Any]:
    with contextlib.redirect_stdout(sys.stderr):
        spec = retrieve_info(TO_SCRAPE["api"])
        has_validation_issue = verify_type_parameters(spec) or verify_method_parameters(spec)
    if has_validation_issue:
        raise RuntimeError("Freshly scraped Telegram Bot API documentation failed schema validation")
    return spec


SPEC: dict[str, Any] = {}
METHODS: dict[str, dict[str, Any]] = {}
TYPES: dict[str, dict[str, Any]] = {}


def load_spec() -> dict[str, Any]:
    global SPEC, METHODS, TYPES
    if SPEC:
        return SPEC

    SPEC = scrape_spec()
    METHODS = SPEC[METHODS_KEY]
    TYPES = SPEC[TYPES_KEY]
    return SPEC


def resolve_name(section: Section, name: str) -> str:
    items = METHODS if section == "methods" else TYPES
    if name in items:
        return name

    lowered = name.lower()
    for item_name in items:
        if item_name.lower() == lowered:
            return item_name

    raise ValueError(f"Unknown Telegram Bot API {section[:-1]}: {name}")


def item_summary(item: dict[str, Any]) -> str:
    description = item.get("description", [])
    return description[0] if description else ""


def field_matches(field: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            field.get("name", ""),
            " ".join(field.get("types", [])),
            field.get("description", ""),
        ]
    ).lower()
    return query in haystack


def item_matches(name: str, item: dict[str, Any], query: str) -> bool:
    parts = [
        name,
        item.get("href", ""),
        " ".join(item.get("description", [])),
        " ".join(item.get("returns", [])),
        " ".join(item.get("subtypes", [])),
        " ".join(item.get("subtype_of", [])),
    ]
    for field in item.get("fields", []):
        parts.extend(
            [
                field.get("name", ""),
                " ".join(field.get("types", [])),
                field.get("description", ""),
            ]
        )
    return query in " ".join(parts).lower()


def format_item(name: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "href": item.get("href"),
        "description": item.get("description", []),
        "returns": item.get("returns", []),
        "fields": item.get("fields", []),
        "subtypes": item.get("subtypes", []),
        "subtype_of": item.get("subtype_of", []),
    }


def page_items(
    items: dict[str, dict[str, Any]],
    query: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)
    normalized_query = query.lower().strip() if query else None

    rows = []
    for name, item in items.items():
        if normalized_query and not item_matches(name, item, normalized_query):
            continue

        rows.append(
            {
                "name": name,
                "href": item.get("href"),
                "summary": item_summary(item),
            }
        )

    return {
        "total": len(rows),
        "offset": safe_offset,
        "limit": safe_limit,
        "items": rows[safe_offset : safe_offset + safe_limit],
    }


@app.tool
def get_bot_api_overview() -> dict[str, Any]:
    """Return Bot API version metadata and counts for the loaded documentation."""
    return {
        "version": SPEC.get("version"),
        "release_date": SPEC.get("release_date"),
        "changelog": SPEC.get("changelog"),
        "method_count": len(METHODS),
        "type_count": len(TYPES),
        "source_url": TO_SCRAPE["api"],
    }


@app.tool
def list_methods(query: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """List Telegram Bot API methods, optionally filtered by a search query."""
    return page_items(METHODS, query, limit, offset)


@app.tool
def list_types(query: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """List Telegram Bot API types, optionally filtered by a search query."""
    return page_items(TYPES, query, limit, offset)


@app.tool
def get_method(name: str, include_return_types: bool = True) -> dict[str, Any]:
    """Return full documentation for a Telegram Bot API method."""
    method_name = resolve_name("methods", name)
    method = format_item(method_name, METHODS[method_name])

    if include_return_types:
        method["return_type_docs"] = {}
        for return_type in method.get("returns", []):
            type_name = return_type.removeprefix("Array of ")
            if type_name in TYPES:
                method["return_type_docs"][type_name] = format_item(type_name, TYPES[type_name])

    return method


@app.tool
def get_type(name: str, include_related_methods: bool = False) -> dict[str, Any]:
    """Return full documentation for a Telegram Bot API type."""
    type_name = resolve_name("types", name)
    type_doc = format_item(type_name, TYPES[type_name])

    if include_related_methods:
        type_doc["related_methods"] = find_methods_using_type(type_name)

    return type_doc


@app.tool
def get_field(owner_name: str, field_name: str, section: Section | None = None) -> dict[str, Any]:
    """Return documentation for a method parameter or type field."""
    sections: list[Section] = [section] if section else ["methods", "types"]
    for current_section in sections:
        try:
            item_name = resolve_name(current_section, owner_name)
        except ValueError:
            continue

        items = METHODS if current_section == "methods" else TYPES
        for field in items[item_name].get("fields", []):
            if field.get("name", "").lower() == field_name.lower():
                return {
                    "section": current_section,
                    "owner": item_name,
                    "field": field,
                    "owner_href": items[item_name].get("href"),
                }

    raise ValueError(f"Unknown field {field_name} on {owner_name}")


@app.tool
def search_bot_api(
    query: str,
    section: Literal["all", "methods", "types"] = "all",
    limit: int = 50,
) -> dict[str, Any]:
    """Search method/type names, descriptions, fields, return types, and relationships."""
    normalized_query = query.lower().strip()
    if not normalized_query:
        raise ValueError("query must not be empty")

    safe_limit = max(1, min(limit, 200))
    results: list[dict[str, Any]] = []
    collections: list[tuple[Section, dict[str, dict[str, Any]]]] = []
    if section in ("all", "methods"):
        collections.append(("methods", METHODS))
    if section in ("all", "types"):
        collections.append(("types", TYPES))

    for current_section, items in collections:
        for name, item in items.items():
            if item_matches(name, item, normalized_query):
                matching_fields = [
                    field
                    for field in item.get("fields", [])
                    if field_matches(field, normalized_query)
                ][:10]
                results.append(
                    {
                        "section": current_section,
                        "name": name,
                        "href": item.get("href"),
                        "summary": item_summary(item),
                        "returns": item.get("returns", []),
                        "matching_fields": matching_fields,
                    }
                )
                if len(results) >= safe_limit:
                    return {"query": query, "total_returned": len(results), "results": results}

    return {"query": query, "total_returned": len(results), "results": results}


@app.tool
def get_related_types(name: str) -> dict[str, Any]:
    """Return subtype, parent type, field-reference, and return-reference relationships for a type."""
    type_name = resolve_name("types", name)
    return {
        "name": type_name,
        "subtypes": TYPES[type_name].get("subtypes", []),
        "subtype_of": TYPES[type_name].get("subtype_of", []),
        "used_by_types": find_types_using_type(type_name),
        "used_by_methods": find_methods_using_type(type_name),
    }


@app.tool
def dump_bot_api_spec(section: Literal["all", "methods", "types"] = "all") -> dict[str, Any]:
    """Return the raw scraped Bot API documentation spec, optionally restricted to one section."""
    if section == "methods":
        return {"methods": METHODS}
    if section == "types":
        return {"types": TYPES}
    return SPEC


def type_is_referenced(type_name: str, type_expr: str) -> bool:
    while type_expr.startswith("Array of "):
        type_expr = type_expr.removeprefix("Array of ")
    return type_expr == type_name


def find_methods_using_type(type_name: str) -> list[dict[str, Any]]:
    matches = []
    for method_name, method in METHODS.items():
        return_match = any(type_is_referenced(type_name, ret) for ret in method.get("returns", []))
        field_matches_for_method = [
            field
            for field in method.get("fields", [])
            if any(type_is_referenced(type_name, t) for t in field.get("types", []))
        ]
        if return_match or field_matches_for_method:
            matches.append(
                {
                    "name": method_name,
                    "href": method.get("href"),
                    "returns": method.get("returns", []),
                    "matching_fields": field_matches_for_method,
                }
            )
    return matches


def find_types_using_type(type_name: str) -> list[dict[str, Any]]:
    matches = []
    for current_name, type_doc in TYPES.items():
        if current_name == type_name:
            continue
        field_matches_for_type = [
            field
            for field in type_doc.get("fields", [])
            if any(type_is_referenced(type_name, t) for t in field.get("types", []))
        ]
        if field_matches_for_type:
            matches.append(
                {
                    "name": current_name,
                    "href": type_doc.get("href"),
                    "matching_fields": field_matches_for_type,
                }
            )
    return matches


@app.resource("telegram-bot-api://overview", mime_type="application/json")
def overview_resource() -> str:
    """Bot API version metadata and counts."""
    return json.dumps(get_bot_api_overview())


@app.resource("telegram-bot-api://methods", mime_type="application/json")
def methods_resource() -> str:
    """All Telegram Bot API methods."""
    return json.dumps(METHODS)


@app.resource("telegram-bot-api://types", mime_type="application/json")
def types_resource() -> str:
    """All Telegram Bot API types."""
    return json.dumps(TYPES)


@app.resource("telegram-bot-api://spec", mime_type="application/json")
def spec_resource() -> str:
    """The full raw Telegram Bot API documentation spec."""
    return json.dumps(SPEC)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram Bot API documentation MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport to run. Use stdio for most AI client bindings.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transport.")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transport.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_spec()
    if args.transport == "http":
        app.run(transport="http", host=args.host, port=args.port)
    else:
        app.run(transport="stdio")


if __name__ == "__main__":
    main()
