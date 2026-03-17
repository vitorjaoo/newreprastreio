import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY          = os.getenv("SECRET_KEY", "limarepresentacoes..")
    TURSO_DATABASE_URL  = os.getenv("libsql://rasrep-vitorrastrep.aws-us-east-2.turso.io")
    TURSO_AUTH_TOKEN    = os.getenv("eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzM3NzIxNDIsImlkIjoiMDE5Y2Y2YjgtMWQwMS03YTRhLTlmMTAtZDU3ZDRiYzUwZWM4IiwicmlkIjoiNWUwZmFiOGEtZGMwZS00MmI2LTlmMWMtZDFiNmU4ZjMwMjY3In0.YsrURbRJdjYAKkNnR9dEb_jlAL4sUPC52pbFDh6LnUYEeo87dUTENFy55kNvB5B5TTIic-Oe6P1CDsMxgMJ-BA")
    ADMIN_SENHA         = os.getenv("ADMIN_SENHA", "admin123")
    ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
    RESEND_API_KEY      = os.getenv("RESEND_API_KEY", "")

    # Identidade visual — troque aqui quando tiver as cores do escritório
    COR_PRIMARIA        = os.getenv("COR_PRIMARIA",  "#1D4ED8")   # azul
    COR_SECUNDARIA      = os.getenv("COR_SECUNDARIA","#1E40AF")   # azul escuro
    NOME_ESCRITORIO     = os.getenv("Lima Representações", "Portal do Cliente")
