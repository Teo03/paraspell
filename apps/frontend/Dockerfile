# Frontend dev image — runs Vite with hot reload bound to all interfaces.
# Build context is the repo root so we can reach the pnpm workspace lockfile.
# Production build (multi-stage with nginx) will be added later.

FROM node:20-alpine

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH" \
    CI=true
RUN corepack enable && corepack prepare pnpm@8.15.3 --activate

WORKDIR /repo

COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/frontend/package.json ./apps/frontend/

RUN pnpm install --frozen-lockfile --filter frontend...

COPY apps/frontend ./apps/frontend

WORKDIR /repo/apps/frontend

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]
