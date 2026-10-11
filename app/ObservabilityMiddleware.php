<?php
declare(strict_types=1);
namespace App;

use Illuminate\Http\Request;
use Closure;

final class ObservabilityMiddleware
{
    public function handle(Request $request, Closure $next): mixed
    {
        $telemetry=new Telemetry(); app()->instance(Telemetry::class,$telemetry);
        $headers=[]; foreach ($request->headers->all() as $k=>$v) $headers[$k]=$v[0];
        $span=$telemetry->server($request->method().' '.$request->path(),$headers); $scope=$span->activate(); $started=microtime(true);
        $store=app(Store::class); $scenario=new Scenario($store); $state=$scenario->status();
        $scenario->transition($telemetry,$state);
        $span->setAttributes(['http.request.method'=>$request->method(),'url.path'=>$request->getPathInfo(),'demo.scenario'=>$state['scenario'],'demo.release'=>$state['release'],'demo.phase'=>$state['phase']]);
        try {
            $response=$next($request); $span->setAttribute('http.response.status_code',$response->getStatusCode());
            if ($response->getStatusCode()>=500) $span->setStatus('Error');
            $response->headers->set('Cache-Control','no-store');
            $response->headers->set('X-Trace-Id',$span->getContext()->getTraceId());
            $response->headers->set('X-Content-Type-Options','nosniff');
            if ($request->getPathInfo()==='/') {
                $origin=fn(string $u) => (($p=parse_url($u)) && isset($p['scheme'],$p['host'])) ? $p['scheme'].'://'.$p['host'].(isset($p['port'])?':'.$p['port']:'') : '';
                $rum=$origin(Settings::get('CORRIDORA_RUM_SCRIPT_URL','https://rum.corridora.com/corridora-rum.js'));
                $ingest=$origin(Settings::get('CORRIDORA_RUM_ENDPOINT',Settings::get('CORRIDORA_OTLP_ENDPOINT','https://ingest.corridora.com')));
                $response->headers->set('Content-Security-Policy',"default-src 'self'; script-src 'self' $rum; connect-src 'self' $ingest; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
            }
            $telemetry->log('HTTP request completed',['http.request.method'=>$request->method(),'url.path'=>$request->getPathInfo(),'http.response.status_code'=>$response->getStatusCode(),'demo.release'=>$state['release']]);
            return $response;
        } catch (\Throwable $e) { $span->recordException($e); $span->setStatus('Error'); throw $e; }
        finally { $scope->detach(); $span->end(); $telemetry->finish(microtime(true)-$started,['http.request.method'=>$request->method(),'demo.phase'=>$state['phase']]); }
    }
}
