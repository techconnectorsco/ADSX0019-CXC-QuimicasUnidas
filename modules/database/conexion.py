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
# SQL CRUDO VIA /SQLQueries
# =============================================================================
# Implementación única. Antes vivía copiada en agentes.py, main.py,
# auditar_cliente.py, descuentos.py, descuentos2.py, generar_descuentos.py,
# pag.py y test_moda.py: ocho copias con el mismo bug de truncado. Vive acá
# para que el arreglo no haya que repetirlo nueve veces.

# Tamaño de página que se le pide a /SQLQueries/List.
#
# Sin esto, /List devuelve SOLO las primeras 20 filas y descarta el resto en
# silencio: $top y $skip los IGNORA por completo (verificado el 30/09/2026
# contra producción — seis páginas con $skip 0, 20, 40... devolvieron las
# mismas 20 filas de un cliente que tenía 81 documentos abiertos). La única
# palanca que funciona es la cabecera "Prefer: odata.maxpagesize", y con ella
# las 1.091 facturas abiertas de toda la empresa llegan en una sola respuesta
# de 0,3 segundos.
class ErrorSqlSl(RuntimeError):
    """
    Un fallo de ejecutar_sql_sl, con el motivo clasificado.

    El motivo importa para decidir si vale reintentar, y la diferencia no es
    cosmetica:

      "timeout"  -> el query SE ESTA EJECUTANDO todavia del lado del Service
                    Layer; el que se rindio fue el cliente. Reintentar le apila
                    otra consulta pesada encima a un servidor que ya esta
                    ocupado. NO se reintenta.
      "auth"     -> la sesion se murio (401). El query no corrio. Reintentar
                    sirve, pero hay que reloguear primero.
      "rechazo"  -> el servidor rechazo el query (un 500 del SLD, por ejemplo).
                    No corrio nada, asi que reintentar es gratis.
      "red"      -> no se pudo ni crear el query. Tampoco corrio nada.
      "tope"     -> el resultado llego al tope de pagina y no hay forma de
                    paginar lo que falta. Reintentar da lo mismo.

    Hereda de RuntimeError a proposito, para no romper a quien ya hace
    `except RuntimeError` alrededor de esta funcion.
    """

    def __init__(self, mensaje: str, tipo: str):
        super().__init__(mensaje)
        self.tipo = tipo


SQL_MAX_PAGE_SIZE = 20000

# /List no tiene timeout propio y la sesión del Service Layer se cuelga cada
# tanto: sin esto un hilo puede quedarse esperando para siempre. Visto en una
# sonda que estuvo 13 minutos en una sola llamada.
SQL_TIMEOUT_SEGS = 120


