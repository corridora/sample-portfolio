#!/usr/bin/env python3
"""Run real Laravel routes against local OTLP/price sinks; optional real RUM browser capture."""
from pathlib import Path
import base64, http.server, json, os, socket, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
ROOT=Path(__file__).resolve().parents[1]
records=[]
fixture_error=False
class Sink(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_OPTIONS(self):
        self.send_response(204); self.headers_out(); self.end_headers()
    def headers_out(self):
        self.send_header('Content-Type','application/json'); self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:'+os.environ.get('TEST_APP_PORT','4105'))
        self.send_header('Access-Control-Allow-Headers','content-type,x-corridora-key,authorization,traceparent'); self.send_header('Access-Control-Allow-Methods','POST,GET,OPTIONS')
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
        records.append({'path':self.path,'headers':dict(self.headers),'body':json.loads(raw)})
        self.send_response(200); self.headers_out(); self.end_headers(); self.wfile.write(b'{}')
    def do_GET(self):
        if self.path=='/records': body=records
        else:
            records.append({'path':self.path,'headers':dict(self.headers),'body':{}})
            body={'prices':{'DEMO':42.5,'CLOUD':17.25,'TRACE':9.75},'fictional':True}
        self.send_response(503 if fixture_error and self.path!='/records' else 200); self.headers_out(); self.end_headers(); self.wfile.write(json.dumps(body).encode())

def free_port():
    with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]
def normalize(value):
    if not value:return ''
    try:return bytes.fromhex(value).hex()
    except ValueError:return base64.b64decode(value).hex()
def spans():
    return [span for r in records if r['path']=='/v1/traces' for resource in r['body'].get('resourceSpans',[]) for scope in resource.get('scopeSpans',[]) for span in scope.get('spans',[])]

