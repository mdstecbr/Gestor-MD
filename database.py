import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    IS_POSTGRES = True
    print("🟢 CONECTADO AO POSTGRESQL")
else:
    DATABASE_URL = "sqlite:///./gestao_local.db"
    IS_POSTGRES = False
    print("🟡 RODANDO EM SQLITE LOCAL")

engine = create_engine(DATABASE_URL)

def conectar():
    return engine.connect()

def inicializar_banco():
    try:
        with conectar() as conn:
            id_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
            
            # Tabelas base
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS usuarios (id {id_type}, nome TEXT, email TEXT, usuario TEXT UNIQUE, senha TEXT, perfil TEXT)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS ordens_servico (id {id_type}, empresa TEXT, numero_os TEXT, cliente TEXT, plataforma TEXT, endereco TEXT, servico_descricao TEXT, relatorio_tecnico TEXT, status TEXT DEFAULT 'Pendente', id_tecnico INTEGER, data_programada DATE, data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS financeiro (id {id_type}, empresa TEXT, descricao TEXT, valor REAL, tipo TEXT, categoria TEXT, status_pagamento TEXT DEFAULT 'Pendente', status_nf TEXT DEFAULT 'Pendente', data_emissao DATE, data_pagamento DATE, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS registro_ponto (id {id_type}, id_tecnico INTEGER, tipo TEXT, data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP, latitude REAL, longitude REAL)"))
            
            # Colunas da V2 (Contador)
            try:
                conn.execute(text("ALTER TABLE financeiro ADD COLUMN id_os INTEGER"))
                conn.execute(text("ALTER TABLE financeiro ADD COLUMN conciliado TEXT DEFAULT 'Não'"))
            except: pass

            # Admin Inicial
            if not conn.execute(text("SELECT id FROM usuarios WHERE usuario = 'admin'")).fetchone():
                conn.execute(text("INSERT INTO usuarios (nome, usuario, senha, perfil) VALUES ('Administrador', 'admin', 'admin123', 'Admin')"))
            
            conn.commit()
            print("✅ BANCO DE DADOS SINCRONIZADO")
    except Exception as e: print(f"❌ ERRO DB: {e}")