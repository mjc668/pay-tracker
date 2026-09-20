FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_APP_VERSION=dev
ENV NEXT_PUBLIC_APP_VERSION=$NEXT_PUBLIC_APP_VERSION
ARG NEXT_PUBLIC_SESSION_HEARTBEAT_SECONDS=180
ENV NEXT_PUBLIC_SESSION_HEARTBEAT_SECONDS=$NEXT_PUBLIC_SESSION_HEARTBEAT_SECONDS
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["/bin/sh", "-c", "echo '' && echo '  Frontend/UI available on: http://localhost:3010' && echo '' && node server.js"]
