# Deploy — fieldagent.thomaspeng.ca

Static `web/out` served by the shared Caddy on the VPS (`file_server`, no live backend →
zero runtime LLM cost/abuse surface). DNS already resolves `fieldagent.thomaspeng.ca` →
65.109.48.171. The snippet is covered by the existing `import sites/personal/*.caddy` line,
so **no Caddyfile edit is needed**.

## Go-live (run from the repo root)
```bash
cd web && npm ci && npm run build && cd ..            # produce web/out (static export)
# Apply the snippet under an advisory lock; validate the FULL assembled config; revert on failure.
( flock 9
  cp deploy/fieldagent.caddy /etc/caddy/sites/personal/fieldagent.caddy
  sudo -n caddy validate --config /etc/caddy/Caddyfile \
    && sudo -n systemctl reload caddy \
    || { rm -f /etc/caddy/sites/personal/fieldagent.caddy; sudo -n systemctl reload caddy; \
         echo "reload FAILED — reverted; siblings restored"; }
) 9>/tmp/caddy-deploy.lock
```

## Post-deploy security check (all must hold)
```bash
curl -sI https://fieldagent.thomaspeng.ca            # 200/3xx
curl -sI https://fieldagent.thomaspeng.ca/.git/config  # MUST be 404 (repo not exposed)
curl -sI https://fieldagent.thomaspeng.ca/.env         # MUST be 404
```
Caddy `root` points at `web/out` (NOT the repo root) and there is no `browse`, so dotfiles and
source are never served. If the validate/reload chain fails, the snippet is reverted automatically;
fix the reported clash and re-run.
