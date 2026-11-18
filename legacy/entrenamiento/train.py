import json,glob,os,collections,sys,re,random,pickle,warnings
warnings.filterwarnings('ignore')
import numpy as np
sys.path.insert(0,sys.argv[1]+'/work'); from situations import norm, label as rule_label
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from scipy.sparse import hstack
S=sys.argv[1]; W=int(sys.argv[2]); STRIDE=int(sys.argv[3]); C=float(sys.argv[4])
MAP={'Goal':'gol','Penalty':'penalti','Yellow card':'amarilla','Red card':'roja','Yellow->red card':'roja','Substitution':'cambio',
 'Offside':'fuera_juego','Corner':'corner','Foul':'falta','Direct free-kick':'falta','Indirect free-kick':'falta',
 'Shots on target':'tiro','Shots off target':'tiro'}
CLS=['gol','cambio','fuera_juego','corner','falta','tiro','amarilla']
lab={os.path.relpath(os.path.dirname(p),S+'/labels'):json.load(open(p))['annotations'] for p in glob.glob(S+'/labels/**/Labels-v2.json',recursive=True)}
segs=collections.defaultdict(list)
for l in open(S+'/work/es.jsonl'):
    r=json.loads(l); segs[r['game']].append(r)
X,Y,G,TM,H,EV=[],[],[],[],[],{}
for g,ss in segs.items():
    gm,half=g.rsplit('/',1)
    if gm not in lab: continue
    ev=[(int(a['position'])/1000,MAP[a['label']]) for a in lab[gm] if a['gameTime'].split(' - ')[0]==half and a['label'] in MAP]
    EV[g]=ev; end=max(s['t1'] for s in ss); ss=sorted(ss,key=lambda s:s['t0']); w=0
    while w<end:
        txt=' '.join(s['text'] for s in ss if s['t1']>w and s['t0']<w+W)
        if txt:
            y=np.zeros(len(CLS),dtype=int)
            for t,c in ev:
                if c in CLS and w-3<=t<=w+W: y[CLS.index(c)]=1
            X.append(norm(txt)); Y.append(y); G.append(gm); H.append(g); TM.append(w+W/2)
        w+=STRIDE
Y=np.array(Y); G=np.array(G); H=np.array(H); TM=np.array(TM)
games=sorted(set(G)); random.Random(7).shuffle(games); n=len(games)
tr,va,te=set(games[:int(.7*n)]),set(games[int(.7*n):int(.85*n)]),set(games[int(.85*n):])
ix=lambda s:np.array([i for i,g in enumerate(G) if g in s]); itr,iva,ite=ix(tr),ix(va),ix(te)
vec=TfidfVectorizer(ngram_range=(1,2),min_df=4,max_features=int(sys.argv[5]),sublinear_tf=True)
Xtr=vec.fit_transform([X[i] for i in itr]); Xva=vec.transform([X[i] for i in iva]); Xte=vec.transform([X[i] for i in ite])
def events_from(prob,times,th,sep=18):
    out=[];last=-1e9
    idx=np.argsort(-prob)
    taken=[]
    for i in idx:
        if prob[i]<th: break
        if all(abs(times[i]-t)>sep for t in taken): taken.append(times[i])
    return sorted(taken)
def evaluate(i_set,probs,th,k,tol=15):
    tp=fp=fn=0; c=CLS[k]
    for g in sorted(set(H[i_set])):
        sel=[j for j,i in enumerate(i_set) if H[i]==g]
        tms=TM[i_set[sel]]; pr=probs[sel]
        order=np.argsort(tms); tms,pr=tms[order],pr[order]
        pred=events_from(pr,tms,th); true=[t for t,cc in EV[g] if cc==c]
        used=set()
        for t in true:
            m=[j for j,p in enumerate(pred) if abs(p-t)<=tol and j not in used]
            if m: used.add(m[0]); tp+=1
            else: fn+=1
        fp+=len(pred)-len(used)
    P=tp/max(tp+fp,1); R=tp/max(tp+fn,1); F=2*P*R/max(P+R,1e-9); return P,R,F,tp+fn
models={};thr={}
print(f'W={W} stride={STRIDE} C={C} | evaluación POR EVENTO (±15 s) en partidos de test')
print(f"{'clase':12s} {'eventos':>7s} | {'P':>5s} {'R':>5s} {'F1':>5s}  umbral")
for k,c in enumerate(CLS):
    m=LogisticRegression(C=C,class_weight='balanced',solver='liblinear',max_iter=500); m.fit(Xtr,Y[itr,k])
    pv=m.predict_proba(Xva)[:,1]; pt=m.predict_proba(Xte)[:,1]
    best=max(np.linspace(.3,.97,28),key=lambda th:evaluate(iva,pv,th,k)[2])
    P,R,F,N=evaluate(ite,pt,best,k)
    print(f"{c:12s} {N:7d} | {P:5.2f} {R:5.2f} {F:5.2f}  {best:.2f}")
    models[c]=m; thr[c]=float(best)
pickle.dump((vec,models,thr,CLS,W,STRIDE),open(S+f'/work/model_small_{sys.argv[5]}.pkl','wb'))
