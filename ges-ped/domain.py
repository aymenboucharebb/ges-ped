import datetime as dt, json, math, re
from database import rows,get,raw_insert,refs,audit,uid,now
from schema import SCHEMA,STAFF,DAYS,DEFAULT_SLOTS
from database import norm

class Invalid(ValueError): pass
def require(ok,message):
    if not ok: raise Invalid(message)
def writable(db,year):
    y=db.execute('SELECT * FROM years WHERE id=?',(year,)).fetchone()
    require(y is not None,'Année introuvable.')
    require(not y['closed'],'Cette année est clôturée : consultation uniquement.')
LINKS={'assignment':['activity','group'],'wish':['activity'],'activity':['subject'],'subject':['department','ue'],'ue':['semester'],'semester':['level'],'level':['track','specialty'],'specialty':['track'],'track':['department','cycle'],'teacher':['department'],'group':['level'],'slot':['assignment','room'],'session':['assignment','room'],'extra':['teacher'],'unavailable':['group','teacher'],'campaign':['department']}
# L'enseignant d'une affectation / d'un vœu est noté sans remonter à son département administratif :
# le département propriétaire d'un enseignement est toujours celui de la matière.
LEAF={'assignment':['teacher'],'wish':['teacher','campaign']}
def context(db,record,index=None):
    """Ascendance métier utilisée par les filtres et les droits départementaux."""
    fetch=(lambda id:index.get(id)) if index is not None else (lambda id:get(db,id))
    out={}; seen=set()
    def walk(r):
        if not r or r['id'] in seen:return
        seen.add(r['id']);d=r['data'];out.setdefault(r['kind'],r['id'])
        for field in LINKS.get(r['kind'],[]):
            if d.get(field):walk(fetch(d[field]))
        for field in LEAF.get(r['kind'],[]):
            if d.get(field):out.setdefault(field,d[field])
    walk(record);return out
def dept_of(db,record,index=None):return context(db,record,index).get('department')
def level_concerned(db,dept,level):
    """Un niveau concerne un département dès qu'il contient une matière de ce département."""
    return any(r['active'] and context(db,r).get('level')==level and context(db,r).get('department')==dept for r in rows(db,get(db,level)['year'],'subject')) if level and get(db,level) else False
def teacher_ids(db,year,user):
    """Fiches enseignant de l'année liées au compte (une seule personne ENSF)."""
    if not user.get('teacher'):return set()
    return {r['id'] for r in rows(db,year,'teacher') if r['data'].get('person')==user['teacher']}
def is_own(db,user,teacher_id):
    t=get(db,teacher_id) if teacher_id else None
    return bool(t and user.get('teacher') and t['data'].get('person')==user['teacher'])
PROFILE_FIELDS=['english_level','english_ok','english_note','email']
WISH_REQUEST=['campaign','teacher','activity','priority','language','note']
def campaign_open(db,campaign):
    c=get(db,campaign)['data'];today=dt.date.today().isoformat()
    require(c['status']=='Ouverte','Cette campagne de vœux n’est pas ouverte au dépôt.')
    require(c['open']<=today<=c['deadline'],f"Dépôt des vœux possible du {c['open']} au {c['deadline']}.")
def capacities(user):
    caps=[user['role']]
    if user.get('teacher') and user['role']!='Enseignant':caps.append('Enseignant')
    return caps
def chef_scope(db,dept,kind,r,existing):
    d=r['data']
    if kind in ['assignment','slot','session','wish']:
        return None if dept_of(db,r)==dept else 'Cet enseignement relève d’un autre département : consultation seulement.'
    if kind=='campaign':return None if d.get('department')==dept else 'Une campagne créée par un chef de département concerne uniquement son département.'
    if kind=='group':return None if level_concerned(db,dept,d.get('level')) else 'Ce niveau ne comporte aucune matière de votre département.'
    if kind=='teacher':
        ok=d.get('department')==dept or (not existing and not d.get('department'))
        return None if ok else 'Seule la direction modifie la fiche d’un enseignant rattaché administrativement à un autre département. Vous pouvez néanmoins l’affecter à vos enseignements.'
    if kind=='unavailable':
        ok=(d.get('group') and level_concerned(db,dept,get(db,d['group'])['data']['level'])) or (d.get('room') and not d.get('teacher') and not d.get('group'))
        return None if ok else 'Indisponibilités d’enseignants : réservées à la direction (elles valent pour toute l’ENSF).'
    if kind=='extra':
        t=get(db,d.get('teacher')) if d.get('teacher') else None
        return None if t and t['data'].get('department')==dept else 'Missions : enseignants rattachés à votre département uniquement.'
    return 'Ce référentiel est administré par la direction.'
