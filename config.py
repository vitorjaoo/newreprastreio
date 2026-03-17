import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY          = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
    TURSO_DATABASE_URL  = os.getenv("TURSO_DATABASE_URL")
    TURSO_AUTH_TOKEN    = os.getenv("TURSO_AUTH_TOKEN")
    ADMIN_SENHA         = os.getenv("ADMIN_SENHA", "admin123")
    ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
    RESEND_API_KEY      = os.getenv("RESEND_API_KEY", "")

    # Identidade visual — troque aqui quando tiver as cores do escritório
    COR_PRIMARIA        = os.getenv("COR_PRIMARIA",  "#1D4ED8")   # azul
    COR_SECUNDARIA      = os.getenv("COR_SECUNDARIA","#1E40AF")   # azul escuro
    NOME_ESCRITORIO     = os.getenv("NOME_ESCRITORIO", "Portal do Cliente")
