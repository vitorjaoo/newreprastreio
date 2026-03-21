import base64, hashlib, io, re
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import db
from config import Config
from extrator_pdf import extrair_dados_xml

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

@app.context_processor
def globals_template():
    return {
        "nome_escritorio": Config.NOME_ESCRITORIO,
        "cor_primaria": Config.COR_PRIMARIA,
        "cor_secundaria": Config.COR_SECUNDARIA,
        "now": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

with app.app_context():
    db.criar_tabelas()

def hash_senha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("perfil"):
                return redirect(url_for("login"))
            if role == "admin" and session.get("perfil") != "admin":
                flash("Acesso restrito.", "erro")
                return redirect(url_for("admin_dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        return redirect(url_for("admin_dashboard") if session["perfil"] in ["admin", "leitor"] else url_for("dashboard"))
    if request.method == "POST":
        u, s = request.form.get("cnpj", "").strip(), request.form.get("senha", "").strip()
        if u.lower() == "admin" and s == Config.ADMIN_SENHA:
            session.update({"perfil": "admin", "usuario": {"nome": "Admin"}})
            return redirect(url_for("admin_dashboard"))
        if u.lower() == "equipe" and s == Config.EQUIPE_SENHA:
            session.update({"perfil": "leitor", "usuario": {"nome": "Equipe"}})
            return redirect(url_for("admin_dashboard"))
        c = db.buscar_cliente_cnpj(u)
        if c and hash_senha(s) == c["senha_hash"] and c["ativo"]:
            session.update({"perfil": "cliente", "usuario": c})
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "erro")
    return render_template("login.html")

@app.route("/admin/upload", methods=["GET", "POST"])
@login_required("admin")
def admin_upload():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        arquivo = request.files.get("arquivo")
        if arquivo and arquivo.filename.endswith(".pdf"):
            pdf_b64 = base64.b64encode(arquivo.read()).decode()
            if tipo == "nf":
                numero_nf = request.form.get("numero_nf")
                nf_id = db.inserir_nf(int(request.form["cliente_id"]), numero_nf, float(request.form["valor"]), request.form["data_emissao"], pdf_b64, arquivo.filename, request.form.get("codigo_rastreio"), request.form.get("transportadora"), "ativo", request.form.get("observacao"), request.form.get("representada"))
                boletos_salvos, i = 0, 0
                while True:
                    num_dup = request.form.get(f"dup_num_{i}")
                    if not num_dup:
                        break
                    p_pdf = request.files.get(f"pdf_boleto_{i}")
                    if p_pdf and p_pdf.filename:
                        db.inserir_titulo(int(request.form["cliente_id"]), num_dup, float(request.form[f"dup_val_{i}"]), request.form[f"dup_venc_{i}"], base64.b64encode(p_pdf.read()).decode(), p_pdf.filename, nf_id)
                        boletos_salvos += 1
                    i += 1
                flash(f"NF {numero_nf} salva com {boletos_salvos} boletos!", "sucesso")
        return redirect(url_for("admin_upload"))
    return render_template("admin/upload.html", clientes=db.listar_clientes(), tipo_ativo=request.args.get("tipo", "nf"))

@app.route("/admin")
@login_required()
def admin_dashboard():
    if session["perfil"] not in ["admin", "leitor"]: return redirect(url_for("dashboard"))
    return render_template("admin/dashboard.html", total_clientes=len(db.listar_clientes()), total_nfs=len(db.listar_todas_nfs()))

@app.route("/admin/clientes", methods=["GET", "POST"])
@login_required()
def admin_clientes():
    if request.method == "POST" and session["perfil"] == "admin":
        acao = request.form.get("acao")
        if acao == "cadastrar":
            db.criar_cliente(request.form["nome"], request.form["cnpj"], request.form.get("email"), request.form.get("whatsapp"), hash_senha(request.form["senha"]))
        elif acao == "inativar":
            db.toggle_cliente_ativo(int(request.form["cliente_id"]))
        return redirect(url_for("admin_clientes"))
    return render_template("admin/clientes.html", clientes=db.listar_clientes())

@app.route("/admin/clientes/editar/<int:cid>", methods=["POST"])
@login_required("admin")
def admin_clientes_editar(cid):
    ns = request.form.get("nova_senha")
    db.atualizar_cliente(cid, request.form["nome"], request.form["cnpj"], request.form["email"], request.form["whatsapp"], hash_senha(ns) if ns else None)
    return redirect(url_for("admin_clientes"))

@app.route("/admin/nfs")
@login_required()
def admin_nfs():
    return render_template("admin/nfs.html", nfs=db.listar_todas_nfs())

@app.route("/admin/titulos")
@login_required()
def admin_titulos():
    return render_template("admin/titulos.html", titulos=db.listar_todos_titulos())

@app.route("/admin/rastreio")
@login_required()
def admin_rastreio():
    nfs = db.listar_todas_nfs()
    for n in nfs: n["eventos"] = db.listar_eventos_rastreio(n["id"])
    return render_template("admin/rastreio.html", nfs=nfs)

@app.route("/admin/extrair-xml", methods=["POST"])
@login_required("admin")
def extrair_xml():
    f = request.files.get("xml")
    if not f: return jsonify({"sucesso": False})
    return jsonify(extrair_dados_xml(f.read()))

@app.route("/dashboard")
@login_required()
def dashboard():
    return render_template("dashboard.html", nfs=db.listar_nfs(session["usuario"]["id"]), titulos=db.listar_titulos(session["usuario"]["id"]))

@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