def rights(db,cap,user,kind,new,old,deleting):
    if cap in STAFF:return None
    if cap=='Consultation':return 'Compte en consultation : modification interdite.'
    if cap=='Enseignant':
        if deleting:return 'Espace enseignant : suppression impossible. Retirez le vœu à la place.'
        if kind=='teacher':
            if not old or not is_own(db,user,old['id']):return 'Vous ne pouvez modifier que votre propre profil.'
            if any(new['data'].get(f['key'])!=old['data'].get(f['key']) for f in SCHEMA['teacher']['fields'] if f['key'] not in PROFILE_FIELDS+['person']):
                return 'Depuis votre espace, seuls le niveau d’anglais, la possibilité d’enseigner en anglais, l’observation et le courriel sont modifiables.'
            return None
        if kind=='wish':
            if not is_own(db,user,new['data'].get('teacher')) or (old and not is_own(db,user,old['data'].get('teacher'))):return 'Vous ne pouvez gérer que vos propres vœux.'
            if old:
                if old['data']['state']!='En attente':return 'Ce vœu a déjà été traité ou retiré : il n’est plus modifiable.'
                if any(new['data'].get(k)!=old['data'].get(k) for k in ['campaign','teacher','activity','decision_note']):return 'Pour une autre activité, formulez un nouveau vœu.'
                if new['data']['state'] not in ['En attente','Retirée']:return 'La décision appartient au chef du département de la matière.'
            elif new['data']['state']!='En attente' or new['data'].get('decision_note'):return 'Un nouveau vœu est toujours en attente de décision.'
            try:campaign_open(db,new['data']['campaign'])
            except Invalid as e:return str(e)
            return None
        return 'Espace enseignant : vous pouvez gérer vos vœux et votre profil. Les affectations relèvent du chef de département.'
    if cap=='Chef de département':
        dept=user.get('department')
        if not dept:return 'Compte chef de département sans département associé.'
        for r,existing in [(new,bool(old)),(old,True)]:
            if r:
                m=chef_scope(db,dept,kind,r,existing)
                if m:return m
        if kind=='wish' and old and any(new['data'].get(k)!=old['data'].get(k) for k in WISH_REQUEST):
            return 'Le chef décide du vœu sans modifier la demande de l’enseignant.'
        return None
    return 'Rôle inconnu.'
def permission(db,user,kind,new=None,old=None,deleting=False):
    if new is None and old is None:
        require(user['role'] in STAFF,'Action réservée à la direction.' if user['role']!='Consultation' else 'Compte en consultation : modification interdite.');return
    errors=[rights(db,cap,user,kind,new or old,old,deleting) for cap in capacities(user)]
    require(any(e is None for e in errors),errors[0])
def parse_slots(text):
    out=[]
    for part in (text or DEFAULT_SLOTS).replace(';',',').split(','):
        part=part.strip()
        if not part:continue
        a,_,b=part.partition('-');a=minutes(a.strip());b=minutes(b.strip());require(a<b,'Créneau invalide : '+part);out.append((a,b))
    require(out,'Aucun créneau défini.');return sorted(out)
def slots_of(db,year):
    rules=[r for r in rows(db,year,'rule') if r['active']]
    return parse_slots(rules[-1]['data'].get('slots') if rules else None)
def hhmm(m):return f'{m//60:02d}:{m%60:02d}'
def check_slot_time(db,year,start,duration):
    """Une séance occupe un ou plusieurs créneaux consécutifs ENSF, sans chevaucher la pause."""
    sl=slots_of(db,year);begin=minutes(start);end=begin+round(duration*60)
    starts=[a for a,_ in sl];ok=False
    if begin in starts:
        i=starts.index(begin);cur=sl[i][1]
        while True:
            if end<=cur:ok=True;break
            if i+1>=len(sl) or sl[i+1][0]!=cur:break
            i+=1;cur=sl[i][1]
    require(ok,'Horaire hors des créneaux ENSF ('+', '.join(hhmm(a)+'–'+hhmm(b) for a,b in sl)+') : une séance commence au début d’un créneau et reste dans un ou plusieurs créneaux consécutifs, sans chevaucher la pause.')
def minutes(value):
    require(isinstance(value,str) and re.fullmatch(r'\d{2}:\d{2}',value),'Heure attendue au format HH:MM.')
    h,m=map(int,value.split(':'));require(0<=h<24 and 0<=m<60,'Heure invalide.');return h*60+m
def weeks(value,total):
    require(float(total).is_integer(),'Le nombre de semaines doit être entier.')
    total=int(total)
    if value.strip().lower()=='toutes':return list(range(1,total+1))
    result=set()
    try:
        for part in value.replace(' ','').split(','):
            if '-' in part:
                a,b=map(int,part.split('-'));require(a<=b,'Intervalle de semaines inversé.');result.update(range(a,b+1))
            else:result.add(int(part))
    except (ValueError,TypeError):raise Invalid('Semaines attendues : toutes, 1-14 ou 1,3,5.')
    require(result and min(result)>=1 and max(result)<=total,'Les semaines dépassent la durée du semestre.')
    return sorted(result)
def semester_for(db,assignment):
    a=get(db,assignment);require(a and a['kind']=='assignment','Affectation introuvable.')
    return get(db,context(db,a)['semester'])
def occurrences(db,slot):
    d=slot['data'];sem=semester_for(db,d['assignment'])['data']
    require(sem.get('start'),'Renseignez le premier dimanche du semestre dans Structure → Semestres.')
    start=dt.date.fromisoformat(sem['start']);require(start.weekday()==6,'La date de référence du semestre doit être un dimanche.')
    require(d['day'] in DAYS,'Jour hors de la semaine ENSF (dimanche → jeudi).')
    day=DAYS.index(d['day'])
    return [dict(d,date=(start+dt.timedelta(weeks=w-1,days=day)).isoformat()) for w in weeks(d['weeks'],sem['weeks'])]
def ancestors(db,id):
    found=set()
    while id and id not in found:
        found.add(id);r=get(db,id);id=r['data'].get('parent') if r else None
    return found