def ejecutar_sql_sl(
    conn,
    sql: str,
    page_size: int = SQL_MAX_PAGE_SIZE,
    estricto: bool = False,
    timeout_segs: int = None,
) -> list:
    """
    Ejecuta un query SQL crudo en Service Layer mediante el endpoint SQLQueries.

    Thread-safe: el código del query temporal lleva un UUID, así que dos hilos
    no se pisan.

    El parser de /SQLQueries es un subconjunto pobre de SQL. Acepta columnas
    planas, COUNT, SUM de una columna, GROUP BY, HAVING, UNION ALL, IN (...) y
    JOIN. NO acepta: SELECT *, aritmética en el SELECT ('a - b'), funciones
    escalares (ABS, COALESCE, UPPER, TRIM), expresiones CASE, ni subqueries en
    FROM. Lo que no se puede calcular en el query se calcula en Python.

    OJO CON LOS MONTOS. La precisión numérica de este endpoint depende de la
    SESIÓN, no del query. El mismo SELECT sobre el mismo documento devuelve
    1479407.52 en una sesión y 1479410.0 en otra: redondeado a 6 cifras
    significativas. Dentro de una sesión es estable, pero cada login sale de un
    lado o del otro, y medido el 30/09/2026 redondearon 5 de 6 sesiones. No hay
    forma de pedir más precisión: se probaron cabeceras, casteos, SUM y todas
    las formas de WHERE.

    Los enteros y las cadenas (DocNum, DocEntry, SlpCode, U_CODV, DocCur,
    U_TDOC) NO se afectan, y el error solo asoma cuando el monto pasa de
    ~100.000, porque recién ahí las 6 cifras se comen los decimales.

    Conclusión práctica: de acá se sacan ruteos y conteos, no montos exactos.
    Para montos exactos hay que ir por OData (Invoices, CreditNotes), que
    siempre devuelve el valor completo. obtener_saldos_favor_masivo() lee los
    saldos a favor por esta vía y por eso varía en céntimos entre corridas.

    CON estricto=True, un fallo de red o un rechazo de SAP levanta
    RuntimeError en vez de devolver []. Hay que usarlo siempre que una lista
    vacía sea indistinguible de "no hay datos" y además signifique algo grave.
    El caso que lo motivó: el 01/10/2026 la consulta de facturas abiertas se
    cayó por timeout mientras se construía el mapa de ruteo de la gira por
    zona; al volver [], el mapa se armó solo con notas de crédito y saldos a
    favor, y habría escondido de la pantalla a casi todos los clientes con
    carga. Un query que falla no es un query sin resultados.

    timeout_segs sube el techo de SQL_TIMEOUT_SEGS para una llamada puntual.
    Hace falta porque el costo de /SQLQueries no depende del query sino de la
    carga del servidor: medido el 01/10/2026 en horario de oficina, un
    COUNT(*) sin joins tardó 30,6s y el query de 1.067 facturas con dos joins
    tardó 24,9s — el mismo que de noche corre en 0,3s. Con picos así, 120s no
    alcanzan para las consultas grandes.
    """
    import uuid

    code = f"QU_SQL_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"
    tope = timeout_segs or SQL_TIMEOUT_SEGS

    try:
        resp = conn.session.post(
            url,
            json={"SqlCode": code, "SqlName": "Query Temporal", "SqlText": sql},
            timeout=tope,
        )
    except Exception as e:
        print(f"   ⚠️ ejecutar_sql_sl: no se pudo crear el query ({e})")
        if estricto:
            raise ErrorSqlSl(
                f"ejecutar_sql_sl: no se pudo crear el query: {e}", "red"
            )
        return []

    if resp.status_code not in (200, 201):
        # A veces SAP devuelve error si la sesión colapsa, no rompemos el script
        # — pero tampoco nos callamos: devolver [] en silencio hacía que los
        # saldos a favor de un lote pudieran desaparecer de una gira sin que
        # nadie se enterara (riesgo anotado en PLAN_GIRAS_POR_ZONA.md 17.13).
        try:
            detalle = resp.json()["error"]["message"]["value"]
        except Exception:
            detalle = resp.text[:160]
        print(
            f"   ⚠️ ejecutar_sql_sl: SAP rechazó el query "
            f"({resp.status_code}): {str(detalle)[:160]}"
        )
        if estricto:
            raise ErrorSqlSl(
                f"ejecutar_sql_sl: SAP rechazó el query "
                f"({resp.status_code}): {str(detalle)[:160]}",
                "auth" if resp.status_code in (401, 403) else "rechazo",
            )
        return []

    try:
        res = conn.session.get(
            f"{url}('{code}')/List",
            headers={"Prefer": f"odata.maxpagesize={page_size}"},
            timeout=tope,
        )
        if res.status_code != 200:
            if estricto:
                raise ErrorSqlSl(
                    f"ejecutar_sql_sl: la lectura del query devolvió "
                    f"{res.status_code}",
                    "auth" if res.status_code in (401, 403) else "rechazo",
                )
            return []
        datos = res.json() or {}
    except RuntimeError:
        raise
    except Exception as e:
        print(f"   ⚠️ ejecutar_sql_sl: falló la lectura del query ({e})")
        if estricto:
            # Un timeout acá NO significa que el query se cancelo: el
            # Service Layer lo sigue ejecutando. Se marca distinto para que
            # nadie lo reintente y le apile otra consulta encima.
            es_timeout = "timed out" in str(e).lower() or isinstance(
                e, requests.exceptions.Timeout
            )
            raise ErrorSqlSl(
                f"ejecutar_sql_sl: falló la lectura del query: {e}",
                "timeout" if es_timeout else "red",
            )
        return []
    finally:
        # Limpiar la consulta temporal de SAP
        try:
            conn.session.delete(f"{url}('{code}')", timeout=tope)
        except Exception:
            pass

    filas = datos.get("value") or []

    # Si se llenó la página justo hasta el tope, puede haber quedado algo afuera
    # y NO hay forma de ir a buscarlo: $skip no funciona en este endpoint. Se
    # avisa fuerte en vez de devolver un resultado incompleto en silencio, que
    # es exactamente el bug que esta función tenía.
    if len(filas) >= page_size:
        print(
            f"   ⚠️ ejecutar_sql_sl: el resultado llegó al tope de {page_size} "
            f"filas y puede estar truncado. Acotá el query o subí "
            f"SQL_MAX_PAGE_SIZE."
        )
        if estricto:
            raise ErrorSqlSl(
                f"ejecutar_sql_sl: el resultado llegó al tope de {page_size} "
                f"filas y no hay forma de paginar lo que falta.",
                "tope",
            )

    return filas


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