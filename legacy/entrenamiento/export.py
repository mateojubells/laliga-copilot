import pickle,json,sys,numpy as np,warnings
warnings.filterwarnings('ignore')
S=sys.argv[1]
vec,models,thr,CLS,W,STRIDE=pickle.load(open(S+'/work/model_small_8000.pkl','rb'))
terms=vec.get_feature_names_out(); idf=vec.idf_
cls=list(CLS)
rows={}
for i,t in enumerate(terms):
    rows[t]=[round(float(idf[i]),3)]+[round(float(models[c].coef_[0][i]),3) for c in cls]
out={"window":W,"classes":cls,"bias":[round(float(models[c].intercept_[0]),3) for c in cls],
     "thr":[round(thr[c],2) for c in cls],"terms":rows}
js="window.SIT_MODEL="+json.dumps(out,ensure_ascii=False,separators=(',',':'))+";\n"
open(S+'/work/situaciones.js','w').write(js)
print('bytes',len(js),'terms',len(rows),cls,out['thr'])
# casos de paridad
import re,random
sys.path.insert(0,S+'/work'); from situations import norm
cases=["gol de messi tras una gran jugada dentro del area","amarilla para sergio ramos por la falta","saque de esquina para el real madrid","fuera de juego del delantero","cambio en el barcelona sale iniesta entra rakitic","remata de cabeza y el portero la desvia","el partido esta muy igualado en el centro del campo"]
exp=[]
for c in cases:
    X=vec.transform([norm(c)])
    exp.append({"text":c,"p":[round(float(models[k].predict_proba(X)[0,1]),4) for k in cls]})
json.dump(exp,open(S+'/work/parity.json','w'),ensure_ascii=False)
