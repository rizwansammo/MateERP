# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS build
ARG MATEERP_BACKEND_URL=http://backend:8000
ENV MATEERP_BACKEND_URL=${MATEERP_BACKEND_URL} NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN npm run build

FROM node:24-bookworm-slim AS prod
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 PORT=3000 MATEERP_BACKEND_URL=http://backend:8000
WORKDIR /app
RUN groupadd --system --gid 1001 mateerp && \
    useradd --system --uid 1001 --gid mateerp mateerp && \
    mkdir -p /app/.next/cache && chown -R mateerp:mateerp /app
COPY --from=build --chown=mateerp:mateerp /app/.next/standalone ./
COPY --from=build --chown=mateerp:mateerp /app/.next/static ./.next/static
USER mateerp
EXPOSE 3000
CMD ["node", "server.js"]
