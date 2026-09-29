"""Recette de bout en bout du pilote ges-ped via HTTPS (tests A à G), avec de vrais navigateurs Chromium.
Usage : python3 tests/e2e_pilote.py https://pilote.ges-ped.test MOT_DE_PASSE_TEMPORAIRE_ADMIN [dossier_captures]
Le certificat du site doit être reconnu par le navigateur : aucune exception de sécurité n'est acceptée."""
import asyncio,sys,re,datetime,json
from playwright.async_api import async_playwright
URL=sys.argv[1].rstrip('/');ADMIN_TMP=sys.argv[2];SHOTS=sys.argv[3] if len(sys.argv)>3 else None
RESULTS=[]
def check(name,ok,detail=''):
    RESULTS.append((name,bool(ok),detail));print(('OK   ' if ok else 'ÉCHEC')+' '+name+(' — '+str(detail) if detail and not ok else ''),flush=True)
async def shot(page,name):
    if SHOTS:await page.screenshot(path=f'{SHOTS}/{name}.png')
async def new_page(browser):
    ctx=await browser.new_context(viewport={'width':1440,'height':900},locale='fr-FR')  # pas d'ignore_https_errors
    page=await ctx.new_page();page.errors=[];page.on('pageerror',lambda e:page.errors.append(str(e)));return page
async def login(page,name,password,new=None):
    await page.goto(URL+'/');await page.wait_for_selector('#login-form')
    await page.fill('input[name=name]',name);await page.fill('input[name=password]',password);await page.click('#login-form button[type=submit]')
    if new:
        await page.wait_for_selector('#change-form');await page.fill('input[name=new]',new);await page.fill('input[name=confirm]',new);await page.click('#change-form button[type=submit]')
    await page.wait_for_selector('.sidebar')
async def api(page,path,data=None):
    return await page.evaluate("""async([path,data])=>{let r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':S.csrf},body:data?JSON.stringify(data):undefined});return [r.status,await r.json()]}""",[path,data])
async def nav(page,name,tab=None):
    await page.click(f'.nav button[data-nav="{name}"]')
    if tab:await page.click(f'.tabs button[data-tab="{tab}"]')
    await page.wait_for_timeout(150)
