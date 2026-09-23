---
project: pay-tracker
researched_at: 2026-06-24
updated: 2026-09-22
recommended_platform: self-hosted-docker-compose
runner_up: railway
context_type: mvp
tech_stack:
  language: TypeScript + Python
  framework: Next.js 16 + FastAPI
  runtime: Node.js + Python 3.13
  database: PostgreSQL 17
---

## Recommendation

**Self-hosted Docker Compose with images published to GitHub Container Registry (GHCR).**

Pay Tracker is built and distributed as a set of Docker images users pull and run via `docker compose up`. There is no required cloud platform — the deployment target is any Linux machine (VPS or local). When remote access is needed, a Hetzner CX22 VPS (~€4.30/month) fronted by Cloudflare's free proxy tier is the reference setup. This matches the PRD's explicit self-host intent, keeps costs near-zero, and avoids any vendor dependency at the MVP stage. Railway is the recommended cloud PaaS if the user later wants managed services without operational overhead.

## Platform Comparison

Platforms were evaluated against five agent-friendly criteria: CLI-first tooling, persistent-process support (required by APScheduler), agent-readable docs, stable deploy API, and MCP/integration support. Hard filter: all serverless-only platforms (Vercel, Netlify, Cloudflare Workers) were eliminated — they cannot run a persistent background scheduler.

| Platform | CLI-first | Persistent processes | Agent-readable docs | Stable deploy API | MCP / Integration | Cost fit | EU reach | Co-location |
|---|---|---|---|---|---|---|---|---|
| **Self-hosted Docker Compose** | Pass (docker CLI) | Pass | n/a | Pass | n/a | ~€4.30/mo ✓✓ | Any region via Hetzner | Self-managed |
| **Railway** | Pass | Pass | Pass (llms.txt + markdown) | Pass | Fail | ~$10-15/mo ✓ | Amsterdam GA | Pass (managed PG) |
| **Render** | Partial (no CLI rollback) | Pass | Pass (llms.txt + exp. MCP) | Pass | Partial | ~$20/mo | Frankfurt only | Pass (managed PG) |
| **Fly.io** | Pass | Pass | Partial (no llms.txt) | Pass | Fail | ~$10-55/mo | 5 EU regions | Managed PG costly |

### Shortlisted Platforms

#### 1. Self-hosted Docker Compose (Recommended)

The project already has a Docker Compose setup with all services defined. Publishing images to GHCR and providing a `docker-compose.yml` with pinned image tags is zero infrastructure overhead — no platform account, no vendor dependency, no managed service fees. A Hetzner CX22 (2 vCPU, 4 GB RAM, ~€3.79/month) comfortably runs Next.js + FastAPI + PostgreSQL with headroom. Cloudflare's free tier handles SSL termination and global CDN caching, making single-region deployments feel fast globally. The operational overhead (manual pg_dump backups, Nginx config) is real but manageable for a solo dev and mirrors the household's existing self-host comfort level.

#### 2. Railway

Railway is the best cloud PaaS option if operational overhead becomes a pain point. It has an official Next.js + FastAPI + Postgres starter template, EU Amsterdam GA since February 2025, persistent APScheduler support, co-located managed Postgres, and full LLM-readable docs (`railway.com/llms.txt`). The Hobby plan ($5/month minimum) typically runs $10-15/month for three services. Main migration step: Postgres must be extracted from the backend container into a separate Railway service. Good escape hatch from self-hosting without rewriting anything.

#### 3. Render

Render offers managed multi-service deployments with a Frankfurt EU region and both `llms.txt` and experimental MCP server support. The Background Worker service type is a clean fit for APScheduler. Main downsides: ~$20/month for a viable setup (two Starter services + Postgres), no CLI rollback (dashboard only), and Frankfurt is the only EU region. A reasonable option if Railway isn't available, but not the first choice.

## Anti-Bias Cross-Check: Self-hosted Docker Compose

### Devil's Advocate — Weaknesses

1. **No managed database backups.** pg_dump cron must be built, tested, and monitored manually. A broken backup script is silently broken until disaster — the most common failure mode for self-hosted Postgres.

2. **Zero-downtime deploys don't come free.** `docker compose up -d` causes a brief service restart gap. A blue-green deploy requires additional scripting not included in a basic Docker Compose setup.

