# Set up Corridora for the portfolio app

Published 2026-10-11 · Updated 2026-10-11

## 1. Choose the tenant and keys

Contributors choose `CORRIDORA_TARGET=own` and create a project in their own
Corridora organization. Maintained demos choose `demo` and use credentials issued
by an authorized operator for Demo tenant
`00000000-0000-4000-8000-000000000201`. The key routes data; the UUID is context,
not authorization. Demo forces environment `demo`. Do not mint management keys
through a public demo persona.

Create separate scoped keys: a backend ingest key for all three OTLP signals and
a browser RUM key with the exact deployed origin allowed. Backend keys stay in
`.sample/secrets.json` or the root-owned VM secret file. Browser keys are visible
in HTML and must have browser ingestion/origin restrictions. A management or
query key is neither of these and is never placed in the app. No key is included
in this repository.

Configure the project's service grouping:

| Service | Role |
| --- | --- |
| `sample-portfolio-web` | HTMX/manual actions and Corridora RUM |
| `sample-portfolio-api` | Laravel SERVER, SQLite, cross-cloud CLIENT |
| `sample-portfolio-host` | Collector Linux hostmetrics and Caddy access logs |
| `sample-portfolio-provider` | Native Linode read-only stats adapter |

Namespace defaults to `corridora-samples.portfolio`. Backend/API namespace and
name are configurable; the documented browser/host/provider names are stable.

## 2. Configure with the script

```sh
./setup configure
./setup deploy --plan
./setup deploy                   # local dependencies/assets
./setup run
# In another terminal:
./setup verify
```

Bare `./setup` performs the local sequence and leaves the validated server in
the background. Linux Chromium dependencies may require the documented system
package installation. Dependency installers verify the official Composer
installer checksum and use Composer/npm lockfiles. `./setup --help` works first.

| Prompt | Default / meaning |
| --- | --- |
| `SAMPLE_MODE`, `PORT` | `local`, `4105`; cloud uses fixed private container port |
| `CORRIDORA_TARGET` | `own`; Demo requires both operator-provisioned keys |
| `CORRIDORA_OTLP_ENDPOINT` | `https://ingest.corridora.com`; backend base URL |
| `CORRIDORA_RUM_ENDPOINT` | Same public ingest base; never the private Collector URL |
| `CORRIDORA_RUM_SCRIPT_URL` | `https://rum.corridora.com/corridora-rum.js` |
| `CORRIDORA_INGEST_KEY`, `CORRIDORA_RUM_KEY` | Masked; optional only for an uninstrumented local first run |
| `OTEL_SERVICE_NAME`, `OTEL_SERVICE_NAMESPACE` | API name and common namespace above |
| `DEPLOYMENT_ENVIRONMENT`, `RESOURCE_PREFIX` | `development`, `sample-portfolio`; Demo environment forced |
| `DEMO_DAILY_START_UTC` | `14:20`; maximum window 600 seconds |
| `ENABLE_SYNTHETICS` | `false`; `true` adds one bounded daily/watchdog browser container |
| `ENABLE_PROVIDER_FORWARDING` | `false`; `true` enables native Linode stats token/polling; Collector hostmetrics/access logs remain baseline |
| `PRICE_FIXTURE_URL`, `DOWNSTREAM_AUTH_TOKEN` | Empty local stub; optional controlled AWS HTTPS endpoint and separate bearer token |
| `LINODE_TOKEN`, `LINODE_REGION` | Masked scoped deploy token; `us-ord` (confirm type availability) |
| `LINODE_EXISTING_ID`, `LINODE_HOST` | Both empty creates a new dedicated VM; both set selects an existing account VM |
| `SSH_USER`, `SSH_KEY_PATH`, `SSH_ALLOWED_CIDR` | Root, chosen private-key path with adjacent `.pub`, restricted admin network |
| `TLS_HOSTNAME` | Required cloud hostname; existing owned DNS zone |
| `COLLECTOR_MEMORY_MB` | Fixed baseline `128` |
| `LINODE_STATS_INTERVAL_SECONDS` | `900` minimum; rendered systemd timer uses the chosen interval |
| `LINODE_STATS_TOKEN` | Masked separate read-only token; prompted only when forwarding enabled |

