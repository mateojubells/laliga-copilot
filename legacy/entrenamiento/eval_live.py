import json,glob,os,collections,sys,random,pickle,warnings
warnings.filterwarnings('ignore')
import numpy as np
sys.path.insert(0,sys.argv[1]+'/work'); from situations import norm
S=sys.argv[1]
vec,models,thr,CLS,W,STRIDE=pickle.load(open(S+'/work/model_small_8000.pkl','rb'))
MAP={'Goal':'gol','Substitution':'cambio','Offside':'fuera_juego','Corner':'corner','Foul':'falta','Direct free-kick':'falta','Indirect free-kick':'falta','Shots on target':'tiro','Shots off target':'tiro','Yellow card':'amarilla'}
lab={os.path.relpath(os.path.dirname(p),S+'/labels'):json.load(open(p))['annotations'] for p in glob.glob(S+'/labels/**/Labels-v2.json',recursive=True)}
segs=collections.defaultdict(list)
for l in open(S+'/work/es.jsonl'):
    r=json.loads(l); segs[r['game']].append(r)
allg=sorted({g.rsplit('/',1)[0] for g in segs if g.rsplit('/',1)[0] in lab}); random.Random(7).shuffle(allg); n=len(allg)
test=set(allg[int(.85*n):])
print('partidos test',len(test))
def probs(texts):
    X=vec.transform([norm(t) for t in texts]); return np.column_stack([models[c].predict_proba(X)[:,1] for c in CLS])
COOL=12
res={s:{c:[0,0,0] for c in CLS} for s in ('ventana','ventana+segmento','segmento')}
for g,ss in segs.items():
    gm,half=g.rsplit('/',1)
    if gm not in test: continue
    ss=sorted(ss,key=lambda s:s['t0']); ev=[(int(a['position'])/1000,MAP[a['label']]) for a in lab[gm] if a['gameTime'].split(' - ')[0]==half and a['label'] in MAP]
    wins=[' '.join(x['text'] for x in ss if s['t1']-W<x['t1']<=s['t1']) for s in ss]
    pw=probs(wins); ps=probs([s['text'] for s in ss])
    for name,P in (('ventana',pw),('ventana+segmento',np.maximum(pw,ps)),('segmento',ps)):
        for k,c in enumerate(CLS):
            last=-1e9; pred=[]
            for i,s in enumerate(ss):
                if P[i,k]>=thr[c] and s['t1']-last>=COOL: pred.append(s['t0']); last=s['t1']
            true=[t for t,cc in ev if cc==c]; used=set(); tp=fn=0
            for t in true:
                m=[j for j,p in enumerate(pred) if abs(p-t)<=15 and j not in used]
                if m: used.add(m[0]); tp+=1
                else: fn+=1
            r=res[name][c]; r[0]+=tp; r[1]+=len(pred)-len(used); r[2]+=fn
print(f"{'clase':12s}"+''.join(f" | {s:^22s}" for s in res))
for c in CLS:
    row=f"{c:12s}"
    for s in res:
        tp,fp,fn=res[s][c]; P=tp/max(tp+fp,1); R=tp/max(tp+fn,1); F=2*P*R/max(P+R,1e-9)
        row+=f" |  P{P:5.2f} R{R:5.2f} F{F:5.2f}  "
    print(row)
