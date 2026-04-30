"""
Módulo conexion.py - Químicas Unidas
Conexión al SAP Business One Service Layer (Novitec Cloud).
"""

import requests
import urllib3
import os
from decouple import config

# Deshabilitar warnings de SSL (común en Service Layer con certificados self-signed)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ServiceLayerConnection:
    """
    Conexión al SAP Business One Service Layer.
    """

    def __init__(self, use_test_db=True):
        # =============================================
        # CREDENCIALES DESDE .env
        # =============================================
        self.base_url = config('SAP_SERVICE_LAYER_URL', default='')
        self.username = config('SAP_USERNAME', default='')
        self.password = config('SAP_PASSWORD', default='')
        
        # Seleccionar BD: TEST para desarrollo, PROD para producción
        if use_test_db:
            self.company_db = config('SAP_COMPANY_DB_TEST', default='')
        else:
            self.company_db = config('SAP_COMPANY_DB_PROD', default='')
        # =============================================

        self.session = requests.Session()
        self.session.verify = False  # SSL verify off (certificados self-signed)
        self.logged_in = False

    def login(self) -> bool:
        """
        Inicia sesión en el Service Layer.
        
        Returns:
            True si login exitoso, False si error
        """
        url = f"{self.base_url}/Login"
        
        payload = {
            "CompanyDB": self.company_db,
            "UserName": self.username,
            "Password": self.password
        }

        try:
            response = self.session.post(url, json=payload)
            
            if response.status_code == 200:
                self.logged_in = True
                print(f"✅ Login exitoso - BD: {self.company_db}")
                return True
            else:
                print(f"❌ Error login: {response.status_code}")
                print(f"   Respuesta: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Error de conexión: {e}")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False

    def logout(self):
        """Cierra la sesión del Service Layer."""
        if self.logged_in:
            try:
                url = f"{self.base_url}/Logout"
                self.session.post(url)
                self.logged_in = False
                print("✅ Logout exitoso")
            except:
                pass

    def get(self, endpoint: str, params: dict = None) -> dict:
        """
        Realiza una petición GET al Service Layer.
        
        Args:
            endpoint: Endpoint a consultar (ej: "BusinessPartners")
            params: Parámetros de query (opcional)
        
        Returns:
            Dict con la respuesta JSON
        """
        if not self.logged_in:
            print("⚠️ No hay sesión activa. Ejecuta login() primero.")
            return None

        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error GET {endpoint}: {response.status_code}")
                print(f"   Respuesta: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def query(self, query: str) -> list:
        """
        Ejecuta una consulta SQL via SQLQueries.
        
        Args:
            query: Consulta SQL a ejecutar
        
        Returns:
            Lista de resultados
        """
        # El Service Layer tiene endpoint para queries
        # Puede variar según versión de SAP B1
        endpoint = f"$crossjoin()"  # O usar SQLQueries si está habilitado
        
        # Alternativa: usar el endpoint QueryService
        # endpoint = "QueryService_PostQuery"
        
        pass  # Implementar según configuración de Novitec

    def test_connection(self):
        """Prueba la conexión listando algunas entidades básicas."""
        print("\n" + "="*50)
        print("🔍 PRUEBA DE CONEXIÓN - SAP SERVICE LAYER")
        print("="*50)
        
        if not self.login():
            return False

        # Probar obtener info de la compañía
        print("\n📌 Probando acceso a BusinessPartners...")
        bp = self.get("BusinessPartners", {"$top": 1, "$select": "CardCode,CardName"})
        if bp:
            print(f"   ✅ Acceso OK - Ejemplo: {bp}")

        # Probar obtener facturas
        print("\n📌 Probando acceso a Invoices...")
        inv = self.get("Invoices", {"$top": 1, "$select": "DocEntry,DocNum,CardCode"})
        if inv:
            print(f"   ✅ Acceso OK - Ejemplo: {inv}")

        self.logout()
        print("\n" + "="*50)
        return True


# =============================================================================
# EJECUCIÓN DIRECTA PARA PRUEBAS
# =============================================================================
if __name__ == "__main__":
    conn = ServiceLayerConnection()
    
    # Verificar que las credenciales estén configuradas
    if not conn.base_url or not conn.company_db or not conn.username:
        print("⚠️ Configura las credenciales en el __init__ antes de probar")
        print("   - base_url")
        print("   - company_db")
        print("   - username")
        print("   - password")
    else:
        conn.test_connection()