`DEMO_CONTROL_TOKEN` and `APP_KEY` are generated cryptographically when absent,
and may be overridden through environment/protected JSON. Never use an account
password. `TRACKER_SIMULATOR_URL` is reserved for fleet configuration; this app
loads no advertising or tracker scripts beyond Corridora RUM. No real finance
records are sent to any ad provider.

`--non-interactive` uses environment or protected JSON. For cloud,
`deploy --apply` validates required keys and the optional stats token before any
provisioning, displays the account and owned resources, and uses real Linode API
operations and SSH transfer. Existing resources are tracked; rerun resumes after
partial errors. Point DNS to the printed IP and trust the SSH fingerprint only
after checking it through Cloud Manager. Subsequent apply updates the same VM.

## 3. Instrumentation and origin configuration

`app/Telemetry.php` uses the official `open-telemetry/sdk` and
`open-telemetry/exporter-otlp` packages with an HTTP PSR implementation. Resource
attributes include service name/namespace/version, deployment environment,
`cloud.provider=akamai`, region and host ID. It exports JSON over HTTP to
`/v1/traces`, `/v1/logs` and `/v1/metrics`, with backend `X-CORRIDORA-KEY` only.
Traces batch in a 64-span queue and flush at request end; all exporters have an
800 ms transport timeout and no per-request retry. The Collector provides bounded
retry/queue behavior. SDK errors remain visible on stderr. Exporter HTTP requests
are not instrumented, preventing recursion. App JSON logs rotate at 5 MiB and
retain one previous file; access logs retain two 5 MiB files.

`app/ObservabilityMiddleware.php` extracts W3C `traceparent`/`tracestate` before
starting a SERVER span. `app/Portfolio.php` creates SQLite and controlled HTTP
CLIENT spans and injects the active context. Empty AWS URL uses a local child
fixture. There are no background queues in this app; other samples provide that
coverage. `app/Scenario.php` emits deployment/recovery logs and stores expiry.

`resources/views/portfolio.blade.php` loads RUM synchronously in the document head
before HTMX or any application fetch. It passes the visible key as `ckid`, exact
API origin, public ingest endpoint, service namespace/environment/version, sample
rate 1 and long-task capture. `resources/app.js` imports only the OTel API and
uses the provider registered by the RUM distribution. It initiates fetch within
the manual action context and ends the action explicitly after asynchronous work.
It never creates another browser SDK.

Cloud Caddy terminates TLS and preserves W3C headers to the private PHP port.
Laravel trusts forwarded origin headers only because its cloud port is private
behind that proxy. HTML CSP restricts scripts to this origin plus the configured
RUM origin and connections to this origin plus public RUM ingest. The API is
same-origin and adds no wildcard CORS policy. Remote fixture endpoints require
HTTPS, accept no embedded credentials, do not follow redirects and receive only
the dedicated dependency token and trace headers. Direct incoming cross-cloud
calls are server-to-server and do not require browser CORS.

## 4. Add provider signals

`infra/compose.yaml` deploys Caddy, PHP and a 128 MB contrib Collector;
`infra/collector.yaml` configures three signal pipelines, memory limiter, bounded
queue/retry, Linux hostmetrics and JSON Caddy filelog ingestion. Secrets are
rendered into an owner-only Collector config transferred via SSH, not command
arguments. The application's key reaches only the private Collector; the
Collector attaches the backend key to external OTLP. Its host filesystem mount
is read-only; retain only the metrics you need to stay within ingest quotas.

File offsets and the 32-batch-per-signal export queue use `file_storage` on a
dedicated writable `collector_state` volume. Batches are limited to 32 items and
queue storage is compacted on start and after draining. Filelog reads current
and retained gzip Caddy rotations from their persisted offsets, starting new
files at the beginning. Key/config updates explicitly restart the Collector;
routine deployment preserves its volume. A 30-second retry budget, full queue,
abrupt in-flight loss or expired log retention can still drop data. Queue size
limits entries rather than disk bytes; monitor available disk space.

`scripts/provider_adapter.py` converts native Linode `/stats` series to OTLP
gauges. Enabling it requires a distinct `linodes:read_only` token, not the
mutation-capable deploy token. The deploy token stays on the operator machine.
An owner-only adapter config and hardened systemd oneshot/timer poll at most every
15 minutes. Test it with a JSON fixture using `--fixture path.json`. Linode API
CPU utilization and host CPU utilization are distinct series; do not merge them.
The adapter reads the API's `data.cpu` envelope, validates finite points and
fails visibly when no CPU points are available, rather than exporting an empty batch.
Longview, CDN, enterprise EdgeWorkers and Object Storage are not enabled.

