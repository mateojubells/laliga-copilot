import re, unicodedata
def norm(s):
    s=unicodedata.normalize('NFD',s.lower()); s=''.join(c for c in s if unicodedata.category(c)!='Mn')
    return re.sub(r'[^a-z0-9ñ ]+',' ',s).strip()
# situación -> patrones (sobre texto normalizado sin tildes)
SIT = {
 'gol':        [r'\bgol\b',r'\bgolazo\b',r'\bgoool',r'\bmarca\b.*\b(el|un)\b',r'\bha marcado\b',r'\bla manda al fondo\b',r'\bla mete\b',r'\bde cabeza.*\bdentro\b',r'\bempata\b',r'\bse adelanta\b',r'\bponen? por delante\b',r'\bdoblete\b',r'\bhat trick\b'],
 'penalti':    [r'\bpenalti\b',r'\bpenalty\b',r'\bpena maxima\b',r'\bdesde los once metros\b',r'\bpunto de penalti\b'],
 'tarjeta':    [r'\bamarilla\b',r'\broja\b',r'\bexpulsa',r'\bexpulsion\b',r'\bamonest',r'\btarjeta\b',r'\bcartulina\b',r'\bdoble amarilla\b'],
 'falta':      [r'\bfalta\b',r'\bfaltas\b',r'\bderriba\b',r'\bentrada dura\b',r'\bfalta peligrosa\b',r'\btiro libre\b',r'\blanzamiento de falta\b',r'\bbarrera\b'],
 'fuera_juego':[r'\bfuera de juego\b',r'\bfuera de lugar\b',r'\bbanderin\b',r'\bposicion adelantada\b',r'\bposicion antirreglamentaria\b'],
 'corner':     [r'\bcorner\b',r'\bsaque de esquina\b',r'\besquina\b'],
 'ocasion':    [r'\bocasion\b',r'\boportunidad\b',r'\bremata\b',r'\bremate\b',r'\bdisparo\b',r'\bdispara\b',r'\btira\b.*\bporteria\b',r'\bpalo\b',r'\blarguero\b',r'\bpor poco\b',r'\bcerca del gol\b',r'\bse va fuera\b',r'\bpasa rozando\b',r'\bgran ocasion\b'],
 'parada':     [r'\bparada\b',r'\bparadon\b',r'\bdespeja\b',r'\bdetiene\b',r'\bse estira\b',r'\bmanos de\b',r'\bpara el portero\b',r'\bportero\b.*\bevita\b'],
 'cambio':     [r'\bcambio\b',r'\bsustitucion\b',r'\bsale\b.*\bentra\b',r'\bentra\b.*\bpor\b',r'\bsustituye\b',r'\bse retira\b'],
 'lesion':     [r'\blesion',r'\bse duele\b',r'\blesionado\b',r'\bcamilla\b',r'\batencion medica\b',r'\bmolestias\b',r'\bqueda tendido\b',r'\bse queda en el suelo\b'],
 'var':        [r'\bvar\b',r'\brevision\b',r'\brevisa\b',r'\bmonitor\b',r'\bvideoarbitraje\b'],
 'resultado':  [r'\bempate\b',r'\bremontada\b',r'\bremontar\b',r'\bventaja\b',r'\bmarcador\b',r'\bresultado\b',r'\b\d a \d\b',r'\bvamos ganando\b',r'\bvamos perdiendo\b',r'\bempatando\b',r'\bganando\b',r'\bperdiendo\b'],
 'tiempo':     [r'\bdescanso\b',r'\bprimera parte\b',r'\bsegunda parte\b',r'\bprimer tiempo\b',r'\bsegundo tiempo\b',r'\bfinal del partido\b',r'\bpita el final\b',r'\bprorroga\b',r'\bminutos de descuento\b',r'\bdescuento\b',r'\bpita\b.*\bfinal\b',r'\bcomienza\b|\bcomenzamos\b|\bempieza el partido\b'],
 'posesion':   [r'\bposesion\b',r'\bdomina\b',r'\bcontrola el balon\b',r'\bcirculacion\b',r'\btoque\b',r'\btiki taka\b',r'\bmonopoliza\b'],
 'presion':    [r'\bpresion\b',r'\bpresiona\b',r'\brecupera\b',r'\brobo\b',r'\bperdida\b',r'\bcontraataque\b',r'\bcontra\b ?ataque\b',r'\bcontragolpe\b',r'\btransicion\b'],
 'defensa':    [r'\bdefensa\b',r'\bdefiende\b',r'\bdespeje\b',r'\bsalvada\b',r'\bcierra\b.*\bespacios\b',r'\bbloque bajo\b',r'\bcentral\b'],
 'juego_aereo':[r'\bde cabeza\b',r'\bcabezazo\b',r'\bcabecea\b',r'\bremate de cabeza\b',r'\bbalon parado\b',r'\bcentro\b'],
 'estadistica':[r'\bestadistica\b',r'\bdatos?\b',r'\bracha\b',r'\bhistorico\b',r'\brecord\b',r'\bsin perder\b',r'\bsin ganar\b',r'\bconsecutiv',r'\bsolo\b.*\bveces\b',r'\bllevaba\b',r'\bacumula\b',r'\bcifra\b'],
}
CRE = {k:[re.compile(p) for p in v] for k,v in SIT.items()}
def label(text):
    t=norm(text); return [k for k,ps in CRE.items() if any(p.search(t) for p in ps)]
