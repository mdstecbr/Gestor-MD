import sqlite3
import os

# Detecta se estamos rodando na Nuvem (Render) ou Localmente
if os.environ.get("RENDER"):
    DB_PATH = "/data/gestao_md.db"
else:
    DB_PATH = "gestao_md.db"

def conectar():
    conn = sqlite3.connect(DB_PATH)
    return conn

def inicializar_banco():
    conn = conectar()
    cursor = conn.cursor()

    # Tabela Usuários
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT,
        usuario TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        perfil TEXT NOT NULL
    )
    ''')

    # Cria o usuário Admin padrão se não existir
    cursor.execute("SELECT id FROM usuarios WHERE usuario = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (nome, usuario, senha, perfil) VALUES ('Administrador', 'admin', 'admin123', 'Admin')")

    # Tabela Ordens de Serviço
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ordens_servico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        numero_os TEXT,
        cliente TEXT NOT NULL,
        plataforma TEXT,
        endereco TEXT,
        servico_descricao TEXT NOT NULL,
        relatorio_tecnico TEXT,
        status TEXT DEFAULT 'Pendente',
        id_tecnico INTEGER,
        data_programada DATE,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_tecnico) REFERENCES usuarios(id)
    )
    ''')

    # Tabela Financeiro
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS financeiro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        tipo TEXT NOT NULL,
        categoria TEXT,
        status_pagamento TEXT DEFAULT 'Pendente',
        status_nf TEXT DEFAULT 'Pendente',
        data_emissao DATE,
        data_pagamento DATE,
        data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()