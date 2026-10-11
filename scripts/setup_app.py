"""Python standard-library orchestration; never interpolate secrets into shell commands."""
from pathlib import Path
import argparse, base64, datetime, getpass, hashlib, ipaddress, json, os, re
import secrets, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request, urllib.error, urllib.parse

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.sample'
SECRET_KEYS = {'CORRIDORA_INGEST_KEY', 'CORRIDORA_RUM_KEY', 'DEMO_CONTROL_TOKEN', 'DOWNSTREAM_AUTH_TOKEN', 'LINODE_TOKEN', 'LINODE_STATS_TOKEN', 'APP_KEY'}
DEFAULTS = {
    'SAMPLE_MODE': 'local', 'PORT': '4105', 'APP_URL': 'http://127.0.0.1:4105',
    'CORRIDORA_TARGET': 'own', 'CORRIDORA_OTLP_ENDPOINT': 'https://ingest.corridora.com',
    'CORRIDORA_RUM_SCRIPT_URL': 'https://rum.corridora.com/corridora-rum.js',
    'CORRIDORA_RUM_ENDPOINT': 'https://ingest.corridora.com',
    'OTEL_SERVICE_NAME': 'sample-portfolio-api', 'OTEL_SERVICE_NAMESPACE': 'corridora-samples.portfolio',
    'DEPLOYMENT_ENVIRONMENT': 'development', 'SERVICE_VERSION': 'local',
    'DEMO_DAILY_START_UTC': '14:20', 'DEMO_WINDOW_SECONDS': '600',
    'ENABLE_PROVIDER_FORWARDING': 'false', 'ENABLE_SYNTHETICS': 'false',
    'PRICE_FIXTURE_URL': '', 'TRACKER_SIMULATOR_URL': '',
    'LINODE_REGION': 'us-ord', 'RESOURCE_PREFIX': 'sample-portfolio',
    'LINODE_HOST': '', 'LINODE_EXISTING_ID': '', 'LINODE_INSTANCE_ID': '', 'SSH_USER': 'root',
    'SSH_KEY_PATH': '', 'SSH_ALLOWED_CIDR': '', 'TLS_HOSTNAME': '',
    'COLLECTOR_MEMORY_MB': '128', 'LINODE_STATS_INTERVAL_SECONDS': '900',
}

def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else (default if default is not None else {})

def protected_json(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2); f.write('\n')
        os.chmod(name, 0o600); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)

def load(config_path=None):
    data = DEFAULTS | read_json(Path(config_path) if config_path else STATE / 'config.json') | read_json(STATE / 'secrets.json')
    for key in data.keys() | SECRET_KEYS:
        if key in os.environ: data[key] = os.environ[key]
    return {k: str(v) for k, v in data.items()}

