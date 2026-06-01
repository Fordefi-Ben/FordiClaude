# FordiClaude — Claude Code setup

When a user opens this project for the first time, greet them briefly and check if `.env` exists.

If `.env` is missing:
1. Tell them a viewer-permissioned Fordefi API token is needed for the `fordefi-explorer` skill (vaults, users, contacts, transaction debugging)
2. Tell them where to get one: Fordefi app → User Management → Dropdown next to "Create User" button in the top right → create a user with Viewer role → generate an API token
3. Offer to create the `.env` file for them once they have the token — use `.env.example` as the template
4. Confirm the `fordefi-api-docs` skill works without any token (it reads the public OpenAPI spec)

Once set up, briefly explain the two available skills:
- `/fordefi-api-docs` — look up endpoints, schemas, auth signing, and docs pages from the live Fordefi API spec
- `/fordefi-explorer` — list vaults, vault groups, users, and address book contacts with their IDs; debug transactions by ID
