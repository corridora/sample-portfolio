import contextlib, importlib.util, io, json, math, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import setup_app as setup
import provider_adapter

class SetupTests(unittest.TestCase):
    def config(self): return setup.DEFAULTS | {'DEMO_CONTROL_TOKEN':'test-control-token-long'}
    def test_help_without_dependencies(self):
        import subprocess
        result=subprocess.run([str(ROOT/'setup'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0); self.assertIn('destroy',result.stdout)
    def test_local_plan_and_no_secret_leak(self):
        config=self.config()|{'CORRIDORA_INGEST_KEY':'secret-backend'}
        text=json.dumps(setup.deploy_plan(setup.validate(config)))
        self.assertNotIn('secret-backend',text); self.assertIn('5',text)
    def test_configuration_validation(self):
        for override in [{'PORT':'1'},{'DEMO_DAILY_START_UTC':'25:00'},{'DEMO_WINDOW_SECONDS':'601'},{'PRICE_FIXTURE_URL':'http://not-local.test'},{'DEMO_CONTROL_TOKEN':''}]:
            with self.assertRaises((ValueError,KeyError)): setup.validate(self.config()|override)
    def test_demo_requires_both_scoped_keys(self):
        with self.assertRaises(ValueError): setup.validate(self.config()|{'CORRIDORA_TARGET':'demo'})
        config=setup.validate(self.config()|{'CORRIDORA_TARGET':'demo','CORRIDORA_INGEST_KEY':'mock-backend','CORRIDORA_RUM_KEY':'mock-rum'})
        self.assertEqual(config['DEPLOYMENT_ENVIRONMENT'],'demo')
    def test_owner_only_secret_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path=Path(directory)/'secrets.json'; setup.protected_json(path,{'key':'mock'})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
    def test_provider_conversion_latest_and_invalid(self):
        body=provider_adapter.convert({'cpu':[[1700000000000,2.5],[1700000001000,3.5],[1700000002000,math.nan]]},'123')
        resource=body['resourceMetrics'][0]
        point=resource['scopeMetrics'][0]['metrics'][0]['gauge']['dataPoints'][0]
        self.assertEqual(point['asDouble'],3.5)
        self.assertEqual(point['timeUnixNano'],'1700000001000000000')
        self.assertTrue(any(a['key']=='host.id' and a['value']['stringValue']=='123' for a in resource['resource']['attributes']))
    def test_provider_native_response_wrapper_and_empty_rejection(self):
        fixture=json.loads((ROOT/'tests/fixtures/linode-stats.json').read_text())
        metrics=provider_adapter.convert(fixture,'123')['resourceMetrics'][0]['scopeMetrics'][0]['metrics']
        self.assertEqual(metrics[0]['gauge']['dataPoints'][0]['asDouble'],3.5)
        for stats in [{'data':{'cpu':[]}},{'data':{'cpu':[[math.nan,1],[1,True],['invalid',2]]}},{'data':None},[],{'data':{'cpu':{}}}]:
            with self.assertRaises(ValueError): provider_adapter.convert(stats,'123')
    def test_collector_offsets_queue_and_volume_are_persistent(self):
        collector=(ROOT/'infra/collector.yaml').read_text()
        compose=(ROOT/'infra/compose.yaml').read_text()
        self.assertIn('extensions: [file_storage]',collector)
        self.assertIn('start_at: beginning',collector)
        self.assertIn('compression: auto',collector)
        self.assertEqual(collector.count('storage: file_storage'),2)
        self.assertIn('queue_size: 32',collector)
        self.assertIn('collector_state:/var/lib/otelcol',compose)
        self.assertIn('  collector_state:',compose)
    def test_plan_does_not_call_cloud(self):
        from argparse import Namespace
        with patch.object(setup,'api',side_effect=AssertionError('no cloud call')),contextlib.redirect_stdout(io.StringIO()) as out:
            setup.deploy(Namespace(plan=True,apply=False),self.config())
        self.assertIn('Plan only',out.getvalue())
    def test_missing_provider_key_rejected_before_mutation(self):
        config=self.config()|{'SAMPLE_MODE':'cloud','APP_URL':'https://portfolio.example.test','SSH_KEY_PATH':'/not/read','TLS_HOSTNAME':'portfolio.example.test','SSH_ALLOWED_CIDR':'192.0.2.1/32','CORRIDORA_INGEST_KEY':'mock-backend','CORRIDORA_RUM_KEY':'mock-rum','LINODE_TOKEN':'mock-deploy','ENABLE_PROVIDER_FORWARDING':'true'}
        with self.assertRaisesRegex(ValueError,'LINODE_STATS_TOKEN'):setup.validate(config,deploy=True)
        self.assertEqual(setup.validate(config|{'LINODE_STATS_TOKEN':'mock-readonly'},deploy=True)['LINODE_STATS_TOKEN'],'mock-readonly')
    def test_source_digest_covers_bootstrap_excludes_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root=Path(directory)
            for name in ['app','bootstrap/cache','config','public/assets','resources','routes']:(root/name).mkdir(parents=True,exist_ok=True)
            (root/'composer.lock').write_text('{}');(root/'bootstrap/app.php').write_text('<?php return 1;')
            with patch.object(setup,'ROOT',root):
                first=setup.source_version();(root/'bootstrap/app.php').write_text('<?php return 2;');second=setup.source_version()
                self.assertNotEqual(first,second)
                (root/'bootstrap/cache/services.php').write_text('generated');self.assertEqual(setup.source_version(),second)
    def test_cloud_provision_resume_and_owned_teardown_with_mock_api(self):
        from types import SimpleNamespace
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root=Path(directory);state=root/'.sample';state.mkdir()
            shutil.copytree(ROOT/'infra',root/'infra')
            key=root/'mock-key';key.write_text('not-a-real-key');(root/'mock-key.pub').write_text('ssh-ed25519 fictional-test-public-key')
            config=self.config()|{'SAMPLE_MODE':'cloud','APP_URL':'https://portfolio.example.test','SSH_KEY_PATH':str(key),'TLS_HOSTNAME':'portfolio.example.test','SSH_ALLOWED_CIDR':'192.0.2.1/32','CORRIDORA_INGEST_KEY':'mock-backend','CORRIDORA_RUM_KEY':'mock-rum','LINODE_TOKEN':'mock-deploy'}
            calls=[];live={}
            def api(data,method,path,body=None):
                calls.append((method,path,body))
                if path=='profile':return {'username':'mock-operator'}
                if method=='POST' and path=='linode/instances':live['vm']={'id':123,'ipv4':['192.0.2.10'],'tags':body['tags'],'status':'running'};return live['vm']
                if method=='POST' and path=='networking/firewalls':live['fw']={'id':456,'tags':body['tags']};return live['fw']
                if path.startswith('linode/instances?'):return {'data':list([live['vm']]) if 'vm' in live else []}
                if path.startswith('networking/firewalls?'):return {'data':list([live['fw']]) if 'fw' in live else []}
                if method=='GET' and path=='linode/instances/123':return live['vm']
                if method=='GET' and path=='networking/firewalls/456':return live['fw']
                if method=='DELETE':return {}
                raise AssertionError((method,path))
            argv=[]
            def command(args,**kwargs):
                argv.append([str(arg) for arg in args])
                if args[:3]==['docker','save','-o']:Path(args[3]).write_bytes(b'fake-image')
            with patch.object(setup,'ROOT',root),patch.object(setup,'STATE',state),patch.object(setup,'api',api),patch.object(setup,'command',command),patch.object(setup,'source_version',return_value='source-test-build'),patch.object(setup.shutil,'which',return_value='/mock/tool'),patch.object(setup.subprocess,'run',return_value=SimpleNamespace(returncode=0)),contextlib.redirect_stdout(io.StringIO()):
                setup.cloud_deploy(config)
                inventory=setup.read_json(state/'inventory.json')
                self.assertTrue(all(r['owned'] for r in inventory['resources']))
                self.assertEqual((state/'deploy/secrets.json').stat().st_mode&0o777,0o600)
                vm_secrets=json.loads((state/'deploy/secrets.json').read_text())
                self.assertNotIn('LINODE_TOKEN',vm_secrets)
                config['CORRIDORA_INGEST_KEY']='mock-rotated-backend'
                setup.cloud_deploy(config)
                self.assertEqual(sum(1 for method,path,_ in calls if method=='POST' and path=='linode/instances'),1)
                self.assertEqual(sum(1 for method,path,_ in calls if method=='POST' and path=='networking/firewalls'),1)
                self.assertIn('mock-rotated-backend',(state/'deploy/collector.yaml').read_text())
                self.assertEqual(sum('docker compose restart collector' in arg for args in argv for arg in args),2)
                self.assertFalse(any('mock-backend' in arg or 'mock-rotated-backend' in arg or 'mock-deploy' in arg for args in argv for arg in args))
                self.assertFalse(any('down -v' in arg or 'volume rm' in arg for args in argv for arg in args))
                setup.destroy(SimpleNamespace(apply=True),config)
                self.assertEqual([path for method,path,_ in calls if method=='DELETE'],['linode/instances/123','networking/firewalls/456'])
                self.assertEqual(setup.read_json(state/'inventory.json')['resources'],[])

if __name__=='__main__': unittest.main()