def main():
    global fixture_error
    appport=free_port(); os.environ['TEST_APP_PORT']=str(appport)
    sink=http.server.ThreadingHTTPServer(('127.0.0.1',0),Sink); threading.Thread(target=sink.serve_forever,daemon=True).start()
    endpoint='http://127.0.0.1:'+str(sink.server_port); base='http://127.0.0.1:'+str(appport); token='mock-control-token-32-characters'
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        env=os.environ|{'PORTFOLIO_DB':tmp+'/test.sqlite','SAMPLE_MODE':'local','APP_URL':base,'CORRIDORA_OTLP_ENDPOINT':endpoint,'CORRIDORA_RUM_ENDPOINT':endpoint,'CORRIDORA_INGEST_KEY':'mock-backend','CORRIDORA_RUM_KEY':'mock-rum','DEMO_CONTROL_TOKEN':token,'PRICE_FIXTURE_URL':endpoint+'/internal/price-fixture','DOWNSTREAM_AUTH_TOKEN':'mock-downstream','SERVICE_VERSION':'test-build','DEMO_DAILY_START_UTC':'23:50','DEMO_WINDOW_SECONDS':'1','CORRIDORA_RUM_SCRIPT_URL':'https://rum.corridora.com/corridora-rum.js'}
        log=open(Path(tmp)/'server.log','w+')
        proc=subprocess.Popen(['php','-S','127.0.0.1:'+str(appport),'-t','public','scripts/router.php'],cwd=ROOT,env=env,stdout=log,stderr=log)
        def get(path,body=None,headers=None,expected=200):
            req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'}|(headers or {}))
            try:
                with urllib.request.urlopen(req,timeout=12) as response:
                    assert response.status==expected; assert 'no-store' in response.headers.get('Cache-Control',''); return json.load(response)
            except urllib.error.HTTPError as exc:
                assert exc.code==expected,(exc.code,exc.read()); return json.load(exc)
        try:
            for _ in range(40):
                try:get('/healthz');break
                except (OSError,AssertionError):time.sleep(.1)
            else:raise RuntimeError('Laravel did not start')
            get('/api/demo/scenario',{'phase':'regression','duration_seconds':60},expected=401)
            auth={'Authorization':'Bearer '+token}
            get('/api/demo/scenario',{'phase':'regression','duration_seconds':601},auth,422)
            get('/api/demo/scenario',{'phase':'healthy','duration_seconds':120},auth)
            trace='0123456789abcdef0123456789abcdef';parent='0123456789abcdef'
            check=get('/api/trace-check',headers={'traceparent':f'00-{trace}-{parent}-01'})
            assert check['trace_id']==trace
            server=next(s for s in spans() if normalize(s['spanId'])==check['span_id'])
            assert normalize(server['parentSpanId'])==parent and server['kind'] in (2,'SPAN_KIND_SERVER')
            healthy=get('/api/valuation');assert healthy['total']==1105.5 and healthy['phase']=='healthy'
            fixture=next(r for r in records if r['path']=='/internal/price-fixture')
            assert fixture['headers']['Authorization']=='Bearer mock-downstream'
            assert 'X-CORRIDORA-KEY' not in fixture['headers']
            assert fixture['headers'].get('traceparent')
            fixture_error=True
            fallback=get('/api/valuation'); assert fallback['total']==1105.5
            fixture_error=False
            with urllib.request.urlopen(base,timeout=5) as page:
                html=page.read().decode(); assert 'mock-backend' not in html and 'mock-control-token' not in html
                assert html.index('corridora-rum.js')<html.index('/assets/htmx.js')
            get('/api/demo/scenario',{'phase':'regression','duration_seconds':2},auth)
            began=time.monotonic();bad=get('/api/valuation');elapsed=time.monotonic()-began
            assert bad['phase']=='regression' and 1.45<=elapsed<8,elapsed
            healthy_control=get('/api/valuation?portfolio=control');assert healthy_control['phase']=='healthy'
            time.sleep(.55)
            assert get('/api/demo/status')['phase']=='healthy'
            get('/api/demo/scenario',{'phase':'recover','duration_seconds':600},auth)
            for signal in ['traces','logs','metrics']:
                batches=[r for r in records if r['path']=='/v1/'+signal]
                assert batches,signal
                assert any(r['headers'].get('X-CORRIDORA-KEY')=='mock-backend' for r in batches),signal
            assert any(s['name']=='sqlite single holding regression' for s in spans())
            logs=[log for r in records if r['path']=='/v1/logs' for resource in r['body'].get('resourceLogs',[]) for scope in resource.get('scopeLogs',[]) for log in scope.get('logRecords',[])]
            assert any(normalize(log.get('traceId'))==healthy['trace_id'] for log in logs),'correlated SDK log trace ID'
            assert any(any(a['key']=='event.name' and a['value'].get('stringValue')=='deployment' for a in log.get('attributes',[])) for log in logs),'deployment log'
            client=next(s for s in spans() if s['name']=='GET AWS fictional prices' and normalize(s['traceId'])==healthy['trace_id'])
            assert fixture['headers']['traceparent'].split('-')[2]==normalize(client['spanId'])
            print('PASS Laravel health/auth/validation/W3C SERVER→CLIENT/DB, bounded regression/control/expiry/recovery, SDK OTLP traces/logs/metrics')
            if os.getenv('RUM_BUNDLE_PATH'):
                subprocess.run(['npm','run','test:browser'],cwd=ROOT,env=env|{'BASE_URL':base,'OTLP_CAPTURE_URL':endpoint},check=True)
            else: print('SKIP actual browser RUM correlation: set RUM_BUNDLE_PATH to a real Corridora RUM distribution')
            subprocess.run(['node','scripts/journey.mjs'],cwd=ROOT,env=env|{'BASE_URL':base},check=True)
        finally:
            proc.terminate();proc.wait(timeout=5);sink.shutdown()
            log.seek(0);errorlog=log.read();log.close()
            if sys.exc_info()[0] is not None or 'Fatal error' in errorlog or 'Export failure' in errorlog: print(errorlog[-12000:],file=sys.stderr)

if __name__=='__main__':main()
