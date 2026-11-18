/* Catálogo de situaciones de juego + enlace con equipos y jugadores.
   Funciona sobre tokens ya normalizados (minúsculas, sin tildes, ñ -> n), igual que index.html.
   - SITS: ~80 situaciones (regates, faltas, penaltis, córners, saques de banda, lanzadores, tarjetas, VAR...).
   - find(toks, ents): localiza las situaciones mencionadas en una frase.
   - link(toks, ents, hits, ctx): decide QUIÉN hace y QUIÉN sufre cada situación
       "penalti sobre Lamine Yamal"      -> Lamine = victim (penalti provocado)
       "penalti para el Barça"           -> Barça = benef
       "falta de Araújo sobre Vinicius"  -> Araújo = actor, Vinicius = victim
       "Pedri ha regateado a Carvajal"   -> Pedri = actor, Carvajal = victim
   Roles: actor | victim | benef | against | recv | ref (citado, sin función clara).
   Sin dependencias: se puede probar en cualquier navegador. */
(function(){
"use strict";
const SITS = [];
// kind: play (hace algo) | duel (play con rival) | award (a favor/en contra) | sanction (lo recibe alguien) | swap (cambio) | event (sin jugador)
function def(id,label,kind,pats,o){ SITS.push(Object.assign({id,label,kind,pats},o||{})); }

/* ---------- goles y remates ---------- */
def("gol","Gol","play",["gol","golazo","golazazo","goool","gooool","ha marcado","acaba de marcar","marco el","anota","anoto","ha anotado","gol olimpico"],{L:{against:"Gol encajado"}});
def("gol_penalti","Gol de penalti","play",["(marca|marco|anota|anoto|convierte|convirtio|transforma|transformo) (de|el|un)? penalti","gol de penalti","gol de pena maxima"],{refines:["penalti","gol"]});
def("autogol","Autogol","play",["autogol","gol en propia","en propia puerta","en propia meta"],{refines:["gol"]});
def("gol_anulado","Gol anulado","play",["gol anulado","anula* el? gol","anulado el? gol","gol no vale","no vale el? gol","gol invalidado"],{refines:["gol"],L:{victim:"Gol anulado"}});
def("doblete","Doblete / triplete","play",["doblete","hat trick","hattrick","triplete"],{refines:["gol"]});
def("adelanta","Se adelanta en el marcador","play",["se adelanta","se pone por delante","pone por delante","ponen por delante","abre el marcador","abre la lata"]);
def("empate","Empata","play",["empata*","empate","iguala*","igualada"]);
def("remontada","Remontada","play",["remontada","remontar","remonta*","da la vuelta al marcador","voltea el partido"]);
def("asistencia","Asistencia","play",["asistencia","asiste","asistio","pase de gol","pase del gol","sirve el gol","sirve en bandeja","deja el gol"],{L:{victim:"Asistencia recibida"},forVictim:true});
def("tiro","Tiro","play",["dispar*","tiro","chut*","remat*","zurdazo","derechazo","trallazo","latigazo","canonazo","empalma*"],{L:{victim:"Tiro recibido"}});
def("tiro_puerta","Tiro a puerta","play",["tiro a puerta","dispara a puerta","remate a puerta","chuta a puerta","entre los tres palos","a porteria"],{refines:["tiro"]});
def("tiro_fuera","Tiro fuera","play",["(tiro|disparo|remate|chut*|dispar*|remat*) fuera","se va fuera","se marcha fuera","por encima del larguero","por encima de la porteria","muy desviado","desviado","rozando el palo","lamiendo el palo"],{refines:["tiro"]});
def("palo","Palo / larguero","play",["palo","poste","larguero"]);
def("remate_cabeza","Remate de cabeza","play",["cabezazo","cabecea*","cabeceo","remate de cabeza","remata de cabeza"],{refines:["tiro"]});
def("chilena","Chilena","play",["chilena","tijereta"]);
def("vaselina","Vaselina","play",["vaselina","vaselin*","picada","pica el balon"]);
def("volea","Volea","play",["volea","vole*"]);
def("taconazo","Taconazo / rabona","play",["taconazo","de tacon","rabona"]);
def("ocasion","Ocasión","play",["(una|gran|primera|segunda|buena|mejor|clara|otra) ocasion","ocasion (clara|clarisima|de gol)","ocasionazo","oportunidad clara","clarisima","tuvo el gol"]);
def("mano_a_mano","Mano a mano","play",["mano a mano","uno contra uno con el portero"]);
def("fallo","Fallo / ocasión perdida","play",["falla","fallo","se lo pierde","lo falla","desperdicia*"]);
def("error","Error","play",["error","error garrafal","cantada","pifia","patinazo"]);

/* ---------- penaltis ---------- */
const PL_ = {actor:"Penalti cometido",victim:"Penalti provocado",benef:"Penalti a favor",against:"Penalti en contra",ref:"Penalti (citado)"};
def("penalti","Penalti","award",["penalti","penalty","penal","pena maxima","once metros","punto de penalti","punto fatidico","punto de cal"],{L:PL_,passive:null});
def("penalti_fallado","Penalti fallado","play",["penalti fallado","falla* el? penalti","fallo el? penalti","no marca el penalti","falla la pena maxima","penalti al palo","penalti a las nubes","penalti desviado","penalti fuera"],{refines:["penalti","fallo"]});
def("penalti_parado","Penalti parado","play",["penalti parado","para* el penalti","paro el penalti","detiene el penalti","ataja el penalti","le para el penalti","penalti atajado","penalti detenido"],{refines:["penalti"]});
def("penalti_reclamado","Penalti reclamado","play",["pide* penalti","piden penalti","reclama* penalti","reclaman penalti","protesta* penalti","penalti reclamado"],{refines:["penalti"]});
def("penalti_no","Penalti no pitado","event",["no es penalti","no hay penalti","no pita penalti","no da penalti","no senala penalti","no es pena maxima","sin penalti","no existe penalti"],{refines:["penalti"]});
def("lanza_penalti","Lanza el penalti","play",["lanz* el? penalti","(chuta*|tira*|patea*|dispara*|pega*) el? penalti","(chuta|tira|patea|dispara) la pena maxima","penalti lo? (lanza|chuta|tira|patea|ejecuta)","ejecut* el? penalti","cobr* el? penalti","penalti lanzado","penalti ejecutado","se encarga del penalti","encargado del penalti","lanzador del penalti","lanz* la pena maxima","va a lanzar la pena maxima"],{refines:["penalti"],L:{actor:"Lanza penaltis"}});

/* ---------- faltas y balón parado ---------- */
const FALTA_L = {actor:"Falta cometida",victim:"Falta recibida",benef:"Falta a favor",against:"Falta en contra",ref:"Falta (citada)"};
def("falta","Falta","award",[
  "(una|esa|esta|otra|primera|segunda|tercera|gran|clara|dura|innecesaria|ingenua|tonta|fuerte) falta",
  "falta (sobre|clara|dura|innecesaria|cometida|a favor|en contra|en campo)","falta de +E","falta a +E",
  "comete* falta","pita* falta","pitan falta","senala* falta","cobra falta","sufre* falta","recibe* falta","provoca* falta","gana* falta","hay falta",
  "infraccion","derriba*","derribad*","derribo","zancadilla","zancadille*","agarron","tiron de camiseta","empujon","patada","pisoton","codazo","manotazo",
  "entrada dura","entrada por detras","entrada tarde","entrada peligrosa","juego peligroso"],{L:FALTA_L,passive:/^(derribad|zancadilleado|empujad|golpead|agarrad)/});
def("falta_tactica","Falta táctica","award",["falta tactica","falta para cortar","falta para evitar"],{refines:["falta"],L:FALTA_L});
def("falta_peligrosa","Falta peligrosa","award",["falta peligrosa","falta lateral","falta frontal","falta directa","falta indirecta","falta al borde del area","falta en la frontal","falta cerca del area","tiro libre","libre directo","libre indirecto","golpe franco"],{refines:["falta"],ofTeam:"benef",L:{actor:"Falta cometida",victim:"Falta recibida",benef:"Falta a favor",against:"Falta en contra",ref:"Falta (citada)"}});
def("lanza_falta","Lanza faltas","play",["lanz* la? (falta|libre)","cobr* la? (falta|libre)","ejecut* la? (falta|libre)","bota* la? (falta|libre)","falta lanzada","lanzador de faltas","especialista en faltas","especialista a balon parado","tiene que lanzar la falta"],{refines:["falta","falta_peligrosa"],L:{actor:"Lanza faltas"}});
def("corner","Córner","award",["(corner|cornel|corne|carner|korner)","saque de esquina","tiro de esquina","saca de esquina"],{ofTeam:"benef",L:{actor:"Córner",benef:"Córner a favor",against:"Córner en contra",victim:"Córner",ref:"Córner (citado)"}});
def("lanza_corner","Lanza córners","play",["lanz* el? (corner|cornel)","bota* el? corner","(centra|centrara|centrar|centran) el? (corner|cornel)","saca el corner","cobra el corner","ejecuta el corner","(corner|cornel) sera? (centrado|lanzado|botado|sacado|cobrado)","(corner|cornel) va a ser (centrado|lanzado|botado|sacado|cobrado)","(corner|cornel) (lo|los)? (centra|centrara|lanza|lanzara|bota|botara|saca|sacara|cobra|cobrara)","(corner|cornel) de (lo|los) (centra|centrara|lanza|lanzara|bota|botara)"],{refines:["corner"],L:{actor:"Lanza córners"}});
def("saque_banda","Saque de banda","award",["saque de banda","saque lateral","saque de lateral","saca de banda","saca de lateral"],{ofTeam:"benef",L:{actor:"Saque de banda",benef:"Saque de banda a favor",against:"Saque de banda en contra",ref:"Saque de banda"}});
def("saque_largo","Saque de banda largo","award",["saque de banda largo","saque largo","saque de mano largo"],{refines:["saque_banda"],ofTeam:"benef",L:{actor:"Saque largo",benef:"Saque largo a favor",against:"Saque largo en contra",ref:"Saque largo"}});
def("saque_puerta","Saque de puerta","award",["saque de puerta","saque de meta","saca de puerta","saca de meta","saque del portero"],{ofTeam:"benef",L:{actor:"Saque de puerta",benef:"Saque de puerta a favor",against:"Saque de puerta en contra",ref:"Saque de puerta"}});
def("balon_parado","Balón parado","event",["balon parado","jugada ensayada","jugada de estrategia"]);
def("falta_lanzador","Lanzador","play",["coloca el balon","coge el balon","se dispone a lanzar","se hace cargo"],{L:{actor:"Lanzador"}});

/* ---------- disciplina ---------- */
def("amarilla","Amarilla","sanction",["amarilla","amonest*","amonestacion","cartulina amarilla","tarjeta amarilla"]);
def("segunda_amarilla","Doble amarilla","sanction",["segunda amarilla","doble amarilla","dos amarillas","segunda tarjeta"],{refines:["amarilla"]});
def("roja","Roja / expulsión","sanction",["roja","expuls*","expulsion","cartulina roja","tarjeta roja","a la ducha","a la calle","roja directa"]);
def("tarjeta","Tarjeta","sanction",["tarjeta","cartulina","tarjetazo"]);
def("fuera_juego","Fuera de juego","sanction",["fuera de juego","offside","posicion adelantada","levanta el banderin","bandera del linier"]);
def("mano","Mano","award",["mano dentro del area","mano en el area","mano clara","toca* con la mano","toca* con el brazo","con el brazo","tocado con la mano"],{L:{actor:"Mano",victim:"Mano (sufrida)",benef:"Mano a favor",against:"Mano en contra",ref:"Mano"}});
def("simulacion","Simulación","play",["simula*","simulacion","piscinazo","se tira"]);
def("protesta","Protestas","play",["protesta*","protestas","rodean al arbitro","encaran al arbitro"]);
def("ventaja","Ley de la ventaja","event",["ley de la ventaja","aplica la ventaja","juega la ventaja","permite la ventaja","deja seguir"]);
def("var","VAR","event",["var","videoarbitro","videoarbitraje","revision","revisa*","revisando","al monitor","va al monitor","pantalla","revisar la jugada","llaman al arbitro"]);
def("lesion","Lesión","sanction",["se lesiona","se ha lesionado","lesionarse","queda lesionado","sale lesionado","se duele","camilla","atencion medica","asistencia medica","atienden a","sanitarios","se queda tendido","se queda en el suelo","cojea","molestias","no puede continuar"]);

/* ---------- regates y jugadas individuales ---------- */
def("regate","Regate","duel",["(regate|regatea|regateo|regatean|regatear|regateando|regateado|regateada|regatearon|regateara|regatee)","(dribla|driblo|driblan|driblar|driblando|driblado|dribling)","se quita*","se deshace de","se zafa","quiebra","quiebro","recorte","recorta*","bicicleta","elastico","croqueta","ruleta"],{L:{victim:"Regateado"}});
def("cano","Caño","duel",["un cano","el cano","le hace un cano","hace un cano"],{L:{victim:"Caño sufrido"}});
def("sombrero","Sombrero","duel",["sombrero","le hace un sombrero"],{L:{victim:"Sombrero sufrido"}});
def("finta","Finta","duel",["finta","amaga*","amago"]);
def("desborde","Desborde","duel",["desborda*","desborde","gana la espalda","gana la linea de fondo","se va por la banda","uno contra uno","un contra uno"],{L:{victim:"Desbordado"}});
def("conduccion","Conducción / carrera","play",["conduce*","conduccion","arrancada","cabalgada","galopada","se va solo","se lleva el balon"]);
def("entrada","Entrada","duel",["entrada limpia","buena entrada","gran entrada","entrada providencial","tackle","se desliza","deslizamiento"],{L:{victim:"Entrada recibida"}});
def("robo","Robo / recuperación","duel",["roba* el? (balon|pelota|esferico|cuero)","le roba*","robo de balon","recupera* el? (balon|pelota|esferico)","gana el balon","quita el balon","le quita"],{L:{victim:"Balón perdido"}});
def("perdida","Pérdida de balón","play",["pierde el balon","perdida de balon","pierde la pelota","balon perdido","pierde la posesion","regala el balon","pierde el esferico"]);
def("intercepcion","Intercepción","duel",["intercept*","anticipa*","anticipacion","corta el pase","corta el balon","corta el centro","corta la jugada"]);
def("bloqueo","Bloqueo","play",["bloquea*","bloqueo","bloqueado","se interpone"]);
def("despeje","Despeje","play",["despeje","despeja*","despejo"]);
def("rechace","Rechace","play",["rechace","rechaza*"]);
def("salvada","Salvada bajo palos","play",["salva en la linea","salvada","sobre la linea","bajo palos"]);
def("parada","Parada","play",["parada","paradon","ataja*","blocaje","bloca*","saca una mano","detiene (el|un|la)? (disparo|tiro|remate|balon|cabezazo)","gran intervencion"],{L:{victim:"Parada sufrida"}});
def("rebote","Rebote","play",["rebote","rebota*"]);
def("pierde_tiempo","Pierde tiempo","play",["pierde tiempo","pierde el tiempo","hace tiempo","gasta tiempo","perder tiempo"]);
def("tiro_lejano","Tiro lejano","play",["tiro lejano","disparo lejano","de media distancia","zapatazo","punterazo","taponazo"],{refines:["tiro"]});
def("tangana","Tangana","play",["tangana","rifirrafe","tumulto","tension entre"]);
def("interrupcion","Juego interrumpido","event",["partido detenido","se detiene el partido","partido interrumpido","interrupcion"]);
def("mal_control","Mal control","play",["mal control","control defectuoso","se le va el balon"]);
def("corner_corto","Córner corto","play",["corner corto","corner en corto"],{refines:["corner"]});
def("salida_portero","Salida del portero","play",["sale el portero","sale el guardameta","salida del portero","portero sale","sale a cortar","sale a por el balon","sale del area"]);
def("duelo_aereo","Duelo aéreo","duel",["duelo aereo","gana por arriba","gana el salto","disputa aerea","por alto"],{L:{victim:"Duelo aéreo perdido"}});
def("duelo","Duelo","duel",["duelo","disputa el balon","forcejea*","forcejeo","lucha el balon"]);

/* ---------- pases y construcción ---------- */
def("pase","Pase","play",["se la pasa*","(la|se la) da para","lada para","pasala","pasalo","pasa* (a|para) +E","pase (de|del|a|para) +E","le pasa*","se la deja","la deja para","toca para +E","se la juega a","da el pase","(un|el) pase"],{L:{victim:"Pase recibido"},forVictim:true});
def("pase_clave","Pase clave","play",["pase filtrado","pase clave","pase al hueco","pase en profundidad","pase vertical","pase magico","balon en profundidad"],{L:{victim:"Pase clave recibido"}});
def("pase_largo","Pase largo / cambio de juego","play",["pase largo","balon largo","pelotazo","cambio de orientacion","cambio de juego","envio largo"]);
def("pared","Pared","play",["pared","una dos","uno dos"],{L:{victim:"Pared con"}});
def("centro","Centro","play",["centro al area","centro lateral","centro desde","centro raso","centro atras","centro medido","centro peligroso","(centra|centran|centrar|centrando|centrara|centraran|centrado|centrada)","pelota colgada","balon colgado","pase de la muerte"],{L:{victim:"Centro recibido"},forVictim:true});
def("cesion","Cesión","play",["cesion","cesion al portero","pase atras"]);
def("contragolpe","Contragolpe","play",["contragolpe","contraataque","contraataca*","a la contra","transicion rapida"]);
def("posesion","Posesión / circulación","play",["posesion","circulacion","tiquitaca","tiki taka"]);
def("presion","Presión","play",["presion","presiona*","pressing","presionando"]);

/* ---------- cambios y partido ---------- */
def("cambio","Cambio","swap",["cambio en el","sustitucion","sustituye*","sustituido","sustituyen","hace el cambio","hace un cambio","doble cambio","triple cambio","primer cambio","segundo cambio","ultimo cambio","entra* por +E","entra* al campo","entra* en el campo","sale del campo","sale sustituido","abandona el campo","abandona el terreno"],{L:{actor:"Entra",victim:"Sale"}});
def("inicio","Comienzo","event",["pitido inicial","arranca el partido","comienza el partido","empieza el partido","saque de centro","saca de centro","saque inicial"]);
def("descanso","Descanso","event",["descanso","al descanso","vestuarios","fin de la primera parte"]);
def("final","Final del partido","event",["pitido final","final del partido","final del encuentro","acaba el partido","termina el partido","fin del partido"]);
def("tiempo_anadido","Tiempo añadido","event",["tiempo anadido","descuento","minutos de descuento","tiempo de descuento","anadidos","minutos anadidos","prolongacion"]);
def("prorroga","Prórroga / tanda","event",["prorroga","tanda de penaltis"]);

/* ======================= compilación ======================= */
const BY = {}; SITS.forEach(s=>BY[s.id]=s);
const tokRe = t => new RegExp("^(?:"+t.replace(/^\(|\)$/g,"").split("|").map(a=>a.endsWith("*")?a.slice(0,-1)+"\\w*":a).join("|")+")$");
function expand(parts){ let seqs=[[]];
  parts.forEach(p=>{ const opt=p.endsWith("?"); if(opt) p=p.slice(0,-1); const next=[]; seqs.forEach(s=>{ next.push(s.concat([p])); if(opt) next.push(s.slice()); }); seqs=next; });
  return seqs.filter(s=>s.length); }
const PATS = [];
SITS.forEach(s=>s.pats.forEach(p=>{
  let needE=false; if(p.endsWith(" +E")){ needE=true; p=p.slice(0,-3); }
  expand(p.split(" ")).forEach(seq=>{
    const c0=new Set(seq[0].replace(/^\(|\)$/g,"").split("|").map(a=>a[0]));
    PATS.push({sit:s.id,res:seq.map(tokRe),c0,needE}); }); }));

/* ======================= búsqueda ======================= */
function find(toks, ents){
  const starts=new Set((ents||[]).map(e=>e.i)), raw=[];
  for(let i=0;i<toks.length;i++){ const c=toks[i][0];
    for(const P of PATS){ if(!P.c0.has(c)) continue; const n=P.res.length; if(i+n>toks.length) continue;
      let ok=true; for(let j=0;j<n;j++) if(!P.res[j].test(toks[i+j])){ ok=false; break; }
      if(!ok) continue;
      if(P.needE){ let f=false; for(let k=i+n;k<=i+n+2&&k<toks.length;k++) if(starts.has(k)){ f=true; break; } if(!f) continue; }
      if(P.sit==="palo" && i>0 && /^(primer|segundo|primero|tercer)$/.test(toks[i-1])) continue;   // "al segundo palo" = posición, no remate
      if(P.sit==="falta" && i>0 && /^(hace|hacen|hacia|haria|hizo|hacer)$/.test(toks[i-1])) continue;   // "hace falta" = necesidad
      raw.push({sit:P.sit,i,L:n}); } }
  for(let i=0;i<toks.length;i++){            // "entra Ferran por Lewandowski": el nombre va entre "entra" y "por"
    if(!/^(entra|entran|entrara|ingresa)$/.test(toks[i])) continue;
    for(let j=i+2;j<=i+6&&j<toks.length;j++){ if(toks[j]!=="por") continue;
      let a=false,b=false; for(let k=i+1;k<j;k++) if(starts.has(k)) a=true; for(let k=j+1;k<=j+2;k++) if(starts.has(k)) b=true;
      if(a&&b){ raw.push({sit:"cambio",i,L:j-i+1}); break; } } }
  const end=h=>h.i+h.L-1, ov=(a,b)=>a.i<=end(b)&&b.i<=end(a);
  let hs=raw.filter(b=>!raw.some(a=>a!==b&&BY[a.sit].refines&&BY[a.sit].refines.includes(b.sit)&&ov(a,b)));
  hs=hs.filter(b=>!hs.some(a=>a!==b&&a.sit!==b.sit&&a.i<=b.i&&end(a)>=end(b)&&a.L>b.L));
  const out=[]; hs.sort((a,b)=>b.L-a.L||a.i-b.i);
  hs.forEach(h=>{ if(!out.some(o=>o.sit===h.sit&&ov(o,h))) out.push(h); });
  return out.sort((a,b)=>a.i-b.i); }

/* ======================= enlace situación <-> entidades ======================= */
function cueOf(toks,e){
  const s=toks.slice(Math.max(0,e.i-3),e.i).join(" ");
  if(/(a favor (de|del)|favor (de|del)|para( el| la| los| las)?)$/.test(s)) return "for";
  if(/(en contra (de|del)|contra( el| la| los| las)?)$/.test(s)) return "against";
  if(/(sobre|ante)( el| la)?$/.test(s)) return "victim";
  if(/(^| )por$/.test(s)) return "by";
  if(/(^| )(a|al)$/.test(s)) return "to";
  if(/(^| )(de|del)( el| la| los| las)?$/.test(s)) return "of";
  return null; }
const VICT_V = /^(recibe|recibio|recibida|sufre|sufrio|provoca|provoco|genera|genero|gana|gano|consigue|consiguio|logra|logro|forzo|fuerza|provocado|generado)$/;
function roleFor(S,e,cue,before,toks,ev,taken,passive){
  const team=e.kind==="team", k=S.kind;
  switch(cue){
    case "for": if(S.forVictim) return "victim"; return k==="sanction"?"recv" : (k==="play"||k==="duel"||k==="swap")?"actor" : (team?"benef":"victim");
    case "against": return k==="sanction"?"recv" : "against";
    case "victim": case "to": return k==="sanction"?"recv" : k==="swap"?"actor" : "victim";
    case "by": return k==="swap"?"victim" : "actor";
    case "of": return k==="sanction"?"recv" : (k==="award"&&team)?(S.ofTeam||"actor") : "actor";
  }
  if(k==="sanction") return "recv";
  if(passive) return before?"victim":"actor";
  if(k==="award"){
    if(before){ for(let j=e.i+e.L;j<ev.i;j++) if(VICT_V.test(toks[j])) return "victim"; }
    return team&&S.ofTeam?S.ofTeam:"actor"; }
  if(k==="swap") return "actor";
  return (before||!taken.actor)?"actor":"victim"; }

function link(toks, ents, hits, ctx){
  ctx=ctx||{};
  const evs=hits.map(h=>({sit:h.sit,i:h.i,L:h.L,links:[],fallback:false}));
  const taken=evs.map(()=>({actor:false}));
  ents.slice().sort((a,b)=>a.i-b.i).forEach(e=>{
    const eEnd=e.i+e.L-1, cue=cueOf(toks,e); let best=-1,bd=1e9;
    evs.forEach((ev,k)=>{
      const before=eEnd<ev.i, hEnd=ev.i+ev.L-1, gap=before?ev.i-eEnd-1:e.i>hEnd?e.i-hEnd-1:0;
      if(gap>(before?5:(cue?8:5))) return;
      const d=gap-(before&&!cue?0.5:0); if(d<bd){ bd=d; best=k; } });
    if(best<0) return;
    const ev=evs[best], S=BY[ev.sit], before=eEnd<ev.i;
    const passive=!!(S.passive&&S.passive.test(toks[ev.i]));
    const role=roleFor(S,e,cue,before,toks,ev,taken[best],passive);
    if(role==="actor") taken[best].actor=true;
    if(!ev.links.some(l=>l.kind===e.kind&&l.ent===e.ent&&l.role===role)) ev.links.push({kind:e.kind,ent:e.ent,role}); });
  evs.forEach((ev,k)=>{
    const S=BY[ev.sit];
    if(S.kind==="sanction"||S.kind==="event"){ const pl=ev.links.filter(l=>l.kind==="player"); if(pl.length) ev.links=pl; }   // la tarjeta es de la persona, no del club
    if(ev.links.length||S.kind==="event") return;
    let who=null;
    if(S.kind==="sanction"){ for(let j=k-1;j>=0;j--){ const p=evs[j]; if(BY[p.sit].id==="falta"||BY[p.sit].id==="falta_tactica"||BY[p.sit].id==="entrada"){ const a=p.links.find(l=>l.role==="actor"); if(a){ who=a; break; } } } }
    if(who){ ev.links=[{kind:who.kind,ent:who.ent,role:"recv"}]; ev.fallback=false; return; }
    if(ctx.subject){ ev.links=[{kind:ctx.subject.kind,ent:ctx.subject.ent,role:S.kind==="sanction"?"recv":S.kind==="award"?"ref":"actor"}]; ev.fallback=true; } });
  return evs; }

function roleLabel(id,role){ const s=BY[id]; if(!s) return id; const L=s.L||{}; if(L[role]) return L[role];
  switch(role){ case "actor": case "recv": return s.label; case "victim": return s.label+" (recibido)"; case "benef": return s.label+" a favor"; case "against": return s.label+" en contra"; default: return s.label+" (citado)"; } }

window.CAT = {SITS,BY,find,link,roleLabel,cueOf,count:PATS.length};
})();