def group_conflict(db,a,b):return a in ancestors(db,b) or b in ancestors(db,a)
def calendar(db,year,exclude=None):
    events=[]
    for slot in rows(db,year,'slot'):
        if slot['id']==exclude or not slot['active']:continue
        if db.execute('SELECT 1 FROM generated WHERE slot=?',(slot['id'],)).fetchone():continue
        for e in occurrences(db,slot):events.append((slot['id'],e))
    for s in rows(db,year,'session'):
        if s['id']!=exclude and s['active'] and s['data']['state'] not in ['Annulée','À reprogrammer']:
            events.append((s['id'],s['data']))
    return events
def check_event(db,year,event,exclude=None):
    a=get(db,event['assignment'])['data'];room=get(db,event['room'])['data'];act=get(db,a['activity'])['data'];g=get(db,a['group'])['data']
    require(get(db,event['assignment'])['active'] and a['state']=='Validée','Seules les affectations actives et validées peuvent être planifiées.')
    require(get(db,event['room'])['active'],'Salle inactive.')
    size=g.get('size')
    if g['type']=='Section' and size is None:
        children=[r['data'].get('size') for r in rows(db,year,'group') if r['active'] and r['data'].get('parent')==get(db,a['group'])['id']]
        if children and all(x is not None for x in children):size=sum(children)
    require(size is not None,'Renseignez l’effectif de la section / du groupe pour contrôler la capacité.')
    require(size<=room['capacity'],'Capacité de salle insuffisante.')
    require(not act.get('roomtype') or act['roomtype']==room['type'],'Type de salle incompatible avec cette activité.')
    begin=minutes(event['start']);end=begin+event['duration']*60;require(end<=1440,'La séance dépasse minuit.')
    for _,other in calendar(db,year,exclude):
        if other['date']!=event['date']:continue
        ob=minutes(other['start']);oe=ob+other['duration']*60
        if begin<oe and ob<end:
            oa=get(db,other['assignment'])['data']
            problems=[]
            if oa['teacher']==a['teacher']:problems.append('enseignant')
            if other['room']==event['room']:problems.append('salle')
            if group_conflict(db,oa['group'],a['group']):problems.append('section / groupe')
            if problems:
                where=' (séance d’un autre département)' if dept_of(db,get(db,other['assignment']))!=dept_of(db,get(db,event['assignment'])) else ''
                raise Invalid(f"Conflit le {event['date']} à {event['start']} : {', '.join(problems)} déjà occupé(e){where}.")
    for r in rows(db,year,'unavailable'):
        u=r['data']
        if not r['active'] or u['date']!=event['date']:continue
        if begin<minutes(u['end']) and minutes(u['start'])<end:
            require(not ((u.get('teacher') and u['teacher']==a['teacher']) or (u.get('room') and u['room']==event['room']) or (u.get('group') and group_conflict(db,u['group'],a['group']))),'Indisponibilité : '+u['name'])
def planned(db,year,assignment,exclude=None):
    events=[(id,e) for id,e in calendar(db,year,exclude) if e['assignment']==assignment]
    total=sum(e['duration'] for _,e in events)
    for id,e in events:
        if e.get('state')=='Partiellement réalisée':
            replaced=sum(x['duration'] for _,x in events if x.get('replaces')==id)
            total-=min(e['duration']-e['actual'],replaced)
    return total
