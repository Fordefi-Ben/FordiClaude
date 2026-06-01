---
name: fordefi-api-docs
description: Look up Fordefi public API docs — endpoints, request/response schemas, query filters, chain-specific transaction shapes, and auth signing. Use when the user is writing code against the Fordefi API, references a Fordefi API endpoint or schema name, asks how to construct a request, or asks what fields/params are available.
argument-hint: "<natural-language query or schema/endpoint name>"
allowed-tools: Bash, Read
---

# Fordefi API Docs Lookup

Retrieves targeted documentation from the live Fordefi OpenAPI spec (`https://api.fordefi.com/openapi.json`).
The spec is cached for 1 hour at `.claude/skills/fordefi-api-docs/.openapi_cache.json`.

## How to invoke

Run from your project root:

```bash
python3 .claude/skills/fordefi-api-docs/fordefi_api.py <subcommand> [args]
```

Use `--refresh` on any subcommand to force re-fetch the spec:
```bash
python3 .claude/skills/fordefi-api-docs/fordefi_api.py --refresh <subcommand> [args]
```

---

## Proactive checks

**Before writing any transaction-creation code**, confirm the user has all of these:

| Requirement | What it is | How to verify |
|---|---|---|
| API access token | Bearer token for all requests | Present in Fordefi app → Settings → API Users |
| API signer | A dedicated signer registered in Fordefi that signs txs programmatically | Set up in Fordefi app → Settings → API Signers |
| API signer private key | The PEM key whose public key is registered in Fordefi | Must be available to the signing environment |
| Request signing | `x-signature` + `x-timestamp` headers on all POST/PUT/DELETE | Covered in `auth` subcommand |

If any of these are unclear, fetch the full guide before writing code:
```bash
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch authentication
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch api-signer
```

**When the user reports errors or a stuck transaction**, diagnose first — don't write more code:

| Symptom | Likely cause | First step |
|---|---|---|
| HTTP 401 | Missing or invalid Bearer token | Verify token; run `auth` |
| HTTP 403 | Token lacks required permissions | Check token scope in Fordefi app |
| HTTP 422 | Malformed request body | Run `schema <type>` to verify required fields |
| HTTP 429 | Rate limit exceeded | Reduce request frequency; add backoff |
| `waiting_for_signing` | API signer not configured or signing service not running | See checklist below |
| `pending_signatures` | Collecting multiple required signatures | Normal if policy requires multi-sig |
| `pending_approval` | Policy requires human approver action | Normal — no code fix needed |

### `waiting_for_signing` checklist

Fetch the API signer guide, then walk through:
```bash
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch api-signer
```

1. **API signer exists** — created in Fordefi app → Settings → API Signers
2. **Signer is authorized on the vault** — the vault's signing policy must include this API signer
3. **`signer_type: "api_signer"`** — must be set in the transaction create request body
4. **Signing service is running** — the process holding the private key must be active and polling
5. **Key pair matches** — the PEM private key in use must correspond to the public key registered in Fordefi

---

## Subcommand reference

### `search <keyword...>`
**Start here** when the user describes what they want to do. Words are ANDed — no quotes needed.

```bash
# Find anything related to EVM transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py search "evm transaction"

# Find transfer-related endpoints and schemas
python3 .claude/skills/fordefi-api-docs/fordefi_api.py search transfer

# Find vault creation
python3 .claude/skills/fordefi-api-docs/fordefi_api.py search "create vault"
```

Returns: matching endpoint table + matching schema names.

---

### `endpoint <path-substring> [--method GET|POST|...]`
Full endpoint details: headers, path params, query params, request body schema, response schema.

```bash
# All transaction endpoints
python3 .claude/skills/fordefi-api-docs/fordefi_api.py endpoint transactions

# Just POST /api/v1/transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py endpoint "/api/v1/transactions" --method POST

# Vault address endpoints
python3 .claude/skills/fordefi-api-docs/fordefi_api.py endpoint "vaults/{id}/addresses"
```

---

### `schema <name> [--expand]`
Show fields for a specific schema. Partial name matching is supported.
`--expand` renders union variants inline (useful for discriminated unions).

```bash
# EVM transaction create request
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema CreateEvmTransactionRequest

# What's inside CreateEvmRawTransactionRequest (the actual fields)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema CreateEvmRawTransactionRequest

# All 13 chain variants of AssetIdentifierRequest, expanded
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema AssetIdentifierRequest --expand

# All CreateTransaction variants, expanded
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema CreateTransactionRequest --expand

# List schemas matching a substring (no --expand)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema "EvmTransfer"
```

---

### `tag <resource-group> [--detail]`
List all endpoints in a resource group. `--detail` adds full per-endpoint docs.

Available tags: `Transactions`, `Vaults`, `Swaps`, `Assets`, `Address Book`,
`Blockchains`, `End Users`, `Authorization Tokens`, `Users`, `User Groups`,
`Vault Groups`, `Organizations`, `Webhooks`, `Audit Log`, `Enclave Keys`, `Exports`, `Batch Transactions`

```bash
# Endpoint table for Transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py tag Transactions

# Full details for Vaults (request/response schemas included)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py tag Vaults --detail

# Swaps
python3 .claude/skills/fordefi-api-docs/fordefi_api.py tag Swaps
```

---

### `chain <chain-name> [--limit N]`
All transaction/vault/asset/transfer schemas for a specific chain. Default shows 15.

