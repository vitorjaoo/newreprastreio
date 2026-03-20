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
            representada    TEXT,
            criado_em       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (nf_id)      REFERENCES notas_fiscais(id)
        )
    """)
    try:
        conn.execute("ALTER TABLE titulos ADD COLUMN representada TEXT")
        conn.commit()
    except Exception:
        pass
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
        "SELECT id, nome, cnpj, email, whatsapp, senha_hash, ativo FROM clientes WHERE cnpj=?",
        [cnpj]
    )
    res = _rows_to_dicts(cur)
    return res[0] if res else None


def criar_cliente(nome: str, cnpj: str, email: str, whatsapp: str, senha_hash: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO clientes (nome, cnpj, email, whatsapp, senha_hash) VALUES (?, ?, ?, ?, ?)",
        [nome, cnpj, email, whatsapp, senha_hash]
    )
    conn.commit()


def atualizar_senha(cliente_id: int, senha_hash: str):
    conn = get_conn()
    conn.execute("UPDATE clientes SET senha_hash=? WHERE id=?", [senha_hash, cliente_id])
    conn.commit()


def toggle_cliente_ativo(cliente_id: int):
    conn = get_conn()
    conn.execute("UPDATE clientes SET ativo = CASE WHEN ativo=1 THEN 0 ELSE 1 END WHERE id=?",
                 [cliente_id])
    conn.commit()

# ─── NFs ─────────────────────────────────────────────────────────────────────

def listar_todas_nfs():
    conn = get_conn()
    cur = conn.execute("""
        SELECT n.id, c.nome as cliente, c.cnpj, n.numero_nf, n.valor,
               n.data_emissao, n.status, n.codigo_rastreio, n.transportadora, n.observacao, n.representada
        FROM notas_fiscais n
        JOIN clientes c ON c.id = n.cliente_id
        ORDER BY n.criado_em DESC
    """)
    return _rows_to_dicts(cur)


def listar_nfs(cliente_id: int):
    conn = get_conn()
    cur = conn.execute("""
        SELECT id, numero_nf, valor, data_emissao, status, codigo_rastreio, transportadora, observacao, representada
        FROM notas_fiscais
        WHERE cliente_id=?
        ORDER BY criado_em DESC
    """, [cliente_id])
    return _rows_to_dicts(cur)


def inserir_nf(cliente_id: int, numero_nf: str, valor: float, data_emissao: str,
               pdf_base64: str, nome_arquivo: str, codigo_rastreio: str, transportadora: str,
               status: str, observacao: str = "", representada: str = ""):
    conn = get_conn()
    cursor = conn.execute("""
        INSERT INTO notas_fiscais
        (cliente_id, numero_nf, valor, data_emissao, pdf_base64, nome_arquivo, codigo_rastreio, transportadora, status, observacao, representada)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [cliente_id, numero_nf, valor, data_emissao, pdf_base64, nome_arquivo, codigo_rastreio, transportadora, status, observacao, representada])
    conn.commit()
    return cursor.lastrowid


def atualizar_status_nf(nf_id: int, status: str, observacao: str):
    conn = get_conn()
    conn.execute("UPDATE notas_fiscais SET status=?, observacao=? WHERE id=?", [status, observacao, nf_id])
    conn.commit()


def deletar_nf(nf_id: int):
    conn = get_conn()
    # Deleta títulos e eventos vinculados primeiro
    conn.execute("DELETE FROM titulos WHERE nf_id=?", [nf_id])
    conn.execute("DELETE FROM rastreio_eventos WHERE nf_id=?", [nf_id])
    conn.execute("DELETE FROM notas_fiscais WHERE id=?", [nf_id])
    conn.commit()

# ─── Rastreio ────────────────────────────────────────────────────────────────

def listar_eventos_rastreio(nf_id: int):
    conn = get_conn()
    cur = conn.execute("""
        SELECT id, descricao, data_hora
        FROM rastreio_eventos
        WHERE nf_id=?
        ORDER BY id DESC
    """, [nf_id])
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
    conn.execute("DELETE FROM rastreio_eventos WHERE id=?", [evento_id])
    conn.commit()

# ─── Títulos (Financeiro) ────────────────────────────────────────────────────

def listar_todos_titulos():
    conn = get_conn()
    cur = conn.execute("""
        SELECT t.id, c.nome as cliente, t.numero_titulo, t.valor, t.vencimento, t.status, t.nf_id, t.representada, n.numero_nf
        FROM titulos t
        JOIN clientes c ON c.id = t.cliente_id
        LEFT JOIN notas_fiscais n ON n.id = t.nf_id
        ORDER BY t.criado_em DESC
    """)
    return _rows_to_dicts(cur)


def listar_titulos(cliente_id: int):
    conn = get_conn()
    cur = conn.execute("""
        SELECT t.id, t.numero_titulo, t.valor, t.vencimento, t.status, t.nf_id, t.representada, n.numero_nf
        FROM titulos t
        LEFT JOIN notas_fiscais n ON n.id = t.nf_id
        WHERE t.cliente_id=?
        ORDER BY t.criado_em DESC
    """, [cliente_id])
    return _rows_to_dicts(cur)


def inserir_titulo(cliente_id: int, numero_titulo: str, valor: float, vencimento: str,
                   boleto_base64: str, nome_arquivo: str, nf_id: int = None, representada: str = ""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO titulos
        (cliente_id, numero_titulo, valor, vencimento, boleto_base64, nome_arquivo, nf_id, representada)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [cliente_id, numero_titulo, valor, vencimento, boleto_base64, nome_arquivo, nf_id, representada])
    conn.commit()


def marcar_titulo_pago(titulo_id: int):
    conn = get_conn()
    conn.execute("UPDATE titulos SET status='pago' WHERE id=?", [titulo_id])
    conn.commit()


def solicitar_confirmacao_pagamento(titulo_id: int):
    conn = get_conn()
    conn.execute("UPDATE titulos SET status='aguardando_confirmacao' WHERE id=?", [titulo_id])
    conn.commit()


def listar_titulos_pendentes():
    """Retorna títulos aguardando confirmação de pagamento"""
    conn = get_conn()
    cur = conn.execute(
        """SELECT t.id, c.nome as cliente, t.numero_titulo, t.valor, t.vencimento
           FROM titulos t
           JOIN clientes c ON c.id = t.cliente_id
           WHERE t.status = 'aguardando_confirmacao'
           ORDER BY t.criado_em DESC"""
    )
    return _rows_to_dicts(cur)

# ─── Downloads ───────────────────────────────────────────────────────────────

def get_pdf_nf(nf_id: int):
    conn = get_conn()
    cur = conn.execute("SELECT pdf_base64, nome_arquivo FROM notas_fiscais WHERE id=?", [nf_id])
    res = _rows_to_dicts(cur)
    return res[0] if res else None


def get_pdf_titulo(titulo_id: int):
    conn = get_conn()
    cur = conn.execute("SELECT boleto_base64, nome_arquivo FROM titulos WHERE id=?", [titulo_id])
    res = _rows_to_dicts(cur)
    return res[0] if res else None
