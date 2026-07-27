# Hosting: NAS, VPS, and getting to it from outside

**Status:** the site runs on the NAS. This is the map for moving it, and
for exposing it without opening a port.

---

## 1. What actually needs to move

Almost nothing, and that is the point of the shape in `compose.yaml`.

The site is static HTML built by `build_site.py` from JSON in `data/sites`.
There is no database, no session state, no uploads, no user accounts. The
whole install is a git clone plus whatever local data files differ from it.
So "moving to a VPS" is: clone, start the container, point DNS at it.

The one thing that is *not* in git is any local-only record on the NAS —
records `update.sh` has been leaving alone. Reconcile those into the repo
**before** moving, or they are gone:

```bash
python3 scripts/merge_records.py        # dry run, read it
python3 scripts/merge_records.py --write
git status                              # anything local worth committing?
```

The ETL side is different. Tile builds want cores, RAM and scratch disk,
and a cheap VPS has none of those. Leave ETL where the disks are and ship
the output; see section 5.

## 2. Sizing

The site is ~550 static pages, a few MB. It is not a load problem, it is
a latency and availability problem — which is exactly what home broadband
is bad at.

| | Enough for |
|---|---|
| 1 vCPU, 1GB, 25GB | The site, comfortably. This is the whole job. |
| 2 vCPU, 4GB | Room for Phase 2's PostGIS alongside. |
| 4 vCPU, 8GB+ | Only if ETL moves too, and it should not. |

Start at the smallest. Serving static files off SSD over a datacentre
uplink is not work.

**Where.** Anything with a UK or Irish region: Hetzner, Vultr, DigitalOcean,
Scaleway, Civo, Mythic Beasts. UK region matters here — the audience is
UK, and a London hop beats a Frankfurt one for no extra money.

## 3. Moving it

On a fresh Debian or Ubuntu box:

```bash
# Docker, from Docker's own repo rather than the distro's old one
curl -fsSL https://get.docker.com | sh

# The project
git clone https://github.com/andrewdunn358-dev/vanlife.git
cd vanlife
cp .env.example .env          # set SITE_PORT if 24721 is taken

docker compose up -d site
curl -sI localhost:24721/index.html | head -1    # expect 200
```

That is the migration. `restart: unless-stopped` handles reboots.

**Do not publish 24721 to the world.** Bind it to loopback and put
something in front — section 4. In `compose.yaml`, or better in a
`compose.override.yaml` the repo will not overwrite:

```yaml
services:
  site:
    ports: ["127.0.0.1:24721:24721"]
```

**Keeping it current.** `update.sh` pulls code and new data without
touching local data, and `serve.py` rebuilds on change, so a cron entry is
the whole deployment pipeline:

```
*/30 * * * * cd /srv/vanlife && ./scripts/update.sh >> /var/log/vanlife-update.log 2>&1
```

A VPS has no local research on it, so unlike the NAS it can also simply
`git pull` and let the container rebuild.

## 4. Cloudflare Tunnel

A tunnel makes an **outbound** connection from the box to Cloudflare and
serves the site through it. No inbound port, no firewall rule, no static
IP, and it works behind CGNAT — which is the reason it suits the NAS. On a
VPS with a public IP it is optional but still worth it: the origin IP
stays hidden and there is nothing listening to be scanned.

Prerequisite: the domain's nameservers point at Cloudflare.

### Set it up once

```bash
# Install cloudflared (Debian/Ubuntu)
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
https://pkg.cloudflare.com/cloudflared any main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared

cloudflared tunnel login                    # opens a browser, pick the zone
cloudflared tunnel create vanlife           # writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns vanlife overnight.example.com
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: vanlife
credentials-file: /root/.cloudflared/<UUID>.json

ingress:
  - hostname: overnight.example.com
    service: http://localhost:24721
  # Every ingress list must end in a catch-all or cloudflared will not start
  - service: http_status:404
```

Run it as a service so it survives reboots:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

### Or run it in Docker, beside the site

Keeps the box clean and moves with the project. Create the tunnel in the
Cloudflare dashboard (Zero Trust → Networks → Tunnels), copy the token,
put it in `.env` as `TUNNEL_TOKEN`, and add to `compose.override.yaml`:

```yaml
services:
  tunnel:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}
    restart: unless-stopped
    depends_on: [site]
```

With both containers on the same compose network the tunnel reaches the
site as `http://site:24721`, so nothing needs publishing to the host at
all — delete the `ports:` block entirely and the site becomes unreachable
except through Cloudflare.

### Worth knowing

- Cloudflare terminates TLS, so no certbot and no renewals.
- The free plan is fine. Tunnels are not metered.
- `cloudflared tunnel list` and `cloudflared tunnel info vanlife` to check.
- Cache: static HTML caches well at the edge. Set a page rule or cache
  rule for `overnight.example.com/*`. Remember `serve.py` sends
  `Cache-Control: no-store` for local editing, so override it at
  Cloudflare rather than wondering why nothing caches.
- The tunnel is the answer for **the NAS too**. It is the cheaper move: no
  VPS, no migration, and it fixes the access half of the problem
  immediately. It does not fix the speed half — the bytes still leave the
  house — but with edge caching on static pages, most requests never reach
  it.

## 5. Where this leaves the split

The architecture in `scoping.md` already assumed this: heavy processing at
home, thin serving elsewhere. A VPS for the site fits it exactly.

- **Site** — VPS or Cloudflare Pages. Small, static, latency-sensitive.
- **ETL and tiles** — stay on the NAS. Hours of CPU and tens of GB of
  scratch; renting that is expensive and pointless.
- **PMTiles** — Cloudflare R2, as scoped. Zero egress, edge-cached, and
  never served from a VPS disk or from home.

One honest alternative to all of the above: the output is static, so
**Cloudflare Pages will host it for nothing**, with no server to run,
patch or pay for. Build on the NAS, push `site/` to a Pages project, and
the only thing left at home is the build. That is fewer moving parts than
a VPS. The reason to want a VPS anyway is if Phase 2's D-TRO sync and
PostGIS need somewhere to live that is not the house — which is a real
reason, just a later one.
