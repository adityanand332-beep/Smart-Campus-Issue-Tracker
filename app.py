import os, sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-before-deployment")
DB = os.path.join(os.path.dirname(__file__), "campus_issues.db")
CATEGORIES = ["Electrical", "Network/Wi-Fi", "Plumbing", "Cleanliness", "Furniture", "Safety", "Other"]
STATUSES = ["Submitted", "Acknowledged", "In Progress", "Resolved", "Rejected"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop("db", None)
    if conn: conn.close()

def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, location TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, reporter_id INTEGER NOT NULL REFERENCES users(id), assigned_to TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS issue_updates(id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id), old_status TEXT, new_status TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL);
    """)
    if not c.execute("SELECT id FROM users WHERE email='admin@campus.local'").fetchone():
        c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                  ("Campus Admin","admin@campus.local",generate_password_hash("Admin@12345"),"admin",datetime.now().isoformat(timespec="seconds")))
    c.commit(); c.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if session.get("role") != "admin": abort(403)
        return fn(*a, **kw)
    return wrapped

@app.context_processor
def globals_for_templates():
    return dict(current_user=session, categories=CATEGORIES, statuses=STATUSES, priorities=PRIORITIES)

@app.route("/")
def home():
    return redirect(url_for("dashboard")) if session.get("user_id") else render_template("home.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        if not name or not email or len(password)<8:
            flash("Name/email required; password must be at least 8 characters.", "danger")
        else:
            try:
                get_db().execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (name,email,generate_password_hash(password),"student",datetime.now().isoformat(timespec="seconds")))
                get_db().commit(); flash("Account created. Please log in.", "success"); return redirect(url_for("login"))
            except sqlite3.IntegrityError: flash("That email is already registered.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=get_db().execute("SELECT * FROM users WHERE email=?", (request.form.get("email","").strip().lower(),)).fetchone()
        if u and check_password_hash(u["password_hash"],request.form.get("password","")):
            session.clear(); session.update(user_id=u["id"],name=u["name"],role=u["role"]); return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    d=get_db()
    counts={s:d.execute("SELECT COUNT(*) FROM issues WHERE status=?",(s,)).fetchone()[0] for s in STATUSES}
    total=d.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
    mine=d.execute("SELECT COUNT(*) FROM issues WHERE reporter_id=?",(session["user_id"],)).fetchone()[0]
    recent=d.execute("SELECT i.*,u.name reporter FROM issues i JOIN users u ON u.id=i.reporter_id ORDER BY i.created_at DESC LIMIT 8").fetchall()
    return render_template("dashboard.html", counts=counts,total=total,mine=mine,issues=recent)

@app.route("/issues")
@login_required
def issue_list():
    status=request.args.get("status",""); category=request.args.get("category",""); q=request.args.get("q","").strip()
    sql="SELECT i.*,u.name reporter FROM issues i JOIN users u ON u.id=i.reporter_id WHERE 1=1"; args=[]
    if status in STATUSES: sql+=" AND i.status=?"; args.append(status)
    if category in CATEGORIES: sql+=" AND i.category=?"; args.append(category)
    if q:
        sql+=" AND (i.title LIKE ? OR i.location LIKE ? OR i.description LIKE ?)"; args += [f"%{q}%"]*3
    sql+=" ORDER BY CASE i.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, i.created_at DESC"
    rows=get_db().execute(sql,args).fetchall()
    return render_template("issues.html",issues=rows,q=q,selected_status=status,selected_category=category)

@app.route("/issues/new", methods=["GET","POST"])
@login_required
def new_issue():
    if request.method=="POST":
        title=request.form.get("title","").strip(); desc=request.form.get("description","").strip()
        cat=request.form.get("category",""); loc=request.form.get("location","").strip(); pri=request.form.get("priority","Medium")
        if not title or not desc or not loc or cat not in CATEGORIES or pri not in PRIORITIES:
            flash("Please complete all fields.", "danger")
        else:
            now=datetime.now().isoformat(timespec="seconds")
            cur=get_db().execute("INSERT INTO issues(title,description,category,location,priority,status,reporter_id,created_at,updated_at) VALUES(?,?,?,?,?,'Submitted',?,?,?)",
                                 (title,desc,cat,loc,pri,session["user_id"],now,now))
            iid=cur.lastrowid
            get_db().execute("INSERT INTO issue_updates(issue_id,user_id,old_status,new_status,note,created_at) VALUES(?,?,NULL,'Submitted','Issue reported',?)",(iid,session["user_id"],now))
            get_db().commit(); flash(f"Issue #{iid} submitted.", "success"); return redirect(url_for("detail",iid=iid))
    return render_template("new_issue.html")

@app.route("/issues/<int:iid>")
@login_required
def detail(iid):
    d=get_db()
    issue=d.execute("SELECT i.*,u.name reporter FROM issues i JOIN users u ON u.id=i.reporter_id WHERE i.id=?",(iid,)).fetchone()
    if not issue: abort(404)
    updates=d.execute("SELECT x.*,u.name updater FROM issue_updates x JOIN users u ON u.id=x.user_id WHERE x.issue_id=? ORDER BY x.created_at DESC",(iid,)).fetchall()
    return render_template("detail.html",issue=issue,updates=updates)

@app.route("/issues/<int:iid>/update", methods=["POST"])
@login_required
@admin_required
def update(iid):
    d=get_db(); old=d.execute("SELECT * FROM issues WHERE id=?",(iid,)).fetchone()
    if not old: abort(404)
    status=request.form.get("status"); pri=request.form.get("priority"); ass=request.form.get("assigned_to","").strip(); note=request.form.get("note","").strip()
    if status not in STATUSES or pri not in PRIORITIES:
        flash("Invalid status or priority.", "danger"); return redirect(url_for("detail",iid=iid))
    now=datetime.now().isoformat(timespec="seconds")
    d.execute("UPDATE issues SET status=?,priority=?,assigned_to=?,updated_at=? WHERE id=?",(status,pri,ass,now,iid))
    if status!=old["status"] or note:
        d.execute("INSERT INTO issue_updates(issue_id,user_id,old_status,new_status,note,created_at) VALUES(?,?,?,?,?,?)",(iid,session["user_id"],old["status"],status,note,now))
    d.commit(); flash("Issue updated successfully.", "success"); return redirect(url_for("detail",iid=iid))

@app.route("/my-issues")
@login_required
def my_issues():
    rows=get_db().execute("SELECT * FROM issues WHERE reporter_id=? ORDER BY created_at DESC",(session["user_id"],)).fetchall()
    return render_template("my_issues.html",issues=rows)

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="Only administrators can update issues."),403
@app.errorhandler(404)
def missing(e): return render_template("error.html",code=404,message="That page or issue was not found."),404

init_db()
if __name__=="__main__": app.run(debug=True)