async def dialog_error(page):return (await page.text_content('#form-error') or '').strip()
async def credentials(page):
    await page.wait_for_selector('#credentials-text');t=await page.inner_text('#credentials-text')
    ident=re.search(r'Identifiant : (\S+)',t).group(1);pw=re.search(r'Mot de passe temporaire : (\S+)',t).group(1);link=re.search(r'Lien : (\S+)',t).group(1)
    await page.click('#dialog [data-action="close"]');return ident,pw,link
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(args=['--no-proxy-server'])
        # ---------- Administration : première connexion et préparation ----------
        adm=await new_page(browser)
        await login(adm,'admin',ADMIN_TMP,'Admin-Pilote-2026!')
        check('Admin : HTTPS valide, changement obligatoire du mot de passe, tableau de bord',await adm.is_visible('.sidebar'))
        check('Nom ges-ped et mention PILOTE',('ges-ped' in await adm.title()) and 'PILOTE' in await adm.inner_text('.sidefoot'))
        st,S=await api(adm,'bootstrap');Y=S['year'];R=lambda k:[r for r in S['records'] if r['kind']==k]
        dA=(await api(adm,'save',{'year':Y,'kind':'department','data':{'name':'Département A (pilote)'}}))[1]
        dB=(await api(adm,'save',{'year':Y,'kind':'department','data':{'name':'Département B (pilote)'}}))[1]
        for t in R('track'):await api(adm,'save',{'year':Y,'kind':'track','id':t['id'],'revision':t['revision'],'data':dict(t['data'],department=dA['id'] if t['data']['name']=='Formation de base' else dB['id'])})
        for s_ in R('semester'):await api(adm,'save',{'year':Y,'kind':'semester','id':s_['id'],'revision':s_['revision'],'data':dict(s_['data'],start='2026-09-27')})
        for g in R('group'):await api(adm,'save',{'year':Y,'kind':'group','id':g['id'],'revision':g['revision'],'data':dict(g['data'],size=25)})
        rt=R('roomtype')[0]['id'];await api(adm,'save',{'year':Y,'kind':'room','data':{'name':'Amphi 1','capacity':300,'type':rt}});await api(adm,'save',{'year':Y,'kind':'room','data':{'name':'Salle 12','capacity':300,'type':rt}})
        stt=R('status')[0]['id']
        await api(adm,'save',{'year':Y,'kind':'teacher','data':{'last':'Laouar','first':'Nadhir','status':stt,'load':'Normale','department':dA['id'],'english_level':'B2','english_ok':'Oui'}})
        await api(adm,'save',{'year':Y,'kind':'teacher','data':{'last':'Ben Salah','first':'Élodie','status':stt,'load':'Normale'}})
        await adm.reload();await adm.wait_for_selector('.sidebar')
        # Comptes créés depuis l'interface d'administration.
        await nav(adm,'Paramètres','users');await adm.wait_for_selector('#users-page table')
        accounts={}
        for dept,label in [(dA,'Département A (pilote)'),(dB,'Département B (pilote)')]:
            await adm.click('[data-action="account-new"][data-role="Chef de département"]');await adm.wait_for_selector('#account-form')
            await adm.select_option('#account-form select[name=department]',label=label);full='Chef '+label.split(' (')[0].split(' ')[1]
            await adm.fill('#account-full',f'Karim Chef{full[-1]}');await adm.click('[data-action="account-suggest"]');await adm.wait_for_timeout(300)
            await adm.click('[data-action="account-save"]');accounts[label]=await credentials(adm);await adm.wait_for_timeout(300)
        for name in ['Laouar Nadhir','Ben Salah Élodie']:
            row=adm.locator('#users-page tr',has_text=name);await row.locator('[data-action="account-new"]').click();await adm.wait_for_selector('#account-form');await adm.wait_for_timeout(400)
            await adm.click('[data-action="account-save"]');accounts[name]=await credentials(adm);await adm.wait_for_timeout(300)
        await shot(adm,'01_admin_comptes')
        check('Identifiants générés : n.laouar, e.bensalah',accounts['Laouar Nadhir'][0]=='n.laouar' and accounts['Ben Salah Élodie'][0]=='e.bensalah',accounts)
        check('Mots de passe temporaires uniques de 8 caractères',len({a[1] for a in accounts.values()})==4 and all(re.fullmatch(r'[A-Za-z2-9]{8}',a[1]) for a in accounts.values()))
        check('Lien transmis = adresse https du site',all(a[2]==URL for a in accounts.values()),[a[2] for a in accounts.values()])
        # ---------- TEST A : chef du département A ----------
        ca=await new_page(browser);ident,pw,_=accounts['Département A (pilote)']
        await ca.goto(URL);await ca.fill('input[name=name]',ident);await ca.fill('input[name=password]',pw);await ca.click('#login-form button[type=submit]')
        await ca.wait_for_selector('#change-form');check('A2-3 Chef A : mot de passe temporaire accepté puis changement exigé',await ca.is_visible('#change-form'))
        st,_=await ca.evaluate("async()=>{let r=await fetch('/api/bootstrap');return [r.status,await r.json()]}");check('A3 Aucun accès aux données avant le changement',st==403)
        await ca.fill('input[name=new]','ChefA-Pilote-2026');await ca.fill('input[name=confirm]','ChefA-Pilote-2026');await ca.click('#change-form button[type=submit]');await ca.wait_for_selector('.sidebar')
        h1=await ca.inner_text('.pagehead h1');sub=await ca.inner_text('.pagehead p')
        check('A4 Tableau de bord du bon département',h1.startswith('Tableau de bord — Mon département') and 'Département A' in sub,h1+' / '+sub)
        await shot(ca,'02_chef_tableau_de_bord')
        await nav(ca,'Vœux','campaign');await ca.click('.pagehead [data-action="add"]');await ca.wait_for_selector('#editor')
        today=datetime.date.today()
        await ca.fill('#editor input[name=name]','Vœux semestre 1 — pilote');await ca.fill('#editor input[name=open]',today.isoformat());await ca.fill('#editor input[name=deadline]',(today+datetime.timedelta(days=10)).isoformat())
        await ca.select_option('#editor select[name=status]','Ouverte');await ca.click('#dialog [data-action="save"]');await ca.wait_for_timeout(500)
        st,SA=await api(ca,'bootstrap');camp=[r for r in SA['records'] if r['kind']=='campaign']
        check('A5 Campagne de vœux créée et ouverte par le chef A',len(camp)==1 and camp[0]['data']['status']=='Ouverte' and camp[0]['data']['department']==dA['id'])
        # Campagne du département B par le chef B.
        cb=await new_page(browser);await login(cb,accounts['Département B (pilote)'][0],accounts['Département B (pilote)'][1],'ChefB-Pilote-2026')
        stb,cB=await api(cb,'save',{'year':Y,'kind':'campaign','data':{'name':'Vœux S1 — département B','period':'1','department':dB['id'],'open':today.isoformat(),'deadline':(today+datetime.timedelta(days=10)).isoformat(),'status':'Ouverte'}})
        # ---------- TEST B / C : enseignants ----------
        e1=await new_page(browser);await login(e1,*accounts['Laouar Nadhir'][:2],'Laouar-Pilote-2026')
        e2=await new_page(browser);await login(e2,*accounts['Ben Salah Élodie'][:2],'BenSalah-Pilote-2026')
        navs=await e1.eval_on_selector_all('.nav button','els=>els.map(e=>e.dataset.nav)')
        check('B3 Enseignant : espace simple (6 menus, aucun menu administratif)',navs==['Accueil','Mes vœux','Mes affectations','Mon emploi du temps','Ma charge','Mon profil'],navs)
        async def wish(page,campaign_text,subject_filter,activity_index,english):
            await nav(page,'Mes vœux');await page.click('.pagehead [data-action="wish-new"]');await page.wait_for_selector('#wish-form')
            opts=await page.eval_on_selector_all('#wish-campaign option','els=>els.map(e=>[e.value,e.textContent])')
            await page.select_option('#wish-campaign',next(v for v,t in opts if campaign_text in t));await page.fill('#wish-search',subject_filter);await page.wait_for_timeout(150)
            await page.select_option('#wish-subject',index=1);await page.wait_for_timeout(150)
            boxes=page.locator('input[name=pick]');aid=await boxes.nth(activity_index).get_attribute('value');await boxes.nth(activity_index).check()
            if english:await page.select_option(f'select[name="language-{aid}"]',label='Anglais')
            await page.click('[data-action="wish-submit"]');await page.wait_for_timeout(500);return aid
        a1=await wish(e1,'pilote','','0',False) if False else await wish(e1,'Vœux semestre 1','Biologie',0,True)
        a2A=await wish(e2,'Vœux semestre 1','Biologie',0,False)
        a2B=await wish(e2,'département B','Écologie',0,True)
        await shot(e2,'03_enseignant_mes_voeux')
        st2,S2=await api(e2,'bootstrap');w2=[r for r in S2['records'] if r['kind']=='wish']
        check('B4-5 / C2-3 Vœux avec langue, dans les deux départements',len(w2)==2 and {r['context']['department'] for r in w2}=={dA['id'],dB['id']})
        # ---------- A6-8 : arbitrage et affectation depuis un vœu ----------
        await ca.reload();await ca.wait_for_selector('.sidebar');await nav(ca,'Vœux','processing');await shot(ca,'04_chef_traitement_voeux')
        row=ca.locator('tr',has_text='Ben Salah');await row.locator('[data-action="decide"][data-state="Acceptée"]').first.click()
        await ca.fill('textarea[name=decision_note]','Accepté pour le pilote');await ca.click('[data-action="decide-confirm"]');await ca.wait_for_timeout(600)
        row=ca.locator('tr',has_text='Laouar');await row.locator('[data-action="decide"][data-state="Refusée"]').first.click();await ca.fill('textarea[name=decision_note]','Test de refus');await ca.click('[data-action="decide-confirm"]');await ca.wait_for_timeout(600)
        st,SA=await api(ca,'bootstrap');ws={r['data']['teacher']:r['data']['state'] for r in SA['records'] if r['kind']=='wish'}
        check('A7 Acceptation et refus enregistrés',sorted(ws.values())==['Acceptée','Refusée'],ws)
        await ca.locator('tr',has_text='Ben Salah').locator('[data-action="wish-assign"]').click();await ca.wait_for_selector('#editor')
        groups=await ca.eval_on_selector_all('#editor select[name=group] option','els=>els.map(e=>e.value).filter(Boolean)')
        await ca.select_option('#editor select[name=group]',groups[0]);await ca.select_option('#editor select[name=state]','Validée');await ca.click('#dialog [data-action="save"]');await ca.wait_for_timeout(700)
        st,SA=await api(ca,'bootstrap');asg=[r for r in SA['records'] if r['kind']=='assignment']
        check('A8 Affectation créée depuis le vœu (préremplie)',len(asg)==1 and asg[0]['data']['wish'] and asg[0]['data']['language']==next(l['id'] for l in R('language') if l['data']['code']=='fr'))
        # A9 : affectation manuelle sans vœu (enseignant venant d'un autre rattachement ou sans rattachement).
        await nav(ca,'Affectations','assignment');await ca.click('.pagehead [data-action="add"]');await ca.wait_for_selector('#editor')
        acts=await ca.eval_on_selector_all('#editor select[name=activity] option','els=>els.map(e=>[e.value,e.textContent]).filter(x=>x[0])')
        manual=next(v for v,t in acts if 'Cours' in t and v!=a2A and v!=a1)
        await ca.select_option('#editor select[name=activity]',manual);await ca.wait_for_timeout(200)
        await ca.select_option('#editor select[name=teacher]',label='Laouar Nadhir');await ca.wait_for_timeout(200)
        g=await ca.eval_on_selector_all('#editor select[name=group] option','els=>els.map(e=>e.value).filter(Boolean)');await ca.select_option('#editor select[name=group]',g[0])
        await ca.fill('#editor input[name=hours]','6');await ca.select_option('#editor select[name=language]',label='Anglais');await ca.select_option('#editor select[name=state]','Validée')
        card=await ca.inner_text('#teacher-hint');await shot(ca,'05_chef_affectation_manuelle')
        await ca.click('#dialog [data-action="save"]');await ca.wait_for_timeout(700)
        st,SA=await api(ca,'bootstrap');check('A9 Affectation manuelle sans vœu',len([r for r in SA['records'] if r['kind']=='assignment' and not r['data']['wish']])==1)
        check('Aide à la décision : charge globale et reste affichés',"charge globale ENSF" in card and 'reste' in card,card[:200])
        # Chef B : vœu accepté et affectation dans le département B pour le même enseignant.
        st,SB=await api(cb,'bootstrap');wB=next(r for r in SB['records'] if r['kind']=='wish')
        await api(cb,'save',{'year':Y,'kind':'wish','id':wB['id'],'revision':wB['revision'],'data':dict(wB['data'],state='Acceptée')})
        actB=next(r for r in SB['records'] if r['id']==a2B);secB=next(r for r in SB['records'] if r['kind']=='group' and r['data']['level']==actB['context']['level'] and r['data']['type']=='Section')
        stB,asgB=await api(cb,'save',{'year':Y,'kind':'assignment','data':{'activity':a2B,'teacher':wB['data']['teacher'],'group':secB['id'],'hours':actB['data']['hours'],'language':wB['data']['language'],'state':'Validée','wish':wB['id']}})
        check('C4 Affectation dans le département B pour le même enseignant',stB==200,asgB)
        # A10 : le chef A ne peut rien modifier dans le département B.
        st,e=await api(ca,'save',{'year':Y,'kind':'assignment','id':asgB['id'],'revision':asgB['revision'],'data':dict(asgB['data'],hours=1)})
        st2_,e2_=await api(ca,'save',{'year':Y,'kind':'wish','id':wB['id'],'revision':wB['revision']+1,'data':dict(wB['data'],state='Refusée')})
        prog=next(r for r in SA['records'] if r['id']==a2B);st3,_=await api(ca,'save',{'year':Y,'kind':'activity','id':prog['id'],'revision':prog['revision'],'data':dict(prog['data'],hours=1)})
        check('A10 Chef A : modification du département B refusée (affectation, vœu, programme)',st==400 and st2_==400 and st3==400,[e,e2_])
        # ---------- TEST F : conflit interdépartemental ----------
        rooms={r['data']['name']:r['id'] for r in SA['records'] if r['kind']=='room'}
        await nav(ca,'Emploi du temps','grid');await ca.click('[data-action="add-slot"]');await ca.wait_for_selector('#editor')
        await ca.select_option('#editor select[name=assignment]',asg[0]['id']);await ca.select_option('#editor select[name=room]',rooms['Amphi 1'])
        await ca.select_option('#editor select[name=day]','Lundi');await ca.select_option('#editor select[name=start]','09:30');await ca.fill('#editor input[name=weeks]','1-4');await ca.click('#dialog [data-action="save"]');await ca.wait_for_timeout(600)
        await cb.reload();await cb.wait_for_selector('.sidebar');await nav(cb,'Emploi du temps','grid');await cb.click('[data-action="add-slot"]');await cb.wait_for_selector('#editor')
        await cb.select_option('#editor select[name=assignment]',asgB['id']);await cb.select_option('#editor select[name=room]',rooms['Salle 12'])
        await cb.select_option('#editor select[name=day]','Lundi');await cb.select_option('#editor select[name=start]','09:30');await cb.fill('#editor input[name=weeks]','2');await cb.click('#dialog [data-action="save"]');await cb.wait_for_timeout(600)
        err=await dialog_error(cb);await shot(cb,'06_conflit_interdepartemental')
        check('F Conflit enseignant entre départements bloqué',"Conflit" in err and 'autre département' in err,err)
        await cb.select_option('#editor select[name=start]','13:30');await cb.select_option('#editor select[name=day]','Mardi');await cb.click('#dialog [data-action="save"]');await cb.wait_for_timeout(600)
        # ---------- C5-6 : charge unique et emploi du temps unique ----------
        await e2.reload();await e2.wait_for_selector('.sidebar');await nav(e2,'Mon emploi du temps')
        lessons=await e2.eval_on_selector_all('.lesson','els=>els.map(e=>e.innerText)');await shot(e2,'07_enseignant_emploi_du_temps')
        check('C6 Un seul emploi du temps regroupant les deux départements',len(lessons)==2 and any('Département A' in l for l in lessons) and any('Département B' in l for l in lessons),lessons)
        selects=await e2.eval_on_selector_all('#page select','els=>els.map(e=>e.id)');check('B7 Aucun sélecteur d’enseignant',selects==['myPeriod'],selects)
        await nav(e2,'Ma charge');rows_=await e2.eval_on_selector_all('#page table tbody tr','els=>els.map(e=>e.innerText)')
        check('C5 Charge totale ENSF unique (ventilée A + B)','Département A' in rows_[0] and 'Département B' in rows_[0],rows_[:1])
        await shot(e2,'08_enseignant_ma_charge')
        # ---------- TEST D : confidentialité via l'API ----------
        st,S2=await api(e2,'bootstrap');st,S1=await api(e1,'bootstrap');me2=S2['me'];ids={r['id'] for r in S1['records']}
        other=[r['id'] for r in S2['records'] if r['kind'] in ['wish','assignment','slot']]
        checks=[me2 not in ids,not (set(other)&ids),all(l['teacher']==S1['me'] for l in S1['summary']['loads'])]
        for rid in other+[me2]:checks.append((await api(e1,'history?id='+rid))[0]==400)
        checks.append((await api(e1,'wish-batch',{'year':Y,'campaign':camp[0]['id'],'teacher':me2,'items':[{'activity':a1,'priority':1,'language':R('language')[0]['id']}]}))[0]==400)
        w_other=next(r for r in S2['records'] if r['kind']=='wish');checks.append((await api(e1,'save',{'year':Y,'kind':'wish','id':w_other['id'],'revision':w_other['revision'],'data':dict(w_other['data'],teacher=S1['me'])}))[0]==400)
        exp=await e1.evaluate("async y=>{let r=await fetch('/api/export?year='+y+'&kind=assignment');return (await r.arrayBuffer()).byteLength}",Y)
        for path in ['users','audit?year='+Y,'backup','feedback']:checks.append((await api(e1,path))[0]==400)
        check('D Enseignant n°1 : données de l’enseignant n°2 refusées par l’API ('+str(len(checks))+' tentatives)',all(checks),checks)
        # ---------- TEST E : cinq utilisateurs simultanés ----------
        pages=[adm,ca,cb,e1,e2]
        res=await asyncio.gather(*[api(pg,'bootstrap') for pg in pages for _ in range(3)])
        res2=await asyncio.gather(api(ca,'save',{'year':Y,'kind':'assignment','id':asg[0]['id'],'revision':asg[0]['revision'],'data':dict(asg[0]['data'],note='chef A')}),api(e1,'feedback',{'page':'test','type':'Amélioration','comment':'Essai simultané'}),api(e2,'feedback',{'page':'test','type':'À corriger','comment':'Essai simultané 2'}),api(cb,'bootstrap'),api(adm,'bootstrap'))
        check('E Cinq utilisateurs connectés simultanément sur la même base',all(r[0]==200 for r in res+list(res2)),[r[0] for r in res+list(res2)])
        # ---------- TEST G : taux d'anglais ----------
        await adm.reload();await adm.wait_for_selector('.sidebar');await nav(adm,'Rapports');await adm.select_option('#report','Taux d’anglais');await adm.wait_for_timeout(300)
        rows_=await adm.eval_on_selector_all('#page table tbody tr','els=>els.map(e=>[...e.children].map(c=>c.innerText))');await shot(adm,'09_taux_anglais')
        ensf=rows_[0];depA=next(r for r in rows_ if r[0].startswith('Département A'));depB=next(r for r in rows_ if r[0].startswith('Département B'))
        st,SS=await api(adm,'bootstrap');e=SS['summary']['english']
        check('G Taux d’anglais ENSF / départements calculés depuis les affectations',e['english']>0 and float(depB[4].replace(',','.').replace(' ',''))>0 and ensf[1].startswith('École'),[ensf,depA,depB])
        await adm.select_option('#report','Enseignants en anglais');await adm.wait_for_timeout(300)
        en_rows=await adm.eval_on_selector_all('#page table tbody tr','els=>els.map(e=>e.innerText)');check('G Liste des enseignants enseignant en anglais',any('Laouar' in r for r in en_rows) and any('Ben Salah' in r for r in en_rows),en_rows)
        # Retours pilotes et déconnexion.
        await e1.click('[data-action="feedback"]');await e1.fill('#feedback-form textarea','Remarque de test pilote');await e1.click('[data-action="feedback-send"]');await e1.wait_for_timeout(400)
        await nav(adm,'Paramètres','feedback');await adm.wait_for_selector('#feedback-page table');n=await adm.locator('#feedback-page tbody tr').count()
        check('Retours pilotes transmis à l’administrateur',n>=3,n)
        await e1.click('[data-action="logout"]');await e1.wait_for_selector('#login-form');st,_=await e1.evaluate("async()=>{let r=await fetch('/api/bootstrap');return [r.status,0]}")
        check('Déconnexion effective',st==401)
        errs=[x for pg in pages for x in pg.errors];check('Aucune erreur JavaScript',not errs,errs[:3])
        await browser.close()
    ok=sum(r[1] for r in RESULTS);print(f'\n{ok}/{len(RESULTS)} contrôles de recette réussis');return 0 if ok==len(RESULTS) else 1
sys.exit(asyncio.run(main()))
