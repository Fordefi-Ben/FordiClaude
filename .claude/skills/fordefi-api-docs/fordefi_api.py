#!/usr/bin/env python3
"""
Fordefi API docs retrieval tool.
Fetches and filters the public OpenAPI spec to return targeted documentation.
Only uses stdlib — no dependencies.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

SPEC_URL = "https://api.fordefi.com/openapi.json"
CACHE_PATH = Path(__file__).parent / ".openapi_cache.json"
MANIFEST_PATH = Path(__file__).parent / ".openapi_manifest.json"
CACHE_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Manifest — lightweight fingerprint of last-seen spec state
# ---------------------------------------------------------------------------

def _build_manifest(spec: dict) -> dict:
    """Build a compact manifest from a spec for change detection."""
    endpoints = sorted(
        f"{method.upper()} {path}"
        for path, methods in spec.get("paths", {}).items()
        for method, details in methods.items()
        if isinstance(details, dict)
    )
    schemas = spec.get("components", {}).get("schemas", {})
    schema_fields = {
        name: sorted(s.get("properties", {}).keys())
        for name, s in schemas.items()
        if s.get("properties")
    }
    return {
        "hash": hashlib.md5(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
        "endpoints": endpoints,
        "schema_names": sorted(schemas.keys()),
        "schema_fields": schema_fields,
    }


def _load_manifest() -> dict | None:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception:
            return None
    return None


def _save_manifest(spec: dict) -> dict:
    m = _build_manifest(spec)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2))
    return m


def _diff_manifests(old: dict, new: dict) -> dict | None:
    """Return a diff dict if anything changed, else None."""
    old_ep = set(old.get("endpoints", []))
    new_ep = set(new.get("endpoints", []))
    old_sn = set(old.get("schema_names", []))
    new_sn = set(new.get("schema_names", []))
    old_sf = old.get("schema_fields", {})
    new_sf = new.get("schema_fields", {})

    added_ep = sorted(new_ep - old_ep)
    removed_ep = sorted(old_ep - new_ep)
    added_schemas = sorted(new_sn - old_sn)
    removed_schemas = sorted(old_sn - new_sn)

    # New fields on existing schemas
    changed_schemas = {}
    for name in new_sf:
        if name in old_sf:
            added_fields = sorted(set(new_sf[name]) - set(old_sf[name]))
            removed_fields = sorted(set(old_sf[name]) - set(new_sf[name]))
            if added_fields or removed_fields:
                changed_schemas[name] = {"added": added_fields, "removed": removed_fields}

    if not any([added_ep, removed_ep, added_schemas, removed_schemas, changed_schemas]):
        return None

    return {
        "added_endpoints": added_ep,
        "removed_endpoints": removed_ep,
        "added_schemas": added_schemas,
        "removed_schemas": removed_schemas,
        "changed_schemas": changed_schemas,
    }


def _print_diff(diff: dict, to_stderr: bool = True) -> None:
    out = sys.stderr if to_stderr else sys.stdout
    out.write("\n⚡ Fordefi API spec changed since last run:\n")

    if diff["added_endpoints"]:
        out.write(f"\n  + {len(diff['added_endpoints'])} new endpoint(s):\n")
        for ep in diff["added_endpoints"]:
            out.write(f"      {ep}\n")

    if diff["removed_endpoints"]:
        out.write(f"\n  - {len(diff['removed_endpoints'])} removed endpoint(s):\n")
        for ep in diff["removed_endpoints"]:
            out.write(f"      {ep}\n")

    if diff["added_schemas"]:
        out.write(f"\n  + {len(diff['added_schemas'])} new schema(s): "
                  f"{', '.join(diff['added_schemas'][:8])}"
                  + (" ..." if len(diff["added_schemas"]) > 8 else "") + "\n")

    if diff["removed_schemas"]:
        out.write(f"\n  - {len(diff['removed_schemas'])} removed schema(s): "
                  f"{', '.join(diff['removed_schemas'][:8])}"
                  + (" ..." if len(diff["removed_schemas"]) > 8 else "") + "\n")

    if diff["changed_schemas"]:
        out.write(f"\n  ~ {len(diff['changed_schemas'])} schema(s) with field changes:\n")
        for name, changes in list(diff["changed_schemas"].items())[:10]:
            parts = []
            if changes["added"]:
                parts.append(f"+{', '.join(changes['added'][:4])}")
            if changes["removed"]:
                parts.append(f"-{', '.join(changes['removed'][:4])}")
            out.write(f"      {name}: {' | '.join(parts)}\n")

    out.write("\n")


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------

def load_spec(refresh: bool = False) -> dict:
    old_manifest = _load_manifest()
    cache_hit = (
        not refresh
        and CACHE_PATH.exists()
        and (time.time() - CACHE_PATH.stat().st_mtime) < CACHE_TTL
    )

    if cache_hit:
        spec = json.loads(CACHE_PATH.read_text())
        # If we have no manifest yet, create one silently from the cached spec
        if old_manifest is None:
            _save_manifest(spec)
        return spec

    # Fresh fetch
    try:
        with urllib.request.urlopen(SPEC_URL, timeout=10) as r:
            raw = r.read()
        CACHE_PATH.write_bytes(raw)
        spec = json.loads(raw)
    except Exception as e:
        if CACHE_PATH.exists():
            sys.stderr.write(f"Warning: fetch failed ({e}), using cached spec\n")
            return json.loads(CACHE_PATH.read_text())
        raise

    # Diff and auto-update manifest
    new_manifest = _build_manifest(spec)
    if old_manifest is not None:
        diff = _diff_manifests(old_manifest, new_manifest)
        if diff:
            _print_diff(diff, to_stderr=True)
    _save_manifest(spec)
    return spec


# ---------------------------------------------------------------------------
# Schema resolution helpers
# ---------------------------------------------------------------------------

def deref(schema: dict, schemas: dict, visited: frozenset = frozenset(), depth: int = 0) -> dict:
    """Follow $ref chains and merge allOf into a flat object."""
    if depth > 4:
        return schema
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        if name in visited:
            return {"type": f"<circular:{name}>"}
        return deref(schemas.get(name, {}), schemas, visited | {name}, depth + 1)
    if "allOf" in schema:
        merged: dict = {}
        merged_props: dict = {}
        merged_required: list = []
        for part in schema["allOf"]:
            resolved = deref(part, schemas, visited, depth + 1)
            merged_props.update(resolved.get("properties", {}))
            merged_required.extend(resolved.get("required", []))
            for k, v in resolved.items():
                if k not in ("properties", "required"):
                    merged[k] = v
        if merged_props:
            merged["properties"] = merged_props
        if merged_required:
            merged["required"] = list(set(merged_required))
        return {**schema, **merged}
    return schema


def type_label(schema: dict, schemas: dict, depth: int = 0) -> str:
    """Return a compact human-readable type string."""
    if depth > 2:
        return "..."
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            variants = schema[key]
            names = []
            for v in variants[:4]:
                if "$ref" in v:
                    names.append(v["$ref"].split("/")[-1])
                elif "type" in v:
                    names.append(v["type"])
            suffix = "..." if len(variants) > 4 else ""
            return "oneOf(" + " | ".join(names) + suffix + ")"
    t = schema.get("type", "")
    if t == "array":
        items = schema.get("items", {})
        return f"array<{type_label(items, schemas, depth + 1)}>"
    if "enum" in schema:
        vals = schema["enum"]
        if len(vals) <= 6:
            return "enum(" + " | ".join(str(v) for v in vals) + ")"
        return f"enum({vals[0]}|{vals[1]}|...+{len(vals) - 2})"
    fmt = schema.get("format", "")
    return f"{t}/{fmt}" if fmt and t else t or "any"


# ---------------------------------------------------------------------------
# Schema rendering
# ---------------------------------------------------------------------------

def render_schema(name: str, schemas: dict, expand_unions: bool = False,
                  visited: frozenset = frozenset(), depth: int = 0) -> str:
    if depth > 2 or name in visited:
        return f"*`{name}`*"
    visited = visited | {name}

    s = schemas.get(name)
    if not s:
        return f"`{name}` _(not found)_"

    # $ref alias — follow silently
    if "$ref" in s and len(s) <= 2:
        alias = s["$ref"].split("/")[-1]
        return render_schema(alias, schemas, expand_unions, visited, depth)

    desc = s.get("description", "")
    header = f"### `{name}`"
    if desc:
        header += f"\n_{desc}_"

    # Enum
    if "enum" in s:
        vals = " | ".join(f"`{v}`" for v in s["enum"])
        return f"{header}\n{vals}"

    # Union
    for key in ("anyOf", "oneOf"):
        if key in s:
            variants = s[key]
            lines = [f"{header}\n**Discriminated union** ({len(variants)} variants):"]
            for v in variants:
                vname = v.get("$ref", "").split("/")[-1]
                if not vname:
                    continue
                vs = schemas.get(vname, {})
                vdesc = vs.get("description", "")
                line = f"- `{vname}`"
                if vdesc:
                    line += f" — {vdesc[:100]}"
                lines.append(line)
            result = "\n".join(lines)
            if expand_unions and depth < 1:
                for v in variants:
                    vname = v.get("$ref", "").split("/")[-1]
                    if vname:
                        result += "\n\n" + render_schema(vname, schemas, False, visited, depth + 1)
            return result

    # Object
    resolved = deref(s, schemas)
    props = resolved.get("properties", {})
    required = set(resolved.get("required", []))

    if not props:
        return f"{header}\nType: `{resolved.get('type', 'object')}`"

    rows = ["| Field | Type | Req | Description |", "|-------|------|-----|-------------|"]
    for fname, fschema in props.items():
        req = "✓" if fname in required else ""
        ft = type_label(fschema, schemas)
        fdesc = fschema.get("description", "")[:100].replace("\n", " ")
        rows.append(f"| `{fname}` | `{ft}` | {req} | {fdesc} |")

    return header + "\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# Endpoint rendering
# ---------------------------------------------------------------------------

def render_endpoint(method: str, path: str, details: dict, schemas: dict,
                    schema_depth: int = 1) -> str:
    out = [f"## `{method} {path}`"]
    summary = details.get("summary", "")
    description = details.get("description", "").strip()
    if summary:
        out.append(f"**{summary}**")
    if description:
        out.append(f"\n{description}\n")

    params = details.get("parameters", [])
    headers = [p for p in params if p.get("in") == "header"]
    path_params = [p for p in params if p.get("in") == "path"]
    query_params = [p for p in params if p.get("in") == "query"]

    if headers:
        out.append("\n**Headers:**")
        for p in headers:
            req = "*(required)*" if p.get("required") else "*(optional)*"
            desc = p.get("description", "")[:120]
            out.append(f"- `{p['name']}` {req} — {desc}")

    if path_params:
        out.append("\n**Path parameters:**")
        for p in path_params:
            ptype = type_label(p.get("schema", {}), schemas)
            req = " *(required)*" if p.get("required") else ""
            out.append(f"- `{p['name']}`: `{ptype}`{req} — {p.get('description', '')}")

    if query_params:
        out.append("\n**Query parameters:**")
        rows = ["| Param | Type | Req | Description |", "|-------|------|-----|-------------|"]
        for p in query_params:
            ptype = type_label(p.get("schema", {}), schemas)
            req = "✓" if p.get("required") else ""
            desc = (p.get("description") or p.get("schema", {}).get("description", ""))[:100].replace("\n", " ")
            rows.append(f"| `{p['name']}` | `{ptype}` | {req} | {desc} |")
        out.append("\n".join(rows))

    rb = details.get("requestBody", {})
    if rb:
        for ct, cv in rb.get("content", {}).items():
            s = cv.get("schema", {})
            sname = s.get("$ref", "").split("/")[-1] if "$ref" in s else None
            out.append(f"\n**Request body** (`{ct}`):")
            if sname and schema_depth > 0:
                out.append(render_schema(sname, schemas))
            elif sname:
                out.append(f"`{sname}`")
            break

    for status, resp in details.get("responses", {}).items():
        if status.startswith("2"):
            for ct, cv in resp.get("content", {}).items():
                s = cv.get("schema", {})
                sname = s.get("$ref", "").split("/")[-1] if "$ref" in s else None
                out.append(f"\n**Response `{status}`:**")
                if sname and schema_depth > 0:
                    out.append(render_schema(sname, schemas))
                elif sname:
                    out.append(f"`{sname}`")
                break
            break

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_endpoint(args, spec):
    schemas = spec["components"]["schemas"]
    query = args.path.lower()
    found = []
    for path, methods in spec["paths"].items():
        if query not in path.lower():
            continue
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            if args.method and method.upper() != args.method.upper():
                continue
            found.append((method.upper(), path, details))

    if not found:
        print(f"No endpoints matching `{args.path}`")
        return
    for method, path, details in found:
        print(render_endpoint(method, path, details, schemas))
        print()


def cmd_schema(args, spec):
    schemas = spec["components"]["schemas"]
    name = args.name

    if name not in schemas:
        matches = [k for k in schemas if name.lower() in k.lower()]
        if not matches:
            print(f"Schema `{name}` not found.")
            return
        if len(matches) == 1:
            name = matches[0]
        else:
            if len(matches) <= 30:
                print(f"Multiple matches for `{name}` ({len(matches)}):")
                for m in matches:
                    print(f"  - {m}")
            else:
                print(f"{len(matches)} matches for `{name}` (top 30):")
                for m in matches[:30]:
                    print(f"  - {m}")
            return

    print(render_schema(name, schemas, expand_unions=args.expand))


def cmd_tag(args, spec):
    schemas = spec["components"]["schemas"]
    query = args.name.lower()
    found = []
    for path, methods in spec["paths"].items():
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            tags = [t.lower() for t in details.get("tags", [])]
            if any(query in t for t in tags):
                found.append((method.upper(), path, details))

    if not found:
        print(f"No endpoints with tag matching `{args.name}`")
        return

    print(f"# {args.name} Endpoints\n")
    print("| Method | Path | Summary |")
    print("|--------|------|---------|")
    for method, path, details in found:
        print(f"| `{method}` | `{path}` | {details.get('summary', '')} |")

    if args.detail:
        print()
        for method, path, details in found:
            print(render_endpoint(method, path, details, schemas))
            print("\n---\n")


def cmd_chain(args, spec):
    """Show transaction/vault/asset schemas for a specific chain."""
    schemas = spec["components"]["schemas"]
    chain = args.chain.capitalize()

    # Collect relevant schema names
    tx_keywords = {"Transaction", "Transfer", "Message", "Asset", "Vault",
                   "Chain", "Suggested", "Request", "Details", "Effect"}
    relevant = []
    for name in sorted(schemas.keys()):
        starts_with_chain = name.startswith(chain)
        starts_with_create = name.startswith(f"Create{chain}")
        if starts_with_chain or starts_with_create:
            if any(k in name for k in tx_keywords):
                relevant.append(name)

    if not relevant:
        print(f"No schemas found for chain `{args.chain}`. "
              f"Known chains: aptos, arch, cosmos, evm, exchange, solana, stacks, starknet, stellar, sui, ton, tron, utxo")
        return

    print(f"# {chain} API Schemas ({len(relevant)} matched)\n")
    # Prioritise Create* request schemas first
    create_first = sorted(relevant, key=lambda n: (0 if n.startswith("Create") else 1, n))
    for name in create_first[:args.limit]:
        print(render_schema(name, schemas))
        print()
    if len(relevant) > args.limit:
        print(f"_(+{len(relevant) - args.limit} more — use `--limit N` to see more)_")


def cmd_search(args, spec):
    """Keyword search across endpoints and schema names."""
    schemas = spec["components"]["schemas"]
    # All words must match (AND), not the literal phrase
    words = args.query.lower().split()

    endpoint_hits = []
    for path, methods in spec["paths"].items():
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            searchable = " ".join([
                path,
                details.get("summary", ""),
                details.get("description", ""),
                details.get("operationId", ""),
            ]).lower()
            if all(w in searchable for w in words):
                endpoint_hits.append((method.upper(), path, details.get("summary", "")))

    schema_hits = [n for n in schemas if all(w in n.lower() for w in words)]

    if endpoint_hits:
        print(f"## Matching endpoints ({len(endpoint_hits)})\n")
        print("| Method | Path | Summary |")
        print("|--------|------|---------|")
        for method, path, summary in endpoint_hits:
            print(f"| `{method}` | `{path}` | {summary} |")
        print()

    if schema_hits:
        limit = 30
        print(f"## Matching schemas ({len(schema_hits)})\n")
        for name in schema_hits[:limit]:
            print(f"- `{name}`")
        if len(schema_hits) > limit:
            print(f"_(+{len(schema_hits) - limit} more)_")

    if not endpoint_hits and not schema_hits:
        print(f"No results for `{args.query}`")


def cmd_diff(args, spec):
    """Compare current live spec against stored manifest and report changes."""
    old_manifest = _load_manifest()
    if old_manifest is None:
        print("No manifest found — run any other subcommand first to create a baseline.")
        return

    new_manifest = _build_manifest(spec)
    diff = _diff_manifests(old_manifest, new_manifest)

    if diff is None:
        print("No changes detected since last run.")
        return

    _print_diff(diff, to_stderr=False)

    if args.update:
        _save_manifest(spec)
        print("Manifest updated.")


def cmd_auth(args, spec):
    """Print authentication / request signing reference."""
    print("""# Fordefi API Authentication

