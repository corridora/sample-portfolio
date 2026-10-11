<?php
use Illuminate\Support\Facades\Route;
use Illuminate\Http\Request;
use App\{Settings,Store,Scenario,Portfolio,Telemetry};

$authorized=function(Request $request): bool {
    $token=Settings::get('DEMO_CONTROL_TOKEN');
    return strlen($token)>=16 && hash_equals('Bearer '.$token,$request->header('Authorization',''));
};
Route::get('/',fn()=>view('portfolio'));
Route::get('/healthz',fn()=>response()->json(['status'=>'ok','service_version'=>Settings::version(),'exporter_configured'=>Settings::get('CORRIDORA_INGEST_KEY')!=='']));
Route::get('/api/trace-check',function() {
    $ctx=\OpenTelemetry\API\Trace\Span::getCurrent()->getContext();
    return response()->json(['trace_id'=>$ctx->getTraceId(),'span_id'=>$ctx->getSpanId()]);
});
Route::get('/api/demo/status',fn()=>response()->json((new Scenario(app(Store::class)))->status()));
Route::post('/api/demo/scenario',function(Request $request) use($authorized) {
    if (!$authorized($request)) return response()->json(['error'=>'Unauthorized'],401);
    try { $scenario=new Scenario(app(Store::class)); $state=$scenario->control($request->input('phase'),$request->input('duration_seconds')); $scenario->transition(app(Telemetry::class),$state); return response()->json($state); }
    catch(\InvalidArgumentException $e) { return response()->json(['error'=>$e->getMessage()],422); }
});
Route::get('/api/holdings',fn()=>response()->json(['holdings'=>(new Portfolio(app(Store::class),app(Telemetry::class)))->holdings(),'fictional'=>true]));
Route::get('/fragments/holdings',fn()=>view('holdings',['holdings'=>(new Portfolio(app(Store::class),app(Telemetry::class)))->holdings()]));
Route::get('/api/valuation',fn(Request $r)=>response()->json((new Portfolio(app(Store::class),app(Telemetry::class)))->valuation($r->query('portfolio')==='control')));
Route::get('/api/fixture',function(Request $r) {
    // Public, fictional, fixed-size leaf used by Fastly. No control credentials are needed; slow is bounded to the same three holdings.
    return response()->json((new Portfolio(app(Store::class),app(Telemetry::class)))->valuation(false,$r->query('slow')==='1'));
});
Route::post('/api/demo/heartbeat',function(Request $r) use($authorized) {
    if (!$authorized($r)) return response()->json(['error'=>'Unauthorized'],401);
    if ($r->input('result')!=='passed' || !is_string($r->input('trace_id')) || !preg_match('/^[a-f0-9]{32}$/',$r->input('trace_id'))) return response()->json(['error'=>'Valid journey result and trace_id required'],422);
    app(Store::class)->put('heartbeat',['date'=>gmdate('Y-m-d'),'at'=>time(),'trace_id'=>$r->input('trace_id'),'result'=>'passed']);
    app(Telemetry::class)->log('Daily browser journey passed',['event.name'=>'demo.heartbeat','demo.simulated'=>true,'demo.scenario'=>'holding-nplus1','journey.trace_id'=>$r->input('trace_id')]);
    return response()->json(['ok'=>true]);
});
Route::get('/api/demo/heartbeat',function(Request $r) use($authorized) {
    if (!$authorized($r)) return response()->json(['error'=>'Unauthorized'],401);
    return response()->json(app(Store::class)->get('heartbeat')??['result'=>'missing']);
});
