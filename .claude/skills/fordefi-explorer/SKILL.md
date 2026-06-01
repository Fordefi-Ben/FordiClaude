---
name: fordefi-explorer
description: Read-only interface for inspecting a Fordefi org's resources — vaults, vault groups, users, and address book contacts. Use when the user needs resource IDs to write code (vault IDs for transactions, user IDs for policy config, contact IDs for transfers), or when debugging a transaction's state. Requires FORDEFI_API_TOKEN in .env — viewer permission is sufficient.
argument-hint: "<subcommand> [args]"
allowed-tools: Bash, Read
---

# Fordefi Explorer

Read-only inspection of org resources. All subcommands are GET requests — a viewer-permissioned token is sufficient, no signing key required.

## Setup

Create a `.env` file in the project root (this file is gitignored — never commit it):
```
FORDEFI_API_TOKEN=<your viewer-permissioned API token>
```

## Subcommands

### `vaults` — list all vaults with IDs
```bash
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py vaults

# Filter by vault group
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py vaults --group-id <vault-group-uuid>

# Raw JSON (all fields)
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py vaults --json
```

Output columns: ID, Name, Type, Group

---

### `vault-groups` — list vault groups with IDs
```bash
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py vault-groups
```

Output columns: ID, Name

---

### `users` — list org users with IDs
```bash
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py users
```

Output columns: ID, Name, Email, Role

---

### `contacts` — list address book entries with IDs
```bash
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py contacts

# Filter by chain type
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py contacts --chain evm
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py contacts --chain solana
```

Output columns: ID, Name, Chain, Address, State

---

### `tx <id>` — fetch and diagnose a transaction
```bash
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py tx <tx-uuid>

# Full raw JSON (all fields including calldata, gas, policy decisions)
python3 .claude/skills/fordefi-explorer/fordefi_explorer.py tx <tx-uuid> --json
```

Output: state, vault, chain, signers table, error if any, and a state-specific diagnosis block.

State-specific diagnosis:

| State | Output |
|---|---|
| `waiting_for_signing` | 5-item API signer checklist |
| `pending_signatures` | Which signers still need to act |
| `pending_approval` | Confirms this is normal; no code fix needed |
| `aborted` / `rejected` / `cancelled` | Terminal state + failure reason |
| `reverted` | Points to block explorer for on-chain revert reason |
| `completed` | Confirms success |

---

## Global flags

| Flag | Effect |
|---|---|
| `--env <path>` | Path to .env file (default: `.env`) |
| `--json` | Print full raw JSON instead of the formatted table |
| `--limit N` | Cap total results for list commands (default varies by resource) |

---

## When to use which subcommand

| Goal | Subcommand |
|---|---|
| Find vault ID to use in a transaction | `vaults` |
| Find vault group ID for vault creation | `vault-groups` |
| Find user ID for policy or approval config | `users` |
| Find contact ID for transfer recipient | `contacts` |
| Debug a stuck or failed transaction | `tx <id>` |

## Notes

- All list commands auto-paginate up to the configured limit
- `--json` on list commands dumps the full array — useful when you need fields not shown in the table (e.g. vault addresses, contact chain-specific details)
- Contacts: `--chain` accepts ChainType values (`evm`, `solana`, `cosmos`, `utxo`, etc.)
