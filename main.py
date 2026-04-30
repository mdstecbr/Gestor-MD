import os
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import text
import database
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from fpdf import FPDF
import tempfile
import jwt
from passlib.context import CryptContext

# --- PROTEÇÃO ANTI-CRASH: Importação Segura do OneDrive ---
try:
    import onedrive_api
    ONEDRIVE_DISPONIVEL = True
except ImportError:
    ONEDRIVE_DISPONIVEL = False
    print("⚠️ AVISO: Módulo 'onedrive_api.py' ausente. Uploads serão salvos no disco local.")

# --- CONFIGURAÇÃO DE AMBIENTE E PASTAS ---
BASE_DIR = "."
PASTAS_SISTEMA = ["Documentos_OS", "Evidencias_OS", "Comprovantes_FIN"]

for pasta in PASTAS_SISTEMA:
    os.makedirs(os.path.join(BASE_DIR, pasta), exist_ok=True)

app = FastAPI(title="Gestor MD API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    print("🚀 Iniciando Servidor Gestor MD... Conectando ao Banco de Dados.")
    database.inicializar_banco()

def hora_brasil():
    return datetime.utcnow() - timedelta(hours=3)

SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

def disparar_email(destinatario: str, assunto: str, corpo_html: str):
    if not SMTP_EMAIL or not SMTP_PASSWORD or not destinatario:
        print(f"⚠️ SMTP não configurado. Notificação para {destinatario} ignorada.")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Gestor MD <{SMTP_EMAIL}>"
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_html, 'html'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")

# --- MOTOR DE SEGURANÇA (JWT & BCRYPT) ---
SECRET_KEY = os.environ.get("JWT_SECRET", "md_solucoes_super_chave_secreta_2026_!@#")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def gerar_hash_senha(senha: str):
    return pwd_context.hash(senha)

def verificar_senha(senha_pura: str, senha_hash: str):
    if not senha_hash.startswith("$2b$"): 
        return senha_pura == senha_hash
    return pwd_context.verify(senha_pura, senha_hash)

def criar_token_acesso(dados: dict):
    to_encode = dados.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def token_valido(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

# --- MODELOS DE DADOS (PYDANTIC) ---
class LoginRequest(BaseModel):
    usuario: str
    senha: str

class UsuarioRequest(BaseModel):
    nome: str
    email: Optional[str] = ""
    usuario: Optional[str] = ""
    senha: Optional[str] = ""
    perfil: str

class FinanceiroRequest(BaseModel):
    empresa: str
    descricao: str
    valor: float
    tipo: str
    categoria: str
    status_pagamento: str
    status_nf: str
    data_emissao: Optional[str] = None
    data_pagamento: Optional[str] = None
    id_os: Optional[int] = None
    id_cliente: Optional[int] = None
    id_fornecedor: Optional[int] = None
    conciliado: Optional[str] = "Não"

class OSRequest(BaseModel):
    empresa: str
    numero_os: str
    cliente: str
    id_cliente: Optional[int] = None
    endereco: Optional[str] = ""
    plataforma: Optional[str] = ""
    servico_descricao: str
    orientacoes_admin: Optional[str] = ""
    id_tecnico: int
    data_programada: Optional[str] = None
    status: str

class StatusOSRequest(BaseModel):
    status: str
    relatorio_tecnico: Optional[str] = ""

class PontoRequest(BaseModel):
    id_tecnico: int
    tipo: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_he: Optional[str] = "Não"
    motivo_he: Optional[str] = ""

class ClienteRequest(BaseModel):
    nome: str
    email: Optional[str] = ""
    telefone: Optional[str] = ""
    cnpj_cpf: Optional[str] = ""
    endereco: Optional[str] = ""

class FornecedorRequest(BaseModel):
    nome: str
    email: Optional[str] = ""
    telefone: Optional[str] = ""
    cnpj_cpf: Optional[str] = ""
    categoria: Optional[str] = ""

# --- ROTAS ABERTAS E DE AUTENTICAÇÃO ---

@app.post("/api/login")
def login(req: LoginRequest):
    with database.conectar() as conn:
        query = text("SELECT id, nome, perfil, senha FROM usuarios WHERE usuario = :u")
        user = conn.execute(query, {"u": req.usuario}).fetchone()
        
        if not user or not verificar_senha(req.senha, user[3]):
            raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

        token_data = {"sub": str(user[0]), "nome": user[1], "perfil": user[2]}
        token_jwt = criar_token_acesso(token_data)
            
        return {"id": user[0], "nome": user[1], "perfil": user[2], "access_token": token_jwt}

@app.get("/api/debug/ler-codigo", dependencies=[Depends(token_valido)])
def ler_codigo_fonte():
    try:
        with open("main.py", "r", encoding="utf-8") as file:
            return PlainTextResponse(file.read())
    except Exception as e:
        return PlainTextResponse(f"Erro ao ler arquivo: {str(e)}")

# --- ROTAS PROTEGIDAS (ERP MD SOLUÇÕES) ---

@app.get("/api/dashboard")
def get_dashboard(inicio: Optional[str] = None, fim: Optional[str] = None, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        f_fin = "WHERE status_pagamento IN ('Pago', 'Pendente')"
        f_os = "WHERE 1=1"
        params = {}
        if inicio and fim:
            f_fin += " AND date(COALESCE(data_pagamento, data_emissao, data_registro)) BETWEEN :inicio AND :fim"
            f_os += " AND date(data_programada) BETWEEN :inicio AND :fim"
            params = {"inicio": inicio, "fim": fim}
            
        df_fin = pd.read_sql_query(text(f"SELECT valor, tipo, status_pagamento, COALESCE(data_pagamento, data_emissao, date(data_registro)) as data FROM financeiro {f_fin}"), conn, params=params)
        df_os = pd.read_sql_query(text(f"SELECT status FROM ordens_servico {f_os}"), conn, params=params)
        
    fat_realizado = float(df_fin[(df_fin['tipo'] == 'Entrada') & (df_fin['status_pagamento'] == 'Pago')]['valor'].sum()) if not df_fin.empty else 0
    fat_previsto = float(df_fin[(df_fin['tipo'] == 'Entrada') & (df_fin['status_pagamento'] == 'Pendente')]['valor'].sum()) if not df_fin.empty else 0
    desp_realizado = float(df_fin[(df_fin['tipo'] == 'Saída') & (df_fin['status_pagamento'] == 'Pago')]['valor'].sum()) if not df_fin.empty else 0
    desp_previsto = float(df_fin[(df_fin['tipo'] == 'Saída') & (df_fin['status_pagamento'] == 'Pendente')]['valor'].sum()) if not df_fin.empty else 0
    
    grafico_fin = {"datas": [], "rec_paga": [], "rec_prev": [], "desp_paga": [], "desp_prev": []}
    if not df_fin.empty:
        df_fin['data'] = pd.to_datetime(df_fin['data']).dt.strftime('%Y-%m-%d')
        df_fin['chave_agrupamento'] = df_fin['tipo'] + '_' + df_fin['status_pagamento']
        grouped = df_fin.groupby(['data', 'chave_agrupamento'])['valor'].sum().unstack(fill_value=0).reset_index()
        grouped = grouped.sort_values('data')
        for col in ['Entrada_Pago', 'Entrada_Pendente', 'Saída_Pago', 'Saída_Pendente']:
            if col not in grouped.columns: grouped[col] = 0
                
        grafico_fin["datas"] = grouped['data'].tolist()
        grafico_fin["rec_paga"] = grouped['Entrada_Pago'].tolist()
        grafico_fin["rec_prev"] = grouped['Entrada_Pendente'].tolist()
        grafico_fin["desp_paga"] = grouped['Saída_Pago'].tolist()
        grafico_fin["desp_prev"] = grouped['Saída_Pendente'].tolist()

    return {
        "faturamento_global": fat_realizado, "faturamento_previsto": fat_previsto,
        "despesas_globais": desp_realizado, "despesas_previstas": desp_previsto,
        "total_os": len(df_os), "grafico_os": df_os['status'].value_counts().to_dict() if not df_os.empty else {},
        "grafico_fin": grafico_fin
    }

@app.get("/api/financeiro")
def list_financeiro(inicio: Optional[str] = None, fim: Optional[str] = None, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = """
            SELECT f.*, c.nome as nome_cliente, fo.nome as nome_fornecedor 
            FROM financeiro f
            LEFT JOIN clientes c ON f.id_cliente = c.id
            LEFT JOIN fornecedores fo ON f.id_fornecedor = fo.id
        """
        params = {}
        if inicio and fim:
            query += " WHERE date(COALESCE(f.data_pagamento, f.data_registro)) BETWEEN :i AND :f"
            params = {"i": inicio, "f": fim}
        query += " ORDER BY f.id DESC"
        df = pd.read_sql_query(text(query), conn, params=params)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")

@app.post("/api/financeiro")
def criar_financeiro(req: FinanceiroRequest, usuario_logado: dict = Depends(token_valido)):
    dh_br = hora_brasil().strftime("%Y-%m-%d %H:%M:%S")
    with database.conectar() as conn:
        res = conn.execute(text("""
            INSERT INTO financeiro 
            (empresa, descricao, valor, tipo, categoria, status_pagamento, status_nf, data_emissao, data_pagamento, id_os, id_cliente, id_fornecedor, conciliado, data_registro) 
            VALUES (:emp, :desc, :val, :tipo, :cat, :spg, :snf, :dem, :dpg, :ido, :idc, :idf, :conc, :dreg)
            RETURNING id
        """), {
            "emp": req.empresa, "desc": req.descricao, "val": req.valor, "tipo": req.tipo, "cat": req.categoria,
            "spg": req.status_pagamento, "snf": req.status_nf, "dem": req.data_emissao, "dpg": req.data_pagamento,
            "ido": req.id_os, "idc": req.id_cliente, "idf": req.id_fornecedor, "conc": req.conciliado, "dreg": dh_br
        })
        novo_id = res.scalar()
        conn.commit()
    return {"status": "ok", "id": novo_id}

@app.put("/api/financeiro/{id}")
def atualizar_financeiro(id: int, req: FinanceiroRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        conn.execute(text("""
            UPDATE financeiro SET 
                empresa=:emp, descricao=:desc, valor=:val, tipo=:tipo, categoria=:cat, 
                status_pagamento=:spg, status_nf=:snf, data_emissao=:dem, data_pagamento=:dpg, 
                id_os=:ido, id_cliente=:idc, id_fornecedor=:idf, conciliado=:conc
            WHERE id=:id
        """), {
            "emp": req.empresa, "desc": req.descricao, "val": req.valor, "tipo": req.tipo, "cat": req.categoria,
            "spg": req.status_pagamento, "snf": req.status_nf, "dem": req.data_emissao, "dpg": req.data_pagamento,
            "ido": req.id_os, "idc": req.id_cliente, "idf": req.id_fornecedor, "conc": req.conciliado, "id": id
        })
        conn.commit()
    return {"status": "ok"}

@app.get("/api/relatorio/financeiro/pdf")
def gerar_pdf_financeiro(inicio: Optional[str] = None, fim: Optional[str] = None, token: str = None):
    if token:
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except:
            raise HTTPException(status_code=401, detail="Não autorizado")
    else:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
            
    with database.conectar() as conn:
        query = "SELECT * FROM financeiro WHERE status_pagamento = 'Pago'"
        params = {}
        if inicio and fim:
            query += " AND date(COALESCE(data_pagamento, data_registro)) BETWEEN :i AND :f"
            params = {"i": inicio, "f": fim}
        query += " ORDER BY data_pagamento ASC"
        df = pd.read_sql_query(text(query), conn, params=params)

    total_entrada = df[df['tipo'] == 'Entrada']['valor'].sum() if not df.empty else 0
    total_saida = df[df['tipo'] == 'Saída']['valor'].sum() if not df.empty else 0
    saldo = total_entrada - total_saida

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="MD Solucoes - Relatorio de Fechamento Financeiro", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    periodo_texto = f"Periodo: {inicio} ate {fim}" if inicio and fim else "Periodo: Todo o Historico"
    pdf.cell(200, 10, txt=periodo_texto, ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Resumo Consolidado:", ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(200, 8, txt=f"Total de Entradas: R$ {total_entrada:.2f}", ln=True)
    pdf.cell(200, 8, txt=f"Total de Saidas: R$ {total_saida:.2f}", ln=True)
    pdf.cell(200, 8, txt=f"SALDO LIQUIDO: R$ {saldo:.2f}", ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 8, "Data", border=1)
    pdf.cell(80, 8, "Descricao", border=1)
    pdf.cell(40, 8, "Categoria", border=1)
    pdf.cell(40, 8, "Valor", border=1)
    pdf.ln()

    pdf.set_font("Arial", '', 9)
    for index, row in df.iterrows():
        data_str = str(row['data_pagamento']) if pd.notna(row['data_pagamento']) else str(row['data_emissao'])
        desc = str(row['descricao']).encode('ascii', 'ignore').decode('ascii')[:35]
        cat = str(row['categoria']).encode('ascii', 'ignore').decode('ascii')[:15]
        val = f"R$ {row['valor']:.2f} ({row['tipo'][0]})"
        pdf.cell(30, 8, data_str, border=1)
        pdf.cell(80, 8, desc, border=1)
        pdf.cell(40, 8, cat, border=1)
        pdf.cell(40, 8, val, border=1)
        pdf.ln()

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp.name)
    return FileResponse(temp.name, media_type='application/pdf', filename=f"Fechamento_MD.pdf")

@app.get("/api/clientes")
def listar_clientes(usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        res = conn.execute(text("SELECT * FROM clientes ORDER BY nome")).mappings().fetchall()
        return [dict(r) for r in res]

@app.post("/api/clientes")
def criar_cliente(req: ClienteRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        conn.execute(text("INSERT INTO clientes (nome, email, telefone, cnpj_cpf, endereco) VALUES (:n, :e, :t, :c, :end)"), 
                     {"n": req.nome, "e": req.email, "t": req.telefone, "c": req.cnpj_cpf, "end": req.endereco})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/fornecedores")
def listar_fornecedores(usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        res = conn.execute(text("SELECT * FROM fornecedores ORDER BY nome")).mappings().fetchall()
        return [dict(r) for r in res]

@app.post("/api/fornecedores")
def criar_fornecedor(req: FornecedorRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        conn.execute(text("INSERT INTO fornecedores (nome, email, telefone, cnpj_cpf, categoria) VALUES (:n, :e, :t, :c, :cat)"), 
                     {"n": req.nome, "e": req.email, "t": req.telefone, "c": req.cnpj_cpf, "cat": req.categoria})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/os")
def list_os(usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = """
            SELECT os.*, u.nome as tecnico 
            FROM ordens_servico os 
            LEFT JOIN usuarios u ON os.id_tecnico = u.id 
            ORDER BY os.id DESC
        """
        df = pd.read_sql_query(text(query), conn)
    return df.to_dict(orient="records")

@app.post("/api/os")
def criar_os(req: OSRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        res = conn.execute(text("""
            INSERT INTO ordens_servico 
            (empresa, numero_os, cliente, id_cliente, endereco, plataforma, servico_descricao, orientacoes_admin, id_tecnico, data_programada, status) 
            VALUES (:e, :n, :c, :idc, :end, :p, :sd, :oa, :it, :dp, :st)
            RETURNING id
        """), {
            "e": req.empresa, "n": req.numero_os, "c": req.cliente, "idc": req.id_cliente,
            "end": req.endereco, "p": req.plataforma, "sd": req.servico_descricao, 
            "oa": req.orientacoes_admin, "it": req.id_tecnico, "dp": req.data_programada, "st": req.status
        })
        novo_id = res.scalar()
        conn.commit()
    return {"status": "ok", "id": novo_id}

@app.put("/api/os/{id}")
def atualizar_os(id: int, req: OSRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        conn.execute(text("""
            UPDATE ordens_servico SET 
                empresa=:e, numero_os=:n, cliente=:c, id_cliente=:idc, endereco=:end, plataforma=:p, 
                servico_descricao=:sd, orientacoes_admin=:oa, id_tecnico=:it, data_programada=:dp, status=:st
            WHERE id=:id
        """), {
            "e": req.empresa, "n": req.numero_os, "c": req.cliente, "idc": req.id_cliente,
            "end": req.endereco, "p": req.plataforma, "sd": req.servico_descricao, 
            "oa": req.orientacoes_admin, "it": req.id_tecnico, "dp": req.data_programada, "st": req.status, "id": id
        })
        conn.commit()
    return {"status": "ok"}

@app.get("/api/minhas-os/{id_tecnico}")
def list_my_os(id_tecnico: int, inicio: Optional[str] = None, fim: Optional[str] = None, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = "SELECT * FROM ordens_servico WHERE id_tecnico = :id AND status != 'Concluído'"
        params = {"id": id_tecnico}
        if inicio and fim:
            query += " AND date(data_programada) BETWEEN :i AND :f"
            params.update({"i": inicio, "f": fim})
        query += " ORDER BY data_programada ASC"
        df = pd.read_sql_query(text(query), conn, params=params)
    return df.to_dict(orient="records")

@app.put("/api/os/{id}/status")
def update_os_status(id: int, req: StatusOSRequest, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = text("UPDATE ordens_servico SET status = :s, relatorio_tecnico = :r WHERE id = :id")
        conn.execute(query, {"s": req.status, "r": req.relatorio_tecnico, "id": id})
        conn.commit()
    return {"status": "ok"}

@app.post("/api/ponto")
def bater_ponto(req: PontoRequest, usuario_logado: dict = Depends(token_valido)):
    dh_br = hora_brasil().strftime("%Y-%m-%d %H:%M:%S")
    with database.conectar() as conn:
        query = text("INSERT INTO registro_ponto (id_tecnico, tipo, latitude, longitude, data_hora, is_he, motivo_he) VALUES (:id, :t, :la, :lo, :dh, :he, :mot)")
        conn.execute(query, {"id": req.id_tecnico, "t": req.tipo, "la": req.lat, "lo": req.lng, "dh": dh_br, "he": req.is_he, "mot": req.motivo_he})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/ponto/status/{id_tecnico}")
def ponto_status(id_tecnico: int, usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = text("SELECT tipo FROM registro_ponto WHERE id_tecnico = :id ORDER BY id DESC LIMIT 1")
        res = conn.execute(query, {"id": id_tecnico}).fetchone()
    return {"ultimo_registro": res[0] if res else "Saída"}

@app.get("/api/ponto/admin")
def list_ponto(usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        query = """
            SELECT p.*, COALESCE(u.nome, 'Técnico Excluído (Inativo)') as tecnico 
            FROM registro_ponto p 
            LEFT JOIN usuarios u ON p.id_tecnico = u.id 
            ORDER BY p.id DESC LIMIT 200
        """
        df = pd.read_sql_query(text(query), conn)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")

@app.get("/api/usuarios")
def list_users(usuario_logado: dict = Depends(token_valido)):
    if usuario_logado["perfil"] != "Admin":
        raise HTTPException(status_code=403, detail="Acesso negado.")
    with database.conectar() as conn:
        df = pd.read_sql_query(text("SELECT id, nome, usuario, perfil, email FROM usuarios ORDER BY id ASC"), conn)
    return df.to_dict(orient="records")

@app.post("/api/usuarios")
def create_user(req: UsuarioRequest, tasks: BackgroundTasks, usuario_logado: dict = Depends(token_valido)):
    if usuario_logado["perfil"] != "Admin": 
        raise HTTPException(status_code=403, detail="Acesso negado.")
        
    senha_segura = gerar_hash_senha(req.senha)
    with database.conectar() as conn:
        query = text("INSERT INTO usuarios (nome, email, usuario, senha, perfil) VALUES (:n, :e, :u, :s, :p)")
        conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "s": senha_segura, "p": req.perfil})
        conn.commit()
        
    if req.email:
        html = f"<h2>Bem-vindo à MD Soluções</h2><p>Seu acesso foi criado.</p><p><b>Login:</b> {req.usuario}<br><b>Senha:</b> {req.senha}</p>"
        tasks.add_task(disparar_email, req.email, "Seu Acesso ao Gestor MD", html)
    return {"status": "ok"}

@app.put("/api/usuarios/{id}")
def update_user(id: int, req: UsuarioRequest, usuario_logado: dict = Depends(token_valido)):
    if usuario_logado["perfil"] != "Admin": 
        raise HTTPException(status_code=403, detail="Acesso negado.")
        
    with database.conectar() as conn:
        if req.senha and req.senha.strip() != "":
            senha_segura = gerar_hash_senha(req.senha)
            query = text("UPDATE usuarios SET nome=:n, email=:e, usuario=:u, perfil=:p, senha=:s WHERE id=:id")
            conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "p": req.perfil, "s": senha_segura, "id": id})
        else:
            query = text("UPDATE usuarios SET nome=:n, email=:e, usuario=:u, perfil=:p WHERE id=:id")
            conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "p": req.perfil, "id": id})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/tecnicos")
def get_tecnicos(usuario_logado: dict = Depends(token_valido)):
    with database.conectar() as conn:
        res = conn.execute(text("SELECT id, nome FROM usuarios WHERE perfil='Tecnico'")).fetchall()
    return [{"id": r[0], "nome": r[1]} for r in res]

@app.delete("/api/{rota}/{id}")
def delete_item(rota: str, id: int, usuario_logado: dict = Depends(token_valido)):
    if usuario_logado["perfil"] != "Admin": 
        raise HTTPException(status_code=403, detail="Acesso negado.")
        
    tabela = "ordens_servico" if rota == "os" else "usuarios" if rota == "usuarios" else "financeiro" if rota == "financeiro" else rota
    with database.conectar() as conn:
        conn.execute(text(f"DELETE FROM {tabela} WHERE id = :id"), {"id": id})
        conn.commit()
    return {"status": "ok"}

@app.post("/api/upload/{modulo}/{id}")
async def upload_file(modulo: str, id: int, arquivos: List[UploadFile] = File(...), usuario_logado: dict = Depends(token_valido)):
    mapeamento_pastas = {"documentos": f"Documentos_OS/OS_{id}", "evidencias": f"Evidencias_OS/OS_{id}", "comprovantes": f"Comprovantes_FIN/FIN_{id}"}
    if modulo not in mapeamento_pastas: raise HTTPException(status_code=400, detail="Módulo inválido")
    path_dest = mapeamento_pastas[modulo]
    for f in arquivos:
        content = await f.read()
        if ONEDRIVE_DISPONIVEL and onedrive_api.is_configured():
            onedrive_api.upload_arquivo(content, f.filename, path_dest)
        else:
            local_path = os.path.join(BASE_DIR, path_dest)
            os.makedirs(local_path, exist_ok=True)
            with open(os.path.join(local_path, f.filename), "wb") as buffer: buffer.write(content)
    return {"status": "ok"}

@app.get("/api/arquivos/{modulo}/{id}")
def list_files(modulo: str, id: int, usuario_logado: dict = Depends(token_valido)):
    lista_arquivos = []
    if not (ONEDRIVE_DISPONIVEL and onedrive_api.is_configured()):
        mapeamento_pastas = {"documentos": f"Documentos_OS/OS_{id}", "evidencias": f"Evidencias_OS/OS_{id}", "comprovantes": f"Comprovantes_FIN/FIN_{id}"}
        if modulo in mapeamento_pastas:
            pasta_alvo = os.path.join(BASE_DIR, mapeamento_pastas[modulo])
            if os.path.exists(pasta_alvo): lista_arquivos = os.listdir(pasta_alvo)
    return {"arquivos": lista_arquivos}

@app.get("/api/download/{modulo}/{id}/{arquivo}")
def download_file(modulo: str, id: int, arquivo: str, token: str = None):
    # Downloads via tag <a> não enviam headers. Exigimos o token via query string para segurança.
    if not token:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Acesso negado")

    mapeamento_pastas = {"documentos": f"Documentos_OS/OS_{id}", "evidencias": f"Evidencias_OS/OS_{id}", "comprovantes": f"Comprovantes_FIN/FIN_{id}"}
    if modulo not in mapeamento_pastas: raise HTTPException(status_code=400, detail="Módulo inválido")
    path_dest = mapeamento_pastas[modulo]
    
    if ONEDRIVE_DISPONIVEL and onedrive_api.is_configured():
        link = onedrive_api.get_download_link(arquivo, path_dest)
        if link: return RedirectResponse(url=link)
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no OneDrive")
    else:
        full_path = os.path.join(BASE_DIR, path_dest, arquivo)
        if os.path.exists(full_path): return FileResponse(full_path)
        raise HTTPException(status_code=404, detail="Arquivo não encontrado localmente")

app.mount("/static", StaticFiles(directory=os.getcwd()), name="static")

@app.get("/manifest.json")
def get_manifest(): return FileResponse("manifest.json")

@app.get("/sw.js")
def get_sw(): return FileResponse("sw.js", media_type="application/javascript")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("index.html", "r", encoding="utf-8") as f: return f.read()