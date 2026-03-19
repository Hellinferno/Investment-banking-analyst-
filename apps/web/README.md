# AIBAA Web Workspace

This is the React + Vite frontend for the AIBAA valuation workspace.

## Local Auth Flow

The frontend no longer sends the raw dev bootstrap token directly to protected API routes.

Instead it uses this flow:
1. Read `VITE_API_TOKEN` from the browser env.
2. If that value already looks like a JWT, use it directly.
3. If it is a bootstrap token such as `dev-local-token`, call `POST /api/v1/auth/dev-token`.
4. Store the returned JWT in memory and attach it to all API requests.

## Environment

Create `apps/web/.env` from `apps/web/.env.example`.

Available variables:
- `VITE_API_BASE_URL`
- `VITE_API_TOKEN`
- `VITE_DEV_AUTH_ROLE`

`VITE_DEV_AUTH_ROLE` controls the local user persona:
- `analyst`
- `reviewer`
- `admin`

Use `reviewer` or `admin` if you want to approve generated outputs from the UI.

## Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```
