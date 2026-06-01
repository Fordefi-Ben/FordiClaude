#!/usr/bin/env python3
"""
Fordefi Explorer — read-only interface for inspecting org resources.
Reads FORDEFI_API_TOKEN from a .env file.
All operations are GET requests; a viewer-permissioned token is sufficient.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.fordefi.com"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def load_env(env_file: str) -> dict:
    path = Path(env_file)
    if not path.exists():
        return {}
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_token(env_file: str) -> str:
    token = load_env(env_file).get("FORDEFI_API_TOKEN") or os.environ.get("FORDEFI_API_TOKEN")
    if not token:
        sys.exit(
            f"Error: FORDEFI_API_TOKEN not found.\n"
            f"Add it to {env_file}:\n"
            f"  FORDEFI_API_TOKEN=<your viewer-permissioned API token>"
        )
    return token


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request(path: str, token: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail") or body
        except Exception:
            detail = body
        hints = {
            401: "Invalid or missing Bearer token.",
            403: "Token lacks permission for this resource.",
            404: "Resource not found. Verify the ID.",
            429: "Rate limit exceeded. Wait and retry.",
        }
        hint = hints.get(e.code, "")
        sys.exit(f"HTTP {e.code}: {detail}" + (f"\nHint: {hint}" if hint else ""))


def fetch_list(path: str, token: str, extra_params: dict | None = None, limit: int = 500) -> list:
    """Collect items from a paginated list endpoint up to `limit`."""
    items: list = []
    page = 1
    page_size = min(100, limit)
    while len(items) < limit:
        params = {"page": page, "size": page_size, "skip_count": "true"}
        if extra_params:
            params.update(extra_params)
        data = _request(path, token, params)
        batch = data.get("data", [])
        items.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    return items[:limit]


def fetch_one(path: str, token: str) -> dict:
    return _request(path, token)


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _col(value, width: int) -> str:
    s = str(value or "")
    return s[:width].ljust(width)


def _table(rows: list[dict], columns: list[tuple]) -> None:
    """
    columns: list of (header, key_or_callable, width)
    key_or_callable: dict key string, or a callable(row) -> str
    """
    header = "  ".join(_col(h, w) for h, _, w in columns)
    sep = "  ".join("-" * w for _, _, w in columns)
    print(header)
    print(sep)
    for row in rows:
        cells = []
        for _, key, width in columns:
            val = key(row) if callable(key) else row.get(key, "")
            cells.append(_col(val, width))
        print("  ".join(cells))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_tx(args, token: str) -> None:
    tx = fetch_one(f"/api/v1/transactions/{args.id}", token)

    if args.as_json:
        print(json.dumps(tx, indent=2))
        return

    state = tx.get("state", "unknown")

    print("── Transaction ──────────────────────────────")
    for label, value in [
        ("ID:", tx.get("id")),
        ("State:", state),
        ("Type:", tx.get("type")),
        ("Chain:", tx.get("chain_unique_id") or tx.get("chain") or (tx.get("details") or {}).get("chain")),
        ("Vault:", _vault_label(tx.get("vault") or {})),
        ("Created:", tx.get("created_at")),
        ("Modified:", tx.get("modified_at")),
        ("Tx hash:", tx.get("transaction_hash") or tx.get("hash")),
        ("Note:", tx.get("note")),
    ]:
        if value:
            print(f"  {label:<16}{value}")

    signers = tx.get("signers") or []
    if signers:
        print(f"\n── Signers ({len(signers)}) " + "─" * 30)
        _table(signers, [
            ("Type", "type", 22),
            ("State", "state", 20),
            ("Who", lambda s: (s.get("user") or {}).get("name") or (s.get("user") or {}).get("email") or s.get("id", ""), 30),
        ])

    error = tx.get("error") or tx.get("failure_reason") or tx.get("rejection_reason")
    if error:
        print(f"\n── Error ────────────────────────────────────")
        print(f"  {error}")

    print(f"\n── Diagnosis ────────────────────────────────")
    _diagnose_state(state, error)


def cmd_vaults(args, token: str) -> None:
    params = {}
    if args.group_id:
        params["vault_group_ids[]"] = args.group_id
    items = fetch_list("/api/v1/vaults", token, extra_params=params or None, limit=args.limit)

    if args.as_json:
        print(json.dumps(items, indent=2))
        return

    print(f"{len(items)} vault(s)\n")
    _table(items, [
        ("ID", "id", 36),
        ("Name", "name", 28),
        ("Type", "type", 18),
        ("Group", lambda v: (v.get("vault_group") or {}).get("name") or (v.get("vault_group") or {}).get("id") or "", 24),
    ])


def cmd_vault_groups(args, token: str) -> None:
    items = fetch_list("/api/v1/vault-groups", token, limit=args.limit)

    if args.as_json:
        print(json.dumps(items, indent=2))
        return

    print(f"{len(items)} vault group(s)\n")
    _table(items, [
        ("ID", "id", 36),
        ("Name", "name", 40),
    ])


def cmd_users(args, token: str) -> None:
    items = fetch_list("/api/v1/users", token, limit=args.limit)

    if args.as_json:
        print(json.dumps(items, indent=2))
        return

    print(f"{len(items)} user(s)\n")
    _table(items, [
        ("ID", "id", 36),
        ("Name", "name", 24),
        ("Email", "email", 32),
        ("Role", "role", 16),
    ])


def cmd_contacts(args, token: str) -> None:
    params = {}
    if args.chain:
        params["chain_types[]"] = args.chain
    items = fetch_list("/api/v1/addressbook/contacts", token, extra_params=params or None, limit=args.limit)

    if args.as_json:
        print(json.dumps(items, indent=2))
        return

    print(f"{len(items)} contact(s)\n")
    _table(items, [
        ("ID", "id", 36),
        ("Name", "name", 24),
        ("Chain", lambda c: c.get("chain_unique_id") or c.get("chain_type") or "", 20),
        ("Address", _contact_address, 44),
        ("State", "state", 12),
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vault_label(vault: dict) -> str:
    if not vault:
        return ""
    name = vault.get("name") or ""
    vid = vault.get("id") or ""
    return f"{name} ({vid})" if name and vid else name or vid


def _contact_address(contact: dict) -> str:
    """Extract the on-chain address from a chain-specific contact object."""
    # Most chains put the address at the top level
    addr = contact.get("address")
    if addr and isinstance(addr, str):
        return addr
    # Some chains nest it
    details = contact.get("details") or {}
    return details.get("address") or details.get("public_key") or ""


def _diagnose_state(state: str, error: str | None) -> None:
    if state == "waiting_for_signing":
        print("  Transaction is waiting for the API signer to sign it.")
        print()
        print("  Checklist:")
        print("  1. API signer exists in Fordefi app → Settings → API Signers")
        print("  2. API signer is authorized on this vault (check vault signing policy)")
        print('  3. Transaction create request included signer_type: "api_signer"')
        print("  4. Signing service/process is running with the private key loaded")
        print("  5. Private key matches the public key registered in Fordefi")
    elif state == "pending_signatures":
        print("  Collecting required signatures per vault policy.")
        print("  Check the signers table above — pending signers must act.")
    elif state == "pending_approval":
        print("  Waiting for policy approvers. No code action needed.")
    elif state in ("aborted", "rejected", "cancelled"):
        print(f"  Terminal state: {state}.")
        if error:
            print(f"  Reason: {error}")
    elif state == "reverted":
        print("  Transaction reached the chain but reverted on-chain.")
        print("  Check the tx hash on a block explorer for the revert reason.")
    elif state == "completed":
        print("  Transaction completed successfully.")
    else:
        print(f"  State: {state}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Shared flags inherited by every subcommand so they come after the subcommand name
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--env", default=".env", help="Path to .env file (default: .env)")
    shared.add_argument("--json", dest="as_json", action="store_true", help="Print raw JSON")

    parser = argparse.ArgumentParser(
        description="Fordefi Explorer — read-only inspection of org resources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # tx
    p_tx = sub.add_parser("tx", parents=[shared], help="Get and diagnose a transaction by ID")
    p_tx.add_argument("id", help="Transaction UUID")

    # vaults
    p_vaults = sub.add_parser("vaults", parents=[shared], help="List vaults with IDs")
    p_vaults.add_argument("--group-id", help="Filter by vault group ID")
    p_vaults.add_argument("--limit", type=int, default=500)

    # vault-groups
    p_vg = sub.add_parser("vault-groups", parents=[shared], help="List vault groups with IDs")
    p_vg.add_argument("--limit", type=int, default=200)

    # users
    p_users = sub.add_parser("users", parents=[shared], help="List users with IDs")
    p_users.add_argument("--limit", type=int, default=200)

    # contacts
    p_contacts = sub.add_parser("contacts", parents=[shared], help="List address book contacts with IDs")
    p_contacts.add_argument("--chain", help="Filter by chain type (e.g. evm, solana)")
    p_contacts.add_argument("--limit", type=int, default=500)

    args = parser.parse_args()
    token = get_token(args.env)

    dispatch = {
        "tx": cmd_tx,
        "vaults": cmd_vaults,
        "vault-groups": cmd_vault_groups,
        "users": cmd_users,
        "contacts": cmd_contacts,
    }
    dispatch[args.command](args, token)


if __name__ == "__main__":
    main()
