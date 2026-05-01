from sqlalchemy import create_engine, text

# ⚠️ TÁTICA DE INFRAESTRUTURA: Cole a sua URL oficial do Neon aqui dentro das aspas
# (A mesma que está no painel do Render nas Variáveis de Ambiente)
DATABASE_URL = "postgresql://neondb_owner:npg_y9McSbXYUKh3@ep-calm-dew-acaj7zvh.sa-east-1.aws.neon.tech/neondb?sslmode=require" 

print("🚀 Conectando diretamente ao banco de produção na nuvem...")

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Força a injeção da nova coluna na tabela
        conn.execute(text("ALTER TABLE fornecedores ADD COLUMN empresa VARCHAR(100) DEFAULT 'Grupo MD';"))
        conn.commit()
        print("✅ SUCESSO ABSOLUTO: Coluna 'empresa' adicionada na tabela de fornecedores no Neon!")
except Exception as e:
    print(f"⚠️ Aviso do Banco (Pode ignorar se a mensagem for 'column already exists'):\n{e}")