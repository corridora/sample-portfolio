import { context, trace, SpanStatusCode } from '@opentelemetry/api';

// Corridora's early-loaded RUM owns the provider. The API obtains that registered provider.
const tracer = trace.getTracer('sample-portfolio-htmx', '1.0.0');
async function revalue(control) {
  const action = tracer.startSpan(control ? 'portfolio.healthy-control' : 'portfolio.revalue');
  const started = performance.now();
  const button = document.querySelector(control ? '#control' : '#revalue');
  button.disabled = true;
  document.querySelector('#state').textContent = 'Calculating…';
  try {
    // Initiate fetch inside action scope; retain action explicitly over the await.
    const response = await context.with(trace.setSpan(context.active(), action), () => fetch(`/api/valuation${control ? '?portfolio=control' : ''}`));
    if (!response.ok) throw new Error(`Valuation failed (${response.status})`);
    const data = await response.json();
    document.querySelector('#total').textContent = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(data.total);
    document.querySelector('#state').textContent = data.phase === 'regression' ? 'Simulated regression · sequential lookups' : 'Healthy · batched valuation';
    document.querySelector('#elapsed').textContent = `${Math.round(performance.now() - started)} ms · ${data.release}`;
    document.querySelector('#trace').textContent = `Trace ${data.trace_id}`;
    action.setAttributes({ 'demo.phase': data.phase, 'demo.release': data.release, 'portfolio.fictional': true });
    window.portfolioLastResult = { ...data, elapsed_ms: performance.now() - started };
  } catch (error) {
    action.recordException(error); action.setStatus({ code: SpanStatusCode.ERROR });
    document.querySelector('#state').textContent = 'Could not calculate. Try again.';
  } finally { button.disabled = false; action.end(); }
}
document.querySelector('#revalue').addEventListener('click', () => revalue(false));
document.querySelector('#control').addEventListener('click', () => revalue(true));
