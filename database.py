import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Ajuste obrigatório para o SQLAlchemy entender o Postgres
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
    # FORÇA BRUTA: Se for banco em nuvem, garante que tem criptografia SSL (Exigência do Neon.tech)
    if "sslmode=require" not in DATABASE_URL and ("neon.tech" in DATABASE_URL or "render.com" in DATABASE_URL):
        separator = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL += f"{separator}sslmode=require"
        
    IS_POSTGRES = True
    print(f"🟢 PREPARANDO CONEXÃO POSTGRESQL (NUVEM)...")
else:
    DATABASE_URL = "sqlite:///./gestao_local.db"
    IS_POSTGRES = False
    print("🟡 PREPARANDO SQLITE LOCAL")

# O pool_pre_ping evita que conexões adormecidas derrubem o servidor
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def conectar():
    return engine.connect()

def inicializar_banco():
    try:
        # BLOCO 1: Criação das Tabelas Principais
        with conectar() as conn:
            id_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
            
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS usuarios (id {id_type}, nome TEXT, email TEXT, usuario TEXT UNIQUE, senha TEXT, perfil TEXT)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS ordens_servico (id {id_type}, empresa TEXT, numero_os TEXT, cliente TEXT, plataforma TEXT, endereco TEXT, servico_descricao TEXT, relatorio_tecnico TEXT, status TEXT DEFAULT 'Pendente', id_tecnico INTEGER, data_programada DATE, data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS financeiro (id {id_type}, empresa TEXT, descricao TEXT, valor REAL, tipo TEXT, categoria TEXT, status_pagamento TEXT DEFAULT 'Pendente', status_nf TEXT DEFAULT 'Pendente', data_emissao DATE, data_pagamento DATE, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS registro_ponto (id {id_type}, id_tecnico INTEGER, tipo TEXT, data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP, latitude REAL, longitude REAL)"))
            conn.commit()

        # BLOCO 2: Atualização de Colunas do Financeiro (Isolado para não envenenar transação)
        with conectar() as conn:
            try:
                conn.execute(text("ALTER TABLE financeiro ADD COLUMN id_os INTEGER"))
                conn.commit()
            except:
                conn.rollback() # Limpa o erro se a coluna já existir

        with conectar() as conn:
            try:
                conn.execute(text("ALTER TABLE financeiro ADD COLUMN conciliado TEXT DEFAULT 'Não'"))
                conn.commit()
            except:
                conn.rollback()

        # BLOCO 3: Colunas de Hora Extra no Ponto (Novidade!)
        with conectar() as conn:
            try:
                conn.execute(text("ALTER TABLE registro_ponto ADD COLUMN is_he TEXT DEFAULT 'Não'"))
                conn.commit()
            except:
                conn.rollback()

        with conectar() as conn:
            try:
                conn.execute(text("ALTER TABLE registro_ponto ADD COLUMN motivo_he TEXT"))
                conn.commit()
            except:
                conn.rollback()

        # BLOCO 4: Verificação e Criação do Admin
        with conectar() as conn:
            if not conn.execute(text("SELECT id FROM usuarios WHERE usuario = 'admin'")).fetchone():
                conn.execute(text("INSERT INTO usuarios (nome, usuario, senha, perfil) VALUES ('Administrador', 'admin', 'admin123', 'Admin')"))
            conn.commit()
            
        print("✅ BANCO DE DADOS CONECTADO E ESTRUTURA VERIFICADA COM SUCESSO!")
        
    except Exception as e: 
        print(f"❌ ERRO CRÍTICO NO BANCO DE DADOS: {e}")