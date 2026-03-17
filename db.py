"""
db.py — conexão com Turso usando o novo SDK libsql
Compatível com migração futura para Oracle (SQL padrão)
"""

import os
import libsql
from dotenv import load_dotenv
load_dotenv()


_conn = None

def get_conn():
    global _conn
    try:
        if _conn is None:
            _conn = libsql.connect(
                database=os.getenv("TURSO_DATABASE_URL"),
                auth_token=os.getenv("TURSO_AUTH_TOKEN"),
            )
        _conn.execute("SELECT 1")
        return _conn
    except Exception:
        _conn = libsql.connect(
            database=os.getenv("TURSO_DATABASE_URL"),
            auth_token=os.getenv("TURSO_AUTH_TOKEN"),
        )
        return _conn


def _rows_to_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def criar_tabelas():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            cnpj        TEXT UNIQUE NOT NULL,
            email       TEXT,
            whatsapp    TEXT,
            senha_hash  TEXT NOT NULL,
            ativo       INTEGER DEFAULT 1,
            criado_em   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notas_fiscais (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id      INTEGER NOT NULL,
            numero_nf       TEXT,
            valor           REAL,
            data_emissao    TEXT,
            status          TEXT DEFAULT 'ativo',
            observacao      TEXT,
            representada    TEXT,
            pdf_base64      TEXT,
            nome_arquivo    TEXT,
            codigo_rastreio TEXT,
            transportadora  TEXT,
            criado_em       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rastreio_eventos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nf_id       INTEGER NOT NULL,
            descricao   TEXT NOT NULL,
            data_hora   TEXT NOT NULL,
            criado_em   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (nf_id) REFERENCES notas_fiscais(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS titulos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id      INTEGER NOT NULL,
            numero_titulo   TEXT,
            valor           REAL,
            vencimento      TEXT,
            status          TEXT DEFAULT 'aberto',
            boleto_base64   TEXT,
            nome_arquivo    TEXT,
            nf_id           INTEGER,
            criado_em       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (nf_id)      REFERENCES notas_fiscais(id)
        )
    """)
    # Migrações seguras para tabelas já existentes
    for col in ["observacao TEXT", "representada TEXT"]:
        try:
            conn.execute(f"ALTER TABLE notas_fiscais ADD COLUMN {col}")
            conn.commit()
        except Exception:
            pass
    conn.commit()


# ─── Clientes ────────────────────────────────────────────────────────────────

def listar_clientes():
    conn = get_conn()
    cur = conn.execute("SELECT id, nome, cnpj, email, whatsapp, ativo FROM clientes ORDER BY nome")
    return _rows_to_dicts(cur)


def buscar_cliente_cnpj(cnpj: str):
    conn = get_conn()
    cur = conn.execute(
        "SELECT id, nome, cnpj, email, whatsapp, senha_hash, ativo FROM clientes WHERE cnpj = ?",
        [cnpj]
    )
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


def criar_cliente(nome, cnpj, email, whatsapp, senha_hash):
    conn = get_conn()
    conn.execute(
        "INSERT INTO clientes (nome, cnpj, email, whatsapp, senha_hash) VALUES (?, ?, ?, ?, ?)",
        [nome, cnpj, email, whatsapp, senha_hash]
    )
    conn.commit()


# ─── Notas Fiscais ────────────────────────────────────────────────────────────

def listar_nfs(cliente_id: int):
    conn = get_conn()
    cur = conn.execute(
        """SELECT id, numero_nf, valor, data_emissao, status, observacao,
                  representada, nome_arquivo, codigo_rastreio, transportadora, criado_em
           FROM notas_fiscais WHERE cliente_id = ? ORDER BY criado_em DESC""",
        [cliente_id]
    )
    return _rows_to_dicts(cur)


def listar_todas_nfs():
    conn = get_conn()
    cur = conn.execute(
        """SELECT nf.id, c.nome as cliente, nf.numero_nf, nf.valor,
                  nf.data_emissao, nf.status, nf.observacao, nf.representada,
                  nf.nome_arquivo, nf.codigo_rastreio, nf.transportadora, nf.criado_em
           FROM notas_fiscais nf
           JOIN clientes c ON c.id = nf.cliente_id
           ORDER BY nf.criado_em DESC"""
    )
    return _rows_to_dicts(cur)


def inserir_nf(cliente_id, numero_nf, valor, data_emissao, pdf_base64,
               nome_arquivo, codigo_rastreio="", transportadora="",
               status="ativo", observacao="", representada=""):
    conn = get_conn()
    conn.execute(
        """INSERT INTO notas_fiscais
           (cliente_id, numero_nf, valor, data_emissao, pdf_base64,
            nome_arquivo, codigo_rastreio, transportadora, status, observacao, representada)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [cliente_id, numero_nf, valor, data_emissao,
         pdf_base64, nome_arquivo, codigo_rastreio, transportadora,
         status, observacao, representada]
    )
    conn.commit()


