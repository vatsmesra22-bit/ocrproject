# Deploying Grahak Sampark on Eko's server

About an hour for someone who has deployed a Docker app before. The app is
one container; customer data lives on two volumes; a reverse proxy in front
gives it HTTPS.

> The Docker files were written but not test-built on the developer's laptop
> (no Docker there). Run step 2 and report any build error back.

## 1. What the server needs

- Linux with Docker + Docker Compose, 2 GB RAM, 2 CPU (OCR uses ~1 GB while reading a photo)
- Disk for `/var/lib/docker/volumes` on an **encrypted** volume (DPDP)
- A domain name, e.g. `sampark.example.com`, pointing at the server
- nginx (or any reverse proxy) with an HTTPS certificate (e.g. Let's Encrypt)

## 2. Install

```bash
git clone <repo-url> grahak-sampark
cd grahak-sampark
cp .env.example .env
# edit .env - see section 3
docker compose up -d --build
docker compose ps            # STATUS should become "healthy"
curl http://127.0.0.1:8000/healthz   # {"ok":true}
```

## 3. Settings in `.env`

| Setting | Value |
|---|---|
| `APP_ENV` | `production` |
| `EKO_BASE_PATH` | the sub-path if the app is not at the root of the address, e.g. `/ocrproject`; empty otherwise |
| `SECRET_KEY` | new long random string: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `OPTOUT_KEY` | another long random string - **never change it after go-live** |
| `RETENTION_DAYS` / `AUDIT_RETENTION_DAYS` | 30 / 365 unless compliance says otherwise |
| `OCR_ENGINE` | `local` - **keep local**; `voxomos` only after the DPDP conditions in DATA_PROTECTION.md |
| `GRIEVANCE_CONTACT` | complaint phone/email from compliance (shown to customers) |
| `LOGIN_MAX_FAILED`, `LOGIN_LOCKOUT_MINUTES` | 5 / 15 |

Leave `DATA_DIR`/`LOG_DIR` out - the container sets them to its volumes.
After editing `.env`: `docker compose up -d`.

## 4. Create the super admin (once)

```bash
docker compose exec app python -m app.cli create-admin
```

It asks for name, login ID and a password (typed twice, not shown). The browser
setup page used on laptops is switched off in production.

## 5. HTTPS reverse proxy (nginx example)

```nginx
server {
    listen 443 ssl http2;
    server_name sampark.example.com;
    ssl_certificate     /etc/letsencrypt/live/sampark.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sampark.example.com/privkey.pem;

    client_max_body_size 16m;          # list photos up to 15 MB

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
    }
}
server { listen 80; server_name sampark.example.com; return 301 https://$host$request_uri; }
```

`FORWARDED_ALLOW_IPS` in `docker-compose.yml` must be the address nginx connects
from as seen by the container (usually the Docker gateway `172.17.0.1`). Never `*`.

## 7. Before CSPs get the link

1. Log in as super admin, add one test CSP ("Add one CSP").
2. As that CSP, open the link **on a phone**, take a photo of a list whose only
   customer is **your own number**, check, tick, and send from WhatsApp.
3. Check the message arrives correctly on your phone.

## Running it

| Task | How |
|---|---|
| Update to a new version | `git pull && docker compose up -d --build` (readings in progress are lost - CSPs upload again) |
| See logs | `docker compose logs -f app`; files in the `sampark_logs` volume |
| Backup | the `sampark_data` volume (`app.db`: logins, counts, STOP hashes - no customer lists) |
| Uptime monitor | `GET /healthz` |
| Expired lists | deleted automatically every 6 hours |

OCR engine: keep `OCR_ENGINE=local` (default). `voxomos` only after the four
conditions in docs/DATA_PROTECTION.md are met; then also set `VOXOMOS_API_KEY`.

Run **one** container only: readings in progress are held in that process's memory.
