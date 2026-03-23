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
                flash("Acesso restrito ao administrador.", "erro")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        if session["perfil"] in ["admin", "leitor"]:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        u, s = request.form.get("cnpj", "").strip(), request.form.get("senha", "").strip()
        
        if u.lower() == "admin" and s == Config.ADMIN_SENHA:
            session.update({"perfil": "admin", "usuario": {"nome": "Admin"}})
            return redirect(url_for("admin_dashboard"))
            
        if u.lower() == "equipe" and s == Config.EQUIPE_SENHA:
            session.update({"perfil": "leitor", "usuario": {"nome": "Equipe Interna", "id": 0}})
            return redirect(url_for("admin_dashboard"))
            
        c = db.buscar_cliente_cnpj(u)
        if c and hash_senha(s) == c["senha_hash"] and c["ativo"]:
            session.update({"perfil": "cliente", "usuario": c})
            return redirect(url_for("dashboard"))
            
        flash("Credenciais inválidas.", "erro")
    return render_template("login.html")

@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))

# ─── ROTAS DO DASHBOARD E FINANCEIRO ─────────────────────────────────────────

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["perfil"] in ["admin", "leitor"]: 
        return redirect(url_for("admin_dashboard"))
    
    nfs = db.listar_nfs(session["usuario"]["id"])
    titulos = db.listar_titulos(session["usuario"]["id"])
    hoje = datetime.now().strftime("%Y-%m-%d")
    titulos_abertos  = [t for t in titulos if t["status"] == "aberto"]
    titulos_vencidos = []
    
    for t in titulos_abertos:
        try:
            p = t["vencimento"].split("/")
            if f"{p[2]}-{p[1]}-{p[0]}" < hoje: titulos_vencidos.append(t)
        except: pass

    for nf in nfs:
        nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
        nf["tem_rastreio"] = len(nf["eventos"]) > 0

    return render_template("dashboard.html", nfs=nfs, titulos_abertos=titulos_abertos, titulos_vencidos=titulos_vencidos)

@app.route("/admin")
@login_required()
def admin_dashboard():
    if session["perfil"] == "admin":
        nfs = db.listar_todas_nfs()
        titulos = db.listar_todos_titulos()
        clientes = db.listar_clientes()
        em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
        titulos_abertos = len([t for t in titulos if t["status"] == "aberto"])
        return render_template("admin/dashboard.html", total_clientes=len(clientes), total_nfs=len(nfs), titulos_abertos=titulos_abertos, em_aberto=em_aberto)
    
    elif session["perfil"] == "leitor":
        nfs = db.listar_todas_nfs()
        titulos = db.listar_todos_titulos()
        
        for n in nfs:
            n["numero_nf"] = f"{n['numero_nf']} - {n.get('cliente', '')}"
        for t in titulos:
            t["numero_titulo"] = f"{t['numero_titulo']} - {t.get('cliente', '')}"
            
        hoje = datetime.now().strftime("%Y-%m-%d")
        titulos_abertos  = [t for t in titulos if t["status"] == "aberto"]
        titulos_vencidos = []
        
        for t in titulos_abertos:
            try:
                p = t["vencimento"].split("/")
                if f"{p[2]}-{p[1]}-{p[0]}" < hoje: titulos_vencidos.append(t)
            except: pass

        for nf in nfs:
            nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
            nf["tem_rastreio"] = len(nf["eventos"]) > 0

        return render_template("dashboard.html", nfs=nfs, titulos_abertos=titulos_abertos, titulos_vencidos=titulos_vencidos)
        
    return redirect(url_for("dashboard"))

