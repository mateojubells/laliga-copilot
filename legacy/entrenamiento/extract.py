import pyarrow as pa, json, collections, re, sys
S=sys.argv[1]
t=pa.ipc.open_stream(open(S+'/echoes/soccer_net_echoes_hf_dataset-train.arrow','rb')).read_all()
lang=json.load(open(S+'/echoes/game_lang.json'))
rows=collections.defaultdict(list)
for gi,st,en,tx,sg in zip(t.column('game').to_pylist(),t.column('start_time').to_pylist(),t.column('end_time').to_pylist(),t.column('text').to_pylist(),t.column('segment_index').to_pylist()):
    gm=gi.rsplit('/',1)[0]
    if lang.get(gm)=='es': rows[gi].append((sg,st,en,tx.strip()))
out=open(S+'/work/es.jsonl','w'); n=0; dup=0
for gi,r in rows.items():
    r.sort(); prev=None; rep=0
    for sg,st,en,tx in r:
        if not tx: continue
        if tx==prev:
            rep+=1; dup+=1
            if rep>=1: continue   # drop consecutive repeats (Whisper hallucination)
        else: rep=0
        prev=tx
        out.write(json.dumps({"game":gi,"seg":sg,"t0":round(st,1),"t1":round(en,1),"text":tx},ensure_ascii=False)+"\n"); n+=1
print('halves',len(rows),'segments kept',n,'repeats dropped',dup)
