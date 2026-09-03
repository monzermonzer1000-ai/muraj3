from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from werkzeug.utils import secure_filename
import sqlite3, os, hashlib

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"muraj3.db")
UPLOAD=os.path.join(BASE,"uploads")
ALLOWED={"pdf"}
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-secret-key")
os.makedirs(UPLOAD,exist_ok=True)

DATABASE_URL=os.environ.get("DATABASE_URL","").strip()

def db():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    c=db()
    if DATABASE_URL:
        for sql in [
            "CREATE TABLE IF NOT EXISTS students(id SERIAL PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS materials(id SERIAL PRIMARY KEY,title TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,filename TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS exams(id SERIAL PRIMARY KEY,title TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,filename TEXT)",
            "CREATE TABLE IF NOT EXISTS questions(id SERIAL PRIMARY KEY,question TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,answer TEXT NOT NULL)"
        ]: c.execute(sql)
    else:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,filename TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,filename TEXT);
        CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY AUTOINCREMENT,question TEXT NOT NULL,subject TEXT NOT NULL,track TEXT NOT NULL,answer TEXT NOT NULL);
        """)
    c.commit(); c.close()
def pw(x): return hashlib.sha256(x.encode()).hexdigest()

def run(c, sql, params=()):
    return c.execute(sql.replace("?", "%s") if DATABASE_URL else sql, params)

init()

subjects={
"علمي":["اللغة العربية","اللغة الإنجليزية","الرياضيات المتخصصة","الفيزياء","الكيمياء","الأحياء"],
"أدبي":["اللغة العربية","اللغة الإنجليزية","الرياضيات الأساسية","التاريخ","الجغرافيا"]
}

@app.route("/health")
def health(): return {"status":"ok"}

@app.route("/")
def home():
    c=db()
    mats=run(c, "SELECT * FROM materials ORDER BY id DESC").fetchall()
    exams=run(c, "SELECT * FROM exams ORDER BY id DESC").fetchall()
    qs=run(c, "SELECT * FROM questions ORDER BY id DESC").fetchall()
    c.close()
    return render_template("index.html",subjects=subjects,materials=mats,exams=exams,questions=qs)

@app.route("/register",methods=["POST"])
def register():
    name=request.form["name"].strip(); email=request.form["email"].strip().lower(); password=request.form["password"]
    if not name or not email or len(password)<4:
        flash("أدخل البيانات بصورة صحيحة.")
        return redirect(url_for("home"))
    c=db()
    try:
        run(c, "INSERT INTO students(name,email,password) VALUES(?,?,?)",(name,email,pw(password))); c.commit()
        session["student"]=email; flash("تم إنشاء حساب الطالب بنجاح.")
    except sqlite3.IntegrityError: flash("البريد الإلكتروني مسجل مسبقًا.")
    c.close(); return redirect(url_for("home"))

@app.route("/login",methods=["POST"])
def login():
    email=request.form["email"].strip().lower(); password=request.form["password"]
    c=db(); row=run(c, "SELECT * FROM students WHERE email=? AND password=?",(email,pw(password))).fetchone(); c.close()
    if row: session["student"]=email; flash("مرحبًا بك.")
    else: flash("البريد أو كلمة المرور غير صحيحة.")
    return redirect(url_for("home"))

@app.route("/logout")
def logout(): session.pop("student",None); return redirect(url_for("home"))

def admin_ok():
    return session.get("admin") is True

@app.route("/admin",methods=["GET","POST"])
def admin():
    if request.method=="POST":
        if request.form.get("action")=="login":
            if request.form.get("password")==os.environ.get("ADMIN_PASSWORD","123456"):
                session["admin"]=True; return redirect(url_for("admin"))
            flash("كلمة مرور المدير غير صحيحة.")
        elif not admin_ok(): flash("سجّل دخول المدير أولاً.")
    if not admin_ok(): return render_template("admin_login.html")
    c=db()
    counts={k:run(c, f"SELECT COUNT(*) n FROM {k}").fetchone()["n"] for k in ["students","materials","exams","questions"]}
    mats=run(c, "SELECT * FROM materials ORDER BY id DESC").fetchall()
    exams=run(c, "SELECT * FROM exams ORDER BY id DESC").fetchall()
    c.close()
    return render_template("admin.html",counts=counts,subjects=subjects,materials=mats,exams=exams)

@app.route("/admin/logout")
def admin_logout(): session.pop("admin",None); return redirect(url_for("home"))

@app.route("/admin/material",methods=["POST"])
def add_material():
    if not admin_ok(): return redirect(url_for("admin"))
    f=request.files.get("file"); title=request.form["title"].strip(); subject=request.form["subject"]; track=request.form["track"]
    if not f or not title or not f.filename.lower().endswith(".pdf"):
        flash("اختر ملف PDF واكتب الاسم."); return redirect(url_for("admin"))
    name=secure_filename(f.filename); f.save(os.path.join(UPLOAD,name))
    c=db(); run(c, "INSERT INTO materials(title,subject,track,filename) VALUES(?,?,?,?)",(title,subject,track,name)); c.commit(); c.close()
    flash("تمت إضافة المذكرة/الملف."); return redirect(url_for("admin"))

@app.route("/admin/exam",methods=["POST"])
def add_exam():
    if not admin_ok(): return redirect(url_for("admin"))
    f=request.files.get("file"); title=request.form["title"].strip(); subject=request.form["subject"]; track=request.form["track"]
    filename=None
    if f and f.filename:
        if not f.filename.lower().endswith(".pdf"): flash("ملف الامتحان يجب أن يكون PDF."); return redirect(url_for("admin"))
        filename=secure_filename(f.filename); f.save(os.path.join(UPLOAD,filename))
    c=db(); run(c, "INSERT INTO exams(title,subject,track,filename) VALUES(?,?,?,?)",(title,subject,track,filename)); c.commit(); c.close()
    flash("تمت إضافة الامتحان."); return redirect(url_for("admin"))

@app.route("/admin/question",methods=["POST"])
def add_question():
    if not admin_ok(): return redirect(url_for("admin"))
    q=request.form["question"].strip(); a=request.form["answer"].strip(); subject=request.form["subject"]; track=request.form["track"]
    if not q or not a: flash("اكتب السؤال والإجابة."); return redirect(url_for("admin"))
    c=db(); run(c, "INSERT INTO questions(question,subject,track,answer) VALUES(?,?,?,?)",(q,subject,track,a)); c.commit(); c.close()
    flash("تمت إضافة السؤال."); return redirect(url_for("admin"))

@app.route("/files/<path:name>")
def files(name): return send_from_directory(UPLOAD,name,as_attachment=False)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)