3. **SSL certificate management is on you.** Certbot + Let's Encrypt requires renewal automation (every 90 days). Cloudflare as a proxy sidesteps this but adds a DNS dependency.

4. **No platform-level health monitoring.** There's no equivalent to Railway's service health dashboard. A crashed container restarts automatically via Docker's restart policy, but silent failures (e.g., APScheduler stops without crashing) are invisible until a user notices missed reminders.

5. **Hetzner support is community-only.** No live chat, no ticketed support on basic plans. DigitalOcean at $12/month offers ticketed support if that matters.

### Pre-Mortem — How This Could Fail

The household self-hosted Pay Tracker on a Hetzner CX22 in 2026. Eight months later, the Postgres volume on the VPS disk filled up — Docker named volumes don't auto-expand, and nobody was monitoring disk usage. The `docker compose up` started failing with cryptic Postgres write errors. The pg_dump backup cron that was set up on day one had been silently failing for two months because the script's `pg_dump` path broke after a Docker image update changed the binary location. Restoring from the last good backup was possible but required manual SQL surgery to replay 6 weeks of missing data. The second failure: Let's Encrypt certificate renewal failed because the Certbot container wasn't in the Compose file — it had been set up separately via SSH and was forgotten when the server was reprovisioned. The PWA install broke for household members because the cert expired. Both failures were entirely preventable with monitoring, but monitoring wasn't included in the MVP scope.

### Unknown Unknowns

1. **Docker named volumes don't auto-expand.** The Postgres data volume grows with usage. The CX22's 40 GB SSD is generous for a household app, but monitoring `df -h` should be part of the ops checklist. A full disk causes Postgres to stop accepting writes with no advance warning.

2. **APScheduler and DST/UTC mismatch.** The scheduler fires on UTC time. If the VPS system clock drifts or DST handling is incorrect in the server's timezone config, reminders can arrive an hour early or late. Always configure the VPS with `timedatectl set-timezone UTC` and test reminder timing across DST transitions.

3. **Docker Compose `restart: unless-stopped` is not the same as systemd supervision.** If the VPS reboots, Docker itself must autostart (enabled by default on most distros), then Compose services restart. But if Docker fails to start (e.g., after a kernel update requiring a reboot), Compose services don't come up. Set `docker.service` as a systemd dependency: `systemctl enable docker`.

4. **GHCR image visibility.** GitHub Container Registry images default to private if the repo is private. Publishing Pay Tracker images for self-hosters requires explicitly setting the package visibility to public or managing per-user access tokens — not automatic.

5. **Cloudflare proxying WebSocket / long-poll.** Cloudflare's free plan proxies HTTP/HTTPS and WebSocket connections but has a 100-second timeout on connections. For Pay Tracker this is irrelevant (no WebSockets), but worth knowing if the app ever adds real-time features.

## Operational Story

- **Preview deploys**: No platform-provided preview URLs. Test locally with `docker compose up --build` before pushing. For staging, a second VPS or a `staging` branch with a separate Compose override (`docker-compose.staging.yml`) is the standard pattern.
- **Secrets**: `.env` file on the VPS (never committed). Copy to server via `scp .env user@server:/app/.env` or use a GitHub Actions secret → SSH deploy step that writes the file before `docker compose up`. Rotate by replacing the `.env` file and restarting the stack.
- **Rollback**: `docker compose down && docker compose up -d` with a pinned image tag (`image: ghcr.io/youruser/pay-tracker-backend:sha-abc123`). Rollback time: ~60 seconds. DB migrations that ran during a bad deploy must be reversed manually with `alembic downgrade -1`.
- **Approval**: All production actions (deploy, rollback, secret rotation, server access) require a human SSH session. No unattended agent access to the VPS.
- **Logs**: `docker compose logs -f --tail=100 backend` or `docker compose logs -f --tail=100 frontend`. For persistent logs across restarts: configure Docker's `json-file` log driver with `max-size: 10m` and `max-file: 3` in `/etc/docker/daemon.json`.

## Notification channels

Reminders and the monthly summary are delivered through the first configured channel:

1. **Apprise** — preferred whenever `APPRISE_BASE_URL` is set. The gateway may hold its own targets (its `APPRISE_STATELESS_URLS` or a saved config key) — `APPRISE_URLS` and `APPRISE_KEY` are optional request-level overrides.
2. **SMTP email** — optional legacy fallback, used when Apprise is not configured or fails. Password reset still requires SMTP; without it the "Forgot password" link is hidden.
3. Neither configured — the scheduler logs a warning and skips; the "send now" endpoints return `400 No notification channel configured`.

