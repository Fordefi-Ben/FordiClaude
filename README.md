# FordiClaude

Claude Code skills for developers building on the [Fordefi API](https://docs.fordefi.com).

Two skills ship in this repo:

| Skill | What it does |
|---|---|
| `fordefi-api-docs` | Look up endpoints, request/response schemas, auth signing, and narrative docs from the live Fordefi OpenAPI spec |
| `fordefi-explorer` | List your org's vaults, vault groups, users, and address book contacts with their IDs; debug transactions by ID |

`fordefi-api-docs` works with no credentials — it reads the public spec. `fordefi-explorer` requires a **viewer-permissioned API token** (read-only, no signing key needed).

---

## Quickstart

```bash
git clone https://github.com/Fordefi-Ben/FordiClaude
cd FordiClaude
claude
```

Once Claude Code opens, just say **"set me up"** — Claude will check your configuration, walk you through creating a `.env` file with your API token, and explain the available skills.

---

## Manual setup

If you prefer to configure things yourself:

1. Get a viewer-permissioned API token from the Fordefi app → Settings → API Users
2. Copy `.env.example` to `.env` and paste in your token:
   ```
   FORDEFI_API_TOKEN=your_token_here
   ```
3. Start using the skills — type `/fordefi-api-docs` or `/fordefi-explorer` in Claude Code

---

## Requirements

- [Claude Code](https://claude.ai/code)
- Python 3.9+ (stdlib only — no pip installs needed)
- A Fordefi account
- A viewer-permissioned API token (for `fordefi-explorer`)
