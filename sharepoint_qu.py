"""
sharepoint_qu.py - Químicas Unidas
Módulo para subir reportes automáticamente a SharePoint (Giras y CXC).
"""

import os
import requests
from datetime import datetime
from msal import ConfidentialClientApplication
from decouple import config

# === 🔐 Credenciales desde .env ===
TENANT_ID = config("TENANT_ID", default="")
CLIENT_ID = config("CLIENT_ID", default="")
CLIENT_SECRET = config("CLIENT_SECRET", default="")

# === 📍 Configuración SharePoint Químicas Unidas ===
SHAREPOINT_HOST = "qucr.sharepoint.com"
SHAREPOINT_SITE = "asistentedigital"
TARGET_LIBRARY_NAME = "Documentos compartidos"  # Nombre de la biblioteca en la URL

# === 📅 Traducción de meses ===
MONTHS_ES = {
    "01": "Enero",
    "02": "Febrero",
    "03": "Marzo",
    "04": "Abril",
    "05": "Mayo",
    "06": "Junio",
    "07": "Julio",
    "08": "Agosto",
    "09": "Septiembre",
    "10": "Octubre",
    "11": "Noviembre",
    "12": "Diciembre",
}


class SharePointUploader:
    def __init__(self):
        if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
            print(
                "⚠️ Advertencia: Faltan credenciales de SharePoint en el archivo .env"
            )
            self.token = None
            return

        self.token = self.get_access_token()
        self.site_id = self.get_site_id()
        self.drive_id = self.get_library_drive_id()

    def get_access_token(self):
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID, client_credential=CLIENT_SECRET, authority=authority
        )
        token_response = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        return token_response["access_token"]

    def get_site_id(self):
        url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE}"
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()["id"]

    def get_library_drive_id(self):
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives"
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(url, headers=headers)
        drives = response.json().get("value", [])

        # Buscar la biblioteca específica
        for drive in drives:
            if (
                drive["name"].lower() == TARGET_LIBRARY_NAME.lower()
                or drive["name"].lower() == "documentos"
            ):
                return drive["id"]

        # Fallback a la primera biblioteca encontrada si no hace match exacto
        if drives:
            return drives[0]["id"]
        raise Exception("❌ No se encontraron bibliotecas en el sitio de SharePoint.")

    def create_folder(self, path):
        """Crea la estructura de carpetas de forma recursiva en SharePoint."""
        parts = path.strip("/").split("/")
        current_path = ""
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{current_path}"
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(url, headers=headers)

            # Si la carpeta no existe, la creamos
            if response.status_code == 404:
                create_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{os.path.dirname(current_path)}:/children"
                if not os.path.dirname(current_path):  # Si es la carpeta raíz
                    create_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/children"

                data = {
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename",
                }
                response = requests.post(
                    create_url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=data,
                )

                if response.status_code not in [200, 201]:
                    raise Exception(
                        f"❌ Error al crear carpeta '{part}': {response.text}"
                    )

    def upload_reporte(self, local_file: str, tipo_reporte: str) -> bool:
        """
        Sube un archivo a SharePoint estructurando por Tipo/Año/Mes/Día.

        Args:
            local_file: Ruta local del PDF generado.
            tipo_reporte: Debe ser "Giras" o "CXC_Clientes".
        """
        if not self.token:
            return False

        if tipo_reporte not in ["Giras", "CXC_Clientes", "Logs_de_CXC"]:
            print(f"❌ Error: El tipo de reporte '{tipo_reporte}' no es válido.")
            return False

        if not os.path.exists(local_file):
            print(f"❌ El archivo no existe localmente: {local_file}")
            return False

        filename = os.path.basename(local_file)
        today = datetime.now()
        year = today.strftime("%Y")
        month_es = MONTHS_ES[today.strftime("%m")]
        day = today.strftime("%d-%m-%Y")

        # Construir la ruta remota: ej. Giras/2026/Mayo/12-05-2026
        remote_folder_path = f"{tipo_reporte}/{year}/{month_es}/{day}"

        try:
            self.create_folder(remote_folder_path)

            remote_path = f"{remote_folder_path}/{filename}"
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{remote_path}:/content"

            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/octet-stream",
            }

            with open(local_file, "rb") as f:
                file_content = f.read()

            response = requests.put(upload_url, headers=headers, data=file_content)

            if response.status_code in [200, 201]:
                print(f"   ☁️  Subido a SharePoint: {remote_path}")
                return True
            else:
                print(
                    f"   ❌ Error SharePoint: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            print(f"   ❌ Excepción subiendo a SharePoint: {e}")
            return False