## Base URL
`https://api.fordefi.com/`

## Authorization header (all endpoints)
```
Authorization: Bearer <api_access_token>
```

## Request signing (sensitive operations: POST, PUT, DELETE)
All state-changing requests must include:

| Header | Type | Description |
|--------|------|-------------|
| `x-signature` | string | Base64-encoded ECDSA P-256 signature (see algorithm below) |
| `x-timestamp` | integer | Unix epoch — units vary by SDK (see note below) |
| `x-idempotence-id` | string (UUID) | Optional. Deduplicate creates — same ID returns the original response. |

### Signing algorithm
1. Build the payload string: `f"{path}|{timestamp}|{request_body}"`
   - `path` is the full endpoint path, e.g. `/api/v1/transactions`
   - `timestamp` is the value you send in `x-timestamp`
   - `request_body` is the raw JSON string of the request body
2. Sign with your API User's private key using ECDSA over NIST P-256 (secp256r1), SHA-256 digest
3. Base64-encode the DER-encoded signature → send as `x-signature`

### Shell example
```bash
TIMESTAMP="$(($(date +%s) * 1000))"   # milliseconds
PAYLOAD="${ENDPOINT}|${TIMESTAMP}|${BODY}"
SIGNATURE="$(echo -n "$PAYLOAD" | openssl dgst -sha256 -sign "$PRIVATE_KEY_FILE" | base64 | tr -d '\\n')"
```

