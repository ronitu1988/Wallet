import hashlib, hmac, json, secrets, sqlite3, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB = ROOT / 'salon.db'

def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def password(value, salt):
    return hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def init():
    with connect() as d:
        d.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT,phone TEXT UNIQUE,salt TEXT,pw TEXT,role TEXT,business TEXT,qr TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires INTEGER);
        CREATE TABLE IF NOT EXISTS businesses(id TEXT PRIMARY KEY,name TEXT,location TEXT);
        CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,business TEXT REFERENCES businesses(id),customer TEXT REFERENCES users(id),paid INTEGER,bonus INTEGER,kind TEXT,description TEXT,method TEXT,actor TEXT,created INTEGER,request_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,business TEXT,customer TEXT,actor TEXT,amount INTEGER,description TEXT,status TEXT,channel TEXT,code_hash TEXT,code_salt TEXT,expires INTEGER,attempts INTEGER,last_sent INTEGER,created INTEGER);
        CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,customer TEXT,request_id TEXT,channel TEXT,message TEXT,code TEXT,created INTEGER);
        CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor TEXT,action TEXT,target TEXT,created INTEGER);
        """)
        for bid,name,loc in [('a','SLAY ME NAIL','Riverside, California'),('b','Velvet Nail House','Sacramento, California')]:
            d.execute('INSERT OR IGNORE INTO businesses VALUES(?,?,?)',(bid,name,loc))
        for uid,email,name,phone,role,business in [
            ('staff-a','owner@lumiere.test','Alex Morgan','+14085550101','staff','a'),
            ('staff-b','owner@velvet.test','Taylor Lee','+19165550101','staff','b'),
            ('jane','jane@example.test','Jane Davis','+14085550123','customer',None)]:
            if not d.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():
                salt=secrets.token_hex(16)
                d.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)',(uid,email,name,phone,salt,password('DemoPass123!',salt),role,business,'salon:'+secrets.token_urlsafe(18)))
        for bid,paid,bonus in [('a',8000,1000),('b',4000,0)]:
            d.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)',('seed-'+bid,bid,'jane',paid,bonus,'reload','Welcome wallet balance','demo','system',int(time.time()),'seed-'+bid))

def balance(d,b,c):
    r=d.execute('SELECT COALESCE(SUM(paid),0) paid,COALESCE(SUM(bonus),0) bonus FROM ledger WHERE business=? AND customer=?',(b,c)).fetchone()
    return dict(r)|{'total':r['paid']+r['bonus']}

def audit(d,u,action,target):
    d.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid.uuid4().hex,u['id'],action,target,int(time.time())))

class Error(Exception):
    def __init__(self,message,status=400): self.message,self.status=message,status

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,obj):
        data=json.dumps(obj).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith('/api/'):
            return self.api('GET')
        file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(urlparse(self.path).path)
        if not file: return self.respond(404,{'error':'Not found'})
        data=(ROOT/file).read_bytes(); self.send_response(200)
        self.send_header('Content-Type',{'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[file])
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_POST(self): self.api('POST')
    def api(self,method):
        try:
            host=self.headers.get('Host','')
            if host not in ('localhost:8000','127.0.0.1:8000'): raise Error('Localhost only',403)
            if method=='POST':
                origin=self.headers.get('Origin')
                if origin and origin not in ('http://localhost:8000','http://127.0.0.1:8000'): raise Error('Invalid origin',403)
                if not self.headers.get('Content-Type','').startswith('application/json'): raise Error('JSON required',415)
                size=int(self.headers.get('Content-Length','0'))
                if size>16000: raise Error('Request too large',413)
                body=json.loads(self.rfile.read(size) or b'{}')
            else: body={}
            with connect() as d:
                d.execute('BEGIN IMMEDIATE')
                out=self.route(d,method,urlparse(self.path).path,body)
            self.respond(200,out)
        except Error as e: self.respond(e.status,{'error':e.message})
        except (ValueError,KeyError,TypeError): self.respond(400,{'error':'Invalid request'})
        except Exception as e:
            print(type(e).__name__,str(e)); self.respond(500,{'error':'Unexpected local server error'})
    def route(self,d,method,path,b):
        now=int(time.time())
        if path in ('/api/login','/api/signup') and method=='POST':
            if path.endswith('signup'):
                email=str(b['email']).strip().lower(); phone=str(b['phone']).strip(); pw=str(b['password']); name=str(b['name']).strip()
                if '@' not in email or not name or len(pw)<12 or not(phone.startswith('+1') and len(phone)==12 and phone[1:].isdigit()): raise Error('Use a name, email, US phone in +1 format, and password of 12+ characters')
                if d.execute('SELECT 1 FROM users WHERE email=? OR phone=?',(email,phone)).fetchone(): raise Error('Email or phone already registered')
                salt=secrets.token_hex(16)
                d.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,email,name,phone,salt,password(pw,salt),'customer',None,'salon:'+secrets.token_urlsafe(18)))
            u=d.execute('SELECT * FROM users WHERE email=?',(str(b['email']).lower().strip(),)).fetchone()
            if not u or not hmac.compare_digest(u['pw'],password(str(b['password']),u['salt'])): raise Error('Invalid email or password',401)
            token=secrets.token_urlsafe(32); d.execute('INSERT INTO sessions VALUES(?,?,?)',(token,u['id'],now+28800))
            return {'token':token}
        auth=self.headers.get('Authorization','').removeprefix('Bearer ')
        u=d.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?',(auth,now)).fetchone()
        if not u: raise Error('Please sign in',401)
        if path=='/api/logout' and method=='POST':
            d.execute('DELETE FROM sessions WHERE token=?',(auth,)); return {'ok':True}
        if path=='/api/me':
            return {k:u[k] for k in ('id','name','email','phone','role','business','qr')}
        if path=='/api/customer' and method=='GET':
            if u['role']!='customer': raise Error('Customer access only',403)
            wallets=[dict(x)|{'balance':balance(d,x['id'],u['id'])} for x in d.execute('SELECT * FROM businesses')]
            tx=[dict(x) for x in d.execute('SELECT l.*,b.name business_name FROM ledger l JOIN businesses b ON b.id=l.business WHERE customer=? ORDER BY l.created DESC,l.rowid DESC',(u['id'],))]
            pending=[dict(x) for x in d.execute("SELECT r.id,r.amount,r.description,r.business,r.status,r.channel,r.expires,b.name business_name FROM requests r JOIN businesses b ON b.id=r.business WHERE r.customer=? AND r.status='pending' AND r.expires>?",(u['id'],now))]
            messages=[dict(x) for x in d.execute('SELECT * FROM inbox WHERE customer=? ORDER BY created DESC,rowid DESC LIMIT 20',(u['id'],))]
            return {'wallets':wallets,'transactions':tx,'pending':pending,'messages':messages}
        if path=='/api/reject' and method=='POST':
            if u['role']!='customer': raise Error('Forbidden',403)
            d.execute("UPDATE requests SET status='rejected' WHERE id=? AND customer=? AND status='pending'",(b['id'],u['id']))
            audit(d,u,'reject',b['id']); return {'ok':True}
        if u['role']!='staff': raise Error('Staff access only',403)
        biz=u['business']
        if path=='/api/staff' and method=='GET':
            business=dict(d.execute('SELECT * FROM businesses WHERE id=?',(biz,)).fetchone())
            tx=[dict(x) for x in d.execute('SELECT l.*,u.name customer_name FROM ledger l JOIN users u ON u.id=l.customer WHERE l.business=? ORDER BY created DESC,l.rowid DESC LIMIT 100',(biz,))]
            return {'business':business,'transactions':tx}
        if path=='/api/lookup' and method=='POST':
            q=str(b['query']).strip()
            c=d.execute("SELECT * FROM users WHERE role='customer' AND (phone=? OR qr=?)",(q,q)).fetchone()
            if not c: raise Error('Customer not found. Use exact +1 phone or QR token.',404)
            audit(d,u,'lookup',c['id'])
            return {'id':c['id'],'name':c['name'],'phone':c['phone'],'balance':balance(d,biz,c['id'])}
        if path in ('/api/reload','/api/request') and method=='POST':
            cid=b['customer']; c=d.execute("SELECT * FROM users WHERE id=? AND role='customer'",(cid,)).fetchone()
            if not c: raise Error('Customer not found',404)
            amount=b['amount']
            if type(amount)!=int or not 1<=amount<=100000: raise Error('Amount must be 0.01–1,000.00')
            if path.endswith('reload'):
                key=str(b['key'])
                prior=d.execute('SELECT * FROM ledger WHERE request_key=?',(key,)).fetchone()
                if prior:
                    if prior['business']!=biz or prior['customer']!=cid or prior['paid']!=amount: raise Error('Idempotency conflict',409)
                    return {'balance':balance(d,biz,cid),'duplicate':True}
                if b['method'] not in ('cash','card'): raise Error('Select cash or card')
                bonus=1000 if b.get('promotion') is True and amount>=10000 else 0
                d.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,biz,cid,amount,bonus,'reload','In-person reload'+(' · +10 bonus' if bonus else ''),b['method'],u['id'],now,key))
                total=balance(d,biz,cid)['total']
                d.execute('INSERT INTO inbox VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,cid,None,'receipt',f'Reload complete: {(amount+bonus)/100:.2f} added. Balance {total/100:.2f}.',None,now))
                audit(d,u,'reload',key); return {'balance':balance(d,biz,cid)}
            if amount>balance(d,biz,cid)['total']: raise Error('Insufficient wallet funds')
            desc=str(b['description']).strip()
            if not 1<=len(desc)<=160: raise Error('Enter service description (1–160 characters)')
            d.execute("UPDATE requests SET status='expired' WHERE status='pending' AND expires<=?",(now,))
            if d.execute("SELECT 1 FROM requests WHERE business=? AND customer=? AND status='pending'",(biz,cid)).fetchone(): raise Error('A pending request already exists; cancel it or wait for expiry',409)
            rid=uuid.uuid4().hex; code=f'{secrets.randbelow(1000000):06d}'; salt=secrets.token_hex(16)
            digest=hashlib.sha256((salt+code).encode()).hexdigest()
            d.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,biz,cid,u['id'],amount,desc,'pending','app',digest,salt,now+180,0,now,now))
            d.execute('INSERT INTO inbox VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,cid,rid,'app',f'Authorize {amount/100:.2f} for {desc}',code,now))
            audit(d,u,'request',rid); return {'id':rid,'expires':now+180,'status':'pending'}
        if path in ('/api/verify','/api/sms','/api/cancel') and method=='POST':
            r=d.execute('SELECT * FROM requests WHERE id=? AND business=?',(b['id'],biz)).fetchone()
            if not r: raise Error('Request not found',404)
            if r['status']=='completed' and path.endswith('verify'): return {'completed':True,'duplicate':True}
            if r['status']!='pending' or r['expires']<=now: raise Error('Request expired or no longer pending')
            if path.endswith('cancel'):
                d.execute("UPDATE requests SET status='cancelled' WHERE id=?",(r['id'],)); audit(d,u,'cancel',r['id']); return {'ok':True}
            if path.endswith('sms'):
                if now-r['last_sent']<30: raise Error('Wait 30 seconds between sends')
                code=f'{secrets.randbelow(1000000):06d}'; salt=secrets.token_hex(16)
                d.execute("UPDATE requests SET channel='sms',code_hash=?,code_salt=?,last_sent=? WHERE id=?",(hashlib.sha256((salt+code).encode()).hexdigest(),salt,now,r['id']))
                d.execute('INSERT INTO inbox VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,r['customer'],r['id'],'sms',f'SIMULATED SMS: authorize {r["amount"]/100:.2f} for {r["description"]}',code,now))
                audit(d,u,'sms',r['id']); return {'ok':True}
            valid=hmac.compare_digest(r['code_hash'],hashlib.sha256((r['code_salt']+str(b.get('code',''))).encode()).hexdigest())
            if not valid:
                attempts=r['attempts']+1
                d.execute('UPDATE requests SET attempts=?,status=? WHERE id=?',(attempts,'locked' if attempts>=5 else 'pending',r['id']))
                audit(d,u,'invalid_code',r['id'])
                return {'error':'Incorrect code'+(' — request locked' if attempts>=5 else f' — {5-attempts} attempts remaining')}
            bal=balance(d,biz,r['customer'])
            if bal['total']<r['amount']: raise Error('Insufficient funds')
            bonus=min(bal['bonus'],r['amount']); paid=r['amount']-bonus
            d.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,biz,r['customer'],-paid,-bonus,'service',r['description'],'wallet',u['id'],now,'deduct-'+r['id']))
            d.execute("UPDATE requests SET status='completed' WHERE id=?",(r['id'],))
            d.execute('INSERT INTO inbox VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,r['customer'],None,'receipt',f'Service payment complete: {r["amount"]/100:.2f} for {r["description"]}.',None,now))
            audit(d,u,'deduct',r['id']); return {'completed':True,'balance':balance(d,biz,r['customer'])}
        raise Error('Not found',404)

if __name__=='__main__':
    init()
    print('LOCAL DEVELOPMENT ONLY — http://localhost:8000')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
