# Hosting through the judging period (Google Cloud)

Space Apps judges evaluate projects for about two months after the hackathon, so the
observatory stays online until **2027-01-31**. This page is the runbook for that
period: what runs, what it costs and how to keep it alive.

## What runs

| Item | Value |
|---|---|
| Project | `loyal-curve-472605-g7` |
| VM | `surface-tango-pitch-e2e`, zone `us-central1-a`, **e2-standard-2** (2 vCPU, 8 GB), standard provisioning (not spot), `automaticRestart: true`, live-migrates on host maintenance, deletion protection on |
| External IP | static address `surface-tango-web-ip` (us-central1), so a stop/start or resize keeps the same URL |
| Stack | `OFFLINE_DEMO_MODE=1 docker compose --profile pitch up -d` (`make pitch`): web on `:8000`, MCP servers on `127.0.0.1:8001` / `127.0.0.1:8002` (host-only) |
| Restart | containers use `restart: unless-stopped` and Docker is enabled at boot, so the stack comes back after a VM restart |
| Logs | json-file, 10 MB × 3 files per container (`docker-compose.yml`) |
| Ingress | network tag `surface-tango-web`; public port `8000` needs a firewall rule targeting that tag (see below) |

Pitch mode serves the staged cache and the hashed LLM cache, so judges' visits do not
start Earth Engine jobs. Keep it in pitch mode for the whole period.

## Sizing *(measured)*

On 2026-11-15, after 8 h of uptime on the previous e2-standard-4 (16 GB), the host used
1,558 of 15,985 MB, load average 0.00, and the three containers used 537 + 144 + 71 MiB
(`free -m`, `docker stats --no-stream` over `gcloud compute ssh`). After the resize to
e2-standard-2 the host used 977 of 7,934 MB at boot, and `GET /` returned 200.

## Cost for the period *(estimate)*

Google Cloud list prices for `us-central1`, 730 h per month, USD. Check real spend in
**Billing → Reports**; these are not measured.

| Item | Per month |
|---|---|
| e2-standard-2 on demand | ≈ 48.9 |
| 50 GB pd-balanced boot disk | ≈ 5.0 |
| Static IPv4 attached to a running VM | ≈ 3.7 |
| Egress (light judging traffic) | ≈ 1–2 |
| **Total** | **≈ 59** |

2026-11-15 → 2027-01-31 is about 2.5 months, so ≈ USD 150 *(estimate)*, plus what was
spent before 2026-11-15 on the e2-standard-4 (≈ USD 107/month at list price). That fits
the budget below with margin for any Vertex AI or Earth Engine use by the team.

## Budget

The billing budget **"Surface Tango hackathon + evaluation (~USD 300)"** is
**949,000 COP** (the billing account bills in COP; ≈ USD 300) over a custom period
**2026-11-01 → 2027-01-31**, for this project only, with e-mail alerts to billing admins at
25 %, 50 %, 75 %, 90 % and 100 % of actual spend. (Custom-period budgets do not accept
forecast-based alerts.) A budget only alerts: it does not stop anything. If an alert
fires early, check Billing → Reports for the service that grew before stopping anything.

## Operating it

Run these from a machine with the Cloud SDK signed in to an account that can administer
the project.

```bash
# Is it up?
gcloud compute instances describe surface-tango-pitch-e2e --zone us-central1-a --format="value(status,machineType.basename())"
gcloud compute ssh surface-tango-pitch-e2e --zone us-central1-a --command "sudo docker ps; curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/"

# Open the web port to the public (only the web app; never 8001/8002)
gcloud compute firewall-rules create surface-tango-web-8000 --network default --direction INGRESS --allow tcp:8000 --source-ranges 0.0.0.0/0 --target-tags surface-tango-web

# Redeploy the latest main (on the VM, from the deployment checkout)
git pull --ff-only && OFFLINE_DEMO_MODE=1 docker compose --profile pitch up --build -d
```

## Shutting it down after judging

1. Turn deletion protection off: `gcloud compute instances update surface-tango-pitch-e2e --zone us-central1-a --no-deletion-protection`.
2. Delete the VM, then release the static IP (`gcloud compute addresses delete surface-tango-web-ip --region us-central1`); an unattached static IP still bills.
3. Delete the firewall rule `surface-tango-web-8000` if it was created.
4. Leave the budget until the last invoice closes.