def validate(db,year,kind,data,id=None):
    require(kind in SCHEMA,'Type de donnée inconnu.')
    clean={}
    for field in SCHEMA[kind]['fields']:
        key=field['key'];v=data.get(key);typ=field['type']
        if field.get('auto'):clean[key]=v if isinstance(v,str) else None;continue
        if isinstance(v,str):v=v.strip()
        if v in ('',None):
            require(not field['required'],field['label']+' : champ obligatoire.');clean[key]=None;continue
        if typ=='number':
            try:v=float(v)
            except (ValueError,TypeError):raise Invalid(field['label']+' : nombre attendu.')
            require(math.isfinite(v) and field.get('min',-1e12)<=v<=field.get('max',1e9),field['label']+' : valeur hors limites.')
        else:require(isinstance(v,str) and len(v)<=10000,field['label']+' : texte invalide.')
        if typ=='ref':
            target=get(db,v);require(target and target['kind']==field['ref'] and target['year']==year,field['label']+' : référence invalide ou autre année.')
            old=get(db,id) if id else None
            require(target['active'] or (old and old['data'].get(key)==v),field['label']+' : donnée inactive.')
        if typ=='select':require(v in field['options'],field['label']+' : choix inconnu.')
        if typ=='date':
            try:dt.date.fromisoformat(v)
            except ValueError:raise Invalid(field['label']+' : date invalide.')
        if typ=='time':minutes(v)
        clean[key]=v
    d=clean
    if kind=='semester':
        require(d['weeks'].is_integer(),'Nombre de semaines entier attendu.')
        if d.get('start'):require(dt.date.fromisoformat(d['start']).weekday()==6,'Choisissez un dimanche comme début des semaines pédagogiques (semaine ENSF : dimanche → jeudi).')
    if kind=='group':
        if d.get('size') is not None:require(d['size'].is_integer(),'Effectif entier attendu.')
        if d.get('parent'):
            p=get(db,d['parent']);require(p['data']['level']==d['level'],'Le parent doit appartenir au même niveau.')
            require(not id or id not in ancestors(db,d['parent']),'Une section / un groupe ne peut être son propre parent.')
            require((d['type'],p['data']['type']) in [('Groupe','Section'),('Sous-groupe','Groupe')],'Hiérarchie attendue : Section → Groupe → Sous-groupe.')
        else:require(d['type']=='Section','Un groupe doit être rattaché à une section ; un sous-groupe à un groupe.')
    if kind=='level' and d.get('specialty'):require(get(db,d['specialty'])['data']['track']==d['track'],'Spécialité et filière incompatibles.')
    if kind=='teacher':
        if d['load']=='Demi-charge':require(d.get('decision') and d.get('decision_date'),'La demi-charge exige un numéro et une date de décision.')
        if d['load']=='Personnalisée':require(d.get('target') is not None and d.get('decision'),'La charge personnalisée exige une cible et une décision.')
        # Une personne = une seule fiche ENSF, quel que soit le nombre de départements où elle intervient.
        others=[r for r in rows(db,year,'teacher') if r['id']!=id]
        if d.get('code'):require(not any(norm(r['data'].get('code'))==norm(d['code']) for r in others),'Un enseignant possède déjà ce matricule. Une seule fiche par personne : s’il intervient dans plusieurs départements, affectez simplement la fiche existante.')
        if d.get('email'):require(not any(norm(r['data'].get('email'))==norm(d['email']) for r in others),'Ce courriel est déjà utilisé par une autre fiche enseignant.')
        for r in others:
            if norm(r['data'].get('last'))==norm(d['last']) and norm(r['data'].get('first'))==norm(d['first']):
                require(d.get('code') and r['data'].get('code'),'Cet enseignant existe déjà (même nom et prénom). Une seule fiche par personne, même s’il intervient dans plusieurs départements. En cas d’homonymie réelle, renseignez le matricule des deux fiches.')
        d['english_level']=d.get('english_level') or 'Non renseigné';d['english_ok']=d.get('english_ok') or 'Non déclaré'
    if kind=='language':
        require(not any(r['id']!=id and r['data']['code'].lower()==d['code'].lower() for r in rows(db,year,kind)),'Ce code de langue existe déjà.')
    if kind=='assignment':
        act=get(db,d['activity']);teacher=get(db,d['teacher']);group=get(db,d['group']);typ=get(db,act['data']['type'])['data']
        require(teacher['active'] and act['active'] and group['active'],'Enseignant, activité et groupe doivent être actifs.')
        require(context(db,act)['level']==group['data']['level'],'Le groupe ne correspond pas au niveau de cette activité.')
        require(typ['target']=='Libre' or typ['target']==group['data']['type'] or (typ['target']=='Groupe' and group['data']['type']=='Sous-groupe'),'Le type d’activité ne correspond pas à une section / un groupe adapté.')
        require(typ.get('factor') is not None,'Équivalence de charge non définie pour ce type d’activité. Renseignez une règle justifiée avant affectation.')
        # La langue appartient à l'affectation (programme officiel en français, langue réelle selon l'enseignant).
        if d.get('wish'):
            w=get(db,d['wish'])['data']
            require(w['teacher']==d['teacher'] and w['activity']==d['activity'],'Le vœu d’origine doit concerner le même enseignant et la même activité.')
            require(w['state'] in ['Acceptée','Acceptée partiellement'],'Seul un vœu accepté (totalement ou partiellement) peut donner lieu à une affectation.')
        others=[r for r in rows(db,year,kind) if r['active'] and r['id']!=id and r['data']['activity']==d['activity']]
        total=d['hours']
        for r in others:
            rd=r['data']
            if rd['group']==d['group']:total+=rd['hours']
            elif group_conflict(db,rd['group'],d['group']):raise Invalid('Cette activité est déjà affectée à un parent / sous-groupe de ce public.')
        require(total<=act['data']['hours']+1e-7,f"Dépassement : {total:g} h affectées pour {act['data']['hours']:g} h réglementaires à ce public.")
    if kind=='campaign':require(d['open']<=d['deadline'],'La date limite doit suivre la date d’ouverture.')
    if kind=='wish':
        act=get(db,d['activity']);camp=get(db,d['campaign'])['data'];teacher=get(db,d['teacher'])
        require(act['data']['category'] in ['Réglementaire','Formation complémentaire'],'Les vœux portent sur les enseignements du programme (Cours, TD, TP).')
        require(camp['status']!='Préparation','Cette campagne est encore en préparation.')
        require(get(db,context(db,act)['semester'])['data']['period']==camp['period'],'Cette activité n’appartient pas au semestre de la campagne.')
        if camp.get('department'):require(dept_of(db,act)==camp['department'],'Cette matière ne relève pas du département de la campagne.')
        require((get(db,d['language'])['data'].get('code') or '').lower() in ['fr','en'],'Langue souhaitée : Français ou Anglais.')
        require(d['priority'].is_integer(),'Priorité : nombre entier (choix 1, 2, 3…).')
        if d['state']!='Retirée':
            require(not any(r['id']!=id and r['active'] and r['data']['state']!='Retirée' and all(r['data'][k]==d[k] for k in ['campaign','teacher','activity']) for r in rows(db,year,'wish')),'Un vœu existe déjà pour cette activité dans cette campagne : modifiez-le plutôt que d’en créer un second.')
        old=get(db,id) if id else None
        if old and old['data']['state']=='Retirée' and d['state']!='Retirée':raise Invalid('Ce vœu a été retiré par l’enseignant ; il ne peut plus être traité.')
        if old and d['state'] not in ['Acceptée','Acceptée partiellement']:
            require(not any(r['active'] and r['data'].get('wish')==id for r in rows(db,year,'assignment')),'Une affectation a été créée depuis ce vœu : archivez-la avant de modifier la décision.')
        if not old:require(teacher['active'],'Enseignant inactif.')
    if kind=='unavailable':
        require(any(d.get(k) for k in ['teacher','room','group']),'Choisissez au moins une ressource indisponible.')
        require(minutes(d['start'])<minutes(d['end']),'La fin doit suivre le début.')
        for _,e in calendar(db,year):
            a=get(db,e['assignment'])['data']
            if e['date']==d['date'] and minutes(e['start'])<minutes(d['end']) and minutes(d['start'])<minutes(e['start'])+e['duration']*60:
                require(not ((d.get('teacher') and d['teacher']==a['teacher']) or (d.get('room') and d['room']==e['room']) or (d.get('group') and group_conflict(db,d['group'],a['group']))),'Une séance existe pendant cette indisponibilité. Déplacez-la d’abord.')
    if kind=='rule' and d.get('slots'):parse_slots(d['slots'])
    if kind in ['slot','session']:
        prev=get(db,id) if id else None
        if kind=='slot' or (d['state'] not in ['Annulée','À reprogrammer'] and (not prev or any(prev['data'].get(k)!=d.get(k) for k in ['date','start','duration']))):check_slot_time(db,year,d['start'],d['duration'])
        events=occurrences(db,dict(data=d)) if kind=='slot' else [d]
        if kind=='session':
            require(d['actual']<=d['duration'],'Le réalisé ne peut dépasser la durée prévue.')
            if d['state'] in ['Prévue','Annulée','À reprogrammer']:require(d['actual']==0,'Ce statut exige zéro heure réalisée.')
            if d['state']=='Réalisée':require(d['actual']==d['duration'],'Une séance réalisée doit avoir son volume entièrement réalisé.')
            if d['state']=='Partiellement réalisée':require(0<d['actual']<d['duration'],'Précisez un volume réalisé strictement compris entre zéro et la durée prévue.')
            if d['state']=='Rattrapée':raise Invalid('Le statut Rattrapée est calculé depuis les séances de remplacement réalisées.')
            if d.get('replaces'):
                orig=get(db,d['replaces']);require(orig['id']!=id and orig['data']['assignment']==d['assignment'] and orig['data']['state'] in ['Annulée','À reprogrammer','Partiellement réalisée'],'Le rattrapage doit viser une séance annulée, partielle ou à reprogrammer de la même affectation.')
                existing=sum(r['data']['duration'] for r in rows(db,year,'session') if r['active'] and r['id']!=id and r['data'].get('replaces')==orig['id'] and r['data']['state']!='Annulée')
                require(existing+d['duration']<=orig['data']['duration']-orig['data']['actual']+1e-7,'Les rattrapages dépassent le volume restant de la séance d’origine.')
            # Les annulations libèrent la place mais conservent le volume historique.
            if d['state'] in ['Annulée','À reprogrammer']:events=[]
        for e in events:check_event(db,year,e,id)
        volume=sum(e['duration'] for e in events)
        already=planned(db,year,d['assignment'],id)
        # Un remplacement de séance partielle ne double pas le volume restant de son origine.
        if kind=='session' and d.get('replaces'):
            orig=get(db,d['replaces'])['data']
            if orig['state']=='Partiellement réalisée' and events:
                other=sum(s['data']['duration'] for s in rows(db,year,'session') if s['active'] and s['id']!=id and s['data'].get('replaces')==d['replaces'] and s['data']['state'] not in ['Annulée','À reprogrammer'])
                already-=min(d['duration'],max(0,orig['duration']-orig['actual']-other))
        require(already+volume<=get(db,d['assignment'])['data']['hours']+1e-7,'Le volume planifié dépasse le volume affecté. Réduisez les semaines ou la durée.')
    return clean

