"""AZM KYC prototype. NOT production-ready. No real Sumsub connection."""
import os, json, sqlite3, uuid, datetime, pathlib, secrets, functools
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge

BASE=pathlib.Path(__file__).parent
app=Flask(__name__)
if os.environ.get('RENDER') == 'true' and not os.environ.get('FLASK_SECRET_KEY'):
 raise RuntimeError('Set FLASK_SECRET_KEY in Render environment variables')
app.secret_key=os.environ.get('FLASK_SECRET_KEY',secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.config['MAX_CONTENT_LENGTH']=12*1024*1024
DATA_DIR=pathlib.Path(os.environ.get('AZM_DATA_DIR',str(BASE)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB=DATA_DIR/'demo_kyc.sqlite3'; UPLOAD=DATA_DIR/'uploads'
UPLOAD.mkdir(parents=True,exist_ok=True)
# AML points are demonstration values pending written Compliance sign-off.
AML_RULES={'pep':40,'sanctions_potential':60,'sanctions_confirmed':100,'adverse_media':25,'high_risk_country':25,'high_risk_sector':15,'unverified_source':20,'fatca_us':5,'id_expired':25}
QUESTIONS=[
 ('knowledge','Knowledge and experience in FOREX and CFDs',[('Excellent',3),('Good',2),('Beginner',1)]),
 ('goal','Trading goals',[('Hedging',3),('Diversification',2),('Speculation',1)]),
 ('frequency','Monthly trading frequency',[('More than 200',3),('51 to 200',2),('Up to 50',1)]),
 ('employment_score','Employment status',[('Employed',3),('Self-employed',2),('Not employed / other',1)]),
 ('income_source','Source of income',[('Salary',3),('Business income',2),('Savings / investments',1)]),
 ('investment','Expected investment amount (USD)',[('More than 100,000',3),('25,001 to 100,000',2),('Up to 25,000',1)]),
 ('annual_income','Annual income (USD)',[('More than 100,000',3),('25,001 to 100,000',2),('Up to 25,000',1)]),
 ('assets','Assets value (USD)',[('More than 100,000',3),('25,001 to 100,000',2),('Up to 25,000',1)]),
 ('expenses','Annual expenses and obligations (USD)',[('Up to 25,000',3),('25,001 to 100,000',2),('More than 100,000',1)]),
]
STEPS=['personal','suitability','professional','tax','screening','review']
FIELDS={
 'personal':['full_name','residence_country','nationality','birth_country','birth_city','dob','address_country','address_city','address_street','employment','sector','employer','job_title','pep','pep_name','pep_designation','pep_employer','pep_country','id_type','id_country','id_number','id_issue','id_expiry'],
 'professional':['professional_request','prof_1','prof_2','accreditation','financial_employee'],
 'tax':['fatca','us_tin','crs_json','cert_date','declaration'],
 'screening':['sanctions','adverse_media','high_risk_country','high_risk_sector','source_verified','screening_reference','analyst_notes','manager_approval','edd_review','bank_first_deposit'],
}
DOC_FIELDS=['id_front','id_back','proof_address','prof_1_evidence','prof_2_evidence','accreditation_evidence','employment_evidence','source_funds_evidence','second_id']

def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, created TEXT, updated TEXT, data TEXT NOT NULL, files TEXT NOT NULL, status TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, time TEXT, event TEXT, details TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL)')
  cols={r[1] for r in c.execute('PRAGMA table_info(applications)')}
  if 'owner' not in cols:c.execute("ALTER TABLE applications ADD COLUMN owner TEXT DEFAULT 'client'")
  if 'decision' not in cols:c.execute("ALTER TABLE applications ADD COLUMN decision TEXT DEFAULT 'Pending'")
  for username,role in [('client','client'),('analyst','analyst'),('manager','manager')]:
   password=os.environ.get('AZM_'+username.upper()+'_PASSWORD')
   if os.environ.get('RENDER') == 'true' and not password:
    raise RuntimeError('Set AZM_'+username.upper()+'_PASSWORD in Render environment variables')
   password=password or 'Demo-'+username+'-2026!'
   if not c.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
    c.execute('INSERT INTO users VALUES(?,?,?)',(username,generate_password_hash(password),role))

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def audit(c,ident,event,details=''):
 c.execute('INSERT INTO audit(application_id,time,event,details) VALUES(?,?,?,?)',(ident,now(),event,details))
def get(ident):
 with conn() as c:
  r=c.execute('SELECT * FROM applications WHERE id=?',(ident,)).fetchone()
 if not r:abort(404)
 return {'id':r['id'],'created':r['created'],'updated':r['updated'],'data':json.loads(r['data']),'files':json.loads(r['files']),'status':r['status'],'owner':r['owner'],'decision':r['decision']}
def save(a,event):
 a['updated']=now()
 with conn() as c:
  c.execute('UPDATE applications SET updated=?,data=?,files=?,status=?,decision=? WHERE id=?',(a['updated'],json.dumps(a['data']),json.dumps(a['files']),a['status'],a['decision'],a['id']))
  audit(c,a['id'],event)
def calculate(a):
 d=a['data']; f=a['files']; errors=[]; breakdown={};score=0
 for key,label,opts in QUESTIONS:
  val=d.get(key,''); mapping={name:pts for name,pts in opts}
  if val in mapping:breakdown[label]={'answer':val,'points':mapping[val]};score+=mapping[val]
  else:errors.append('Missing suitability response: '+label)
 suitable=score>=18 and not errors
 pro_requested=d.get('professional_request')=='Yes'
 pro_answers=[d.get(x)=='Yes' for x in ('prof_1','prof_2','accreditation','financial_employee')]
 evidence={'prof_1':'prof_1_evidence','prof_2':'prof_2_evidence','accreditation':'accreditation_evidence','financial_employee':'employment_evidence'}
 pro_pending=[key for key in evidence if d.get(key)=='Yes' and evidence[key] not in f]
 pro_eligible=pro_requested and any(pro_answers) and not pro_pending
 classification='Professional Investor — provisional, compliance verification required' if pro_eligible else 'Ordinary Investor'
 if pro_requested and any(pro_answers) and pro_pending:errors.append('Professional investor evidence missing: '+', '.join(pro_pending))
 if pro_requested:
  for key in evidence:
   if d.get(key) not in ('Yes','No'):errors.append('Professional investor eligibility answer missing: '+key)
 if pro_requested and d.get('prof_1')=='Yes' or pro_requested and d.get('prof_2')=='Yes':errors.append('Professional questions 1–2 are not legible in source; Compliance must define eligibility criteria')
 if pro_eligible:message='Based on the information and documents provided, CFDs are likely suitable for you, and you are classified as Professional Investor. I agree to proceed'
 elif suitable:message='Based on the information provided, CFDs are likely suitable for you, and you are classified as an Ordinary Investor. I agree to proceed'
 else:message='Based on the information provided, CFDs are unlikely to be suitable for you, and you are classified as an Ordinary Investor. I agree to proceed'
 flags=[];points=0
 def flag(cond,key,label):
  nonlocal points
  if cond:points+=AML_RULES[key];flags.append({'indicator':label,'points':AML_RULES[key]})
 flag(d.get('pep')=='Yes','pep','Declared PEP or PEP associate')
 flag(d.get('sanctions')=='Potential match','sanctions_potential','Potential sanctions match — manual review')
 flag(d.get('sanctions')=='Confirmed match','sanctions_confirmed','Confirmed sanctions match — block and escalate')
 flag(d.get('adverse_media')=='Yes','adverse_media','Adverse media')
 flag(d.get('high_risk_country')=='Yes','high_risk_country','High-risk country (analyst supplied)')
 flag(d.get('high_risk_sector')=='Yes','high_risk_sector','High-risk employment sector (analyst supplied)')
 flag(d.get('source_verified')=='No','unverified_source','Source of funds unverified')
 flag(d.get('fatca')=='Yes','fatca_us','US FATCA declaration (illustrative review indicator only)')
 try:flag(bool(d.get('id_expiry')) and datetime.date.fromisoformat(d['id_expiry'])<datetime.date.today(),'id_expired','Expired ID')
 except ValueError:errors.append('Invalid ID expiry date')
 risk='High' if points>=60 else 'Medium-High' if points>=35 else 'Medium' if points>=15 else 'Low'
 if d.get('sanctions')=='Confirmed match':risk='High'
 edd=risk in ('Medium-High','High') or d.get('pep')=='Yes'
 for k in ('full_name','residence_country','nationality','birth_country','dob','address_country','address_city','address_street','employment','id_type','id_country','id_number','id_issue','id_expiry'):
  if not d.get(k):errors.append('Missing KYC: '+k)
 if d.get('employment')=='Employed' and not d.get('employer'):errors.append('Employer required')
 if d.get('pep')=='Yes' and not all(d.get(k) for k in ('pep_name','pep_designation','pep_employer','pep_country')):errors.append('PEP details incomplete')
 for k in ('id_front','id_back','proof_address'):
  if k not in f:errors.append('Missing document: '+k)
 if d.get('fatca') not in ('Yes','No'):errors.append('FATCA answer required')
 if d.get('fatca')=='Yes' and not d.get('us_tin'):errors.append('US TIN required')
 if not d.get('cert_date'):errors.append('Tax certification date required')
 if d.get('declaration')!='Yes':errors.append('Declaration acceptance required')
 if not d.get('crs_json'):errors.append('CRS tax jurisdictions required')
 else:
  try:
   rows=json.loads(d['crs_json']);assert isinstance(rows,list) and rows
   for row in rows:
    if not row.get('country') or not (row.get('tin') or row.get('reason')):errors.append('Incomplete CRS jurisdiction')
  except (ValueError,AssertionError,TypeError):errors.append('Invalid CRS jurisdictions')
 if d.get('sanctions') not in ('Clear','Potential match','Confirmed match'):errors.append('Sanctions screening result missing')
 if d.get('adverse_media') not in ('Yes','No'):errors.append('Adverse media screening missing')
 if not d.get('screening_reference'):errors.append('Sumsub screening reference required (demo reference accepted)')
 if edd:
  if 'source_funds_evidence' not in f:errors.append('EDD: source of funds / wealth evidence required')
  if d.get('edd_review')!='Completed':errors.append('EDD compliance review incomplete')
  if d.get('manager_approval')!='Approved':errors.append('Senior management approval required')
 if risk=='High' and d.get('bank_first_deposit')!='Enabled':errors.append('High risk: bank-origin first deposit restriction required')
 if d.get('sanctions') in ('Potential match','Confirmed match'):errors.append('Sanctions screening escalation: do not activate')
 return dict(score=score,max_score=27,breakdown=breakdown,suitable=suitable,classification=classification,message=message,professional_evidence_pending=pro_pending,aml_score=points,aml_risk=risk,flags=flags,edd=edd,errors=errors,activation='Blocked / pending compliance' if errors else 'Eligible for compliance-authorized activation (not activated)',rules=AML_RULES)

def login_required(fn):
 @functools.wraps(fn)
 def wrapper(*args,**kwargs):
  if not session.get('user'):return redirect(url_for('login'))
  return fn(*args,**kwargs)
 return wrapper

def admin_required(fn):
 @login_required
 @functools.wraps(fn)
 def wrapper(*args,**kwargs):
  if session.get('role') not in ('analyst','manager'):abort(403)
  return fn(*args,**kwargs)
 return wrapper

def authorized(a):
 if session.get('role')=='client' and a['owner']!=session.get('user'):abort(403)

@app.before_request
def csrf_guard():
 if request.method=='POST' and request.endpoint!='login':
  if not session.get('user') or request.form.get('_csrf')!=session.get('csrf'):abort(403)

@app.context_processor
def auth_context():return dict(current_user=session.get('user'),role=session.get('role'),csrf=session.get('csrf'))

@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  username=request.form.get('username','').strip();password=request.form.get('password','')
  with conn() as c:r=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
  if r and check_password_hash(r['password_hash'],password):
   session.clear();session.update(user=username,role=r['role'],csrf=secrets.token_hex(24))
   return redirect(url_for('index'))
  flash('Incorrect username or password','error')
 return render_template('login.html')

@app.get('/logout')
def logout():session.clear();return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
 with conn() as c:
  if session['role']=='client':rows=c.execute('SELECT * FROM applications WHERE owner=? ORDER BY created DESC',(session['user'],)).fetchall()
  else:rows=c.execute('SELECT * FROM applications ORDER BY created DESC').fetchall()
 data=[dict(id=r['id'],created=r['created'],status=r['status'],decision=r['decision'],name=json.loads(r['data']).get('full_name','New applicant')) for r in rows]
 if session['role']=='client':return render_template('client_dashboard.html',rows=data)
 return render_template('admin_dashboard.html',rows=data,stats={'total':len(data),'submitted':sum(x['status']=='Submitted' for x in data),'review':sum(x['decision']=='Pending' for x in data),'approved':sum(x['decision']=='Approved' for x in data)})

@app.post('/new')
@login_required
def new():
 if session['role']!='client':abort(403)
 ident=str(uuid.uuid4());t=now()
 with conn() as c:
  c.execute('INSERT INTO applications(id,created,updated,data,files,status,owner,decision) VALUES(?,?,?,?,?,?,?,?)',(ident,t,t,'{}','{}','Draft',session['user'],'Pending'));audit(c,ident,'Application created','client')
 return redirect(url_for('step',ident=ident,name='personal'))

@app.route('/application/<ident>/<name>',methods=['GET','POST'])
@login_required
def step(ident,name):
 if name not in STEPS:abort(404)
 a=get(ident);authorized(a)
 if name=='screening' and session['role']=='client':abort(403)
 if session['role']!='client' and name!='screening':return redirect(url_for('report',ident=ident))
 if request.method=='POST':
  if a['status']=='Submitted' and session['role']=='client':abort(403)
  for k in FIELDS.get(name,[]):
   if k in request.form:a['data'][k]=request.form[k].strip()
  if name=='suitability':
   for k,_,_ in QUESTIONS:a['data'][k]=request.form.get(k,'')
  for k in DOC_FIELDS:
   if session['role']=='client' and k in ('source_funds_evidence','second_id'):pass # Clients can supply evidence if requested.
   file=request.files.get(k)
   if file and file.filename:
    ext=pathlib.Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ('.pdf','.jpg','.jpeg','.png'):flash('Only PDF/JPG/PNG accepted','error');continue
    dest=UPLOAD/(a['id']+'_'+k+ext);file.save(dest);a['files'][k]=dest.name
  if name=='professional':
   requested=a['data'].get('professional_request')
   if requested not in ('Yes','No'):
    flash('Select Yes or No for Professional Investor classification.','error')
    return redirect(url_for('step',ident=ident,name=name))
   if requested=='Yes':
    missing_answers=[k for k in ('prof_1','prof_2','accreditation','financial_employee') if a['data'].get(k) not in ('Yes','No')]
    evidence_map={'prof_1':'prof_1_evidence','prof_2':'prof_2_evidence','accreditation':'accreditation_evidence','financial_employee':'employment_evidence'}
    missing_evidence=[k for k,v in evidence_map.items() if a['data'].get(k)=='Yes' and v not in a['files']]
    if missing_answers or missing_evidence:
     save(a,'Professional page incomplete; missing required answers or evidence')
     flash('Complete all eligibility answers and upload evidence for each Yes answer. Missing: '+', '.join(missing_answers+missing_evidence),'error')
     return redirect(url_for('step',ident=ident,name=name))
  a['status']='In progress' if session['role']=='client' else a['status']
  save(a,'Saved '+name+' by '+session['user'])
  if name=='screening':return redirect(url_for('report',ident=ident))
  if name=='review':return redirect(url_for('report',ident=ident))
  client_steps=[x for x in STEPS if x!='screening']
  idx=client_steps.index(name)
  return redirect(url_for('step',ident=ident,name=client_steps[idx+1]))
 return render_template('step.html',a=a,name=name,steps=[s for s in STEPS if s!='screening'],questions=QUESTIONS,result=calculate(a),doc_fields=DOC_FIELDS)

@app.post('/application/<ident>/submit')
@login_required
def submit(ident):
 a=get(ident);authorized(a)
 if session['role']!='client' or a['status']=='Submitted':abort(403)
 d=a['data'];f=a['files'];missing=[]
 for key in ('full_name','residence_country','nationality','birth_country','birth_city','dob','address_country','address_city','address_street','employment','sector','pep','id_type','id_country','id_number','id_issue','id_expiry','fatca','cert_date'):
  if not d.get(key):missing.append(key)
 if d.get('employment')=='Employed' and not d.get('employer'):missing.append('employer')
 if d.get('pep')=='Yes' and not all(d.get(k) for k in ('pep_name','pep_designation','pep_employer','pep_country')):missing.append('PEP information')
 if d.get('fatca')=='Yes' and not d.get('us_tin'):missing.append('US TIN')
 if d.get('declaration')!='Yes':missing.append('declaration acceptance')
 for k,_,_ in QUESTIONS:
  if not d.get(k):missing.append(k)
 for k in ('id_front','id_back','proof_address'):
  if k not in f:missing.append(k)
 if d.get('professional_request') not in ('Yes','No'):missing.append('professional classification decision')
 if d.get('professional_request')=='Yes':
  for key in ('prof_1','prof_2','accreditation','financial_employee'):
   if not d.get(key):missing.append(key)
  if d.get('prof_1')=='Yes' and 'prof_1_evidence' not in f:missing.append('criterion 1 evidence')
  if d.get('prof_2')=='Yes' and 'prof_2_evidence' not in f:missing.append('criterion 2 evidence')
  if d.get('accreditation')=='Yes' and 'accreditation_evidence' not in f:missing.append('accreditation evidence')
  if d.get('financial_employee')=='Yes' and 'employment_evidence' not in f:missing.append('employment evidence')
 try:
  jurisdictions=json.loads(d.get('crs_json','[]'))
  if not jurisdictions or any(not j.get('country') or not (j.get('tin') or j.get('reason')) for j in jurisdictions):missing.append('CRS jurisdiction and TIN/reason')
 except (ValueError,TypeError):missing.append('CRS jurisdictions')
 if missing:
  flash('Submission blocked. Complete: '+', '.join(missing[:15]),'error')
  return redirect(url_for('step',ident=ident,name='review'))
 a['status']='Submitted';save(a,'Customer submitted questionnaire')
 flash('Questionnaire submitted. Compliance review is pending.','ok')
 return redirect(url_for('report',ident=ident))

@app.post('/application/<ident>/decision')
@admin_required
def decision(ident):
 a=get(ident)
 if session['role']!='manager':abort(403)
 choice=request.form.get('decision')
 if choice not in ('Approved','Rejected','Request more information'):abort(400)
 assessment=calculate(a)
 if choice=='Approved' and (a['status']!='Submitted' or assessment['errors']):
  flash('Approval blocked: outstanding compliance controls must be cleared.','error')
  return redirect(url_for('report',ident=ident))
 a['decision']=choice
 a['status']='Approved' if choice=='Approved' else ('Rejected' if choice=='Rejected' else 'More information requested')
 save(a,'Manager decision: '+choice+' by '+session['user'])
 return redirect(url_for('report',ident=ident))

@app.get('/application/<ident>/report')
@login_required
def report(ident):
 a=get(ident);authorized(a);result=calculate(a)
 with conn() as c:events=[dict(r) for r in c.execute('SELECT time,event,details FROM audit WHERE application_id=? ORDER BY id',(ident,)).fetchall()]
 return render_template('report.html',a=a,result=result,events=events)

@app.get('/application/<ident>/json')
@admin_required
def export(ident):
 a=get(ident);result=calculate(a)
 return jsonify({'application_id':a['id'],'created':a['created'],'status':a['status'],'decision':a['decision'],'customer':a['data'],'documents_received':list(a['files']),'assessment':result})

@app.get('/application/<ident>/document/<key>')
@login_required
def document(ident,key):
 from flask import send_file
 a=get(ident);authorized(a)
 if key not in a['files']:abort(404)
 path=UPLOAD/a['files'][key]
 if not path.is_file():abort(404)
 return send_file(path,as_attachment=True,download_name=path.name.split('_',1)[-1])

@app.errorhandler(RequestEntityTooLarge)
def large(e):return 'File upload too large (12 MB total)',413
@app.get('/healthz')
def healthz():
 return {'status':'ok'},200

init()
if __name__=='__main__':app.run(host='127.0.0.1',port=5000,debug=False)
