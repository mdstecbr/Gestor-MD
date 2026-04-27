from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import text
import database
import pandas as pd
import os
import smtplib
import shutil
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import onedrive_api
from datetime import datetime

# --- CONFIGURAÇÃO DE AMBIENTE E PASTAS ---
BASE_DIR = "."
PASTA_DOCS = os.path.join(BASE_DIR, "Documentos_OS")
PASTA_EVID = os.path.join(BASE_DIR, "Evidencias_OS")

# Garante que as pastas locais existem (fallback caso OneDrive não esteja configurado)
os.makedirs(PASTA_DOCS, exist_ok=True)
os.makedirs(PASTA_EVID, exist_ok=True)

# Inicializa a estrutura do Banco de Dados (Postgres ou SQLite)
database.inicializar_banco()

app = FastAPI(title="Gestor MD API")

# Configuração de CORS para permitir que o Frontend comunique com o Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURAÇÃO DE E-MAIL (GMAIL SMTP) ---
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

def disparar_email(destinatario: str, assunto: str, corpo_html: str):
    """Função auxiliar para envio de e-mails via Gmail SMTP"""
    if not SMTP_EMAIL or not SMTP_PASSWORD or not destinatario:
        print(f"Aviso: E-mail para {destinatario} ignorado (Faltam credenciais SMTP).")
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
        print(f"E-mail enviado com sucesso para: {destinatario}")
    except Exception as e:
        print(f"Falha ao enviar e-mail: {e}")

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

class OSRequest(BaseModel):
    empresa: str
    numero_os: str
    cliente: str
    plataforma: Optional[str] = ""
    endereco: Optional[str] = ""
    servico_descricao: str
    id_tecnico: int
    data_programada: str
    relatorio_tecnico: Optional[str] = ""
    status: Optional[str] = "Pendente"

class StatusOSRequest(BaseModel):
    status: str
    relatorio_tecnico: Optional[str] = ""

class PontoRequest(BaseModel):
    id_tecnico: int
    tipo: str # 'Entrada' ou 'Saída'
    lat: Optional[float] = None
    lng: Optional[float] = None

# --- ROTAS DE AUTENTICAÇÃO ---

@app.post("/api/login")
def login(req: LoginRequest):
    with database.conectar() as conn:
        query = text("SELECT id, nome, perfil FROM usuarios WHERE usuario = :u AND senha = :s")
        user = conn.execute(query, {"u": req.usuario, "s": req.senha}).fetchone()
        if user:
            return {"id": user[0], "nome": user[1], "perfil": user[2]}
    raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

# --- ROTAS DE DASHBOARD ---

@app.get("/api/dashboard")
def get_dashboard(inicio: Optional[str] = None, fim: Optional[str] = None):
    with database.conectar() as conn:
        f_fin = "WHERE status_pagamento = 'Pago'"
        f_os = "WHERE 1=1"
        params = {}
        
        if inicio and fim:
            f_fin += " AND date(data_pagamento) BETWEEN :inicio AND :fim"
            f_os += " AND date(data_programada) BETWEEN :inicio AND :fim"
            params = {"inicio": inicio, "fim": fim}
            
        df_fin = pd.read_sql_query(text(f"SELECT valor, tipo FROM financeiro {f_fin}"), conn, params=params)
        df_os = pd.read_sql_query(text(f"SELECT status FROM ordens_servico {f_os}"), conn, params=params)
        
    return {
        "faturamento_global": float(df_fin[df_fin['tipo']=='Entrada']['valor'].sum()) if not df_fin.empty else 0,
        "despesas_globais": float(df_fin[df_fin['tipo']=='Saída']['valor'].sum()) if not df_fin.empty else 0,
        "total_os": len(df_os),
        "grafico_os": df_os['status'].value_counts().to_dict() if not df_os.empty else {}
    }

# --- ROTAS FINANCEIRAS (CRUD) ---

@app.get("/api/financeiro")
def list_financeiro():
    with database.conectar() as conn:
        df = pd.read_sql_query(text("SELECT * FROM financeiro ORDER BY id DESC"), conn)
    return df.to_dict(orient="records")

@app.post("/api/financeiro")
def add_financeiro(req: FinanceiroRequest):
    with database.conectar() as conn:
        query = text("""INSERT INTO financeiro (empresa, descricao, valor, tipo, categoria, status_pagamento, status_nf, data_emissao, data_pagamento) 
                        VALUES (:emp, :des, :val, :tip, :cat, :spg, :snf, :dem, :dpg)""")
        conn.execute(query, {
            "emp": req.empresa, "des": req.descricao, "val": req.valor, "tip": req.tipo,
            "cat": req.categoria, "spg": req.status_pagamento, "snf": req.status_nf,
            "dem": req.data_emissao, "dpg": req.data_pagamento
        })
        conn.commit()
    return {"status": "ok"}

