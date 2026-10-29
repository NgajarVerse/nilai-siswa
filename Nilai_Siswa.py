from flask import Flask, request, redirect, url_for, render_template_string, Response
import sqlite3
import csv
import io
from datetime import date

app = Flask(__name__)
DB = "nilaisiswa_v2.db"

KELAS = ["X IPA", "XI IPA", "XII IPA"]
MAPEL = ["Pendidikan Pancasila", "Kimia"]
STATUS_ABSEN = ["Hadir", "Sakit dengan Surat", "Izin Resmi", "Alfa"]
BOBOT = {
    "kehadiran": 10,
    "keaktifan": 20,
    "tugas": 10,
    "uh1": 15,
    "uh2": 15,
    "uts": 15,
    "uas": 15,
}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS siswa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nis TEXT NOT NULL DEFAULT '',
            nama TEXT NOT NULL,
            kelas TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pertemuan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kelas TEXT NOT NULL,
            mapel TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            UNIQUE(kelas, mapel, tanggal)
        );
        CREATE TABLE IF NOT EXISTS absensi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pertemuan_id INTEGER NOT NULL,
            siswa_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Hadir',
            UNIQUE(pertemuan_id, siswa_id),
            FOREIGN KEY(pertemuan_id) REFERENCES pertemuan(id) ON DELETE CASCADE,
            FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS keaktifan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pertemuan_id INTEGER NOT NULL,
            siswa_id INTEGER NOT NULL,
            skor INTEGER,
            UNIQUE(pertemuan_id, siswa_id),
            FOREIGN KEY(pertemuan_id) REFERENCES pertemuan(id) ON DELETE CASCADE,
            FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS nilai (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            siswa_id INTEGER NOT NULL,
            kelas TEXT NOT NULL,
            mapel TEXT NOT NULL,
            tugas REAL,
            uh1 REAL,
            uh2 REAL,
            uts REAL,
            uas REAL,
            UNIQUE(siswa_id, kelas, mapel),
            FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
        );
        """)

def angka(nilai):
    try:
        if nilai is None or str(nilai).strip() == "":
            return None
        n = float(nilai)
        return max(0, min(100, n))
    except (ValueError, TypeError):
        return None

def nilai_kehadiran(con, siswa_id, kelas, mapel):
    pertemuan = con.execute(
        "SELECT id FROM pertemuan WHERE kelas=? AND mapel=?", (kelas, mapel)
    ).fetchall()
    total = len(pertemuan)
    if total == 0:
        return 0.0
    alfa = con.execute("""
        SELECT COUNT(*) AS n FROM absensi a
        JOIN pertemuan p ON p.id=a.pertemuan_id
        WHERE a.siswa_id=? AND p.kelas=? AND p.mapel=? AND a.status='Alfa'
    """, (siswa_id, kelas, mapel)).fetchone()["n"]
    return round((total - alfa) / total * 100, 2)

def nilai_keaktifan(con, siswa_id, kelas, mapel):
    row = con.execute("""
        SELECT AVG(k.skor) AS rata FROM keaktifan k
        JOIN pertemuan p ON p.id=k.pertemuan_id
        WHERE k.siswa_id=? AND p.kelas=? AND p.mapel=? AND k.skor IS NOT NULL
    """, (siswa_id, kelas, mapel)).fetchone()
    if row["rata"] is None:
        return 0.0
    return round(row["rata"] / 4 * 100, 2)

def predikat(n):
    if n >= 90: return "A"
    if n >= 80: return "B"
    if n >= 75: return "C"
    return "D"

def rekap_siswa(con, siswa, kelas, mapel):
    kh = nilai_kehadiran(con, siswa["id"], kelas, mapel)
    ka = nilai_keaktifan(con, siswa["id"], kelas, mapel)
    row = con.execute(
        "SELECT * FROM nilai WHERE siswa_id=? AND kelas=? AND mapel=?",
        (siswa["id"], kelas, mapel)
    ).fetchone()
    komponen = {
        "Kehadiran": kh, "Keaktifan": ka,
        "Tugas": row["tugas"] if row and row["tugas"] is not None else 0,
        "UH 1": row["uh1"] if row and row["uh1"] is not None else 0,
        "UH 2": row["uh2"] if row and row["uh2"] is not None else 0,
        "UTS": row["uts"] if row and row["uts"] is not None else 0,
        "UAS": row["uas"] if row and row["uas"] is not None else 0,
    }
    akhir = (
        kh * .10 + ka * .20 + komponen["Tugas"] * .10
        + komponen["UH 1"] * .15 + komponen["UH 2"] * .15
        + komponen["UTS"] * .15 + komponen["UAS"] * .15
    )
    return {"kh": kh, "ka": ka, "nilai": row, "komponen": komponen,
            "akhir": round(akhir, 2), "predikat": predikat(akhir),
            "ketuntasan": "Tuntas" if akhir >= 75 else "Belum tuntas"}

BASE = """
<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nilai Siswa</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f3f5f9;color:#202938}
header{background:#243b63;color:white;padding:16px}
header h1{margin:0;font-size:23px} nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
nav a{color:#fff;background:#385784;padding:9px 11px;border-radius:7px;text-decoration:none;font-size:14px}
main{padding:16px;max-width:1200px;margin:auto}.card{background:white;padding:16px;border-radius:10px;margin-bottom:15px;box-shadow:0 1px 5px #0001}
h2{margin-top:0;font-size:20px}label{display:block;font-weight:bold;margin:10px 0 5px}
input,select,button{padding:10px;border:1px solid #cbd2dc;border-radius:6px;font-size:15px;max-width:100%;box-sizing:border-box}
button,.btn{background:#2457a7;color:white;border:0;padding:10px 13px;border-radius:6px;text-decoration:none;display:inline-block;cursor:pointer}
.danger{background:#a62c37}.muted{color:#64748b;font-size:13px}
form.inline{display:inline} .row{display:flex;flex-wrap:wrap;gap:12px;align-items:end}.row>div{flex:1;min-width:145px}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #dbe1e8;padding:8px;text-align:left;white-space:nowrap}th{background:#eaf0f8}
input[type=number]{width:95px} .msg{background:#e5f7e9;padding:10px;border-radius:6px}
@media print{header,nav,.noprint,button,.btn{display:none!important}body{background:white}.card{box-shadow:none;padding:0}main{max-width:none;padding:0}}
</style></head><body><header><h1>Nilai Siswa</h1><div>Aplikasi daftar siswa, absensi, keaktifan, dan rekap nilai</div>
<nav><a href="/">Beranda</a><a href="/siswa">Daftar Siswa</a><a href="/absen">Daftar Hadir</a><a href="/aktif">Daftar Keaktifan</a><a href="/nilai">Daftar Nilai</a><a href="/rekap">Rekap Nilai</a></nav></header>
<main>{% if pesan %}<p class="msg">{{pesan}}</p>{% endif %}{{ isi|safe }}</main></body></html>
"""

def page(isi, pesan=""):
    return render_template_string(BASE, isi=isi, pesan=pesan)

def filter_form(action, kelas, mapel, tanggal=None, with_date=False):
    s = f'<form method="get" action="{action}" class="card noprint"><div class="row"><div><label>Kelas</label><select name="kelas">'
    for k in KELAS:
        s += f'<option {"selected" if k==kelas else ""}>{k}</option>'
    s += '</select></div><div><label>Mata pelajaran</label><select name="mapel">'
    for m in MAPEL:
        s += f'<option {"selected" if m==mapel else ""}>{m}</option>'
    s += '</select></div>'
    if with_date:
        s += f'<div><label>Tanggal pertemuan</label><input type="date" name="tanggal" value="{tanggal or date.today().isoformat()}" required></div>'
    s += '<div><button type="submit">Tampilkan</button></div></div></form>'
    return s

@app.route("/")
def home():
    with db() as con:
        n_siswa = con.execute("SELECT COUNT(*) n FROM siswa").fetchone()["n"]
        n_pertemuan = con.execute("SELECT COUNT(*) n FROM pertemuan").fetchone()["n"]
    isi = f"""
    <section class="card"><h2>Selamat datang!</h2>
    <p>Isi data siswa satu kali. Setelah itu, nama siswa akan muncul otomatis pada daftar hadir, keaktifan, daftar nilai, dan rekap.</p>
    <div class="row"><div class="card"><b>{n_siswa}</b><br>Data siswa</div><div class="card"><b>{n_pertemuan}</b><br>Pertemuan tercatat</div></div>
    <p><b>Bobot nilai:</b> Kehadiran 10%, Keaktifan 20%, Tugas 10%, UH 1 15%, UH 2 15%, UTS 15%, UAS 15%.</p>
    <p><b>KKM:</b> 75. Sakit dengan surat dan izin resmi tidak mengurangi nilai kehadiran; hanya status Alfa yang mengurangi.</p></section>"""
    return page(isi)

@app.route("/siswa", methods=["GET", "POST"])
def siswa():
    pesan = ""
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        nis = request.form.get("nis", "").strip()
        kelas = request.form.get("kelas", "")
        if nama and kelas in KELAS:
            with db() as con:
                con.execute("INSERT INTO siswa(nis,nama,kelas) VALUES(?,?,?)", (nis,nama,kelas))
            return redirect(url_for("siswa", pesan="Siswa berhasil ditambahkan"))
        pesan = "Nama dan kelas wajib diisi."
    with db() as con:
        daftar = con.execute("SELECT * FROM siswa ORDER BY kelas,nama").fetchall()
    isi = """
    <section class="card"><h2>Tambah siswa</h2><form method="post"><div class="row">
    <div><label>NIS (opsional)</label><input name="nis"></div><div><label>Nama siswa</label><input name="nama" required></div>
    <div><label>Kelas</label><select name="kelas">{% for k in kelas %}<option>{{k}}</option>{% endfor %}</select></div>
    <div><button>Tambah siswa</button></div></div></form></section>
    <section class="card"><h2>Daftar siswa</h2><div class="tablewrap"><table><tr><th>No.</th><th>NIS</th><th>Nama</th><th>Kelas</th><th class="noprint">Aksi</th></tr>
    {% for s in daftar %}<tr><td>{{loop.index}}</td><td>{{s.nis}}</td><td>{{s.nama}}</td><td>{{s.kelas}}</td><td class="noprint"><form method="post" action="/siswa/hapus/{{s.id}}" onsubmit="return confirm('Hapus siswa ini beserta datanya?')" class="inline"><button class="danger">Hapus</button></form></td></tr>{% else %}<tr><td colspan="5">Belum ada siswa.</td></tr>{% endfor %}
    </table></div></section>"""
    result = render_template_string(isi, daftar=daftar, kelas=KELAS)
    if request.args.get("pesan"): pesan = request.args["pesan"]
    return page(result, pesan)

@app.route("/siswa/hapus/<int:sid>", methods=["POST"])
def hapus_siswa(sid):
    with db() as con:
        con.execute("DELETE FROM siswa WHERE id=?", (sid,))
    return redirect(url_for("siswa", pesan="Data siswa dihapus."))

def get_filters():
    kelas = request.values.get("kelas", KELAS[0])
    mapel = request.values.get("mapel", MAPEL[0])
    if kelas not in KELAS: kelas = KELAS[0]
    if mapel not in MAPEL: mapel = MAPEL[0]
    return kelas, mapel

@app.route("/absen", methods=["GET", "POST"])
def absen():
    kelas, mapel = get_filters()
    tanggal = request.values.get("tanggal", date.today().isoformat())
    pesan = request.args.get("pesan", "")
    with db() as con:
        if request.method == "POST":
            con.execute("INSERT OR IGNORE INTO pertemuan(kelas,mapel,tanggal) VALUES(?,?,?)", (kelas,mapel,tanggal))
            pid = con.execute("SELECT id FROM pertemuan WHERE kelas=? AND mapel=? AND tanggal=?", (kelas,mapel,tanggal)).fetchone()["id"]
            students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama", (kelas,)).fetchall()
            for st in students:
                status = request.form.get(f"status_{st['id']}", "Hadir")
                if status not in STATUS_ABSEN: status = "Hadir"
                con.execute("""INSERT INTO absensi(pertemuan_id,siswa_id,status) VALUES(?,?,?)
                ON CONFLICT(pertemuan_id,siswa_id) DO UPDATE SET status=excluded.status""", (pid,st["id"],status))
            # Setelah menyimpan, kembali ke tanggal hari ini. Tampilkan tanggal yang benar-benar disimpan.
            return redirect(url_for("absen", kelas=kelas, mapel=mapel,
                                    tanggal=date.today().isoformat(),
                                    pesan=f"Absensi tanggal {tanggal} tersimpan untuk {kelas} — {mapel}."))
        students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama", (kelas,)).fetchall()
        existing = con.execute("SELECT id FROM pertemuan WHERE kelas=? AND mapel=? AND tanggal=?", (kelas,mapel,tanggal)).fetchone()
        marks = {}
        if existing:
            for a in con.execute("SELECT siswa_id,status FROM absensi WHERE pertemuan_id=?", (existing["id"],)):
                marks[a["siswa_id"]] = a["status"]
        meetings = con.execute("SELECT DISTINCT tanggal FROM pertemuan WHERE kelas=? AND mapel=? ORDER BY tanggal", (kelas,mapel)).fetchall()
        summary = con.execute("""
            SELECT s.id,s.nama,COUNT(CASE WHEN a.status='Alfa' THEN 1 END) alfa
            FROM siswa s LEFT JOIN absensi a ON a.siswa_id=s.id
            LEFT JOIN pertemuan p ON p.id=a.pertemuan_id AND p.kelas=? AND p.mapel=?
            WHERE s.kelas=? GROUP BY s.id ORDER BY s.nama
        """, (kelas,mapel,kelas)).fetchall()
        total = len(meetings)
        rows = []
        for st in students:
            alfa = con.execute("""SELECT COUNT(*) n FROM absensi a JOIN pertemuan p ON p.id=a.pertemuan_id
                WHERE a.siswa_id=? AND p.kelas=? AND p.mapel=? AND a.status='Alfa'""", (st["id"],kelas,mapel)).fetchone()["n"]
            score = round((total-alfa)/total*100,2) if total else 0
            rows.append((st, alfa, score))
    isi = filter_form("/absen",kelas,mapel,tanggal,True) + f"""
    <section class="card"><h2>Daftar hadir</h2><p>Jumlah pertemuan terlaksana untuk {kelas} — {mapel}: <b>{total}</b>. Setiap tanggal hanya dihitung satu kali.</p>
    <form method="post"><input type="hidden" name="kelas" value="{kelas}"><input type="hidden" name="mapel" value="{mapel}"><input type="hidden" name="tanggal" value="{tanggal}">
    <div class="tablewrap"><table><tr><th>No.</th><th>Nama siswa</th><th>Status hadir</th></tr>"""
    if students:
        for i,st in enumerate(students,1):
            status = marks.get(st["id"], "Hadir")
            isi += f'<tr><td>{i}</td><td>{st["nama"]}</td><td><select name="status_{st["id"]}">'
            for opt in STATUS_ABSEN:
                isi += f'<option {"selected" if status==opt else ""}>{opt}</option>'
            isi += '</select></td></tr>'
    else:
        isi += '<tr><td colspan="3">Belum ada siswa di kelas ini. Tambahkan melalui menu Daftar Siswa.</td></tr>'
    isi += '</table></div><p><button>Simpan absensi</button></p></form></section>'
    isi += f"""<section class="card"><h2>Ringkasan nilai kehadiran</h2><p>Rumus: (pertemuan terlaksana − jumlah Alfa) ÷ pertemuan terlaksana × 100.</p><div class="tablewrap"><table><tr><th>Nama</th><th>Jumlah Alfa</th><th>Pertemuan</th><th>Nilai kehadiran</th></tr>"""
    for st,alfa,score in rows:
        isi += f"<tr><td>{st['nama']}</td><td>{alfa}</td><td>{total}</td><td>{score:g}</td></tr>"
    isi += '</table></div>'
    tanggal_tercatat = ", ".join(r["tanggal"] for r in meetings) if meetings else "Belum ada"
    isi += f'<p><b>Tanggal pertemuan yang tercatat:</b> {tanggal_tercatat}</p></section>'
    return page(isi,pesan)

@app.route("/aktif", methods=["GET", "POST"])
def aktif():
    kelas,mapel = get_filters()
    tanggal = request.values.get("tanggal", date.today().isoformat())
    pesan = ""
    with db() as con:
        if request.method == "POST":
            con.execute("INSERT OR IGNORE INTO pertemuan(kelas,mapel,tanggal) VALUES(?,?,?)", (kelas,mapel,tanggal))
            pid = con.execute("SELECT id FROM pertemuan WHERE kelas=? AND mapel=? AND tanggal=?", (kelas,mapel,tanggal)).fetchone()["id"]
            students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama",(kelas,)).fetchall()
            for st in students:
                val = request.form.get(f"skor_{st['id']}", "")
                try:
                    skor = int(val) if val.strip() else None
                    if skor is not None and skor not in [1,2,3,4]: skor = None
                except ValueError: skor = None
                con.execute("""INSERT INTO keaktifan(pertemuan_id,siswa_id,skor) VALUES(?,?,?)
                ON CONFLICT(pertemuan_id,siswa_id) DO UPDATE SET skor=excluded.skor""",(pid,st["id"],skor))
            pesan = "Skor keaktifan tersimpan. Nilai dan rekap diperbarui otomatis."
        students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama",(kelas,)).fetchall()
        meeting = con.execute("SELECT id FROM pertemuan WHERE kelas=? AND mapel=? AND tanggal=?",(kelas,mapel,tanggal)).fetchone()
        marks = {}
        if meeting:
            for r in con.execute("SELECT siswa_id,skor FROM keaktifan WHERE pertemuan_id=?",(meeting["id"],)):
                marks[r["siswa_id"]] = r["skor"]
        rows = []
        for st in students:
            avg = con.execute("""SELECT AVG(k.skor) rata,COUNT(k.skor) jumlah FROM keaktifan k
                JOIN pertemuan p ON p.id=k.pertemuan_id
                WHERE k.siswa_id=? AND p.kelas=? AND p.mapel=?""",(st["id"],kelas,mapel)).fetchone()
            raw = round(avg["rata"],2) if avg["rata"] is not None else 0
            score = round(raw/4*100,2)
            rows.append((st,raw,score,avg["jumlah"]))
    isi = filter_form("/aktif",kelas,mapel,tanggal,True) + f"""
    <section class="card"><h2>Daftar keaktifan</h2><p>Isi skor 1–4 untuk siswa pada pertemuan yang dipilih. Kosongkan jika tidak dinilai.</p>
    <form method="post"><input type="hidden" name="kelas" value="{kelas}"><input type="hidden" name="mapel" value="{mapel}"><input type="hidden" name="tanggal" value="{tanggal}">
    <div class="tablewrap"><table><tr><th>No.</th><th>Nama siswa</th><th>Skor (1–4)</th></tr>"""
    for i,st in enumerate(students,1):
        val = marks.get(st["id"])
        isi += f'<tr><td>{i}</td><td>{st["nama"]}</td><td><select name="skor_{st["id"]}"><option value="" {"selected" if val is None else ""}>Belum dinilai</option>'
        for n in [1,2,3,4]:
            isi += f'<option value="{n}" {"selected" if val==n else ""}>{n}</option>'
        isi += '</select></td></tr>'
    if not students: isi += '<tr><td colspan="3">Belum ada siswa di kelas ini.</td></tr>'
    isi += '</table></div><p><button>Simpan keaktifan</button></p></form></section>'
    isi += '<section class="card"><h2>Ringkasan keaktifan</h2><div class="tablewrap"><table><tr><th>Nama</th><th>Jumlah skor</th><th>Rata-rata skor</th><th>Nilai keaktifan</th></tr>'
    for st,raw,score,jml in rows:
        isi += f"<tr><td>{st['nama']}</td><td>{jml}</td><td>{raw:g}</td><td>{score:g}</td></tr>"
    isi += '</table></div></section>'
    return page(isi,pesan)

@app.route("/nilai", methods=["GET", "POST"])
def nilai():
    kelas,mapel = get_filters()
    pesan = ""
    with db() as con:
        students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama",(kelas,)).fetchall()
        if request.method == "POST":
            for st in students:
                vals = [angka(request.form.get(f"{key}_{st['id']}")) for key in ["tugas","uh1","uh2","uts","uas"]]
                con.execute("""INSERT INTO nilai(siswa_id,kelas,mapel,tugas,uh1,uh2,uts,uas)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(siswa_id,kelas,mapel) DO UPDATE SET
                    tugas=excluded.tugas,uh1=excluded.uh1,uh2=excluded.uh2,uts=excluded.uts,uas=excluded.uas""",
                    (st["id"],kelas,mapel,*vals))
            pesan = "Nilai tersimpan. Nilai akhir dan rekap dihitung otomatis."
        rows = [(st,rekap_siswa(con,st,kelas,mapel)) for st in students]
    isi = filter_form("/nilai",kelas,mapel) + """
    <section class="card"><h2>Daftar nilai</h2><p>Kolom kehadiran dan keaktifan berasal dari daftar hadir dan daftar keaktifan. Isi komponen lainnya di sini.</p>
    <p class="muted">Bobot: Kehadiran 10%, Keaktifan 20%, Tugas 10%, UH 1 15%, UH 2 15%, UTS 15%, UAS 15%.</p>
    <form method="post"><input type="hidden" name="kelas" value="{{kelas}}"><input type="hidden" name="mapel" value="{{mapel}}">
    <div class="tablewrap"><table><tr><th>Nama siswa</th><th>Kehadiran (10%)</th><th>Keaktifan (20%)</th><th>Tugas (10%)</th><th>UH 1 (15%)</th><th>UH 2 (15%)</th><th>UTS (15%)</th><th>UAS (15%)</th><th>Nilai akhir</th></tr>
    {% for st,r in rows %}<tr><td>{{st.nama}}</td><td>{{r.kh}}</td><td>{{r.ka}}</td>
    {% for key in ['tugas','uh1','uh2','uts','uas'] %}<td><input type="number" min="0" max="100" step="0.01" name="{{key}}_{{st.id}}" value="{{r.nilai[key] if r.nilai and r.nilai[key] is not none else ''}}"></td>{% endfor %}
    <td><b>{{r.akhir}}</b></td></tr>{% else %}<tr><td colspan="9">Belum ada siswa di kelas ini.</td></tr>{% endfor %}
    </table></div><p><button>Simpan semua nilai</button></p></form></section>"""
    result = render_template_string(isi,kelas=kelas,mapel=mapel,rows=rows)
    return page(result,pesan)

@app.route("/rekap")
def rekap():
    kelas,mapel = get_filters()
    with db() as con:
        students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama",(kelas,)).fetchall()
        rows = [(st,rekap_siswa(con,st,kelas,mapel)) for st in students]
    isi = filter_form("/rekap",kelas,mapel) + f"""
    <section class="card"><h2>Rekap nilai — {kelas} — {mapel}</h2>
    <p>KKM 75. Predikat: A ≥ 90; B ≥ 80; C ≥ 75; D &lt; 75.</p>
    <p class="noprint"><a class="btn" href="/ekspor?kelas={kelas}&mapel={mapel}">Ekspor CSV (bisa dibuka di Excel)</a> <button onclick="window.print()">Cetak / Simpan PDF</button></p>
    <div class="tablewrap"><table><tr><th>No.</th><th>Nama siswa</th><th>Kehadiran</th><th>Keaktifan</th><th>Tugas</th><th>UH 1</th><th>UH 2</th><th>UTS</th><th>UAS</th><th>Nilai akhir</th><th>Predikat</th><th>Ketuntasan</th></tr>"""
    for i,(st,r) in enumerate(rows,1):
        c = r["komponen"]
        isi += f"<tr><td>{i}</td><td>{st['nama']}</td><td>{r['kh']:g}</td><td>{r['ka']:g}</td><td>{c['Tugas']:g}</td><td>{c['UH 1']:g}</td><td>{c['UH 2']:g}</td><td>{c['UTS']:g}</td><td>{c['UAS']:g}</td><td><b>{r['akhir']:g}</b></td><td>{r['predikat']}</td><td>{r['ketuntasan']}</td></tr>"
    if not rows: isi += '<tr><td colspan="12">Belum ada siswa di kelas ini.</td></tr>'
    isi += '</table></div></section>'
    return page(isi)

@app.route("/ekspor")
def ekspor():
    kelas,mapel = get_filters()
    output = io.StringIO()
    output.write("\\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["NIS","Nama","Kelas","Mata Pelajaran","Kehadiran","Keaktifan","Tugas","UH 1","UH 2","UTS","UAS","Nilai Akhir","Predikat","Ketuntasan"])
    with db() as con:
        students = con.execute("SELECT * FROM siswa WHERE kelas=? ORDER BY nama",(kelas,)).fetchall()
        for st in students:
            r = rekap_siswa(con,st,kelas,mapel)
            c = r["komponen"]
            writer.writerow([st["nis"],st["nama"],kelas,mapel,r["kh"],r["ka"],c["Tugas"],c["UH 1"],c["UH 2"],c["UTS"],c["UAS"],r["akhir"],r["predikat"],r["ketuntasan"]])
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":f"attachment; filename=rekap_{kelas.replace(' ','_')}.csv"})

init_name_=="_main_":
    app.run(host="0.0.0.0",port=5000,debug=false)
    