def validate(data, deploy=False):
    if data['SAMPLE_MODE'] not in ('local', 'cloud'): raise ValueError('SAMPLE_MODE must be local or cloud')
    if not 1024 <= int(data['PORT']) <= 65535: raise ValueError('PORT must be 1024–65535')
    if data['CORRIDORA_TARGET'] not in ('own', 'demo'): raise ValueError('CORRIDORA_TARGET must be own or demo')
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', data['DEMO_DAILY_START_UTC']): raise ValueError('Daily time must be HH:MM UTC')
    if not 1 <= int(data['DEMO_WINDOW_SECONDS']) <= 600: raise ValueError('DEMO_WINDOW_SECONDS must be 1–600')
    for key in ['APP_URL','CORRIDORA_OTLP_ENDPOINT','CORRIDORA_RUM_SCRIPT_URL','CORRIDORA_RUM_ENDPOINT','PRICE_FIXTURE_URL','TRACKER_SIMULATOR_URL']:
        if not data.get(key): continue
        parsed=urllib.parse.urlparse(data[key])
        local=parsed.hostname in ('localhost','127.0.0.1','::1')
        if parsed.username or parsed.password or parsed.fragment: raise ValueError(f'{key}: embedded credentials/fragments forbidden')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local and data['SAMPLE_MODE']=='local'): raise ValueError(f'{key} requires HTTPS (localhost HTTP in local mode only)')
    if len(data.get('DEMO_CONTROL_TOKEN','')) < 16: raise ValueError('DEMO_CONTROL_TOKEN needs at least 16 characters')
    if data['CORRIDORA_TARGET']=='demo':
        if not data.get('CORRIDORA_INGEST_KEY') or not data.get('CORRIDORA_RUM_KEY'): raise ValueError('Demo requires operator-provisioned ingest and RUM keys')
        data['DEPLOYMENT_ENVIRONMENT']='demo'
    if data['SAMPLE_MODE']=='cloud':
        for key in ['SSH_KEY_PATH','TLS_HOSTNAME','SSH_ALLOWED_CIDR','CORRIDORA_INGEST_KEY','CORRIDORA_RUM_KEY']:
            if not data.get(key): raise ValueError(f'Missing {key}')
        if data['SSH_USER'] != 'root': raise ValueError('Cloud installer currently requires dedicated root SSH; cloud-init disables password login')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{1,240}', data['TLS_HOSTNAME']): raise ValueError('Invalid TLS hostname')
        if not re.fullmatch(r'[a-z][a-z0-9-]{2,40}',data['RESOURCE_PREFIX']): raise ValueError('RESOURCE_PREFIX needs 3–41 lowercase letters/digits/hyphens')
        network=ipaddress.ip_network(data['SSH_ALLOWED_CIDR'],strict=False)
        if network.prefixlen==0: raise ValueError('Restrict SSH_ALLOWED_CIDR to your admin network')
        if data['LINODE_HOST'] and not data['LINODE_EXISTING_ID'] and not data.get('LINODE_INSTANCE_ID'): raise ValueError('Existing host requires LINODE_EXISTING_ID for account/ownership validation')
        if int(data['COLLECTOR_MEMORY_MB']) != 128: raise ValueError('Baseline Collector limit is 128 MB')
        if int(data['LINODE_STATS_INTERVAL_SECONDS']) < 900: raise ValueError('Stats polling minimum is 900 seconds')
        if data['ENABLE_PROVIDER_FORWARDING']=='true' and not data.get('LINODE_STATS_TOKEN'): raise ValueError('Provider forwarding requires separate read-only LINODE_STATS_TOKEN')
        if deploy and not data.get('LINODE_TOKEN'): raise ValueError('LINODE_TOKEN with scoped instance/firewall permissions required')
    return data

def save(data):
    protected_json(STATE/'config.json',{k:v for k,v in data.items() if k not in SECRET_KEYS})
    protected_json(STATE/'secrets.json',{k:v for k,v in data.items() if k in SECRET_KEYS})

def configure(args):
    data=load(args.config)
    if not data.get('DEMO_CONTROL_TOKEN'): data['DEMO_CONTROL_TOKEN']=secrets.token_urlsafe(32)
    if not data.get('APP_KEY'): data['APP_KEY']='base64:'+base64.b64encode(secrets.token_bytes(32)).decode()
    prompts=['SAMPLE_MODE','PORT','CORRIDORA_TARGET','CORRIDORA_OTLP_ENDPOINT','CORRIDORA_RUM_ENDPOINT','CORRIDORA_RUM_SCRIPT_URL','CORRIDORA_INGEST_KEY','CORRIDORA_RUM_KEY','OTEL_SERVICE_NAME','OTEL_SERVICE_NAMESPACE','DEPLOYMENT_ENVIRONMENT','RESOURCE_PREFIX','DEMO_DAILY_START_UTC','ENABLE_SYNTHETICS','ENABLE_PROVIDER_FORWARDING','PRICE_FIXTURE_URL','DOWNSTREAM_AUTH_TOKEN']
    if not args.noninteractive:
        for key in prompts:
            previous=data.get(key,''); display='saved' if key in SECRET_KEYS and previous else previous
            answer=(getpass.getpass if key in SECRET_KEYS else input)(f'{key} [{display}]: ').strip()
            if answer: data[key]=answer
        if data['SAMPLE_MODE']=='cloud':
            provider_prompts=['LINODE_TOKEN','LINODE_REGION','LINODE_EXISTING_ID','LINODE_HOST','SSH_USER','SSH_KEY_PATH','SSH_ALLOWED_CIDR','TLS_HOSTNAME','COLLECTOR_MEMORY_MB','LINODE_STATS_INTERVAL_SECONDS']
            if data['ENABLE_PROVIDER_FORWARDING']=='true': provider_prompts.append('LINODE_STATS_TOKEN')
            for key in provider_prompts:
                previous=data.get(key,''); display='saved' if key in SECRET_KEYS and previous else previous
                answer=(getpass.getpass if key in SECRET_KEYS else input)(f'{key} [{display}]: ').strip()
                if answer: data[key]=answer
    data['APP_URL']=f"https://{data['TLS_HOSTNAME']}" if data['SAMPLE_MODE']=='cloud' else f"http://127.0.0.1:{data['PORT']}"
    validate(data); save(data)
    print('Saved .sample/config.json and owner-only .sample/secrets.json. Local telemetry is disabled until keys are provided.' if not data.get('CORRIDORA_INGEST_KEY') else 'Saved protected configuration.')