### Python example
```python
import datetime, base64, hashlib
from ecdsa import SigningKey

timestamp = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))  # seconds
payload = f"{path}|{timestamp}|{request_body}"
with open(private_key_file) as f:
    signing_key = SigningKey.from_pem(f.read())
signature = base64.b64encode(
    signing_key.sign_deterministic(payload.encode(), hashfunc=hashlib.sha256)
).decode()
```

GET/read-only endpoints do NOT require `x-signature` or `x-timestamp`.

> Source: https://docs.fordefi.com/developers/authentication.md
> Full guide: `python3 Knowledge_bot/fordefi_api.py docs authentication`
""")


# ---------------------------------------------------------------------------
# Docs — fetch narrative documentation pages from docs.fordefi.com
# ---------------------------------------------------------------------------

DOCS_BASE = "https://docs.fordefi.com"
LLMS_TXT_URL = f"{DOCS_BASE}/llms.txt"
DOCS_INDEX_CACHE = Path(__file__).parent / ".docs_index_cache.json"
DOCS_INDEX_TTL = 86400  # 24 hours


def _load_docs_index(refresh: bool = False) -> list[dict]:
    """Return [{title, url, slug}] parsed from llms.txt, cached locally."""
    if not refresh and DOCS_INDEX_CACHE.exists():
        age = time.time() - DOCS_INDEX_CACHE.stat().st_mtime
        if age < DOCS_INDEX_TTL:
            return json.loads(DOCS_INDEX_CACHE.read_text())
    try:
        with urllib.request.urlopen(LLMS_TXT_URL, timeout=10) as r:
            text = r.read().decode()
    except Exception as e:
        if DOCS_INDEX_CACHE.exists():
            sys.stderr.write(f"Warning: docs index fetch failed ({e}), using cache\n")
            return json.loads(DOCS_INDEX_CACHE.read_text())
        raise

    import re
    entries = []
    for m in re.finditer(r"-\s+\[([^\]]+)\]\((https://docs\.fordefi\.com/([^\)]+))\)", text):
        title, url, slug = m.group(1), m.group(2), m.group(3)
        # Normalise slug: strip .md suffix for matching
        slug_clean = slug.removesuffix(".md") if slug.endswith(".md") else slug
        entries.append({"title": title, "url": url, "slug": slug_clean})
    DOCS_INDEX_CACHE.write_text(json.dumps(entries, indent=2))
    return entries


def _fetch_doc_page(url: str) -> str:
    """Fetch a .md docs page. Ensures .md suffix."""
    if not url.endswith(".md"):
        url = url + ".md"
    if not url.startswith("http"):
        url = f"{DOCS_BASE}/{url.lstrip('/')}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode()


def cmd_docs(args, spec):
    index = _load_docs_index(refresh=args.refresh_docs)

    # List mode
    if args.docs_action == "list":
        words = (args.filter or "").lower().split()
        print(f"# Fordefi Docs Index ({len(index)} pages)\n")
        for entry in index:
            if words and not all(w in (entry["title"] + entry["slug"]).lower() for w in words):
                continue
            print(f"  [{entry['title']}]  {entry['slug']}")
        return

    # Search + fetch mode
    query = args.query_or_slug
    words = query.lower().split()

    # Exact or substring slug match first
    matches = [e for e in index if query.lower() in e["slug"].lower()]
    # Fall back to title match
    if not matches:
        matches = [e for e in index if all(w in e["title"].lower() for w in words)]

    if not matches:
        print(f"No doc pages matching '{query}'.\nTry: python3 Knowledge_bot/fordefi_api.py docs list --filter <keyword>")
        return

    if len(matches) > 1 and not args.all:
        print(f"Multiple matches ({len(matches)}) — showing best match. Use --all to fetch all.\n")
        for e in matches:
            print(f"  {e['slug']}  —  {e['title']}")
        print()
        matches = matches[:1]

    for entry in matches:
        url = entry["url"]
        if not url.endswith(".md"):
            url += ".md"
        try:
            content = _fetch_doc_page(url)
            print(f"<!-- source: {url} -->")
            print(content)
            if len(matches) > 1:
                print("\n---\n")
        except Exception as e:
            print(f"Error fetching {url}: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fordefi API docs lookup — fetch and filter the public OpenAPI spec",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Force re-fetch the spec (ignore cache)")
    sub = parser.add_subparsers(dest="command", required=True)

    ep = sub.add_parser("endpoint", help="Look up endpoint(s) by path substring")
    ep.add_argument("path", help="Path substring (e.g. 'transactions', 'vaults/{id}')")
    ep.add_argument("--method", "-m", help="Filter by HTTP method (GET, POST, etc.)")

    sc = sub.add_parser("schema", help="Show schema fields by name")
    sc.add_argument("name", help="Schema name (partial match supported)")
    sc.add_argument("--expand", "-e", action="store_true",
                    help="Expand union variants inline")

    tg = sub.add_parser("tag", help="List endpoints by resource group")
    tg.add_argument("name", help="Tag name (partial match, e.g. 'Transactions', 'Vaults')")
    tg.add_argument("--detail", "-d", action="store_true",
                    help="Show full endpoint details (not just table)")

    ch = sub.add_parser("chain", help="Show tx/vault/asset schemas for a chain")
    ch.add_argument("chain", help="Chain name (evm, solana, cosmos, ton, stellar, sui, aptos, ...)")
    ch.add_argument("--limit", "-n", type=int, default=15,
                    help="Max schemas to show (default 15)")

    sr = sub.add_parser("search", help="Search endpoints and schema names by keyword")
    sr.add_argument("query", help="Keyword to search for")

    sub.add_parser("auth", help="Show API authentication / signing reference")

    df = sub.add_parser("diff", help="Show what changed in the spec since last run")
    df.add_argument("--update", "-u", action="store_true",
                    help="Update the manifest after showing diff")

    dc = sub.add_parser("docs", help="Browse or fetch Fordefi narrative docs pages")
    dc.add_argument("--refresh-docs", action="store_true",
                    help="Force re-fetch the docs page index")
    dc_sub = dc.add_subparsers(dest="docs_action", required=True)

    dc_list = dc_sub.add_parser("list", help="List all available doc pages")
    dc_list.add_argument("--filter", "-f", help="Filter by keyword")

    dc_fetch = dc_sub.add_parser("fetch", help="Fetch a doc page by slug or keyword")
    dc_fetch.add_argument("query_or_slug", help="Slug substring or keyword (e.g. 'authentication', 'evm-transfers')")
    dc_fetch.add_argument("--all", "-a", action="store_true",
                          help="Fetch all matching pages (not just the best match)")

    args = parser.parse_args()
    # docs subcommand skips spec loading (no need to hit the API)
    spec = None if args.command == "docs" else load_spec(refresh=args.refresh)

    dispatch = {
        "endpoint": cmd_endpoint,
        "schema": cmd_schema,
        "tag": cmd_tag,
        "chain": cmd_chain,
        "search": cmd_search,
        "auth": cmd_auth,
        "diff": cmd_diff,
        "docs": cmd_docs,
    }
    dispatch[args.command](args, spec)


if __name__ == "__main__":
    main()
