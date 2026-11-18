"""Plot application acceptance data, not formal protocol benchmarks."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'logs/milestone1-20261118/acceptance-final'
output=ROOT/'docs/evidence';output.mkdir(parents=True,exist_ok=True)
results=json.loads((folder/'results.json').read_text())['results']
rows=list(csv.DictReader((folder/'status.csv').open(encoding='utf-8')))
events=[json.loads(line) for line in (ROOT/'logs/milestone1-20261118/events.jsonl').read_text().splitlines()]
cases=[('inspection_faster','Inspection faster: cycle 200 ms / inspect 50 ms'),
       ('production_faster_with_room','Production faster: cycle 80 ms / inspect 180 ms'),
       ('pause_resume','Pause / resume: cycle 120 ms / inspect 150 ms'),
       ('queue_full_fault','Queue full: cycle 50 ms / inspect 400 ms, capacity 2')]
fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
for ax,(case,title) in zip(axes.flat,cases):
    batch=next(str(r['batch_id']) for r in results if r['case']==case)
    samples=[r for r in rows if r['case']==case and r['batch_id']==batch]
    terminal=next((event for event in events if event['event']=='batch_completed' and str(event['batch_id'])==batch),None)
    if terminal:
        # Preserve the raw WebSocket CSV; add the separately logged terminal event
        # only to this derived plotting dataset, so the final counts are visible.
        samples.append({'monotonic_ns':terminal['monotonic_ns'],'produced':terminal['target'],
                        'inspected':terminal['accepted']+terminal['rejected'],'waiting':0,'state':'Idle'})
        samples.sort(key=lambda row:int(row['monotonic_ns']))
    origin=int(samples[0]['monotonic_ns'])
    x=[(int(r['monotonic_ns'])-origin)/1e9 for r in samples]
    ax.step(x,[int(r['produced']) for r in samples],where='post',label='Produced',color='#176f9e')
    ax.step(x,[int(r['inspected']) for r in samples],where='post',label='Inspected',color='#198777')
    ax.step(x,[int(r['waiting']) for r in samples],where='post',label='Waiting queue',color='#ba7c20')
    ax.set(title=title,xlabel='Elapsed since first status sample (s)',ylabel='Parts (count)')
    ax.grid(alpha=.2)
    if case=='queue_full_fault':
        fault=next((t for t,r in zip(x,samples) if r['state']=='Fault'),None)
        if fault is not None:ax.axvline(fault,color='#b73651',linestyle='--',label='Fault')
    ax.legend(loc='upper left',fontsize=8)
fig.suptitle('Milestone 1 — real production / inspection application checks',fontsize=15)
fig.savefig(output/'application-validation.png',dpi=160)
fig.savefig(output/'application-validation.svg')
print(output/'application-validation.png')