Note: `unraid/apprise-go` is a CLI-only port with no HTTP server — run `caronc/apprise` or `lscr.io/linuxserver/apprise-api` as the gateway, or wrap the Go CLI yourself.

| Env var | Default | Meaning |
|---|---|---|
| `APPRISE_BASE_URL` | — | Apprise API base URL, e.g. `http://10.112.200.5:8000` (trailing `/` stripped) |
| `APPRISE_URLS` | — | Stateless mode: space/comma-separated target URLs passed through as-is |
| `APPRISE_KEY` | — | Stateful mode: config key stored in the Apprise container (wins over `APPRISE_URLS`) |
| `APPRISE_TIMEOUT_SECONDS` | `10` | HTTP timeout for the Apprise call |

The Apprise container must be reachable from the backend container — use the host IP or a shared Docker network (`localhost` would point at the backend container itself). Example sidecar:

```yaml
services:
  apprise:
    image: caronc/apprise:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - apprise-config:/config

volumes:
  apprise-config:
```

Stateless example:

```bash
APPRISE_BASE_URL=http://10.112.200.5:8000
APPRISE_URLS="ntfy://paytracker discord://1234/abcdef"
```

Apprise failures fall back to email immediately (no queue or retry). `email_sent_at` is stamped only for email deliveries; reminder flags are set for any successful channel.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| pg_dump cron fails silently | Devil's advocate | M | H | Test the backup script on day 1 with a dry-run restore; add a cron health-check (`healthchecks.io` free tier or similar) that pings on successful backup |
| Disk fills up (Postgres volume) | Unknown unknowns | L | H | Set up a disk-usage alert: `df -h` cron that emails when >80% full; or use Hetzner's free server monitoring dashboard |
| APScheduler stops without crashing | Devil's advocate | L | M | Add a `/healthz` endpoint that returns scheduler job count; monitor via `curl` cron that alerts on missing jobs |
| Let's Encrypt cert expires | Pre-mortem | M | M | Use Cloudflare as TLS proxy (eliminates cert management entirely); or put Certbot renewal in a Compose service with `restart: always` |
| Docker doesn't autostart after VPS reboot | Unknown unknowns | L | M | `systemctl enable docker`; add `restart: unless-stopped` to all Compose services; test with `sudo reboot` before going live |
| GHCR images accidentally private | Unknown unknowns | L | L | Explicitly set package visibility to Public in GitHub repo → Packages → Settings after first push |
| DST causes reminder timing shift | Unknown unknowns | L | L | Set VPS timezone to UTC; document the UTC-to-local offset in the user-facing settings UI (already planned in PRD) |
| Zero-downtime deploy gap | Devil's advocate | H | L | For a household app, a 5-10 second restart gap is acceptable; document expected downtime during deploys |

## Getting Started

These steps assume Hetzner CX22 (Ubuntu 24.04) + Cloudflare DNS + GHCR image publishing. Adapt for local-only use by skipping steps 3-4.

1. **Provision the VPS and install Docker:**
   ```bash
   # On the VPS (SSH in first)
   curl -fsSL https://get.docker.com | sh
   systemctl enable docker
   usermod -aG docker $USER
   ```

2. **Publish images to GHCR from CI:**
   ```yaml
   # In .github/workflows/publish.yml
   - name: Build and push backend
     uses: docker/build-push-action@v5
     with:
       context: ./backend
       push: true
       tags: ghcr.io/${{ github.repository_owner }}/pay-tracker-backend:${{ github.sha }}
   ```

3. **Write a production Compose file** (`docker-compose.prod.yml`) with pinned image tags instead of `build:` directives, pulling from GHCR:
   ```yaml
   services:
     backend:
       image: ghcr.io/youruser/pay-tracker-backend:sha-abc123
       restart: unless-stopped
     frontend:
       image: ghcr.io/youruser/pay-tracker-frontend:sha-abc123
       restart: unless-stopped
   ```

4. **Set up Cloudflare:** Point your domain's nameservers to Cloudflare, add an A record to the VPS IP, enable the orange-cloud proxy. This gives free SSL, CDN, and DDoS mitigation — no Certbot needed.

