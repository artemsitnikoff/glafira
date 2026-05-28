# Multi-stage: build статики через Node, раздача через nginx.

# ---------- Stage 1: build ----------
FROM node:20-alpine AS builder

WORKDIR /app

# Кэш зависимостей: ставим из lockfile до копирования исходников
COPY package.json package-lock.json* ./
RUN npm ci

# Build-time API URL зашивается в статику
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Исходники + контракты (types:gen читает ../contracts/openapi.json)
COPY . .

# tsc -b + vite build → dist/
RUN npm run build

# ---------- Stage 2: serve ----------
FROM nginx:alpine

# Кастомный конфиг с SPA fallback (React Router)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Статика
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
