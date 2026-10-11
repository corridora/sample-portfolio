<?php
declare(strict_types=1);
require dirname(__DIR__).'/vendor/autoload.php';
use App\{Store,Scenario,Settings};
function check(bool $result,string $name): void { if (!$result) throw new \RuntimeException($name); echo "PASS $name\n"; }
putenv('PORTFOLIO_DB=:memory:'); putenv('DEMO_DAILY_START_UTC=14:20'); putenv('DEMO_WINDOW_SECONDS=600');
$store=new Store(); $scenario=new Scenario($store);
check(count($store->db->query('SELECT symbol FROM holdings')->fetchAll())===3,'three seeded holdings');
check($scenario->status(strtotime('2026-10-11 14:19:59 UTC'))['phase']==='healthy','healthy before daily window');
check($scenario->status(strtotime('2026-10-11 14:20:00 UTC'))['phase']==='regression','regression at daily boundary');
check($scenario->status(strtotime('2026-10-11 14:30:00 UTC'))['phase']==='healthy','daily automatic recovery');
putenv('DEMO_DAILY_START_UTC=23:55');
$before=$scenario->status(strtotime('2026-10-11 23:59:59 UTC'));
$after=$scenario->status(strtotime('2026-10-12 00:00:00 UTC'));
check($after['phase']==='regression','daily regression continues after UTC midnight');
check($before['release']===$after['release'],'daily rollout keeps identity across midnight');
check($after['expires_at']===strtotime('2026-10-12 00:05:00 UTC'),'midnight window retains full expiry');
check($scenario->status(strtotime('2026-10-12 00:05:00 UTC'))['phase']==='healthy','midnight window recovers at exact expiry');
putenv('DEMO_DAILY_START_UTC=14:20');
foreach ([0,601,1.5,'120',null] as $duration) {
    try { $scenario->control('regression',$duration); check(false,'reject invalid duration'); }
    catch(\InvalidArgumentException $e) { echo 'PASS reject duration '.json_encode($duration)."\n"; }
}
$state=$scenario->control('regression',2);
check($scenario->status($state['expires_at']-1)['phase']==='regression','override active before expiry');
check($scenario->status($state['expires_at'])['source']==='daily','override expires at exact boundary');
check($scenario->control('recover',60)['phase']==='healthy','recover maps to bounded healthy override');
check($scenario->status()['service_version']===Settings::version(),'scenario carries actual service version');
