"""Contrat des formulaires et validation, commun au serveur et à l'interface."""
def f(key, label, type='text', required=False, **kw):
    return dict(key=key, label=label, type=type, required=required, **kw)
def ref(key, label, kind, required=True):
    return f(key,label,'ref',required,ref=kind)
def choice(key,label,values,required=True):
    return f(key,label,'select',required,options=values)
NAME=f('name','Libellé',required=True)
# Semaine ENSF : dimanche → jeudi. Créneaux par défaut (modifiables dans une nouvelle version des règles).
DAYS=['Dimanche','Lundi','Mardi','Mercredi','Jeudi']
DEFAULT_SLOTS='08:00-09:30, 09:30-11:00, 11:00-12:30, 13:30-15:00, 15:00-16:30'
ENGLISH_LEVELS=['Non renseigné','Débutant','A1','A2','B1','B2','C1','C2']
CAMPAIGN_STATES=['Préparation','Ouverte','Clôturée','Affectations terminées']
WISH_STATES=['En attente','Acceptée','Acceptée partiellement','Refusée','Retirée']
NOTE=f('note','Observations','textarea')
SCHEMA={}
def entity(key,title,module,fields):
    SCHEMA[key]=dict(title=title,module=module,fields=fields)
entity('department','Départements','Structure',[NAME,NOTE])
entity('cycle','Cycles','Structure',[NAME,NOTE])
entity('track','Filières','Structure',[NAME,ref('cycle','Cycle','cycle'),ref('department','Département responsable des matières','department',False),NOTE])
entity('specialty','Spécialités','Structure',[NAME,ref('track','Filière','track'),NOTE])
entity('level','Niveaux','Structure',[NAME,ref('track','Filière','track'),ref('specialty','Spécialité','specialty',False),NOTE])
entity('semester','Semestres','Structure',[NAME,ref('level','Niveau','level'),choice('period','Période de charge',['1','2']),f('start','Premier dimanche des semaines pédagogiques','date'),f('weeks','Nombre de semaines','number',True,min=1,max=52),NOTE])
entity('group','Sections et groupes','Structure',[NAME,ref('level','Niveau','level'),ref('parent','Section / groupe parent','group',False),choice('type','Type',['Section','Groupe','Sous-groupe']),f('size','Effectif (vide si inconnu)','number',False,min=0),NOTE])
entity('language','Langues','Paramètres',[NAME,f('code','Code ISO (en, fr, ar...)',required=True)])
entity('grade','Grades','Paramètres',[NAME])
entity('status','Statuts enseignants','Paramètres',[NAME])
entity('roomtype','Types de salles','Paramètres',[NAME])
entity('uetype','Types d’UE','Paramètres',[NAME])
entity('activitytype','Types d’activités','Paramètres',[NAME,choice('target','Public attendu',['Section','Groupe','Libre']),f('factor','Coefficient équivalent cours','number',False,min=0),NOTE])
entity('ue','Unités d’enseignement','Programmes',[NAME,f('code','Code UE'),ref('semester','Semestre','semester'),ref('type','Type d’UE','uetype'),NOTE])
entity('subject','Matières','Programmes',[NAME,f('code','Code matière'),ref('ue','UE','ue'),ref('department','Département responsable (si différent de celui de la filière)','department',False),f('coefficient','Coefficient','number',False,min=0),f('credits','Crédits','number',False,min=0),f('source_volume','Volume total imprimé (h)','number',False,min=0),f('personal','Travail personnel (h)','number',False,min=0),f('source','Référence / page'),NOTE])
entity('activity','Activités pédagogiques','Programmes',[ref('subject','Matière','subject'),ref('type','Type d’activité','activitytype'),f('hours','Volume semestriel (h)','number',True,min=0.01),choice('category','Bloc',['Réglementaire','Formation complémentaire','PFE','Sortie']),ref('roomtype','Type de salle exigé','roomtype',False),NOTE])
entity('teacher','Enseignants','Enseignants',[f('last','Nom',required=True),f('first','Prénom',required=True),f('code','Matricule'),ref('grade','Grade','grade',False),ref('department','Département administratif (facultatif, sans effet sur les affectations)','department',False),ref('status','Statut','status'),f('function','Fonction / poste supérieur'),choice('load','Type de charge',['Normale','Demi-charge','Personnalisée']),f('target','Cible personnalisée par semestre (Eq. cours)','number',False,min=0),f('decision','N° de décision'),f('decision_date','Date de décision','date'),f('email','Courriel'),choice('english_level','Niveau d’anglais',ENGLISH_LEVELS,False),choice('english_ok','Déclare pouvoir enseigner en anglais',['Non déclaré','Oui','Non'],False),f('english_note','Observation sur l’anglais','textarea'),f('person','Identifiant ENSF unique',auto=True),NOTE])
entity('room','Salles','Structure',[NAME,f('building','Bâtiment'),f('capacity','Capacité','number',True,min=1),ref('type','Type de salle','roomtype'),f('equipment','Équipements'),NOTE])
entity('rule','Règles de charge','Paramètres',[NAME,f('normal','Cible normale semestrielle','number',True,min=0),f('half','Cible demi-charge semestrielle','number',True,min=0),f('annual','Référence annuelle','number',True,min=0),f('weeks','Semaines par défaut','number',True,min=1,max=52),f('duration','Séance standard (h)','number',True,min=0.25,max=8),f('outing','Heures TP par sortie','number',True,min=0),f('source','Base juridique / décision',required=True),f('slots','Créneaux horaires (ex. 08:00-09:30, 09:30-11:00…)'),NOTE])
entity('assignment','Affectations','Affectations',[ref('activity','Activité','activity'),ref('teacher','Enseignant','teacher'),ref('group','Section / groupe','group'),f('hours','Volume affecté (h)','number',True,min=0.01),ref('language','Langue réellement utilisée','language'),choice('state','État',['Brouillon','Validée']),ref('wish','Vœu d’origine (vide = affectation manuelle)','wish',False),NOTE])
entity('unavailable','Indisponibilités','Emploi du temps',[NAME,ref('teacher','Enseignant','teacher',False),ref('room','Salle','room',False),ref('group','Section / groupe','group',False),f('date','Date','date',True),f('start','Début','time',True),f('end','Fin','time',True),NOTE])
entity('slot','Séances récurrentes','Emploi du temps',[ref('assignment','Affectation validée','assignment'),ref('room','Salle','room'),choice('day','Jour',DAYS),f('start','Début','time',True),f('duration','Durée (h)','number',True,min=0.25,max=8),f('weeks','Semaines : toutes, 1-14 ou 1,3,5',required=True),NOTE])
entity('session','Séances datées','Suivi',[ref('assignment','Affectation','assignment'),ref('room','Salle','room'),f('date','Date','date',True),f('start','Début','time',True),f('duration','Durée prévue (h)','number',True,min=0.25,max=8),choice('state','Statut',['Prévue','Réalisée','Partiellement réalisée','Annulée','À reprogrammer','Rattrapée']),f('actual','Heures réalisées','number',True,min=0),ref('replaces','Séance d’origine (rattrapage)','session',False),NOTE])
entity('extra','Sorties et missions','Affectations',[NAME,ref('teacher','Enseignant','teacher'),choice('period','Période',['1','2']),choice('type','Nature',['Sortie pédagogique','CDE','Incubateur','Autre']),f('hours','Heures physiques','number',True,min=0),f('equivalent','Eq. cours explicitement reconnues','number',True,min=0),f('decision','Décision / PV obligatoire',required=True),choice('state','État',['Brouillon','Validée']),NOTE])
entity('campaign','Campagnes de vœux','Vœux',[NAME,choice('period','Semestre concerné (1 = S1, S3, S5… ; 2 = S2, S4…)',['1','2']),ref('department','Département (vide = tous les départements)','department',False),f('open','Date d’ouverture','date',True),f('deadline','Date limite','date',True),choice('status','Statut',CAMPAIGN_STATES),NOTE])
entity('wish','Vœux pédagogiques','Vœux',[ref('campaign','Campagne','campaign'),ref('teacher','Enseignant','teacher'),ref('activity','Matière · activité','activity'),f('priority','Priorité (choix n°)','number',True,min=1,max=20),ref('language','Langue souhaitée','language'),f('note','Observation de l’enseignant','textarea'),choice('state','Décision',WISH_STATES),f('decision_note','Commentaire de décision','textarea'),f('submitted','Date de dépôt',auto=True),f('updated','Dernière modification par l’enseignant',auto=True),f('decision_date','Date de décision',auto=True),f('decided_by','Décision prise par',auto=True)])
ROLES=['Administrateur','Direction / DAP','Chef de département','Enseignant','Consultation']
STAFF=['Administrateur','Direction / DAP']
