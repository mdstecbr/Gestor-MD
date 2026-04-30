import os
from dotenv import load_dotenv

# 🚀 TÁTICA DE ENGENHARIA: Carrega as variáveis do arquivo .env (URL do Neon) 
# ANTES de importar o módulo database. Assim forçamos a conexão na nuvem!
load_dotenv()

import database
from sqlalchemy import text
from passlib.context import CryptContext

# Inicializa o motor de criptografia com as mesmas regras do nosso main.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def rodar_migracao():
    print("Iniciando varredura de segurança no banco de dados...")
    
    try:
        with database.conectar() as conn:
            # Coleta todos os usuários cadastrados no banco da nuvem
            usuarios = conn.execute(text("SELECT id, usuario, senha FROM usuarios")).fetchall()
            
            atualizados = 0
            for u in usuarios:
                user_id = u[0]
                login = u[1]
                senha_atual = str(u[2]) if u[2] else ""
                
                # A mágica: Verifica se a senha já é um Hash do Bcrypt (começa com $2b$)
                if senha_atual and not senha_atual.startswith("$2b$"):
                    senha_segura = pwd_context.hash(senha_atual)
                    
                    # Sobrescreve a senha de texto puro pelo Hash indescritível
                    conn.execute(
                        text("UPDATE usuarios SET senha = :s WHERE id = :id"),
                        {"s": senha_segura, "id": user_id}
                    )
                    atualizados += 1
                    print(f"[LOCK] Usuário '{login}' criptografado com sucesso.")
                else:
                    print(f"[OK] Usuário '{login}' já estava seguro ou sem senha. Pulando...")
            
            # Confirma a transação no banco Neon
            conn.commit()
            print(f"\n🚀 Migração concluída! {atualizados} senhas foram convertidas para Bcrypt.")
            
    except Exception as e:
        print(f"❌ Erro crítico durante a migração: {str(e)}")

if __name__ == "__main__":
    rodar_migracao()