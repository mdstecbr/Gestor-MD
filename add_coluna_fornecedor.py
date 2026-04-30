import os
from dotenv import load_dotenv
load_dotenv()
import database
from sqlalchemy import text

print("Iniciando alteração no banco de dados...")
try:
    with database.conectar() as conn:
        # Adiciona a coluna 'empresa' na tabela de fornecedores
        conn.execute(text("ALTER TABLE fornecedores ADD COLUMN empresa VARCHAR(100) DEFAULT 'Grupo MD';"))
        conn.commit()
        print("✅ Coluna 'empresa' adicionada com sucesso na tabela de fornecedores!")
except Exception as e:
    # Se der erro porque a coluna já existe, ele avisa e segue a vida
    print(f"Aviso (Pode ignorar se a coluna já existir): {e}")