def atualizar_status_nf(nf_id, status, observacao=""):
    conn = get_conn()
    conn.execute(
        "UPDATE notas_fiscais SET status=?, observacao=? WHERE id=?",
        [status, observacao, nf_id]
    )
    conn.commit()


def atualizar_rastreio_nf(nf_id, codigo_rastreio, transportadora):
    conn = get_conn()
    conn.execute(
        "UPDATE notas_fiscais SET codigo_rastreio=?, transportadora=? WHERE id=?",
        [codigo_rastreio, transportadora, nf_id]
    )
    conn.commit()


def atualizar_representada(nf_id, representada):
    conn = get_conn()
    conn.execute(
        "UPDATE notas_fiscais SET representada=? WHERE id=?",
        [representada, nf_id]
    )
    conn.commit()


def get_pdf_nf(nf_id: int):
    conn = get_conn()
    cur = conn.execute(
        "SELECT pdf_base64, nome_arquivo FROM notas_fiscais WHERE id = ?", [nf_id]
    )
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


# ─── Rastreio Eventos ─────────────────────────────────────────────────────────

def listar_eventos_rastreio(nf_id: int):
    conn = get_conn()
    cur = conn.execute(
        "SELECT id, descricao, data_hora FROM rastreio_eventos WHERE nf_id = ? ORDER BY data_hora ASC",
        [nf_id]
    )
    return _rows_to_dicts(cur)


def inserir_evento_rastreio(nf_id: int, descricao: str, data_hora: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO rastreio_eventos (nf_id, descricao, data_hora) VALUES (?, ?, ?)",
        [nf_id, descricao, data_hora]
    )
    conn.commit()


def deletar_evento_rastreio(evento_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM rastreio_eventos WHERE id = ?", [evento_id])
    conn.commit()


# ─── Títulos ──────────────────────────────────────────────────────────────────

def listar_titulos(cliente_id: int):
    conn = get_conn()
    cur = conn.execute(
        """SELECT id, numero_titulo, valor, vencimento, status,
                  nome_arquivo, nf_id, criado_em
           FROM titulos WHERE cliente_id = ? ORDER BY vencimento ASC""",
        [cliente_id]
    )
    return _rows_to_dicts(cur)


def listar_todos_titulos():
    conn = get_conn()
    cur = conn.execute(
        """SELECT t.id, c.nome as cliente, t.numero_titulo, t.valor,
                  t.vencimento, t.status, t.nome_arquivo, t.nf_id, t.criado_em
           FROM titulos t
           JOIN clientes c ON c.id = t.cliente_id
           ORDER BY t.vencimento ASC"""
    )
    return _rows_to_dicts(cur)


def inserir_titulo(cliente_id, numero_titulo, valor, vencimento,
                   boleto_base64, nome_arquivo, nf_id=None):
    conn = get_conn()
    conn.execute(
        """INSERT INTO titulos
           (cliente_id, numero_titulo, valor, vencimento,
            boleto_base64, nome_arquivo, nf_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [cliente_id, numero_titulo, valor, vencimento,
         boleto_base64, nome_arquivo, nf_id]
    )
    conn.commit()


def get_pdf_titulo(titulo_id: int):
    conn = get_conn()
    cur = conn.execute(
        "SELECT boleto_base64, nome_arquivo FROM titulos WHERE id = ?", [titulo_id]
    )
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


def marcar_titulo_pago(titulo_id: int):
    conn = get_conn()
    conn.execute("UPDATE titulos SET status='pago' WHERE id=?", [titulo_id])
    conn.commit()


def titulos_vencendo(dias: int = 5):
    conn = get_conn()
    cur = conn.execute(
        """SELECT t.id, c.nome, c.email, c.whatsapp,
                  t.numero_titulo, t.valor, t.vencimento
           FROM titulos t
           JOIN clientes c ON c.id = t.cliente_id
           WHERE t.status = 'aberto'
             AND date(t.vencimento) <= date('now', ? || ' days')
             AND date(t.vencimento) >= date('now')
           ORDER BY t.vencimento ASC""",
        [str(dias)]
    )
    return _rows_to_dicts(cur)


def atualizar_senha(cliente_id: int, senha_hash: str):
    conn = get_conn()
    conn.execute("UPDATE clientes SET senha_hash=? WHERE id=?", [senha_hash, cliente_id])
    conn.commit()


def toggle_cliente_ativo(cliente_id: int):
    conn = get_conn()
    conn.execute("UPDATE clientes SET ativo = CASE WHEN ativo=1 THEN 0 ELSE 1 END WHERE id=?",
                 [cliente_id])
    conn.commit()
