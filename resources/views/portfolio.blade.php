<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Field Notes — Fictional portfolio</title>
@if(\App\Settings::get('CORRIDORA_RUM_KEY') !== '')
<script src="{{ \App\Settings::get('CORRIDORA_RUM_SCRIPT_URL','https://rum.corridora.com/corridora-rum.js') }}{{ str_contains(\App\Settings::get('CORRIDORA_RUM_SCRIPT_URL'),'?') ? '&' : '?' }}ckid={{ rawurlencode(\App\Settings::get('CORRIDORA_RUM_KEY')) }}"
 data-endpoint="{{ \App\Settings::get('CORRIDORA_RUM_ENDPOINT',\App\Settings::get('CORRIDORA_OTLP_ENDPOINT','https://ingest.corridora.com')) }}" data-service="sample-portfolio-web"
 data-service-namespace="{{ \App\Settings::get('OTEL_SERVICE_NAMESPACE','corridora-samples.portfolio') }}" data-env="{{ \App\Settings::get('DEPLOYMENT_ENVIRONMENT','development') }}"
 data-version="{{ \App\Settings::version() }}" data-trace-sample-rate="1" data-long-tasks="true" data-trace-origins="{{ request()->getSchemeAndHttpHost() }}" data-encoding="json"></script>
@endif
<meta name="htmx-config" content='{"allowEval":false,"includeIndicatorStyles":false}'>
<link rel="stylesheet" href="/assets/style.css"><script src="/assets/htmx.js" defer></script><script src="/assets/app.js" defer></script></head>
<body><nav><a href="/" class="brand">FIELD NOTES<span> FICTIONAL FINANCE</span></a><span class="pill">Akamai / PHP / HTMX</span></nav>
<main><header><p class="eyebrow">PORTFOLIO / 001</p><h1>Small holdings.<br>Clear signals.</h1><p class="intro">A fictional portfolio to explore valuation, dependency calls and the cost of a slow change. Prices are seeded fixtures; no market data or brokerage connection.</p></header>
<section class="summary"><div><span class="label">VALUATION</span><h2 id="total">$1,105.50</h2><p id="state" aria-live="polite">Ready to calculate</p></div><div class="actions"><button id="revalue">Revalue portfolio <span>↗</span></button><button id="control" class="secondary">Healthy control</button><p id="elapsed">Three fictional holdings · USD</p></div></section>
<section class="positions"><div class="section-title"><h2>Your positions</h2><span>SEEDED DATA / NO ACCOUNT REQUIRED</span></div><div id="holdings" hx-get="/fragments/holdings" hx-trigger="load" hx-swap="innerHTML"><p>Loading positions…</p></div></section>
<section class="notes"><div><p class="eyebrow">WHAT TO INVESTIGATE</p><h3>The same answer.<br>A different path.</h3></div><p>Every day at 14:20 UTC a simulated release replaces one batch operation with three sequential holding lookups and a bounded 1.5-second delay. The healthy control keeps the original path. Corridora connects the browser action to Laravel, SQLite and an optional AWS price fixture.</p></section>
<footer><span id="trace">Trace appears after valuation</span><span>Fictional assets · Educational sample</span></footer></main></body></html>