## 5. Verify stored telemetry and replay

```sh
./setup verify
./setup scenario --phase regression --duration-seconds 120
./setup scenario --phase recover --duration-seconds 600
```

Verification executes real page clicks, records trace IDs and posts the daily
heartbeat after success. A configured RUM script must report ready; blocked or
failed initialization withholds the heartbeat. This does not prove export or
remote storage. It does not have a scoped query credential. Open
Corridora, choose the destination organization/project and find the fresh browser
session. Locate `portfolio.revalue`, its RUM HTTP CLIENT, and Laravel SERVER with
the same trace ID and the CLIENT's span ID as the SERVER parent. Inspect SQLite
children and the optional AWS CLIENT/SERVER continuation. Check an application
log carries the same trace/span IDs, then check
`http.server.request.duration`, a host metric, native Linode CPU gauge if enabled,
and Caddy access log. Filter `demo.scenario=holding-nplus1` and `demo.release` for
the rollout, affected call, healthy control and automatic recovery. An HTTP 200
from ingestion alone does not prove any of these stored relationships.

The optional runner checks and persists `/api/demo/heartbeat`. A missing result
after the daily window triggers a new bounded simulated release and complete
browser replay. Schedule periods run from the configured UTC start to the next
day's start, including across midnight; only a successful heartbeat timestamp
inside that period suppresses replay. Inspect runner logs and alert on a
missing daily heartbeat. A VM outage, memory pressure or browser failure can
still prevent the goal. The GitHub workflow offers a separate runner and watchdog
but scheduled jobs may be delayed/dropped and inactive public schedules disable
after 60 days. Keep the runtime window and manual replay available.

## 6. Rotate, troubleshoot and remove

Rerun `./setup configure`, enter rotated scoped keys and `deploy --apply`. This
updates root-owned secret files and restarts the deployment. Revoke old keys in
Corridora only after verifying new telemetry. Never paste key values into logs.

Missing telemetry: confirm the RUM script loads before HTMX, browser key origin
matches HTTPS hostname, CSP allows RUM and public ingest, and each exporter URL is
a base URL without `/v1/*`. Inspect PHP stderr/Collector logs. Parentage missing:
confirm W3C headers survive Caddy and the remote fixture is controlled/allowlisted.
Healthy controls slow: check genuine dependency latency separately from the
injected three 500 ms spans. SSH error: check host fingerprint, key and CIDR; the
installer never disables host checks. TLS error: check A/AAAA records and 80/443.
Memory/disk pressure: move Chromium to the GitHub runner, inspect Docker limits,
log rotation and old images. Initial generation did not validate hosted behavior.

```sh
./setup destroy --plan
./setup destroy --apply
```

Owned new VM/firewall resources require matching live tags before deletion.
Existing shared VMs survive; their marked Compose deployment stops and files are
retained. Local teardown stops only a matching sample PID and keeps local
credentials/data. Remove `.sample` and `storage/portfolio.sqlite*` yourself when
you want a complete local reset. Domain/DNS and other sample clouds are separate.

See [PHP OTel exporters](https://opentelemetry.io/docs/languages/php/exporters/),
[Collector configuration](https://opentelemetry.io/docs/collector/configuration/),
[Linode stats](https://techdocs.akamai.com/linode-api/reference/get-linode-stats)
and [GitHub scheduled-run limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

For an external scheduled browser, set repository variables
`ENABLE_DAILY_JOURNEY=true` and `SAMPLE_URL=https://your-hostname`, plus repository
secret `DEMO_CONTROL_TOKEN`. `.github/workflows/daily.yml` runs at 14:20 UTC and
checks/replays missing heartbeats at 15:00, 18:00 and 22:00. Enable either this
workflow or the VM runner to avoid unnecessary duplicate synthetic traffic;
heartbeat checks prevent repeat daily successes. Alert on failed jobs or a
missing daily heartbeat. Public repositories use standard hosted runners within
GitHub's published allowance; no artifacts are retained by this workflow.