def save(db,user,year,kind,data,id=None,revision=None,active=1):
    writable(db,year);old=get(db,id) if id else None
    if id:require(old and old['year']==year and old['kind']==kind,'Élément introuvable.')
    if old:permission(db,user,kind,old,old)  # droits vérifiés avant toute validation métier
    else:
        allowed=set()
        for cap in capacities(user):
            if cap in STAFF:allowed|=set(SCHEMA)
            if cap=='Chef de département':allowed|={'assignment','slot','session','wish','campaign','group','teacher','unavailable','extra'}
            if cap=='Enseignant':allowed|={'wish'}
        if kind not in allowed:
            raise Invalid('Compte en consultation : modification interdite.' if user['role']=='Consultation' else ('Espace enseignant : vous pouvez gérer vos vœux et votre profil. Les affectations relèvent du chef de département.' if user['role']=='Enseignant' else 'Ce référentiel est administré par la direction.'))
    clean=validate(db,year,kind,data,id)
    if old:
        require(revision==old['revision'],'Cette fiche a changé. Actualisez la page avant de réessayer.')
        used=any(id in context(db,r).values() or r['data'].get('room')==id or (kind=='activitytype' and r['kind']=='assignment' and get(db,r['data']['activity'])['data']['type']==id) for r in rows(db,year) if r['kind'] in ['assignment','slot','session'])
        if kind=='assignment':used=bool(db.execute("SELECT 1 FROM links JOIN records ON records.id=links.source WHERE target=? AND records.kind<>'wish'",(id,)).fetchone())
        if kind=='campaign':used=bool(db.execute('SELECT 1 FROM links WHERE target=?',(id,)).fetchone())
        if kind in ['semester','group']:
            used=any(id in context(db,r).values() for r in rows(db,year) if r['kind'] in ['slot','session'])
        if used:
            protected={'activity':['subject','type','hours','category'],'campaign':['period','department'],'assignment':['activity','teacher','group','hours','language','state'],'semester':['level','start','weeks','period'],'group':['level','parent','type','size'],'room':['capacity','type'],'activitytype':['factor','target'],'subject':['ue','department'],'ue':['semester'],'level':['track','specialty'],'track':['department','cycle']}.get(kind,[])
            require(not any(clean.get(k)!=old['data'].get(k) for k in protected),'Cette fiche est utilisée. Retirez les éléments dépendants avant de modifier ses caractéristiques pédagogiques, ou créez une nouvelle fiche.')
        if kind=='slot':require(not db.execute('SELECT 1 FROM generated WHERE slot=?',(id,)).fetchone(),'Les séances datées ont été générées : modifiez-les dans Suivi.')
        if kind=='session' and any(r['active'] and r['data'].get('replaces')==id for r in rows(db,year,'session')):
            require(all(clean.get(k)==old['data'].get(k) for k in ['assignment','duration','state','actual','replaces']),'Cette séance possède des rattrapages. Conservez son volume et son état d’origine ; modifiez d’abord les remplacements si nécessaire.')
        if kind=='rule':raise Invalid('Les règles sont versionnées : créez une nouvelle version.')
    stamp=now()
    if kind=='teacher':clean['person']=old['data'].get('person') if old and old['data'].get('person') else (clean.get('person') or uid())
    if kind=='wish':
        for k in ['submitted','updated','decision_date','decided_by']:clean[k]=old['data'].get(k) if old else None
        if not old:clean['submitted']=stamp
        elif any(clean.get(k)!=old['data'].get(k) for k in ['priority','language','note']) or ((clean['state']=='Retirée')!=(old['data']['state']=='Retirée')):clean['updated']=stamp
        if clean['state'] in ['Acceptée','Acceptée partiellement','Refusée'] and (not old or clean['state']!=old['data']['state'] or clean.get('decision_note')!=old['data'].get('decision_note')):
            clean['decision_date']=stamp;clean['decided_by']=user['name']
        if clean['state'] in ['En attente','Retirée']:clean['decision_date']=clean['decided_by']=None
    new=dict(id=id or '',kind=kind,year=year,data=clean)
    permission(db,user,kind,new,old,deleting=bool(old) and bool(active)!=bool(old['active']))
    if not active:
        require(not db.execute('SELECT 1 FROM links JOIN records ON records.id=links.source WHERE links.target=? AND records.active=1',(id,)).fetchone(),'Des éléments actifs utilisent cette fiche. Archivez-les d’abord.')
    if old:
        db.execute('UPDATE records SET data=?,active=?,revision=revision+1 WHERE id=?',(json.dumps(clean,ensure_ascii=False),int(bool(active)),id))
    else:id=raw_insert(db,year,kind,clean)
    if kind=='rule':db.execute("UPDATE records SET active=0,revision=revision+1 WHERE year=? AND kind='rule' AND id<>?",(year,id))
    refs(db,id,kind,clean);audit(db,user['name'],'Modification' if old else 'Création',year,kind,id,old,get(db,id))
    return get(db,id)
