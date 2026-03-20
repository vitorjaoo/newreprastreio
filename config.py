import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "limarepresentações..")
    NOME_ESCRITORIO = "Lima Representações"
    COR_PRIMARIA = "#0f172a"
    COR_SECUNDARIA = "#3b82f6"
    
    # --- BANCO DE DADOS (TURSO) ---
    # Estas linhas garantem que o db.py continue a funcionar
    TURSO_DATABASE_URL = os.getenv("libsql://rasrep-vitorrastrep.aws-us-east-2.turso.io")
    TURSO_AUTH_TOKEN = os.getenv("eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzQwNDAyOTYsImlkIjoiMDE5Y2Y2YjgtMWQwMS03YTRhLTlmMTAtZDU3ZDRiYzUwZWM4IiwicmlkIjoiNWUwZmFiOGEtZGMwZS00MmI2LTlmMWMtZDFiNmU4ZjMwMjY3In0.hrZEmnZmNXq_jVEPS1qcY_IErm_1iikxdWMlukgs1dRnbrxx127Vn4d-hr5Qj4TioidL-vUc3Uc8t3ZPL9FZAA")

    # --- ACESSOS ADMINISTRATIVOS ---
    # Senha do Administrador (você)
    ADMIN_SENHA = os.getenv("ADMIN_SENHA", "123456")
    
    # Senha da Equipe (Apenas visualização)
    EQUIPE_SENHA = os.getenv("EQUIPE_SENHA", "equipe123")

    # --- EMAIL (RESEND) ---
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
