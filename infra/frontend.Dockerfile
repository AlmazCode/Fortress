# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/src ./src
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
RUN npm run build

FROM nginx:stable-alpine@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5 AS harness
COPY infra/nginx.conf /etc/nginx/nginx.conf
RUN printf '<!doctype html><html lang="en"><title>Fortress infra-only harness</title><h1>Synthetic infrastructure harness</h1><p>No application or model inference is running.</p></html>' > /usr/share/nginx/html/index.html

FROM harness AS production
COPY --from=build /frontend/dist /usr/share/nginx/html