5. **Deploy:**
   ```bash
   # On the VPS
   cd /app
   docker compose -f docker-compose.prod.yml pull
   docker compose -f docker-compose.prod.yml up -d --remove-orphans
   docker compose -f docker-compose.prod.yml logs -f
   ```

6. **Set up pg_dump backup cron** (on the VPS):
   ```bash
   # /etc/cron.daily/pg-backup
   #!/bin/bash
   docker compose -f /app/docker-compose.prod.yml exec -T backend \
     pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
     | gzip > /backups/db-$(date +%Y%m%d).sql.gz
   find /backups -mtime +7 -delete
   # Test restore monthly: gunzip -c /backups/db-YYYYMMDD.sql.gz | psql ...
   ```

## HTTPS & PWA deployment

PWA installation and secure cookies both require HTTPS (browsers exempt only `localhost`). A reference Caddy config lives at `infra/caddy/Caddyfile`; all options below keep the backend's month-based routes working unchanged.

Relevant env vars:

| Env var | HTTPS value | Why |
|---|---|---|
| `COOKIE_SECURE` | `true` | Adds `Secure` to the auth cookies. Over plain HTTP browsers drop them and login bounces back to `/login` — the backend logs a startup warning if this is misconfigured. |
| `TRUST_PROXY` | `true` | Rate limiting uses the real client IP from `X-Forwarded-For`. |
| `APP_BASE_URL` | `https://pay.example.com` | Used in password-reset links. |
| `ALLOWED_ORIGINS` | `["https://pay.example.com"]` | Cross-origin mode only (separate API hostname). |
| `NEXT_PUBLIC_API_URL` | empty | Same-origin mode: the proxy forwards `/api/*` to the backend. |
| `API_PREFIX` | `/api` | Pairs with an empty `NEXT_PUBLIC_API_URL`. |

### Option A — Caddy (recommended)

`infra/caddy/Caddyfile` terminates HTTPS, serves the frontend, and proxies `/api/*` to the backend with the prefix stripped:

```caddy
pay.example.com {
	reverse_proxy 10.112.200.5:3010

	handle /api/* {
		uri strip_prefix /api
		reverse_proxy 10.112.200.5:8010
	}
}
```

- **Public domain:** point an A record at the host; Caddy obtains and renews Let's Encrypt certificates automatically.
- **LAN-only:** use a local name (e.g. `pay.local`) and add `tls internal`. Caddy signs with its own CA — install Caddy's root certificate on every device, or PWA installation can fail silently on some platforms.

### Option B — nginx + Certbot

```nginx
server {
    listen 443 ssl;
    server_name pay.example.com;

    ssl_certificate     /etc/letsencrypt/live/pay.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pay.example.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8010/;   # trailing slash strips /api
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:3010;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

Renew with `certbot renew` (systemd timer or cron). Keep the renewal in the same managed stack as the app — the pre-mortem above is exactly the failure mode where a forgotten renewal breaks PWA installs when the certificate expires.

### Option C — Cloudflare proxy (public domain)

Point the domain's nameservers at Cloudflare and proxy the A record to the host. TLS terminates at Cloudflare (no Certbot) and the origin can stay HTTP on the LAN. Still set `COOKIE_SECURE=true` and `TRUST_PROXY=true` — the browser sees HTTPS. Use Cloudflare Tunnel if no inbound ports should be opened.

### Verify the install

1. DevTools → Application → Cookies: `access_token` and `auth_logged_in` show the `Secure` flag.
2. DevTools → Application → Service Workers: the service worker is active and the manifest lists the Pay Tracker icons.
3. The install prompt appears (Chrome/Edge address bar; iOS Safari → Share → Add to Home Screen).
4. Layout stays usable at 375px.

Common pitfalls:

- **Mixed content:** an HTTPS page calling an `http://` API is blocked — use same-origin `/api` or an HTTPS API hostname.
- **`COOKIE_SECURE=true` over plain HTTP:** browsers drop the auth cookies; login appears to succeed then bounces to `/login`.
- **`tls internal`:** the Caddy CA must be trusted on every device.
- **Cross-origin mode:** `ALLOWED_ORIGINS` must list the exact HTTPS frontend origin.

## Out of Scope

The following were not evaluated in this research:
- CI/CD pipeline configuration (GitHub Actions deploy workflow)
- Production-scale architecture (multi-region, HA, disaster recovery)
- Email delivery provider configuration (FR-012)