@app.route("/entrega/<int:nf_id>")
@login_required()
def entrega(nf_id):
    if session["perfil"] == "admin": 
        return redirect(url_for("admin_dashboard"))
    
    if session["perfil"] == "leitor":
        nfs = db.listar_todas_nfs()
        titulos_nf = [t for t in db.listar_todos_titulos() if t.get("nf_id") == nf_id]
        for t in titulos_nf:
            t["numero_titulo"] = f"{t['numero_titulo']} - {t.get('cliente', '')}"
    else:
        nfs = db.listar_nfs(session["usuario"]["id"])
        titulos_nf = [t for t in db.listar_titulos(session["usuario"]["id"]) if t.get("nf_id") == nf_id]

    nf = next((n for n in nfs if n["id"] == nf_id), None)
    if not nf:
        flash("Nota fiscal não encontrada.", "erro")
        return redirect(url_for("admin_dashboard") if session["perfil"] == "leitor" else url_for("dashboard"))

    nf["eventos"] = db.listar_eventos_rastreio(nf_id)
    nf["pdf"] = db.get_pdf_nf(nf_id)
    
    return render_template("entrega.html", nf=nf, titulos=titulos_nf)

@app.route("/financeiro")
@login_required()
def financeiro():
    if session["perfil"] in ["admin", "leitor"]: return redirect(url_for("admin_dashboard"))
    
    titulos = db.listar_titulos(session["usuario"]["id"])
    hoje = datetime.now().strftime("%Y-%m-%d")
    from datetime import date
    for t in titulos:
        try:
            p = t["vencimento"].split("/")
            iso = f"{p[2]}-{p[1]}-{p[0]}"
            venc_date = date.fromisoformat(iso)
            hoje_date = date.today()
            t["dias_vencimento"] = (venc_date - hoje_date).days
            t["status_visual"] = "vencido" if t["status"] == "aberto" and iso < hoje else t["status"]
        except:
            t["status_visual"] = t["status"]
            t["dias_vencimento"] = None

    em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    quitado   = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    return render_template("financeiro.html", titulos=titulos, em_aberto=em_aberto, quitado=quitado)

@app.route("/trocar-senha", methods=["GET", "POST"])
@login_required()
def trocar_senha():
    if session["perfil"] != "cliente": return redirect(url_for("admin_dashboard"))
    cliente = session["usuario"]
    if request.method == "POST":
        atual, nova, conf = request.form.get("senha_atual", ""), request.form.get("senha_nova", ""), request.form.get("confirmar", "")
        dados = db.buscar_cliente_cnpj(cliente["cnpj"])
        if hash_senha(atual) != dados["senha_hash"]: flash("Senha atual incorreta.", "erro")
        elif nova != conf: flash("As senhas não coincidem.", "erro")
        elif len(nova) < 4: flash("A nova senha deve ter no mínimo 4 caracteres.", "erro")
        else:
            db.atualizar_senha(cliente["id"], hash_senha(nova))
            flash("Senha alterada com sucesso!", "sucesso")
            return redirect(url_for("dashboard"))
    return render_template("trocar_senha.html", cliente=cliente)

@app.route("/download/nf/<int:nf_id>")
@login_required()
def download_nf(nf_id):
    if session["perfil"] == "cliente":
        nfs = db.listar_nfs(session["usuario"]["id"])
        if not any(n["id"] == nf_id for n in nfs): return "Não autorizado", 403
    dados = db.get_pdf_nf(nf_id)
    if not dados or not dados.get("pdf_base64"): return "PDF não disponível", 404
    return send_file(io.BytesIO(base64.b64decode(dados["pdf_base64"])), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"NF_{nf_id}.pdf")

@app.route("/download/boleto/<int:titulo_id>")
@login_required()
def download_boleto(titulo_id):
    if session["perfil"] == "cliente":
        titulos = db.listar_titulos(session["usuario"]["id"])
        if not any(t["id"] == titulo_id for t in titulos): return "Não autorizado", 403
    dados = db.get_pdf_titulo(titulo_id)
    if not dados or not dados.get("boleto_base64"): return "PDF não disponível", 404
    return send_file(io.BytesIO(base64.b64decode(dados["boleto_base64"])), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"Boleto_{titulo_id}.pdf")

