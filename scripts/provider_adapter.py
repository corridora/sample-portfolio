#!/usr/bin/env python3
"""Read-only Linode stats → bounded OTLP JSON gauges. Not a Longview agent."""
import argparse, json, math, time, urllib.request
from pathlib import Path

def convert(stats, instance_id, now_ns=None):
    now_ns=now_ns or time.time_ns()
    if not isinstance(stats,dict): raise ValueError('Linode stats must be an object')
    # The API wraps native series under data; allow a flat series for older local fixtures.
    data=stats.get('data',stats)
    if not isinstance(data,dict): raise ValueError('Linode stats data must be an object')
    metrics=[]
    # Keep the native signal narrow; Linux disk/memory/network use Collector hostmetrics.
    series=[('akamai.linode.cpu.utilization','%',data.get('cpu',[]))]
    for name,unit,points in series:
        if not isinstance(points,list): raise ValueError('Linode CPU stats must be an array')
        valid=[p for p in points if isinstance(p,list) and len(p)==2 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in p) and p[0]>0 and p[1]>=0]
        if valid:
            timestamp,value=max(valid,key=lambda p:p[0])
            metrics.append({'name':name,'unit':unit,'gauge':{'dataPoints':[{'timeUnixNano':str(int(timestamp)*1_000_000),'asDouble':float(value)}]}})
    if not metrics: raise ValueError('Linode stats contained no valid CPU data points; nothing forwarded')
    return {'resourceMetrics':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'sample-portfolio-provider'}},{'key':'service.namespace','value':{'stringValue':'corridora-samples.portfolio'}},{'key':'cloud.provider','value':{'stringValue':'akamai'}},{'key':'host.id','value':{'stringValue':str(instance_id)}}]},'scopeMetrics':[{'scope':{'name':'linode-stats-adapter','version':'1.0.0'},'metrics':metrics}]}]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',default='/opt/corridora-portfolio/adapter.json'); parser.add_argument('--fixture'); args=parser.parse_args()
    if args.fixture:
        print(json.dumps(convert(json.loads(Path(args.fixture).read_text()),'fixture'))); return
    config=json.loads(Path(args.config).read_text())
    request=urllib.request.Request('https://api.linode.com/v4/linode/instances/'+str(int(config['instance_id']))+'/stats',headers={'Authorization':'Bearer '+config['token']})
    with urllib.request.urlopen(request,timeout=10) as response: stats=json.load(response)
    envelope=convert(stats,config['instance_id'])
    request=urllib.request.Request(config['endpoint'].rstrip('/')+'/v1/metrics',data=json.dumps(envelope).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:
        if response.status!=200: raise RuntimeError('Collector rejected provider metrics')
    print('Linode native stats forwarded; inspect Corridora storage separately')

if __name__=='__main__': main()
