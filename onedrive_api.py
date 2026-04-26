import os
import requests
import msal

# Chaves que você vai pegar no Microsoft Azure (Variáveis de Ambiente do Render)
TENANT_ID = os.environ.get("MS_TENANT_ID")
CLIENT_ID = os.environ.get("MS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
USER_ID = os.environ.get("MS_USER_ID") # E-mail do dono da pasta (Ex: admin@mdsolucoes.com)

def is_configured():
    """Verifica se as chaves da Microsoft foram configuradas no Render."""
    return all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, USER_ID])

def get_token():
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    raise Exception("Falha ao autenticar no Microsoft Azure AD.")

def upload_arquivo(file_bytes, nome_arquivo, pasta_destino):
    """Envia um arquivo diretamente para o OneDrive via API."""
    if not is_configured(): return False
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
    # URL do Microsoft Graph para salvar arquivos (< 4MB)
    url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/drive/root:/GestorMD/{pasta_destino}/{nome_arquivo}:/content"
    response = requests.put(url, headers=headers, data=file_bytes)
    return response.status_code in [200, 201]

def get_download_link(nome_arquivo, pasta_destino):
    """Gera um link de download direto do OneDrive para o botão do Técnico."""
    if not is_configured(): return None
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://graph.microsoft.com/v1.0/users/{USER_ID}/drive/root:/GestorMD/{pasta_destino}/{nome_arquivo}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("@microsoft.graph.downloadUrl")
    return None