def source_version():
    digest=hashlib.sha256()
    for directory in ['app','bootstrap','config','public/assets','resources','routes']:
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and 'bootstrap/cache' not in path.as_posix():
                digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
    digest.update((ROOT/'composer.lock').read_bytes())
    return 'source-'+digest.hexdigest()[:16]

def command(argv, env=None, **kwargs):
    subprocess.run([str(x) for x in argv],cwd=ROOT,env=os.environ|(env or {}),check=True,**kwargs)

def composer():
    executable=shutil.which('composer')
    if executable: return [executable]
    local=ROOT/'.tools/composer'
    if local.exists(): return ['php',str(local)]
    print('Downloading official Composer installer into Git-ignored .tools; checking SHA-384 against composer.github.io.')
    import hashlib
    local.parent.mkdir(mode=0o700,exist_ok=True)
    with urllib.request.urlopen('https://getcomposer.org/installer',timeout=30) as response: installer=response.read()
    with urllib.request.urlopen('https://composer.github.io/installer.sig',timeout=30) as response: expected=response.read().decode().strip()
    if hashlib.sha384(installer).hexdigest()!=expected: raise RuntimeError('Composer installer checksum mismatch')
    path=local.parent/'composer-setup.php';path.write_bytes(installer)
    command(['php',path,'--install-dir='+str(local.parent),'--filename=composer']);path.unlink()
    return ['php',str(local)]

