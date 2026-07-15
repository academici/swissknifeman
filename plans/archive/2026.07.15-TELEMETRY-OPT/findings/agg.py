#!/usr/bin/env python3
import json, os, collections, time, subprocess

CUTOFF = time.time() - 4*86400
out = subprocess.run(
    ["find","/home/vostrikov","-path","*/.claude/runs/*.json","-type","f","-mtime","-4"],
    capture_output=True, text=True).stdout
files = [f for f in out.splitlines() if f]

def proj(f):
    p = f.split('/.claude/runs/')[0]
    return p.replace('/home/vostrikov/', '')

per = collections.defaultdict(lambda: {
    'runs':0,'in':0,'out':0,'cr':0,'cc':0,'msgs':0,
    'by_model':collections.Counter(),
    'model_out':collections.Counter(),
    'error_loops':0,'wf':0,'wf_agents':0,'tool_fail':0,'test_fail':0,
    'rereads':0,'rep_queries':0,'low_cache':0,'cache_sum':0.0,'cache_n':0,
    'agents':collections.Counter(),
})
glob_tf = collections.Counter()
wf_detail = []
loop_detail = []

for f in files:
    try: d = json.load(open(f))
    except: continue
    p = proj(f)
    r = per[p]; r['runs']+=1
    u = d.get('usage') or {}
    t = u.get('totals') or {}
    r['in']+=t.get('in',0); r['out']+=t.get('out',0)
    r['cr']+=t.get('cache_read',0); r['cc']+=t.get('cache_creation',0)
    ch = u.get('cache_hit')
    if ch is not None:
        r['cache_sum']+=ch; r['cache_n']+=1
        if ch < 0.90: r['low_cache']+=1
    for m,mv in (u.get('by_model') or {}).items():
        r['by_model'][m]+=mv.get('out',0)+mv.get('in',0)
        r['model_out'][m]+=mv.get('out',0)
        r['msgs']+=mv.get('msgs',0)
    for a in (u.get('agents') or []):
        r['agents'][a.get('label','?')]+=a.get('out',0) if isinstance(a.get('out'),int) else 0
    el = d.get('error_loops') or []
    r['error_loops']+=len(el)
    for e in el: loop_detail.append((p, e))
    wf = d.get('workflows') or []
    r['wf']+=len(wf)
    for w in wf:
        r['wf_agents']+=w.get('agents',0) if isinstance(w.get('agents'),int) else 0
        wf_detail.append((p, w))
    r['tool_fail']+=len(d.get('tool_failures') or [])
    for tf in (d.get('tool_failures') or []):
        glob_tf[tf.get('tool','?')]+=1
    b = d.get('bash') or {}
    for tst in (b.get('tests') or []):
        if not tst.get('ok'): r['test_fail']+=1
    rd = d.get('reads') or {}
    r['rereads']+=sum(x.get('count',0)-1 for x in (rd.get('top_rereads') or []))
    rq = (d.get('retrieval') or {}).get('repeated_queries') or []
    r['rep_queries']+=len(rq)

def fmt(n):
    for u,d in (('B',1e9),('M',1e6),('K',1e3)):
        if abs(n)>=d: return f"{n/d:.1f}{u}"
    return str(n)

print("="*90)
print(f"{'PROJECT':<40}{'runs':>5}{'out':>8}{'cache_rd':>9}{'cache%':>7}{'loops':>6}{'wf':>4}{'Tfail':>6}")
print("="*90)
tot=collections.Counter()
rows=[]
for p,r in per.items():
    cache=r['cache_sum']/r['cache_n'] if r['cache_n'] else 0
    rows.append((r['out'],p,r,cache))
    for k in ('in','out','cr','cc','runs','error_loops','wf','tool_fail','test_fail','rereads','rep_queries','low_cache'):
        tot[k]+=r[k]
rows.sort(reverse=True)
for out,p,r,cache in rows:
    print(f"{p:<40}{r['runs']:>5}{fmt(r['out']):>8}{fmt(r['cr']):>9}{cache*100:>6.1f}%{r['error_loops']:>6}{r['wf']:>4}{r['tool_fail']:>6}")
print("="*90)
print(f"{'TOTAL':<40}{tot['runs']:>5}{fmt(tot['out']):>8}{fmt(tot['cr']):>9}{'':>7}{tot['error_loops']:>6}{tot['wf']:>4}{tot['tool_fail']:>6}")
print()
print(f"out={fmt(tot['out'])} in={fmt(tot['in'])} cache_read={fmt(tot['cr'])} cache_creation={fmt(tot['cc'])}")
print(f"reread(extra)={tot['rereads']} repeated_queries={tot['rep_queries']} low_cache_runs(<90%)={tot['low_cache']}/{tot['runs']}")
print(f"test_failures={tot['test_fail']}")
print()
print("=== tool_failures by tool (all projects) ===")
for tool,n in glob_tf.most_common(): print(f"  {tool:<14}{n}")
print()
print("=== model spend (out tokens) aggregated ===")
mo=collections.Counter()
for _,r in per.items():
    for m,v in r['model_out'].items(): mo[m]+=v
for m,v in mo.most_common(): print(f"  {m:<28}{fmt(v)}")
print()
print(f"=== error_loops ({len(loop_detail)}) ===")
for p,e in loop_detail[:25]:
    s=json.dumps(e) if not isinstance(e,str) else e
    print(f"  [{p.split('/')[-1]}] {s[:150]}")
print()
print(f"=== workflows ({len(wf_detail)}) ===")
for p,w in wf_detail[:30]:
    s=json.dumps(w) if not isinstance(w,str) else w
    print(f"  [{p.split('/')[-1]}] {s[:200]}")
