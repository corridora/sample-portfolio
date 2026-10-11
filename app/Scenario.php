<?php
declare(strict_types=1);
namespace App;

final class Scenario
{
    public function __construct(private Store $store) {}
    public function status(?int $now=null): array
    {
        $now ??= time(); $manual=$this->store->get('scenario');
        if ($manual && $manual['expires_at']>$now) return $manual+['source'=>'override','service_version'=>Settings::version()];
        $start=Settings::get('DEMO_DAILY_START_UTC','14:20');
        $seconds=(int)Settings::get('DEMO_WINDOW_SECONDS','600');
        $today=strtotime(gmdate('Y-m-d',$now).' '.$start.' UTC');
        // Use the most recent start, including a window that began before UTC midnight.
        if ($now < $today) $today-=86400;
        $bad=$now >= $today && $now < $today+$seconds;
        return ['phase'=>$bad?'regression':'healthy','expires_at'=>$bad?$today+$seconds:null,'release'=>gmdate('Ymd',$bad?$today:$now).($bad?'-nplus1':'-batch'),'scenario'=>'holding-nplus1','source'=>'daily','service_version'=>Settings::version()];
    }
    public function control(mixed $phase,mixed $duration): array
    {
        if (!in_array($phase,['healthy','regression','recover'],true) || !is_int($duration) || $duration<1 || $duration>600) throw new \InvalidArgumentException('phase must be healthy, regression or recover; duration_seconds must be an integer from 1 to 600');
        $state=['phase'=>$phase==='recover'?'healthy':$phase,'expires_at'=>time()+$duration,'release'=>gmdate('Ymd-His').'-'.bin2hex(random_bytes(3)).'-'.$phase,'scenario'=>'holding-nplus1'];
        $this->store->put('scenario',$state); return $state;
    }
    public function transition(Telemetry $telemetry,array $state): void
    {
        $previous=$this->store->get('last_effective');
        if (($previous['release']??null)!==$state['release']) {
            $telemetry->log('Simulated portfolio rollout',['event.name'=>'deployment','demo.simulated'=>true,'demo.scenario'=>$state['scenario'],'demo.release'=>$state['release'],'demo.phase'=>$state['phase'],'service.version'=>Settings::version()]);
            $this->store->put('last_effective',['release'=>$state['release'],'phase'=>$state['phase']]);
        }
    }
}
