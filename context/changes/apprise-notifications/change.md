---
change_id: apprise-notifications
title: Apprise notification channel with email fallback
status: in-progress
created: 2026-09-21
updated: 2026-09-21
---

## Notes

Route bill reminders and the monthly summary through an Apprise API gateway (the standard `POST /notify` stateless / `POST /notify/{key}` stateful contract served by `caronc/apprise` and `linuxserver/apprise-api`; `unraid/apprise-go` itself is CLI-only and has no HTTP server). Apprise is preferred when configured; SMTP email is the fallback when Apprise is unset, fails, or times out. Settings gains an Apprise status line and a Send-test-notification button. All Apprise connection details come from env vars so deployments can point at different hosts.
