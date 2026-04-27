import os
import requests
import msal
import os
def is_configured(): return os.environ.get("MS_CLIENT_ID") is not None
def upload_arquivo(content, name, path): pass # Lógica de upload aqui

TENANT_ID = os.environ.get("MS_TENANT_ID")
CLIENT_ID = os.environ.get("MS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
USER_ID = os.environ.get("MS_USER_ID")

def is_configured():
    return all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, USER_ID])

def get_token():
    try:
        app = msal.ConfidentialClientApplication(
            CLIENT_ID, authority=f"https://login.microsoftonline.com/{TENANT_ID}",
            client_credential=CLIENT_SECRET
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        return result.get("access_token")
    except Exception as e:
        print(f"Erro MSAL: {e}")
        return None

def upload_arquivo(file_bytes, nome_arquivo, pasta_destino):
    if not is_configured(): 
        return False
    token = get_token()
    if not token: 
        return False
    url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/drive/root:/GestorMD/{pasta_destino}/{nome_arquivo}:/content"
    res = requests.put(url, headers={"Authorization": f"Bearer {token}"}, data=file_bytes)
    return res.status_code in [200, 201]

def get_download_link(nome_arquivo, pasta_destino):
    if not is_configured(): 
        return None
    token = get_token()
    if not token: 
        return None
    url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/drive/root:/GestorMD/{pasta_destino}/{nome_arquivo}"
    res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    return res.json().get("@microsoft.graph.downloadUrl") if res.status_code == 200 else None