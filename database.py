import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    IS_POSTGRES = True
else:
    DATABASE_URL = "sqlite:///./gestao_local.db"
    IS_POSTGRES = False

engine = create_engine(DATABASE_URL)

def conectar():
    return engine.connect()

def inicializar_banco():
    try:
        with conectar() as conn:
            # O PULO DO GATO: Se for Postgres usa SERIAL, se for SQLite usa AUTOINCREMENT
            id_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
            
            # Tabela Usuários
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS usuarios (id {id_type}, nome TEXT, email TEXT, usuario TEXT UNIQUE, senha TEXT, perfil TEXT)"))
            
            check_admin = conn.execute(text("SELECT id FROM usuarios WHERE usuario = 'admin'")).fetchone()
            if not check_admin:
                conn.execute(text("INSERT INTO usuarios (nome, usuario, senha, perfil) VALUES ('Administrador', 'admin', 'admin123', 'Admin')"))
            
            # Tabela OS
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS ordens_servico (id {id_type}, empresa TEXT, numero_os TEXT, cliente TEXT, plataforma TEXT, endereco TEXT, servico_descricao TEXT, relatorio_tecnico TEXT, status TEXT DEFAULT 'Pendente', id_tecnico INTEGER, data_programada DATE, data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            
            # Tabela Financeiro
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS financeiro (id {id_type}, empresa TEXT, descricao TEXT, valor REAL, tipo TEXT, categoria TEXT, status_pagamento TEXT DEFAULT 'Pendente', status_nf TEXT DEFAULT 'Pendente', data_emissao DATE, data_pagamento DATE, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            
            conn.commit()
            print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"ALERTA: Erro ao conectar no Banco de Dados: {e}")