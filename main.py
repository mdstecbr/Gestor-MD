from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text  # <--- O tradutor do Banco de Dados
import database
import pandas as pd
import os  # <--- O criador de Pastas
import shutil
import onedrive_api

# --- AMBIENTE E PASTAS ---
# Sem disco pago, usamos a pasta padrão do servidor (".")
BASE_DIR = "."

PASTA_DOCUMENTOS = os.path.join(BASE_DIR, "Documentos_OS")
PASTA_EVIDENCIAS = os.path.join(BASE_DIR, "Evidencias_OS")
os.makedirs(PASTA_DOCUMENTOS, exist_ok=True)
os.makedirs(PASTA_EVIDENCIAS, exist_ok=True)

# Inicializa banco de dados
database.inicializar_banco()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- MODELOS (PYDANTIC) ---
class LoginRequest(BaseModel): 
    usuario: str
    senha: str

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

class OSUpdateRequest(OSRequest): 
    status: str

class StatusOSRequest(BaseModel): 
    status: str
    relatorio_tecnico: Optional[str] = ""

# --- ROTAS DA API ---
@app.post("/api/login")
def login(req: LoginRequest):
    with database.conectar() as conn:
        query = text("SELECT id, nome, perfil FROM usuarios WHERE usuario = :u AND senha = :s")
        user = conn.execute(query, {"u": req.usuario, "s": req.senha}).fetchone()
        if user: 
            return {"id": user[0], "nome": user[1], "perfil": user[2]}
    raise HTTPException(status_code=401)

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
        
        df_fin = pd.read_sql_query(text(f"SELECT valor, tipo, data_pagamento, data_registro FROM financeiro {f_fin}"), conn, params=params)
        df_os = pd.read_sql_query(text(f"SELECT id, status FROM ordens_servico {f_os}"), conn, params=params)
    
    cat_in, cat_out = {}, {}
    if not df_fin.empty:
        df_fin['ref'] = df_fin['data_pagamento'].fillna(df_fin['data_registro']).astype(str).str[:10]
        for _, r in df_fin.groupby(['ref', 'tipo'])['valor'].sum().reset_index().iterrows():
            if r['tipo'] == 'Entrada': 
                cat_in[r['ref']] = r['valor']
            else: 
                cat_out[r['ref']] = r['valor']
            
    return {
        "faturamento_global": float(df_fin[df_fin['tipo']=='Entrada']['valor'].sum()) if not df_fin.empty else 0,
        "despesas_globais": float(df_fin[df_fin['tipo']=='Saída']['valor'].sum()) if not df_fin.empty else 0,
        "total_os": len(df_os),
        "grafico_os": df_os['status'].value_counts().to_dict() if not df_os.empty else {},
        "grafico_fin_entradas": cat_in, 
        "grafico_fin_saidas": cat_out
    }

@app.get("/api/financeiro")
def list_fin(inicio: Optional[str]=None, fim: Optional[str]=None):
    with database.conectar() as conn:
        query = "SELECT * FROM financeiro"
        params = {}
        if inicio and fim: 
            query += " WHERE date(COALESCE(data_pagamento, data_registro)) BETWEEN :i AND :f"
            params = {"i": inicio, "f": fim}
        query += " ORDER BY id DESC"
        df = pd.read_sql_query(text(query), conn, params=params)
    return df.to_dict(orient="records")

@app.post("/api/financeiro")
def add_fin(req: FinanceiroRequest):
    with database.conectar() as conn:
        query = text('''INSERT INTO financeiro (empresa, descricao, valor, tipo, categoria, status_pagamento, status_nf, data_emissao, data_pagamento) 
                        VALUES (:emp, :des, :val, :tip, :cat, :spg, :snf, :dem, :dpg)''')
        conn.execute(query, {
            "emp": req.empresa, "des": req.descricao, "val": req.valor, "tip": req.tipo, 
            "cat": req.categoria, "spg": req.status_pagamento, "snf": req.status_nf, 
            "dem": req.data_emissao, "dpg": req.data_pagamento
        })
        conn.commit()
    return {"status": "ok"}

@app.get("/api/os")
def list_os(inicio: Optional[str]=None, fim: Optional[str]=None):
    with database.conectar() as conn:
        query = "SELECT os.*, u.nome as tecnico FROM ordens_servico os LEFT JOIN usuarios u ON os.id_tecnico = u.id"
        params = {}
        if inicio and fim: 
            query += " WHERE date(os.data_programada) BETWEEN :i AND :f"
            params = {"i": inicio, "f": fim}
        query += " ORDER BY os.id DESC"
        df = pd.read_sql_query(text(query), conn, params=params)
    return df.to_dict(orient="records")