@app.put("/api/financeiro/{id}")
def update_financeiro(id: int, req: FinanceiroRequest):
    with database.conectar() as conn:
        query = text("""UPDATE financeiro SET empresa=:emp, descricao=:des, valor=:val, tipo=:tip, categoria=:cat, 
                        status_pagamento=:spg, status_nf=:snf, data_emissao=:dem, data_pagamento=:dpg WHERE id=:id""")
        conn.execute(query, {
            "emp": req.empresa, "des": req.descricao, "val": req.valor, "tip": req.tipo, "cat": req.categoria,
            "spg": req.status_pagamento, "snf": req.status_nf, "dem": req.data_emissao, "dpg": req.data_pagamento, "id": id
        })
        conn.commit()
    return {"status": "ok"}

# --- ROTAS DE ORDENS DE SERVIÇO (CRUD) ---

@app.get("/api/os")
def list_os():
    with database.conectar() as conn:
        query = "SELECT os.*, u.nome as tecnico FROM ordens_servico os LEFT JOIN usuarios u ON os.id_tecnico = u.id ORDER BY os.id DESC"
        df = pd.read_sql_query(text(query), conn)
    return df.to_dict(orient="records")

@app.post("/api/os")
def add_os(req: OSRequest, tasks: BackgroundTasks):
    with database.conectar() as conn:
        query = text("""INSERT INTO ordens_servico (empresa, numero_os, cliente, plataforma, endereco, servico_descricao, id_tecnico, data_programada, status) 
                        VALUES (:emp, :num, :cli, :pla, :end, :des, :tec, :dat, :sta) RETURNING id""")
        res = conn.execute(query, {
            "emp": req.empresa, "num": req.numero_os, "cli": req.cliente, "pla": req.plataforma,
            "end": req.endereco, "des": req.servico_descricao, "tec": req.id_tecnico, "dat": req.data_programada, "sta": req.status
        })
        os_id = res.fetchone()[0]
        
        # Busca e-mail do técnico para notificação
        tec = conn.execute(text("SELECT nome, email FROM usuarios WHERE id = :id"), {"id": req.id_tecnico}).fetchone()
        conn.commit()

    if tec and tec[1]:
        corpo = f"<h2>Nova OS Atribuída: #{req.numero_os}</h2><p>Olá {tec[0]}, você tem uma nova tarefa para o cliente {req.cliente}. Verifique o App.</p>"
        tasks.add_task(disparar_email, tec[1], f"Nova OS MD: #{req.numero_os}", corpo)
        
    return {"id": os_id}

@app.put("/api/os/{id}")
def update_os(id: int, req: OSRequest):
    with database.conectar() as conn:
        query = text("""UPDATE ordens_servico SET empresa=:emp, numero_os=:num, cliente=:cli, plataforma=:pla, 
                        endereco=:end, servico_descricao=:des, relatorio_tecnico=:rel, id_tecnico=:tec, 
                        data_programada=:dat, status=:sta WHERE id=:id""")
        conn.execute(query, {
            "emp": req.empresa, "num": req.numero_os, "cli": req.cliente, "pla": req.plataforma, "end": req.endereco,
            "des": req.servico_descricao, "rel": req.relatorio_tecnico, "tec": req.id_tecnico, "dat": req.data_programada, "sta": req.status, "id": id
        })
        conn.commit()
    return {"status": "ok"}

@app.get("/api/minhas-os/{id_tecnico}")
def list_my_os(id_tecnico: int):
    with database.conectar() as conn:
        query = text("SELECT * FROM ordens_servico WHERE id_tecnico = :id AND status != 'Concluído' ORDER BY data_programada ASC")
        df = pd.read_sql_query(query, conn, params={"id": id_tecnico})
    return df.to_dict(orient="records")

@app.put("/api/os/{id}/status")
def update_os_status(id: int, req: StatusOSRequest):
    with database.conectar() as conn:
        conn.execute(text("UPDATE ordens_servico SET status = :s, relatorio_tecnico = :r WHERE id = :id"), {"s": req.status, "r": req.relatorio_tecnico, "id": id})
        conn.commit()
    return {"status": "ok"}

# --- ROTAS DE PONTO ELETRÓNICO (GPS) ---

@app.post("/api/ponto")
def bater_ponto(req: PontoRequest):
    with database.conectar() as conn:
        query = text("INSERT INTO registro_ponto (id_tecnico, tipo, latitude, longitude) VALUES (:id, :t, :la, :lo)")
        conn.execute(query, {"id": req.id_tecnico, "t": req.tipo, "la": req.lat, "lo": req.lng})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/ponto/status/{id_tecnico}")
def check_ponto_status(id_tecnico: int):
    with database.conectar() as conn:
        res = conn.execute(text("SELECT tipo FROM registro_ponto WHERE id_tecnico = :id ORDER BY id DESC LIMIT 1"), {"id": id_tecnico}).fetchone()
    return {"ultimo_registro": res[0] if res else "Saída"}

