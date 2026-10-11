<?php
declare(strict_types=1);
namespace App;

use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\Propagation\TraceContextPropagator;

final class Portfolio
{
    public function __construct(private Store $store,private Telemetry $otel) {}
    public function holdings(): array
    {
        return $this->otel->child('sqlite holdings batch',SpanKind::KIND_CLIENT,['db.system.name'=>'sqlite','db.operation.name'=>'SELECT','db.collection.name'=>'holdings'],fn()=> $this->store->db->query('SELECT symbol,shares FROM holdings ORDER BY symbol')->fetchAll(\PDO::FETCH_ASSOC));
    }
    public function prices(): array
    {
        $url=Settings::get('PRICE_FIXTURE_URL');
        if ($url==='') return $this->otel->child('prices local fixture',SpanKind::KIND_INTERNAL,['dependency.mode'=>'fixture'],fn()=>['DEMO'=>42.5,'CLOUD'=>17.25,'TRACE'=>9.75]);
        $parsed=parse_url($url); $local=in_array($parsed['host']??'',['localhost','127.0.0.1','::1'],true);
        if (($parsed['scheme']??'')!=='https' && !($local && Settings::get('SAMPLE_MODE','local')==='local')) throw new \RuntimeException('Configured price endpoint must use HTTPS (localhost allowed in local mode)');
        return $this->otel->child('GET AWS fictional prices',SpanKind::KIND_CLIENT,['server.address'=>$parsed['host'],'http.request.method'=>'GET','dependency.mode'=>'cross-cloud'],function($span) use($url) {
            $headers=['Accept'=>'application/json']; TraceContextPropagator::getInstance()->inject($headers);
            if (Settings::get('DOWNSTREAM_AUTH_TOKEN')!=='') $headers['Authorization']='Bearer '.Settings::get('DOWNSTREAM_AUTH_TOKEN');
            try {
                $client=new \GuzzleHttp\Client(['timeout'=>0.75,'connect_timeout'=>0.35,'allow_redirects'=>false]);
                $response=$client->get($url,['headers'=>$headers,'stream'=>true]); $span->setAttribute('http.response.status_code',$response->getStatusCode());
                $body=$response->getBody()->read(16385); if (strlen($body)>16384) throw new \RuntimeException('Fixture too large');
                $json=json_decode($body,true,32,JSON_THROW_ON_ERROR);
                if (($json['fictional']??false)!==true) throw new \RuntimeException('Only fictional price fixtures accepted');
                foreach (['DEMO','CLOUD','TRACE'] as $symbol) if (!is_numeric($json['prices'][$symbol]??null) || !is_finite((float)$json['prices'][$symbol]) || $json['prices'][$symbol]<0 || $json['prices'][$symbol]>1000000) throw new \RuntimeException('Invalid fixture prices');
                return $json['prices'];
            } catch (\Throwable $e) {
                $span->setStatus('Error','price dependency unavailable');
                $this->otel->log('Price dependency fallback',['dependency.fallback'=>true,'error.type'=>get_class($e)]);
                return ['DEMO'=>42.5,'CLOUD'=>17.25,'TRACE'=>9.75];
            }
        });
    }
    public function valuation(bool $control=false,bool $forceSlow=false): array
    {
        $state=(new Scenario($this->store))->status(); $bad=!$control && ($forceSlow || $state['phase']==='regression');
        $holdings=$this->holdings(); $prices=$bad?null:$this->prices(); $rows=[]; $total=0.0;
        foreach ($holdings as $holding) {
            if ($bad) {
                $holding=$this->otel->child('sqlite single holding regression',SpanKind::KIND_CLIENT,['db.system.name'=>'sqlite','db.operation.name'=>'SELECT','demo.simulated'=>true],function() use ($holding) {
                    $s=$this->store->db->prepare('SELECT symbol,shares FROM holdings WHERE symbol=?'); $s->execute([$holding['symbol']]); return $s->fetch(\PDO::FETCH_ASSOC);
                });
                $prices=$this->prices();
                $this->otel->child('holding regression delay',SpanKind::KIND_INTERNAL,['demo.simulated'=>true,'demo.delay_ms'=>500],fn()=>usleep(500000));
            }
            $value=round($holding['shares']*$prices[$holding['symbol']],2); $total+=$value;
            $rows[]=$holding+['price'=>(float)$prices[$holding['symbol']],'value'=>$value];
        }
        return ['holdings'=>$rows,'total'=>round($total,2),'currency'=>'USD','fictional'=>true,'phase'=>$bad?'regression':'healthy','release'=>$state['release'],'control'=>$control,'trace_id'=>\OpenTelemetry\API\Trace\Span::getCurrent()->getContext()->getTraceId()];
    }
}