Supported chains: `evm`, `solana`, `cosmos`, `stellar`, `aptos`, `sui`, `ton`, `tron`,
`starknet`, `stacks`, `utxo`, `arch`, `exchange`

```bash
# EVM transaction schemas (CreateEvmTransactionRequest, raw tx, transfer, etc.)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py chain evm

# Cosmos schemas (default 15)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py chain cosmos

# See more
python3 .claude/skills/fordefi-api-docs/fordefi_api.py chain solana --limit 30
```

---

### `auth`
Print the API authentication and request signing reference (headers, algorithm, code examples).

```bash
python3 .claude/skills/fordefi-api-docs/fordefi_api.py auth
```

Signing payload format: `"{path}|{timestamp}|{request_body}"` — pipe-separated, **not** dot-separated.
For full details including code samples, use `docs fetch authentication`.

---

### `docs list [--filter <keyword>]`
List all 253 narrative doc pages from the docs site (cached 24h).

```bash
# All pages
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs list

# Filter by keyword
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs list --filter evm
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs list --filter solana
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs list --filter "transaction-types"
```

---

### `docs fetch <slug-or-keyword> [--all]`
Fetch the full markdown content of a specific doc page. Partial slug or keyword matching is supported.
Use `--all` to fetch every matching page.

```bash
# Authentication and signing guide
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch authentication

# EVM raw transaction guide (with code examples)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch evm-smart-contract-calls

# EVM transfers
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch evm-transfers

# Solana raw transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch solana-raw-transactions

# Error reference
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch errors

# Webhooks
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch webhooks

# Getting started: create transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py docs fetch create-and-authenticate-transactions
```

Doc pages contain **narrative explanations, JSON examples, and code samples** — much richer than the raw schema tables from `schema`/`endpoint`. Prefer `docs fetch` when the user needs a working code example for a specific chain or operation.

---

## Decision guide — which subcommand to use

| User is asking about... | Use |
|---|---|
| How to create a transaction on chain X (with code) | `docs fetch <chain>-transfers` or `docs fetch <chain>-raw-transactions` |
| Request/response field shapes | `chain <X>` then `schema Create<X>TransactionRequest` |
| Specific schema field details | `schema <SchemaName>` |
| What endpoints exist for a resource | `tag <ResourceGroup>` |
| A known endpoint path | `endpoint <path>` |
| An unknown concept or keyword | `search <keyword>` |
| How to sign API requests | `auth` (quick) or `docs fetch authentication` (full guide) |
| Asset identifier for a token type | `schema AssetIdentifierRequest --expand` |
| List/filter params for transactions | `endpoint transactions --method GET` |
| List/filter params for vaults | `endpoint /api/v1/vaults --method GET` |
| Working code examples | `docs fetch <topic>` |
| Error codes | `docs fetch errors` |
| Webhook setup | `docs fetch webhooks` |
| What doc pages exist | `docs list --filter <keyword>` |

### `diff [--update]`
Show what changed in the spec since the last run. Compares the current live spec against the stored manifest.

```bash
# Check for changes (read-only)
python3 .claude/skills/fordefi-api-docs/fordefi_api.py diff

# Check and update manifest to the new state
python3 .claude/skills/fordefi-api-docs/fordefi_api.py diff --update
```

---

## Common patterns

### Creating a chain-specific transaction
```bash
# 1. Get the chain's request schema
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema CreateEvmTransactionRequest

# 2. Get the details variants
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema CreateEvmRawTransactionRequest

# 3. Get asset identifier shape for that chain
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema EvmAssetIdentifierRequest --expand
```

### Understanding a response object
```bash
# Get Transaction response (what comes back from GET /transactions/{id})
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema GetTransactionResponse

# Then drill into the chain-specific transaction union
python3 .claude/skills/fordefi-api-docs/fordefi_api.py schema Transaction --expand
```

### Building a filtered list query
```bash
# See all query params for listing transactions
python3 .claude/skills/fordefi-api-docs/fordefi_api.py endpoint "/api/v1/transactions" --method GET
```

---

## Auto change detection

**Every time the spec is freshly fetched** (cache miss or `--refresh`), the tool automatically diffs the new spec against the stored manifest and prints any changes to stderr — before the command output. No action needed; it self-updates the manifest.

The manifest (`.openapi_manifest.json`) tracks:
- All endpoint method+path combinations
- All schema names
- All field names per schema

Changes reported: new endpoints, removed endpoints, new schemas, removed schemas, new/removed fields on existing schemas.

If you see a change warning, use `schema`, `endpoint`, or `chain` subcommands to inspect the new shapes before writing code against them.

---

## Notes

- The spec is **publicly accessible** — no auth required to fetch it.
- All `Create*` write endpoints require `x-signature` + `x-timestamp` headers. Run `auth` for details.
- Pagination: all list endpoints accept `page` (default 1), `size` (default 50, max 100), `skip_count`.
- `CreateTransactionRequest` is a 24-variant union; the `type` field is the discriminator.
- `CreateVaultRequest` is similarly a union discriminated by `type` (e.g. `"evm_vault"`, `"solana_vault"`).
- Chain unique IDs (e.g. `"ethereum_mainnet"`, `"solana_mainnet"`) differ from `ChainType` enum values (e.g. `"evm"`, `"solana"`). Use `chain evm` or `schema EvmChainName` to see valid chain unique IDs.