@app.get("/api/ponto/admin")
def list_ponto_all():
    with database.conectar() as conn:
        query = """SELECT p.*, u.nome as tecnico FROM registro_ponto p 
                   JOIN usuarios u ON p.id_tecnico = u.id ORDER BY p.id DESC LIMIT 100"""
        df = pd.read_sql_query(text(query), conn)
    return df.to_dict(orient="records")

# --- ROTAS DE USUÁRIOS E EQUIPA ---

@app.get("/api/usuarios")
def list_users():
    with database.conectar() as conn:
        df = pd.read_sql_query(text("SELECT id, nome, usuario, perfil, email FROM usuarios ORDER BY id ASC"), conn)
    return df.to_dict(orient="records")

@app.post("/api/usuarios")
def create_user(req: UsuarioRequest, tasks: BackgroundTasks):
    with database.conectar() as conn:
        query = text("INSERT INTO usuarios (nome, email, usuario, senha, perfil) VALUES (:n, :e, :u, :s, :p)")
        conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "s": req.senha, "p": req.perfil})
        conn.commit()
    if req.email:
        corpo = f"<h2>Bem-vindo ao Gestor MD</h2><p>Login: {req.usuario}<br>Senha: {req.senha}</p>"
        tasks.add_task(disparar_email, req.email, "Acesso ao Sistema MD", corpo)
    return {"status": "ok"}

@app.put("/api/usuarios/{id}")
def update_user(id: int, req: UsuarioRequest):
    with database.conectar() as conn:
        if req.senha:
            query = text("UPDATE usuarios SET nome=:n, email=:e, usuario=:u, perfil=:p, senha=:s WHERE id=:id")
            conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "p": req.perfil, "s": req.senha, "id": id})
        else:
            query = text("UPDATE usuarios SET nome=:n, email=:e, usuario=:u, perfil=:p WHERE id=:id")
            conn.execute(query, {"n": req.nome, "e": req.email, "u": req.usuario, "p": req.perfil, "id": id})
        conn.commit()
    return {"status": "ok"}

@app.get("/api/tecnicos")
def get_tecnicos_list():
    with database.conectar() as conn:
        res = conn.execute(text("SELECT id, nome FROM usuarios WHERE perfil='Tecnico'")).fetchall()
    return [{"id": r[0], "nome": r[1]} for r in res]

# --- ROTA DE DELETE GENÉRICA ---

@app.delete("/api/{rota}/{id}")
def delete_item(rota: str, id: int):
    tabela = "ordens_servico" if rota == "os" else "usuarios" if rota == "usuarios" else "financeiro"
    with database.conectar() as conn:
        conn.execute(text(f"DELETE FROM {tabela} WHERE id = :id"), {"id": id})
        conn.commit()
    return {"status": "ok"}

# --- GESTÃO DE FICHEIROS (ONEDRIVE / LOCAL) ---

@app.post("/api/os/{id}/{tipo}")
async def upload_file(id: int, tipo: str, arquivos: List[UploadFile] = File(...)):
    pasta_nome = "Documentos_OS" if tipo == "documentos" else "Evidencias_OS"
    path_dest = f"{pasta_nome}/OS_{id}"
    
    for f in arquivos:
        content = await f.read()
        if onedrive_api.is_configured():
            onedrive_api.upload_arquivo(content, f.filename, path_dest)
        else:
            local_path = os.path.join(BASE_DIR, path_dest)
            os.makedirs(local_path, exist_ok=True)
            with open(os.path.join(local_path, f.filename), "wb") as buffer:
                buffer.write(content)
    return {"status": "ok"}

@app.get("/api/os/{id}/arquivos")
def list_os_files(id: int):
    docs, evids = [], []
    if not onedrive_api.is_configured():
        p_d = os.path.join(BASE_DIR, f"Documentos_OS/OS_{id}")
        p_e = os.path.join(BASE_DIR, f"Evidencias_OS/OS_{id}")
        if os.path.exists(p_d): docs = os.listdir(p_d)
        if os.path.exists(p_e): evids = os.listdir(p_e)
    return {"documentos": docs, "evidencias": evids}

@app.get("/api/download/{tipo}/{id}/{arquivo}")
def download_file(tipo: str, id: int, arquivo: str):
    pasta_nome = "Documentos_OS" if tipo == "documentos" else "Evidencias_OS"
    path_dest = f"{pasta_nome}/OS_{id}"
    
    if onedrive_api.is_configured():
        link = onedrive_api.get_download_link(arquivo, path_dest)
        if link: return RedirectResponse(url=link)
        raise HTTPException(status_code=404)
    else:
        full_path = os.path.join(BASE_DIR, path_dest, arquivo)
        if os.path.exists(full_path): return FileResponse(full_path)
        raise HTTPException(status_code=404)

# --- SERVIR FRONTEND E PWA ---

app.mount("/static", StaticFiles(directory=os.getcwd()), name="static")

@app.get("/manifest.json")
def get_manifest():
    return FileResponse("manifest.json")

@app.get("/sw.js")
def get_sw():
    return FileResponse("sw.js", media_type="application/javascript")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()