@app.post("/api/os")
def add_os(req: OSRequest):
    with database.conectar() as conn:
        query = text('''INSERT INTO ordens_servico (empresa, numero_os, cliente, plataforma, endereco, servico_descricao, id_tecnico, data_programada) 
                        VALUES (:emp, :num, :cli, :pla, :end, :des, :tec, :dat) RETURNING id''')
        result = conn.execute(query, {
            "emp": req.empresa, "num": req.numero_os, "cli": req.cliente, "pla": req.plataforma, 
            "end": req.endereco, "des": req.servico_descricao, "tec": req.id_tecnico, "dat": req.data_programada
        })
        os_id = result.fetchone()[0]
        conn.commit()
    return {"id": os_id}

@app.get("/api/minhas-os/{id_tecnico}")
def list_my_os(id_tecnico: int, inicio: Optional[str]=None, fim: Optional[str]=None):
    with database.conectar() as conn:
        query = "SELECT * FROM ordens_servico WHERE id_tecnico=:id AND status != 'Concluído'"
        params = {"id": id_tecnico}
        if inicio and fim: 
            query += " AND date(data_programada) BETWEEN :i AND :f"
            params.update({"i": inicio, "f": fim})
        query += " ORDER BY data_programada ASC"
        df = pd.read_sql_query(text(query), conn, params=params)
    return df.to_dict(orient="records")

@app.put("/api/os/{id}/status")
def update_status(id: int, req: StatusOSRequest):
    with database.conectar() as conn:
        query = text("UPDATE ordens_servico SET status = :s, relatorio_tecnico = :r WHERE id = :id")
        conn.execute(query, {"s": req.status, "r": req.relatorio_tecnico, "id": id})
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/{rota}/{id}")
def deletar_item(rota: str, id: int):
    tabela = "ordens_servico" if rota == "os" else "usuarios" if rota == "usuarios" else "financeiro"
    with database.conectar() as conn:
        conn.execute(text(f"DELETE FROM {tabela} WHERE id = :id"), {"id": id})
        conn.commit()
    return {"status": "ok"}

# --- INTEGRAÇÃO COM ARQUIVOS / ONEDRIVE ---
@app.post("/api/os/{id}/{tipo}")
async def upload(id: int, tipo: str, arquivos: list[UploadFile] = File(...)):
    folder = "Documentos_OS" if tipo == "documentos" else "Evidencias_OS"
    path_dest = f"{folder}/OS_{id}"
    for f in arquivos:
        content = await f.read()
        if onedrive_api.is_configured(): 
            onedrive_api.upload_arquivo(content, f.filename, path_dest)
        else:
            p_local = os.path.join(BASE_DIR, path_dest)
            os.makedirs(p_local, exist_ok=True)
            with open(os.path.join(p_local, f.filename), "wb") as buffer: 
                buffer.write(content)
    return {"status": "ok"}

@app.get("/api/os/{id}/arquivos")
def list_files(id: int):
    d, e = [], []
    if not onedrive_api.is_configured():
        p_d = os.path.join(BASE_DIR, f"Documentos_OS/OS_{id}")
        p_e = os.path.join(BASE_DIR, f"Evidencias_OS/OS_{id}")
        if os.path.exists(p_d): d = os.listdir(p_d)
        if os.path.exists(p_e): e = os.listdir(p_e)
    return {"documentos": d, "evidencias": e}

@app.get("/api/download/{tipo}/{id}/{arquivo}")
def baixar_arquivo(tipo: str, id: int, arquivo: str):
    pasta = "Documentos_OS" if tipo == "documentos" else "Evidencias_OS"
    pasta_destino = f"{pasta}/OS_{id}"
    
    if onedrive_api.is_configured():
        link = onedrive_api.get_download_link(arquivo, pasta_destino)
        if link: 
            return RedirectResponse(url=link)
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no OneDrive")
    else:
        caminho = os.path.join(BASE_DIR, pasta_destino, arquivo)
        if os.path.exists(caminho): 
            return FileResponse(path=caminho, filename=arquivo)
        raise HTTPException(status_code=404, detail="Arquivo não encontrado localmente")

# --- USUÁRIOS ---
@app.get("/api/tecnicos")
def list_tecs():
    with database.conectar() as conn:
        res = conn.execute(text("SELECT id, nome FROM usuarios WHERE perfil='Tecnico'")).fetchall()
    return [{"id": r[0], "nome": r[1]} for r in res]

@app.get("/api/usuarios")
def list_users():
    with database.conectar() as conn:
        df = pd.read_sql_query(text("SELECT id, nome, usuario, perfil FROM usuarios"), conn)
    return df.to_dict(orient="records")

# --- SERVIR FRONTEND ---
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve():
    with open("index.html", "r", encoding="utf-8") as f: 
        return f.read()