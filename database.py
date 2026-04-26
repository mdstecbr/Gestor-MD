import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = "sqlite:///./gestao_local.db"

engine = create_engine(DATABASE_URL)

def conectar():
    return engine.connect()

def inicializar_banco():
    try:
        with conectar() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nome TEXT, email TEXT, usuario TEXT UNIQUE, senha TEXT, perfil TEXT)"))
            
            check_admin = conn.execute(text("SELECT id FROM usuarios WHERE usuario = 'admin'")).fetchone()
            if not check_admin:
                conn.execute(text("INSERT INTO usuarios (nome, usuario, senha, perfil) VALUES ('Administrador', 'admin', 'admin123', 'Admin')"))
            
            conn.execute(text("CREATE TABLE IF NOT EXISTS ordens_servico (id SERIAL PRIMARY KEY, empresa TEXT, numero_os TEXT, cliente TEXT, plataforma TEXT, endereco TEXT, servico_descricao TEXT, relatorio_tecnico TEXT, status TEXT DEFAULT 'Pendente', id_tecnico INTEGER, data_programada DATE, data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            
            conn.execute(text("CREATE TABLE IF NOT EXISTS financeiro (id SERIAL PRIMARY KEY, empresa TEXT, descricao TEXT, valor REAL, tipo TEXT, categoria TEXT, status_pagamento TEXT DEFAULT 'Pendente', status_nf TEXT DEFAULT 'Pendente', data_emissao DATE, data_pagamento DATE, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.commit()
            print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"ALERTA: Erro ao conectar no Banco de Dados: {e}")