# ─── ROTAS DA OPERAÇÃO E CADASTRO (ADMIN / EQUIPA) ───────────────────────────

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
                    if not num_dup: break
                    p_pdf = request.files.get(f"pdf_boleto_{i}")
                    if p_pdf and p_pdf.filename:
                        db.inserir_titulo(int(request.form["cliente_id"]), num_dup, float(request.form[f"dup_val_{i}"]), request.form[f"dup_venc_{i}"], base64.b64encode(p_pdf.read()).decode(), p_pdf.filename, nf_id)
                        boletos_salvos += 1
                    i += 1
                flash(f"NF {numero_nf} salva com {boletos_salvos} boletos!", "sucesso")
            elif tipo == "boleto":
                db.inserir_titulo(int(request.form["cliente_id"]), request.form["numero_titulo"], float(request.form["valor"]), request.form["vencimento"], pdf_b64, arquivo.filename, request.form.get("nf_id"))
                flash("Boleto salvo!", "sucesso")
        return redirect(url_for("admin_upload"))
    return render_template("admin/upload.html", clientes=db.listar_clientes(), tipo_ativo=request.args.get("tipo", "nf"))

@app.route("/admin/clientes", methods=["GET", "POST"])
@login_required()
def admin_clientes():
    if session["perfil"] not in ["admin", "leitor"]: return redirect(url_for("dashboard"))
    if request.method == "POST":
        if session["perfil"] == "leitor":
            flash("Acesso Negado. Apenas visualização.", "erro")
            return redirect(url_for("admin_clientes"))
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

@app.route("/admin/nfs", methods=["GET", "POST"])
@login_required()
def admin_nfs():
    if session["perfil"] not in ["admin", "leitor"]: return redirect(url_for("dashboard"))
    if request.method == "POST":
        if session["perfil"] == "leitor":
            flash("Acesso Negado.", "erro")
            return redirect(url_for("admin_nfs"))
        db.atualizar_status_nf(int(request.form["nf_id"]), request.form.get("status",""), request.form.get("observacao",""))
        flash("NF atualizada!", "sucesso")
        return redirect(url_for("admin_nfs"))
    return render_template("admin/nfs.html", nfs=db.listar_todas_nfs())

# ---> NOVA ROTA ADICIONADA AQUI PARA APAGAR AS NFS <---
@app.route("/admin/nfs/deletar/<int:nf_id>", methods=["POST"])
@login_required("admin")
def admin_deletar_nf(nf_id):
    try:
        db.deletar_nf(nf_id)
        flash("Nota Fiscal apagada com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao apagar NF: {str(e)}", "erro")
    return redirect(url_for("admin_nfs"))

@app.route("/admin/titulos", methods=["GET", "POST"])
@login_required()
def admin_titulos():
    if session["perfil"] not in ["admin", "leitor"]: return redirect(url_for("dashboard"))
    if request.method == "POST":
        if session["perfil"] == "leitor":
            flash("Acesso Negado.", "erro")
            return redirect(url_for("admin_titulos"))
        db.marcar_titulo_pago(int(request.form["titulo_id"]))
        flash("Marcado como pago!", "sucesso")
        return redirect(url_for("admin_titulos"))
        
    titulos = db.listar_todos_titulos()
    em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    recebido = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    return render_template("admin/titulos.html", titulos=titulos, em_aberto=em_aberto, recebido=recebido)

@app.route("/admin/rastreio")
@login_required()
def admin_rastreio():
    if session["perfil"] not in ["admin", "leitor"]: return redirect(url_for("dashboard"))
    nfs = db.listar_todas_nfs()
    for n in nfs: n["eventos"] = db.listar_eventos_rastreio(n["id"])
    return render_template("admin/rastreio.html", nfs=nfs)

@app.route("/admin/extrair-xml", methods=["POST"])
@login_required("admin")
def extrair_xml():
    f = request.files.get("xml")
    if not f: return jsonify({"sucesso": False})
    return jsonify(extrair_dados_xml(f.read()))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