def api(data, method, path, body=None):
    request=urllib.request.Request('https://api.linode.com/v4/'+path,method=method,headers={'Authorization':'Bearer '+data['LINODE_TOKEN'],'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request,timeout=30) as response: return json.load(response) if response.status!=204 else {}
    except urllib.error.HTTPError as exc: raise RuntimeError(f'Linode API {method} {path} failed HTTP {exc.code}; response omitted to protect request data') from None

def deploy_plan(data):
    return {'provider':'Akamai/Linode','account':'resolved with GET /profile before apply','mode':data['SAMPLE_MODE'],'region':data['LINODE_REGION'],'label':data['RESOURCE_PREFIX'],'vm':'existing '+data['LINODE_EXISTING_ID'] if data['LINODE_EXISTING_ID'] else 'new g6-nanode-1 / Ubuntu 24.04 / 1 GB','resources':['dedicated VM unless existing selected','owned Cloud Firewall','Caddy TLS','Laravel SQLite','128 MB Collector','optional read-only stats adapter'],'monthly_usd_estimate':5,'cost_assumptions':'No Object Storage, backups, managed DB or extra volume. Domain already owned; low traffic; prebuilt images. Alerts do not cap billing.','hostname':data['TLS_HOSTNAME'],'ssh_cidr':data['SSH_ALLOWED_CIDR'],'synthetics':data['ENABLE_SYNTHETICS'],'provider_forwarding':data['ENABLE_PROVIDER_FORWARDING']}

def cloud_init():
    return '''#cloud-config
package_update: true
packages: [docker.io, docker-compose-v2, python3]
ssh_pwauth: false
runcmd:
  - [systemctl, enable, --now, docker]
'''

def ssh_args(data):
    key=Path(data['SSH_KEY_PATH']).expanduser()
    if not key.is_file(): raise ValueError('SSH key path does not exist')
    # Keep host-key checking enabled. Trust a new host fingerprint through your normal SSH flow before apply.
    return ['-i',str(key),'-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes']

def cloud_deploy(data):
    for name in ['docker','ssh','scp']:
        if not shutil.which(name): raise RuntimeError('Missing cloud build/deploy prerequisite: '+name)
    ssh_args(data)
    if not data['LINODE_EXISTING_ID']:
        pub=Path(data['SSH_KEY_PATH']).expanduser().with_suffix(Path(data['SSH_KEY_PATH']).suffix+'.pub')
        if not pub.is_file(): raise ValueError('Adjacent SSH public key .pub file required before provisioning')
    engine=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True)
    if engine.returncode: raise RuntimeError('Docker Engine is not running; no cloud resources were changed')
    profile=api(data,'GET','profile')
    print('Akamai account user:',profile.get('username','unknown'))
    inventory=read_json(STATE/'inventory.json')
    owner=inventory.get('owner') or secrets.token_hex(12)
    if not re.fullmatch('[a-f0-9]{24}',owner): raise ValueError('Invalid ownership inventory identifier')
    inventory.setdefault('owner',owner)
    inventory.setdefault('resources',[])
    protected_json(STATE/'inventory.json',inventory)
    tag='corridora-portfolio-'+owner
    vm=next((r for r in inventory['resources'] if r['kind']=='linode'),None)
    if vm:
        live=api(data,'GET',f"linode/instances/{vm['id']}")
        if vm.get('owned') and tag not in live.get('tags',[]): raise RuntimeError('VM ownership tag mismatch; refusing update')
    elif data['LINODE_EXISTING_ID']:
        live=api(data,'GET','linode/instances/'+str(int(data['LINODE_EXISTING_ID'])))
        if data['LINODE_HOST'] not in live.get('ipv4',[]): raise ValueError('LINODE_HOST is not an IPv4 address belonging to selected account VM')
        vm={'kind':'linode','id':live['id'],'owned':False,'ipv4':data['LINODE_HOST']}
        inventory['resources'].append(vm); protected_json(STATE/'inventory.json',inventory)
    else:
        # Recover a create operation whose response was lost, rather than blindly creating a duplicate.
        existing=api(data,'GET','linode/instances?page_size=500')['data']
        matches=[v for v in existing if tag in v.get('tags',[])]
        if len(matches)>1: raise RuntimeError('Multiple VMs with this ownership tag; resolve inventory before continuing')
        if matches: live=matches[0]
        else:
            pub=Path(data['SSH_KEY_PATH']).expanduser().with_suffix(Path(data['SSH_KEY_PATH']).suffix+'.pub')
            if not pub.is_file(): raise ValueError('Adjacent SSH public key .pub file required')
            live=api(data,'POST','linode/instances',{'label':data['RESOURCE_PREFIX'],'region':data['LINODE_REGION'],'type':'g6-nanode-1','image':'linode/ubuntu24.04','authorized_keys':[pub.read_text().strip()],'root_pass':secrets.token_urlsafe(40)+'aA1!','tags':[tag],'metadata':{'user_data':base64.b64encode(cloud_init().encode()).decode()},'backups_enabled':False})
        vm={'kind':'linode','id':live['id'],'owned':True,'ipv4':live['ipv4'][0]}
        inventory['resources'].append(vm); protected_json(STATE/'inventory.json',inventory)
    data['LINODE_HOST']=vm['ipv4']; data['LINODE_INSTANCE_ID']=str(vm['id'])
    firewall=next((r for r in inventory['resources'] if r['kind']=='firewall'),None)
    if not firewall and vm['owned']:
        matches=[f for f in api(data,'GET','networking/firewalls?page_size=500')['data'] if tag in f.get('tags',[])]
        if len(matches)>1: raise RuntimeError('Multiple owned firewalls; resolve inventory')
        ipv='ipv6' if ':' in data['SSH_ALLOWED_CIDR'] else 'ipv4'
        fw=matches[0] if matches else api(data,'POST','networking/firewalls',{'label':data['RESOURCE_PREFIX']+'-fw','tags':[tag],'devices':{'linodes':[vm['id']]},'rules':{'inbound_policy':'DROP','outbound_policy':'ACCEPT','inbound':[{'label':'ssh','action':'ACCEPT','protocol':'TCP','ports':'22','addresses':{ipv:[data['SSH_ALLOWED_CIDR']]}},{'label':'http-tls','action':'ACCEPT','protocol':'TCP','ports':'80,443','addresses':{'ipv4':['0.0.0.0/0'],'ipv6':['::/0']}}],'outbound':[]}})
        inventory['resources'].append({'kind':'firewall','id':fw['id'],'owned':True}); protected_json(STATE/'inventory.json',inventory)
    save(data)
    print('VM:',vm['ipv4'],'— point the TLS hostname A record here. SSH host fingerprint must be trusted before transfer.')
    for _ in range(30):
        if api(data,'GET',f"linode/instances/{vm['id']}")['status']=='running': break
        time.sleep(10)
    else: raise RuntimeError('VM still provisioning; rerun deploy --apply to resume')
    version=source_version(); data['SERVICE_VERSION']=version; save(data)
    (ROOT/'BUILD_VERSION').write_text(version+'\n')
    # Build on the operator/CI machine; never compile on the 1 GB VM.
    command(['docker','build','--platform','linux/amd64','-t','corridora-sample-portfolio:'+version,'.'])
    archive=STATE/'image.tar'; command(['docker','save','-o',archive,'corridora-sample-portfolio:'+version])
    host=data['SSH_USER']+'@'+data['LINODE_HOST']; opts=ssh_args(data)
    command(['ssh',*opts,host,'cloud-init status --wait && command -v docker && docker compose version'])
    command(['ssh',*opts,host,'if [ -d /opt/corridora-portfolio ]; then test "$(cat /opt/corridora-portfolio/.owner 2>/dev/null)" = '+owner+'; else mkdir -m 700 /opt/corridora-portfolio && printf %s '+owner+' > /opt/corridora-portfolio/.owner; fi'])
    payload=STATE/'deploy'; payload.mkdir(exist_ok=True,mode=0o700)
    for name in ['compose.yaml','collector.yaml']:
        shutil.copyfile(ROOT/'infra'/name,payload/name)
    protected_json(payload/'config.json',{k:v for k,v in data.items() if k not in SECRET_KEYS})
    protected_json(payload/'secrets.json',{k:v for k,v in data.items() if k in SECRET_KEYS and k not in {'LINODE_TOKEN','LINODE_STATS_TOKEN'}})
    (payload/'Caddyfile').write_text((ROOT/'infra/Caddyfile').read_text().replace('__HOSTNAME__',data['TLS_HOSTNAME']))
    (payload/'.env').write_text('SAMPLE_IMAGE=corridora-sample-portfolio:'+version+'\n')
    os.chmod(payload/'.env',0o600)
    # Collector receives secrets through a JSON file, not unsafe dotenv interpolation.
    protected_json(payload/'collector-secrets.json',{'endpoint':data['CORRIDORA_OTLP_ENDPOINT'],'key':data['CORRIDORA_INGEST_KEY']})
    (payload/'collector.yaml').write_text((ROOT/'infra/collector.yaml').read_text().replace('__EXPORT_ENDPOINT__',json.dumps(data['CORRIDORA_OTLP_ENDPOINT'])).replace('__EXPORT_KEY__',json.dumps(data['CORRIDORA_INGEST_KEY'])))
    os.chmod(payload/'collector.yaml',0o600)
    command(['scp',*opts,archive,host+':/opt/corridora-portfolio/image.tar'])
    for path in payload.iterdir(): command(['scp',*opts,path,host+':/opt/corridora-portfolio/'+path.name])
    command(['ssh',*opts,host,'cd /opt/corridora-portfolio && chmod 600 secrets.json collector.yaml && mkdir -p storage/logs storage/framework/views storage/framework/cache bootstrap/cache && docker load -i image.tar && docker compose up -d --remove-orphans && docker compose restart collector && rm image.tar'])
    archive.unlink(missing_ok=True)
    if data['ENABLE_SYNTHETICS']=='true':
        runner_image='corridora-sample-portfolio-runner:'+version
        command(['docker','build','--platform','linux/amd64','-f','infra/Dockerfile.runner','-t',runner_image,'.'])
        runner_archive=STATE/'runner-image.tar'; command(['docker','save','-o',runner_archive,runner_image])
        command(['scp',*opts,runner_archive,host+':/opt/corridora-portfolio/runner-image.tar'])
        with (payload/'.env').open('a') as file: file.write('RUNNER_IMAGE='+runner_image+'\n')
        command(['scp',*opts,payload/'.env',host+':/opt/corridora-portfolio/.env'])
        command(['ssh',*opts,host,'cd /opt/corridora-portfolio && docker load -i runner-image.tar && docker compose --profile synthetics up -d runner && rm runner-image.tar'])
        runner_archive.unlink(missing_ok=True)
    else:
        command(['ssh',*opts,host,'cd /opt/corridora-portfolio && docker compose --profile synthetics stop runner'])
    if data['ENABLE_PROVIDER_FORWARDING']=='true': install_adapter(data,opts,host)
    else:
        command(['ssh',*opts,host,'if test -f /etc/systemd/system/portfolio-stats.timer; then systemctl disable --now portfolio-stats.timer; fi'])
    print('Deployed',data['APP_URL'],'; run ./setup verify after DNS/TLS propagation. Enable the GitHub daily workflow if the optional VM browser runner is disabled.')

def install_adapter(data,opts,host):
    # Read-only API token is separately scoped; never install a mutation-capable deployment token on VM.
    token=data.get('LINODE_STATS_TOKEN','')
    if not token: raise ValueError('ENABLE_PROVIDER_FORWARDING requires separate LINODE_STATS_TOKEN (read-only linodes:read_only scope)')
    adapter=STATE/'adapter.json'
    protected_json(adapter,{'token':token,'instance_id':data['LINODE_INSTANCE_ID'],'endpoint':'http://127.0.0.1:4318','interval':int(data['LINODE_STATS_INTERVAL_SECONDS'])})
    command(['scp',*opts,ROOT/'scripts/provider_adapter.py',host+':/opt/corridora-portfolio/provider_adapter.py'])
    command(['scp',*opts,adapter,host+':/opt/corridora-portfolio/adapter.json'])
    for name in ['portfolio-stats.service','portfolio-stats.timer']:
        source=ROOT/'infra'/name
        if name.endswith('.timer'):
            source=STATE/name
            source.write_text((ROOT/'infra'/name).read_text().replace('OnUnitActiveSec=15min','OnUnitActiveSec='+str(int(data['LINODE_STATS_INTERVAL_SECONDS']))+'s'))
        command(['scp',*opts,source,host+':/etc/systemd/system/'+name])
    command(['ssh',*opts,host,'chmod 600 /opt/corridora-portfolio/adapter.json && systemctl daemon-reload && systemctl enable --now portfolio-stats.timer'])

def deploy(args,data):
    validate(data,deploy=data['SAMPLE_MODE']=='cloud' and args.apply)
    print(json.dumps(deploy_plan(data),indent=2))
    if args.plan or (data['SAMPLE_MODE']=='cloud' and not args.apply):
        print('Plan only. Apply explicitly with ./setup deploy --apply.'); return
    if data['SAMPLE_MODE']=='local':
        command([*composer(),'install','--no-interaction','--prefer-dist']); command(['npm','ci','--no-audit','--no-fund']); command(['npm','run','build'])
        data['SERVICE_VERSION']=source_version(); (ROOT/'BUILD_VERSION').write_text(data['SERVICE_VERSION']+'\n'); save(data); print('Local dependencies/assets ready; ./setup run')
    else: cloud_deploy(data)

def request(data,path,body=None):
    req=urllib.request.Request(data['APP_URL']+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+data['DEMO_CONTROL_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)

def verify(data):
    health=request(data,'/healthz'); print('App:',data['APP_URL'],'version:',health['service_version'])
    ensure_browser(data)
    command(['node','scripts/journey.mjs'],env=data|{'BASE_URL':data['APP_URL']})
    trace=request(data,'/api/trace-check'); print('Backend trace:',trace['trace_id'])
    print('Check stored Corridora browser CLIENT → Laravel SERVER parentage, rollout log, metric and host signal; HTTP 200 is not storage/correlation proof. No query credential configured.')

def ensure_browser(data):
    if not (ROOT/'node_modules/@playwright/test').exists(): command(['npm','ci','--no-audit','--no-fund'])
    if not data.get('CHROMIUM_EXECUTABLE_PATH'):
        # Playwright validates its matching executable itself; download only if absent.
        result=subprocess.run(['node','--input-type=module','-e','import {chromium} from "@playwright/test"; import {existsSync} from "node:fs"; process.exit(existsSync(chromium.executablePath())?0:1)'],cwd=ROOT)
        if result.returncode: command(['npx','playwright','install','chromium'])

def destroy(args,data):
    inventory=read_json(STATE/'inventory.json')
    print('Owned resources eligible for teardown:',json.dumps(inventory.get('resources',[])))
    if not args.apply: print('Plan only; ./setup destroy --apply removes owned resources. Existing VM survives.'); return
    if data['SAMPLE_MODE']=='local':
        pidfile=STATE/'server.pid'
        if pidfile.exists():
            # Never kill an arbitrary stale PID: only kill if live process command contains this app router path.
            pid=int(pidfile.read_text()); output=subprocess.run(['ps','-p',str(pid),'-o','args='],capture_output=True,text=True).stdout
            if str(ROOT/'scripts/router.php') in output: os.kill(pid,15)
            pidfile.unlink()
        print('Local process stopped; seeded data/secrets retained.'); return
    validate(data,deploy=True)
    if not re.fullmatch('[a-f0-9]{24}',inventory.get('owner','')): raise ValueError('Invalid ownership inventory identifier')
    owner='corridora-portfolio-'+inventory['owner']
    host=data['SSH_USER']+'@'+data['LINODE_HOST'] if data['LINODE_HOST'] else None
    vm=next((r for r in inventory.get('resources',[]) if r['kind']=='linode'),None)
    if vm and not vm['owned'] and host:
        command(['ssh',*ssh_args(data),host,'test "$(cat /opt/corridora-portfolio/.owner)" = '+inventory['owner']+' && cd /opt/corridora-portfolio && docker compose --profile synthetics down && if systemctl list-unit-files portfolio-stats.timer --no-legend | head -1 | grep -q portfolio-stats; then systemctl disable --now portfolio-stats.timer; fi'])
        print('Existing VM retained; /opt/corridora-portfolio files retained for operator inspection.')
    # Remove firewall after owned VM; reverse order otherwise could briefly expose running VM.
    for kind in ['linode','firewall']:
        for resource in list(inventory.get('resources',[])):
            if resource['kind']!=kind or not resource['owned']: continue
            path=('linode/instances/' if kind=='linode' else 'networking/firewalls/')+str(resource['id'])
            try: live=api(data,'GET',path)
            except RuntimeError as exc:
                if 'HTTP 404' not in str(exc): raise
                live=None
            if live is not None:
                if owner not in live.get('tags',[]): raise RuntimeError('Ownership mismatch; refusing deletion')
                api(data,'DELETE',path)
            inventory['resources'].remove(resource); protected_json(STATE/'inventory.json',inventory)
    print('Owned cloud resources removed. DNS and existing VM are retained.')

def main():
    parser=argparse.ArgumentParser(description='Configure, deploy and validate the fictional Akamai Laravel portfolio sample.')
    parser.add_argument('action',choices=['configure','deploy','run','verify','scenario','destroy'],nargs='?')
    parser.add_argument('--config',help='JSON config; credentials should be env vars or owner-only files')
    parser.add_argument('--noninteractive','--non-interactive',action='store_true'); parser.add_argument('--plan',action='store_true'); parser.add_argument('--apply','--yes',action='store_true')
    parser.add_argument('--phase',choices=['healthy','regression','recover'],default='regression'); parser.add_argument('--duration-seconds',type=int,default=120)
    args=parser.parse_args()
    if args.action is None:
        configure(args); data=load(args.config); args.action='deploy'
        if data['SAMPLE_MODE']=='cloud':
            print(json.dumps(deploy_plan(data),indent=2))
            if input('Apply this cloud plan? [y/N]: ').strip().lower()!='y': return
            args.apply=True; deploy(args,data); verify(data)
        else:
            deploy(args,data)
            log=open(STATE/'server.log','a')
            proc=subprocess.Popen(['php','-S','127.0.0.1:'+data['PORT'],'-t',str(ROOT/'public'),str(ROOT/'scripts/router.php')],cwd=ROOT,env=os.environ|data,stdout=log,stderr=log,start_new_session=True)
            (STATE/'server.pid').write_text(str(proc.pid)); time.sleep(1)
            try: verify(data)
            except BaseException: proc.terminate(); raise
            print('Running:',data['APP_URL'],'; ./setup destroy --apply stops it')
        return
    if args.action=='configure': configure(args); return
    data=load(args.config); validate(data)
    if args.action=='deploy': deploy(args,data)
    elif args.action=='run':
        if data['SAMPLE_MODE']=='cloud': print(data['APP_URL'],request(data,'/healthz'))
        else:
            if not (ROOT/'vendor/autoload.php').exists() or not (ROOT/'public/assets/app.js').exists(): raise RuntimeError('Run ./setup deploy first')
            command(['php','-S','127.0.0.1:'+data['PORT'],'-t','public','scripts/router.php'],env=data)
    elif args.action=='verify': verify(data)
    elif args.action=='scenario': print(json.dumps(request(data,'/api/demo/scenario',{'phase':args.phase,'duration_seconds':args.duration_seconds}),indent=2))
    elif args.action=='destroy': destroy(args,data)