def generate(db,user,year):
    writable(db,year);require(user['role'] in ['Administrateur','Direction / DAP'],'Validation de l’emploi du temps réservée à la direction.')
    count=0
    for slot in rows(db,year,'slot'):
        if not slot['active'] or db.execute('SELECT 1 FROM generated WHERE slot=?',(slot['id'],)).fetchone():continue
        for e in occurrences(db,slot):
            check_event(db,year,e,slot['id'])
            d={k:e[k] for k in ['assignment','room','date','start','duration']};d.update(state='Prévue',actual=0,note=e.get('note'))
            id=raw_insert(db,year,'session',d);refs(db,id,'session',d);db.execute('INSERT INTO generated VALUES(?,?)',(slot['id'],id));count+=1
        audit(db,user['name'],'Validation et génération',year,'slot',slot['id'],None,{'séances':len(occurrences(db,slot))})
    return count
def duplicate_year(db,user,source,name):
    require(user['role']=='Administrateur','Action réservée à l’administrateur.')
    require(name.strip() and len(name)<80,'Libellé d’année invalide.')
    year=uid();db.execute('INSERT INTO years(id,name) VALUES(?,?)',(year,name))
    records=[r for r in rows(db,source) if r['kind'] not in ['assignment','slot','session','extra','unavailable','campaign','wish']]
    mapping={r['id']:uid() for r in records}
    for r in records:
        d=dict(r['data'])
        for f in SCHEMA[r['kind']]['fields']:
            if f['type']=='ref' and d.get(f['key']):d[f['key']]=mapping.get(d[f['key']])
        if r['kind']=='semester':d['start']=None
        raw_insert(db,year,r['kind'],d,mapping[r['id']],r['active'])
    for r in rows(db,year):refs(db,r['id'],r['kind'],r['data'])
    audit(db,user['name'],'Nouvelle année sans affectations',year,'year',year,None,{'source':source,'name':name})
    return year
