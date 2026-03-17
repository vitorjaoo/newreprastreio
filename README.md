# Portal do Cliente — Flask

Portal web completo para clientes acessarem NFs, rastreio de entregas e boletos.

**Stack:** Python + Flask + Turso (libSQL) + HTML/CSS puro

---

## Estrutura

```
portal-flask/
├── app.py                  # Rotas Flask
├── db.py                   # Banco de dados (Turso)
├── config.py               # Configurações
├── Procfile                # Para deploy no Render
├── requirements.txt
├── .env.exemplo            # Template das variáveis
├── static/
│   └── css/
│       └── style.css       # Todo o CSS (troque cores aqui)
└── templates/
    ├── base.html           # Layout com sidebar
    ├── login.html
    ├── dashboard.html      # Cards de entrega
    ├── entrega.html        # Rastreio + NF + Boletos
    ├── financeiro.html
    ├── trocar_senha.html
    └── admin/
        ├── dashboard.html
        ├── upload.html
        ├── rastreio.html
        ├── clientes.html
        ├── nfs.html
        └── titulos.html
```

---

## Configuração local

```bash
# 1. Clone o repositório
git clone <seu-repositorio>
cd portal-flask

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure o .env
cp .env.exemplo .env
# Edite o .env com suas credenciais do Turso

# 4. Rode
python app.py
# Acesse: http://localhost:5000
```

---

## Deploy no Render (grátis)

1. Suba o projeto no GitHub
2. Acesse [render.com](https://render.com) → **New Web Service**
3. Conecte seu repositório
4. Configure as variáveis de ambiente (mesmo conteúdo do `.env`)
5. O `Procfile` já configura tudo automaticamente

---

## Login

| Usuário | Senha |
|---|---|
| `admin` | valor de `ADMIN_SENHA` no `.env` |
| CNPJ do cliente | senha definida no cadastro |

---

## Personalizar as cores do escritório

Edite o arquivo `static/css/style.css`, linhas 6-8:

```css
--primary:    #1D4ED8;   /* cor principal */
--primary-dk: #1E40AF;   /* tom escuro */
--primary-lt: #EFF6FF;   /* tom claro (fundo) */
```

Ou configure via variáveis de ambiente no `.env`:
```
COR_PRIMARIA=#sua-cor
NOME_ESCRITORIO=Nome do Seu Escritório
```
