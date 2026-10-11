<?php
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\{Exceptions,Middleware};
use Illuminate\Support\Facades\Route;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(using: fn()=>Route::middleware([])->group(dirname(__DIR__).'/routes/web.php'))
    ->withMiddleware(function(Middleware $middleware) {
        // Only the TLS proxy publishes a cloud port; Caddy overwrites these forwarded values.
        $middleware->trustProxies(at: '*', headers: \Illuminate\Http\Request::HEADER_X_FORWARDED_FOR | \Illuminate\Http\Request::HEADER_X_FORWARDED_HOST | \Illuminate\Http\Request::HEADER_X_FORWARDED_PORT | \Illuminate\Http\Request::HEADER_X_FORWARDED_PROTO);
        $middleware->append(\App\ObservabilityMiddleware::class);
    })
    ->withExceptions(function(Exceptions $exceptions) {})
    ->create();