def load_status(gap):
    if gap is None:return 'Cible non définie'
    return 'Sous-charge' if gap<-.01 else ('Dépassement' if gap>.01 else 'Charge atteinte')
def summary(db,year):
    """Synthèses globales ENSF : charges tous départements confondus, couverture, anglais."""
    allrows=rows(db,year);index={r['id']:r for r in allrows};active=[r for r in allrows if r['active']]
    ctx={r['id']:context(db,r,index) for r in allrows}
    def anc(id):
        found=set()
        while id and id not in found:found.add(id);id=index[id]['data'].get('parent') if id in index else None
        return found
    rules=[r for r in active if r['kind']=='rule'];rule=rules[-1]['data'] if rules else None
    events=calendar(db,year)
    def planned_of(aid):
        ev=[(i,e) for i,e in events if e['assignment']==aid];total=sum(e['duration'] for _,e in ev)
        for i,e in ev:
            if e.get('state')=='Partiellement réalisée':total-=min(e['duration']-e['actual'],sum(x['duration'] for _,x in ev if x.get('replaces')==i))
        return total
    assignments=[r for r in active if r['kind']=='assignment'];sessions=[r for r in active if r['kind']=='session']
    valid_all=[a for a in assignments if a['data']['state']=='Validée']
    def factor(a):return index[index[a['data']['activity']]['data']['type']]['data'].get('factor') or 0
    def period(a):return index[ctx[a['id']]['semester']]['data']['period']
    def code(lang):return (index.get(lang) or {}).get('data',{}).get('code','').lower() if lang else ''
    loads=[];annual=[]
    for t in [r for r in active if r['kind']=='teacher']:
        year_rows=[]
        for per in ['1','2']:
            selected=[a for a in assignments if a['data']['teacher']==t['id'] and period(a)==per]
            valid=[a for a in selected if a['data']['state']=='Validée'];ids={a['id'] for a in valid}
            assigned=sum(a['data']['hours']*factor(a) for a in valid)
            pl=sum(planned_of(a['id'])*factor(a) for a in valid)
            actual=sum(s['data']['actual']*factor(index[s['data']['assignment']]) for s in sessions if s['data']['assignment'] in ids)
            extra=sum(r['data']['equivalent'] for r in active if r['kind']=='extra' and r['data']['teacher']==t['id'] and r['data']['period']==per and r['data']['state']=='Validée')
            target=(t['data'].get('target') if t['data']['load']=='Personnalisée' else (rule['half'] if t['data']['load']=='Demi-charge' else rule['normal'])) if rule else None
            depts={}
            for a in valid:
                k=ctx[a['id']].get('department') or '';depts[k]=depts.get(k,0)+a['data']['hours']*factor(a)
            gap=assigned+extra-target if target is not None else None
            row=dict(teacher=t['id'],period=per,assigned=assigned,planned=pl,actual=actual,extra=extra,target=target,gap=gap,status=load_status(gap),depts=depts,
                english=sum(a['data']['hours'] for a in valid if code(a['data']['language'])=='en'),
                draft=sum(a['data']['hours']*factor(a) for a in selected if a['data']['state']=='Brouillon'),types={name:sum(a['data']['hours'] for a in valid if index[index[a['data']['activity']]['data']['type']]['data']['name']==name) for name in ['Cours','TD','TP']})
            loads.append(row);year_rows.append(row)
        tot=lambda k:sum(r[k] for r in year_rows)
        target=None if any(r['target'] is None for r in year_rows) else tot('target')
        depts={}
        for r in year_rows:
            for k,v in r['depts'].items():depts[k]=depts.get(k,0)+v
        gap=tot('assigned')+tot('extra')-target if target is not None else None
        annual.append(dict(teacher=t['id'],assigned=tot('assigned'),planned=tot('planned'),actual=tot('actual'),extra=tot('extra'),target=target,gap=gap,status=load_status(gap),depts=depts,english=tot('english'),reference=rule['annual'] if rule else None))
    # Publics d'une activité : sections, ou groupes / sous-groupes les plus fins du niveau.
    groups=[r for r in active if r['kind']=='group']
    def publics(a):
        typ=index[a['data']['type']]['data'];level=ctx[a['id']].get('level')
        pub=[g for g in groups if g['data']['level']==level and (g['data']['type']==typ['target'] or (typ['target']=='Groupe' and g['data']['type']=='Sous-groupe'))]
        if typ['target']=='Groupe':pub=[g for g in pub if not any(x['data'].get('parent')==g['id'] for x in pub)]
        return pub
    coverage=[];stats={}
    for a in [r for r in active if r['kind']=='activity' and r['data']['category']!='PFE']:
        mine=[x for x in valid_all if x['data']['activity']==a['id']];h=a['data']['hours'];pub=publics(a)
        if pub:
            per_pub=[]
            for g in pub:
                lineage=anc(g['id']);inside=[x for x in mine if x['data']['group'] in lineage]
                assigned=sum(x['data']['hours'] for x in inside);en=sum(x['data']['hours'] for x in inside if code(x['data']['language'])=='en')
                coverage.append(dict(activity=a['id'],group=g['id'],required=h,assigned=assigned,remaining=h-assigned));per_pub.append((min(h,assigned),min(h,en)))
            cov=sum(p[0] for p in per_pub)/len(per_pub);en=sum(p[1] for p in per_pub)/len(per_pub)
        else:
            assigned=sum(x['data']['hours'] for x in mine);coverage.append(dict(activity=a['id'],group=None,required=h,assigned=assigned,remaining=h-assigned))
            cov=min(h,assigned);en=min(h,sum(x['data']['hours'] for x in mine if code(x['data']['language'])=='en'))
        # Heures réglementaires affectées en anglais : moyenne sur les publics, jamais multipliées par les groupes.
        stats[a['id']]=dict(hours=h,english=en,assigned=cov,publics=len(pub) or 1,category=a['data']['category'])
    regulatory=[a for a in active if a['kind']=='activity' and a['data']['category']=='Réglementaire']
    def english(items):
        total=sum(a['data']['hours'] for a in items);en=sum(stats[a['id']]['english'] for a in items);cov=sum(stats[a['id']]['assigned'] for a in items)
        return dict(total=total,english=en,assigned=cov,rate=en/total*100 if total else None,coverage=cov/total*100 if total else None)
    breakdown=[]
    for k in ['department','cycle','track','specialty','level','semester']:
        for r in active:
            if r['kind']==k:
                selected=[a for a in regulatory if ctx[a['id']].get(k)==r['id']]
                if selected:breakdown.append(dict(kind=k,id=r['id'],**english(selected)))
    for per in ['1','2']:
        selected=[a for a in regulatory if index[ctx[a['id']]['semester']]['data']['period']==per]
        if selected:breakdown.append(dict(kind='period',id=per,**english(selected)))
    progression=[]
    for a in assignments:
        ss=[s for s in sessions if s['data']['assignment']==a['id']];actual=sum(s['data']['actual'] for s in ss)
        late=sum(max(0,s['data']['duration']-s['data']['actual']-sum(x['data']['actual'] for x in ss if x['data'].get('replaces')==s['id'])) for s in ss if s['data']['date']<dt.date.today().isoformat() and not s['data'].get('replaces'))
        progression.append(dict(assignment=a['id'],assigned=a['data']['hours'],planned=planned_of(a['id']),actual=actual,remaining=max(0,a['data']['hours']-actual),rate=actual/a['data']['hours']*100,late=late,makeups=sum(s['data']['actual'] for s in ss if s['data'].get('replaces'))))
    busy=[]
    for sl in [r for r in active if r['kind']=='slot']:
        a=index.get(sl['data']['assignment'])
        if a:busy.append(dict(teacher=a['data']['teacher'],day=sl['data']['day'],start=sl['data']['start'],duration=sl['data']['duration'],weeks=sl['data']['weeks'],period=period(a),department=ctx[a['id']].get('department')))
    return dict(english=english(regulatory),breakdown=breakdown,activityStats=stats,loads=loads,annual=annual,coverage=coverage,progression=progression,busy=busy,counts={k:sum(r['kind']==k for r in active) for k in SCHEMA})
