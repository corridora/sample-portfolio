<?php
declare(strict_types=1);
namespace App;

use OpenTelemetry\API\Trace\SpanInterface;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\Propagation\TraceContextPropagator;
use OpenTelemetry\API\Logs\LogRecord;
use OpenTelemetry\Contrib\Otlp\{OtlpHttpTransportFactory,SpanExporter,LogsExporter,MetricExporter};
use OpenTelemetry\SDK\Common\Attribute\Attributes;
use OpenTelemetry\SDK\Resource\ResourceInfo;
use OpenTelemetry\SDK\Trace\TracerProvider;
use OpenTelemetry\SDK\Trace\SpanProcessor\BatchSpanProcessor;
use OpenTelemetry\SDK\Logs\LoggerProvider;
use OpenTelemetry\SDK\Logs\Processor\SimpleLogRecordProcessor;
use OpenTelemetry\SDK\Metrics\MeterProvider;
use OpenTelemetry\SDK\Metrics\MetricReader\ExportingReader;

final class Telemetry
{
    public readonly mixed $tracer;
    private mixed $traces;
    private mixed $logs;
    private mixed $metrics;
    private mixed $logger;
    private mixed $duration;
    public function __construct()
    {
        $resource = ResourceInfo::create(Attributes::create([
            'service.name'=>Settings::get('OTEL_SERVICE_NAME','sample-portfolio-api'),
            'service.namespace'=>Settings::get('OTEL_SERVICE_NAMESPACE','corridora-samples.portfolio'),
            'service.version'=>Settings::version(), 'deployment.environment.name'=>Settings::get('DEPLOYMENT_ENVIRONMENT','development'),
            'cloud.provider'=>'akamai', 'cloud.region'=>Settings::get('LINODE_REGION','local'),
            'host.id'=>Settings::get('LINODE_INSTANCE_ID',gethostname()),
        ]));
        $tb = TracerProvider::builder()->setResource($resource);
        $lb = LoggerProvider::builder()->setResource($resource);
        $mb = MeterProvider::builder()->setResource($resource);
        if (Settings::get('CORRIDORA_INGEST_KEY') !== '' || Settings::get('CORRIDORA_OTLP_ENDPOINT') === 'http://127.0.0.1:4318') {
            $endpoint = rtrim(Settings::get('CORRIDORA_OTLP_ENDPOINT','https://ingest.corridora.com'),'/');
            $headers = Settings::get('CORRIDORA_INGEST_KEY') === '' ? [] : ['X-CORRIDORA-KEY'=>Settings::get('CORRIDORA_INGEST_KEY')];
            $factory = new OtlpHttpTransportFactory();
            $transport = fn(string $signal) => $factory->create($endpoint.'/v1/'.$signal,'application/json',$headers,null,0.8,0,0);
            $tb->addSpanProcessor(new BatchSpanProcessor(new SpanExporter($transport('traces')), \OpenTelemetry\API\Common\Time\Clock::getDefault(), 64, 5000, 1000, 64, false));
            $lb->addLogRecordProcessor(new SimpleLogRecordProcessor(new LogsExporter($transport('logs'))));
            $mb->addReader(new ExportingReader(new MetricExporter($transport('metrics'),'delta')));
        }
        $this->traces=$tb->build(); $this->logs=$lb->build(); $this->metrics=$mb->build();
        $this->tracer=$this->traces->getTracer('corridora.portfolio','1.0.0');
        $this->logger=$this->logs->getLogger('corridora.portfolio');
        $this->duration=$this->metrics->getMeter('corridora.portfolio')->createHistogram('http.server.request.duration','s','Request duration');
    }
    public function server(string $name,array $headers): SpanInterface
    {
        return $this->tracer->spanBuilder($name)->setParent(TraceContextPropagator::getInstance()->extract($headers))->setSpanKind(SpanKind::KIND_SERVER)->startSpan();
    }
    public function child(string $name, int $kind, array $attributes, callable $fn): mixed
    {
        $span=$this->tracer->spanBuilder($name)->setSpanKind($kind)->setAttributes($attributes)->startSpan(); $scope=$span->activate();
        try { return $fn($span); } catch (\Throwable $e) { $span->recordException($e); $span->setStatus('Error',$e->getMessage()); throw $e; }
        finally { $scope->detach(); $span->end(); }
    }
    public function log(string $body,array $attributes=[]): void
    {
        $span=\OpenTelemetry\API\Trace\Span::getCurrent()->getContext();
        $line=['timestamp'=>gmdate('c'),'body'=>$body,'trace_id'=>$span->getTraceId(),'span_id'=>$span->getSpanId(),'attributes'=>$attributes];
        // This structured file is for local/operator inspection. Collector reads Caddy access logs only to avoid duplicate application exports.
        $file=dirname(__DIR__).'/storage/logs/app.jsonl';
        if (is_file($file) && filesize($file)>5*1024*1024) rename($file,$file.'.1');
        file_put_contents($file,json_encode($line,JSON_UNESCAPED_SLASHES)."\n",FILE_APPEND|LOCK_EX);
        $this->logger->emit((new LogRecord($body))->setSeverityNumber(9)->setSeverityText('INFO')->setAttributes($attributes));
    }
    public function finish(float $seconds,array $attributes): void
    {
        $this->duration->record($seconds,$attributes);
        $results=[$this->traces->forceFlush(),$this->logs->forceFlush(),$this->metrics->forceFlush()];
        if (in_array(false,$results,true)) error_log('portfolio exporter flush failed; inspect local Collector/backend configuration');
        $this->traces->shutdown(); $this->logs->shutdown(); $this->metrics->shutdown();
    }
}