PUBLIC=['department','cycle','track','specialty','level','semester','group','language','grade','status','roomtype','uetype','activitytype','ue','subject','activity','room','rule','campaign']
def visible(db,year,user,allrows=None):
    """Filtrage côté serveur : chaque rôle ne reçoit que les données auxquelles il a droit."""
    allrows=rows(db,year) if allrows is None else allrows
    role=user['role']
    if role in STAFF or role=='Consultation':return allrows
    index={r['id']:r for r in allrows};mine=teacher_ids(db,year,user);dept=user.get('department') if role=='Chef de département' else None
    out=[]
    for r in allrows:
        k=r['kind'];c=context(db,r,index) if k not in PUBLIC else {}
        ok=k in PUBLIC
        if not ok and k in ['assignment','slot','session','wish','extra','unavailable']:ok=c.get('teacher') in mine or (k=='unavailable' and r['data'].get('teacher') in mine)
        if not ok and k=='teacher':ok=r['id'] in mine
        if not ok and dept:
            if k in ['teacher','unavailable']:ok=True
            elif k in ['assignment','slot','session','wish']:ok=c.get('department')==dept
            elif k=='extra':ok=(index.get(r['data'].get('teacher')) or {}).get('data',{}).get('department')==dept
        if ok:out.append(r)
    return out
def scoped_summary(db,year,user,shown):
    s=summary(db,year);role=user['role']
    if role in STAFF or role=='Consultation':return s
    ids={r['id'] for r in shown};mine=teacher_ids(db,year,user)
    s['progression']=[p for p in s['progression'] if p['assignment'] in ids]
    s['counts']={k:sum(r['kind']==k and r['active'] for r in shown) for k in SCHEMA}
    if role=='Chef de département':
        # Informations globales strictement nécessaires à l'affectation : charges et créneaux occupés, sans détail des enseignements des autres départements.
        s['coverage']=[c for c in s['coverage'] if dept_of(db,get(db,c['activity']))==user.get('department') or False]
        return s
    s['loads']=[l for l in s['loads'] if l['teacher'] in mine];s['annual']=[l for l in s['annual'] if l['teacher'] in mine]
    s['busy']=[b for b in s['busy'] if b['teacher'] in mine]
    s['coverage']=[];s['activityStats']={};s['breakdown']=[];s['english']=None
    return s
