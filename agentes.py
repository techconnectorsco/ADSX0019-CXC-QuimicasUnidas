"""
agente.py - Químicas Unidas
Automatización de Reportes de Gira para Agentes/Vendedores.
"""

import sys
import os
import unicodedata
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import time
from collections import Counter
from decouple import config
from supabase_manager import verificar_estado_rpa, finalizar_y_reportar, ID_RPA_QU_GIRAS
from global_status_giras import status_global_giras

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import (
    SQL_MAX_PAGE_SIZE,
    SQL_TIMEOUT_SEGS,
    ErrorSqlSl,
    ServiceLayerConnection,
    ejecutar_sql_sl,
)
from agentepdf import generar_pdf_reporte_gira
from sendemailCXC import EmailSenderAgente
from sharepoint_qu import SharePointUploader
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# CONSTANTES
# =============================================================================

EMAIL_PRUEBA = "devs@techconnectors.co"
# EMAIL_PRUEBA = "credito@qu.cr"
MODO_PRUEBA = False  # True = envía a EMAIL_PRUEBA, False = envía al correo del agente

# AGENTES PERMITIDOS: Siviany (6), Berny (7), José (9)
# AGENTES_VALIDOS = {6, 7, 9}

# CORREOS EN COPIA (CC) SOLICITADOS POR TANIA
CORREOS_CC = [
    "dev@soportexperto.com",
    "erich.hoepker@qu.cr",
    "apuschendorf@qu.cr",
    "creditodenis@qu.cr",
    "credito@qu.cr",
]

TIPOS_QUE_RESTAN = {
    "DEP",
    "N",
    "N/C",
    "NC",
    "REC",
    "TEF",
    "O/C",
    "RC",
    "PR",
    "REM",
    "NCM",
}

TRADUCCION_TIPOS = {
    "FRM": "FRM",
    "FRT": "FRT",
    "FEC": "FEC",
    "FEM": "FEM",
    "NC": "NC",
    "NCM": "NCM",
    "N/C": "N/C",
    "RC": "RC",
    "REM": "REM",
    "PR": "PR",
    "ND": "ND",
    "NDM": "NDM",
    "N/D": "N/D",
    "AS": "AS",
}

# =============================================================================
# FUNCIONES
# =============================================================================


def obtener_todos_paginado(
    conn: ServiceLayerConnection,
    entidad: str,
    params: dict,
    campo_orden: str = "DocNum",
) -> List[Dict]:
    todos = []
    skip = 0
    page_size = 20
    params["$top"] = page_size
    params["$orderby"] = campo_orden

    while True:
        params["$skip"] = skip
        resultado = conn.get(entidad, params)

        if not resultado or "value" not in resultado or len(resultado["value"]) == 0:
            break

        todos.extend(resultado["value"])
        if len(resultado["value"]) < page_size:
            break

        skip += page_size
        if skip >= 10000:
            break
    return todos


def obtener_clientes_con_saldo(
    conn: ServiceLayerConnection, limite: int = None
) -> List[Dict]:
    # NUEVO FILTRO UNIVERSAL:
    # Clientes Activos/Inactivos que tengan saldo O que sean sucursales (FatherCard)
    filtro = (
        "CardType eq 'cCustomer' and (CurrentAccountBalance ne 0 or FatherCard ne null)"
    )

    params = {
        "$filter": filtro,
        "$select": "CardCode,CardName,Phone1,Phone2,Cellular,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,CreditLimit,ContactPerson,Address,Currency,FatherCard,PayTermsGrpCode",
    }

    if limite:
        params["$top"] = limite
        clientes = conn.get("BusinessPartners", params)
        return clientes.get("value", []) if clientes else []
    else:
        return obtener_todos_paginado(conn, "BusinessPartners", params, "CardCode")


def calcular_descuento_bp(grupos: List[Dict]) -> float:
    """
    Descuento del cliente = el % que más se repite entre sus DiscountGroups (>0).
    Es la fuente real configurada en SAP (la misma que ve la encargada).

    IMPORTANTE: idéntico al método validado contra los 10 clientes del correo
    de Tania. Misma extracción (DiscountPercentage), mismo filtro (>0),
    misma moda (Counter + max con desempate por mayor valor).
    """
    valores = [
        float(g.get("DiscountPercentage", 0) or 0)
        for g in (grupos or [])
        if float(g.get("DiscountPercentage", 0) or 0) > 0
    ]
    if not valores:
        return 0.0
    conteo = Counter(valores)
    # Más frecuente; desempate: el mayor
    return max(conteo.items(), key=lambda x: (x[1], x[0]))[0]


def obtener_descuento_cliente(conn: ServiceLayerConnection, card_code: str) -> float:
    """
    Trae el BP (completo, sin $select porque DiscountGroups no responde a $select)
    y devuelve el descuento por moda. Se usa para la herencia padre->hijo.
    """
    try:
        bp = conn.get(f"BusinessPartners('{card_code}')", {})
        if bp:
            return calcular_descuento_bp(bp.get("DiscountGroups", []))
    except:
        pass
    return 0.0


def obtener_vendedores(conn: ServiceLayerConnection) -> Dict[int, Dict]:
    vendedores = {}
    params = {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"}
    resultado = obtener_todos_paginado(
        conn, "SalesPersons", params, "SalesEmployeeCode"
    )
    for v in resultado:
        vendedores[v["SalesEmployeeCode"]] = {
            "nombre": v.get("SalesEmployeeName", "No asignado"),
            "correo": v.get("Email", ""),
        }
    return vendedores


def obtener_contacto_y_descuento(
    conn: ServiceLayerConnection, card_code: str, contact_code: int
) -> tuple:
    """
    Trae el BP COMPLETO (sin $select, porque DiscountGroups no responde a $select)
    y devuelve (contacto, descuento) en UNA sola llamada.

    Antes esto eran dos cosas separadas (contacto por un lado, descuento por otro);
    ahora ambos salen del mismo viaje al BusinessPartner.
    """
    contacto = {"nombre": "", "telefono": "", "email": ""}
    descuento = 0.0
    try:
        bp = conn.get(f"BusinessPartners('{card_code}')", {})
        if bp:
            # Descuento real desde DiscountGroups (fuente configurada en SAP)
            descuento = calcular_descuento_bp(bp.get("DiscountGroups", []))

            # Contacto principal (si aplica)
            if contact_code and "ContactEmployees" in bp:
                for c in bp["ContactEmployees"]:
                    if c.get("InternalCode") == contact_code:
                        contacto = {
                            "nombre": c.get("Name", ""),
                            "telefono": c.get("Phone1", "") or c.get("MobilePhone", ""),
                            "email": c.get("E_Mail", ""),
                        }
                        break
    except:
        pass
    return contacto, descuento


def obtener_mapeo_direcciones(
    conn: ServiceLayerConnection, card_code: str
) -> Dict[str, int]:
    """
    Obtiene un diccionario que mapea cada dirección de envío (ShipTo)
    con su vendedor asignado (U_CODV).
    Ejemplo: {'JACO': 7, 'BELEN': 6, 'DESAMPARADOS': 9}
    """
    mapeo = {}
    try:
        res = conn.get(f"BusinessPartners('{card_code}')", {"$select": "BPAddresses"})
        if not res or "BPAddresses" not in res:
            return mapeo

        for d in res["BPAddresses"]:
            # Solo nos interesan las direcciones de destino
            if d.get("AddressType") == "bo_ShipTo":
                nombre_dir = d.get("AddressName", "")
                vendedor_dir = d.get("U_CODV")

                # Si el campo existe y es un número válido, lo guardamos
                if (
                    nombre_dir
                    and vendedor_dir is not None
                    and str(vendedor_dir).strip() != ""
                ):
                    try:
                        mapeo[nombre_dir] = int(vendedor_dir)
                    except ValueError:
                        pass

    except Exception as e:
        print(f"   ⚠️ Error obteniendo direcciones de {card_code}: {e}")

    return mapeo


def calcular_saldo_documento(
    moneda_doc,
    total_fc,
    pagado_fc,
    total_local,
    pagado_local,
    tipo_doc,
    es_nota_credito: bool,
) -> Optional[Tuple[float, float, str]]:
    """
    La regla de saldo y signo de un documento abierto, en UN solo lugar.

    La usan dos caminos que reciben los mismos datos con nombres distintos:
    procesar_documento(), que trabaja sobre el dict de OData (DocCurrency,
    DocTotalFc, PaidToDateFC), y obtener_mapa_ruteo_masivo(), que trabaja
    sobre la fila cruda de /SQLQueries, donde los nombres son los de la base
    (DocCur, DocTotalFC, PaidFC).

    Tener la regla acá es lo único que impide que la pantalla y el PDF vuelvan
    a decir cosas distintas, que es exactamente el defecto que el prefiltro de
    clientes con carga vino a corregir. Si se reescribe en cualquiera de los
    dos lados, el problema regresa en silencio.

    Devuelve (saldo, total, moneda), o None si el documento no entra porque su
    saldo es despreciable (< 0.005).

    Ojo con el patrón `total_fc or total_local`: si el total en moneda
    extranjera viene en 0, cae al total en colones. Se conserva tal cual
    porque es lo que decide el monto que sale impreso.
    """

    def num(v):
        return float(v or 0)

    if str(moneda_doc or "") in ["USD", "US$", "DOL"]:
        total = num(total_fc) or num(total_local)
        pagado = num(pagado_fc) or num(pagado_local)
        moneda = "USD"
    else:
        total = num(total_local)
        pagado = num(pagado_local)
        moneda = "CRC"

    saldo = total - pagado
    if abs(saldo) < 0.005:
        return None

    tipo = str(tipo_doc or "").strip().upper()

    # Para notas de crédito O documentos de la lista, el saldo DEBE ser negativo
    if es_nota_credito or tipo in TIPOS_QUE_RESTAN or tipo == "PR":
        saldo = -abs(saldo)
        total = -abs(total)

    return saldo, total, moneda


def procesar_documento(doc: Dict, tipo_origen: str) -> Optional[Dict]:
    hoy = datetime.now().date()

    tipo_doc = str(doc.get("U_TDOC", "") or "").strip().upper()

    calculo = calcular_saldo_documento(
        doc.get("DocCurrency"),
        doc.get("DocTotalFc"),
        doc.get("PaidToDateFC"),
        doc.get("DocTotal"),
        doc.get("PaidToDate"),
        tipo_doc,
        tipo_origen == "creditnote",
    )
    if calculo is None:
        return None

    saldo, total, moneda = calculo

    fecha_vence_str = doc.get("DocDueDate", "")
    dias_vencido = 0
    esta_vencido = False

    if fecha_vence_str:
        try:
            fecha_vence = datetime.strptime(
                str(fecha_vence_str)[:10], "%Y-%m-%d"
            ).date()
            dias_vencido = (hoy - fecha_vence).days
            esta_vencido = dias_vencido > 0 and saldo > 0
        except:
            pass

    descripcion = ""
    lineas = doc.get("DocumentLines", [])
    if lineas:
        descripciones = [
            l.get("ItemDescription", "") for l in lineas if l.get("ItemDescription")
        ]
        descripcion = " | ".join(descripciones)

    if not descripcion:
        descripcion = doc.get("Comments", "") or ""

    if len(descripcion) > 79:
        descripcion = descripcion[:76] + "..."

    consecutivo = doc.get("U_NVT_ConsecutivoFE", "") or doc.get("U_NUM_CONSE", "") or ""

    return {
        "doc_num": doc.get("DocNum"),
        "consecutivo_fe": consecutivo,
        "tipo_codigo": tipo_doc,
        "destino": doc.get("ShipToCode", "") or "",  # <-- NUEVO CAMPO DE ZONA/DESTINO
        "descripcion": descripcion,
        "fecha": str(doc.get("DocDate", ""))[:10],
        "fecha_vence": str(fecha_vence_str)[:10] if fecha_vence_str else "",
        "total": total,
        "saldo": saldo,
        "moneda": moneda,
        "esta_vencido": esta_vencido,
        "dias_vencido": dias_vencido,
        "orden_compra": doc.get("NumAtCard", "") or "",
    }


# ejecutar_sql_sl vive en modules/database/conexion.py: era la misma funcion
# copiada en ocho archivos, todas con el bug de truncado a 20 filas. Se
# re-exporta para no romper a quien hace "from agentes import ejecutar_sql_sl".


def obtener_saldos_favor_masivo(
    conn: ServiceLayerConnection,
    card_codes: List[str],
    lote: int = 15,  # <--- Bajamos a 15
) -> Dict[str, List[Dict]]:
    cache: Dict[str, List[Dict]] = {}
    codigos = [c for c in card_codes if c]
    total_lotes = (len(codigos) + lote - 1) // lote  # <--- Agregamos esto

    for i in range(0, len(codigos), lote):
        lote_actual = (i // lote) + 1  # <--- Agregamos esto
        print(
            f"   ⏳ Consultando JDT1: Lote {lote_actual}/{total_lotes}...", end="\r"
        )  # <--- Agregamos esto para ver que no se congela

        bloque = codigos[i : i + lote]
        lista_in = ", ".join([f"'{c}'" for c in bloque])
        sql = f"""
            SELECT 
                T0."ShortName",
                T0."RefDate", 
                T0."BaseRef" AS "DocNum", 
                T0."TransType", 
                T0."BalDueCred", 
                T0."BalFcCred", 
                T0."FCCurrency", 
                T0."LineMemo" 
            FROM "JDT1" T0 
            WHERE T0."ShortName" IN ({lista_in}) 
              AND T0."BalDueCred" > 0 
              AND T0."RefDate" >= '20220101'
              AND T0."TransType" NOT IN ('13', '14', '30')
        """
        filas = ejecutar_sql_sl(conn, sql)
        for r in filas:
            sn = str(r.get("ShortName", ""))
            cache.setdefault(sn, []).append(r)

    return cache


def obtener_documentos_cliente(
    conn: ServiceLayerConnection, cliente_info: Dict, saldos_favor_cache: Dict = None
) -> List[Dict]:
    documentos = []
    card_code = cliente_info.get("CardCode")
    vendedor_general = cliente_info.get("SalesPersonCode", -1)

    mapeo_dir = obtener_mapeo_direcciones(conn, card_code)

    # 1. FACTURAS (Invoices) - Aquí NO filtramos por fecha, la deuda vieja sigue siendo deuda
    facturas = obtener_todos_paginado(
        conn,
        "Invoices",
        {
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,ShipToCode,DocumentLines",
        },
        "DocEntry",
    )
    for f in facturas:
        doc = procesar_documento(f, "invoice")
        if doc:
            destino = doc["destino"]
            doc["vendedor_final"] = mapeo_dir.get(destino, vendedor_general)
            documentos.append(doc)

    # 2. NOTAS DE CRÉDITO (CreditNotes) - AHORA CON FILTRO DESDE EL 2022
    notas_credito = obtener_todos_paginado(
        conn,
        "CreditNotes",
        {
            # AÑADIDO: DocDate ge '2022-01-01' para evitar la basura vieja del 2019
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open' and DocDate ge '2022-01-01'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,ShipToCode,DocumentLines",
        },
        "DocEntry",
    )
    for nc in notas_credito:
        doc = procesar_documento(nc, "creditnote")
        if doc:
            destino = doc["destino"]
            doc["vendedor_final"] = mapeo_dir.get(destino, vendedor_general)
            documentos.append(doc)

    # 3. SALDOS A FAVOR (desde el cache masivo: ya NO se hace un query por cliente)
    filas_pr = (saldos_favor_cache or {}).get(card_code, [])

    for r in filas_pr:
        moneda_linea = r.get("FCCurrency")
        if moneda_linea in ["USD", "US$", "DOL"]:
            moneda_pago = "USD"
            sobrante = float(r.get("BalFcCred", 0) or 0)
        else:
            moneda_pago = "CRC"
            sobrante = float(r.get("BalDueCred", 0) or 0)

        if sobrante > 0.05:
            # FIX DE FECHAS: Convertir '20260526' a '2026-05-26'
            raw_date = str(r.get("RefDate", ""))[:10]
            if raw_date and "-" not in raw_date and len(raw_date) >= 8:
                fecha_pago = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            else:
                fecha_pago = raw_date

            memo = r.get("LineMemo") or "Saldo a favor no aplicado"

            doc_pr = {
                "doc_num": r.get("DocNum"),
                "consecutivo_fe": "",
                "tipo_codigo": "PR",
                "destino": "N/A",
                "descripcion": memo[:76],
                "fecha": fecha_pago,
                "fecha_vence": fecha_pago,
                "total": -abs(sobrante),
                "saldo": -abs(sobrante),
                "moneda": moneda_pago,
                "esta_vencido": False,
                "dias_vencido": 0,
                "orden_compra": "",
                "vendedor_final": vendedor_general,
            }
            documentos.append(doc_pr)

    return documentos


def procesar_datos_cliente(
    conn: ServiceLayerConnection,
    cliente: Dict,
    saldos_favor_cache: Dict = None,
) -> List[Dict]:
    """
    Procesa un cliente y devuelve UNA LISTA de diccionarios,
    uno por cada vendedor que tenga facturas en este cliente.
    """
    card_code = cliente.get("CardCode")

    # Contacto + descuento real (DiscountGroups) en UNA sola llamada al BP
    contacto, descuento_porcent = obtener_contacto_y_descuento(
        conn, card_code, cliente.get("ContactPerson")
    )

    condicion_pago, plazo_dias = obtener_condicion_pago(
        conn, cliente.get("PayTermsGrpCode")
    )

    # Herencia padre->hijo: si la sucursal no tiene descuento propio, hereda del padre
    if descuento_porcent == 0:
        father = cliente.get("FatherCard")
        if father:
            descuento_porcent = obtener_descuento_cliente(conn, father)

    grupo_descuento = cliente.get("GroupCode", -1)

    moneda_bp = cliente.get("Currency", "CRC")
    moneda_limite = "USD" if moneda_bp in ["USD", "US$"] else "CRC"

    todos_docs = obtener_documentos_cliente(conn, cliente, saldos_favor_cache)
    if not todos_docs:
        return []

    # Agrupar los documentos por vendedor_final
    docs_por_vendedor = {}
    for doc in todos_docs:
        v_id = doc["vendedor_final"]
        if v_id not in docs_por_vendedor:
            docs_por_vendedor[v_id] = []
        docs_por_vendedor[v_id].append(doc)

    # Crear los perfiles de cliente para cada vendedor
    resultados = []

    for v_id, docs_vendedor in docs_por_vendedor.items():
        doc_colones = [d for d in docs_vendedor if d["moneda"] == "CRC"]
        doc_dolares = [d for d in docs_vendedor if d["moneda"] == "USD"]

        total_colones = sum(d["saldo"] for d in doc_colones)
        total_dolares = sum(d["saldo"] for d in doc_dolares)

        if total_colones == 0 and total_dolares == 0:
            continue

        # Determinar las zonas afectadas por este vendedor en este cliente
        zonas_afectadas = list(
            set(
                [
                    d["destino"]
                    for d in docs_vendedor
                    if d["destino"] and d["destino"] != "N/A"
                ]
            )
        )
        zona_gira = (
            ", ".join(zonas_afectadas)
            if zonas_afectadas
            else cliente.get("U_ZGIRA", "N/A")
        )

        perfil_cliente = {
            "vendedor_asignado": v_id,  # Guardamos el ID del vendedor para poder agruparlo luego
            "cliente": {
                "codigo": card_code,
                "nombre": cliente.get("CardName", ""),
                "telefono": cliente.get("Phone1", "")
                or cliente.get("Phone2", "")
                or cliente.get("Cellular", ""),
                "direccion": cliente.get("Address", ""),
                "contacto": contacto.get("nombre", ""),
                "plazo_dias": plazo_dias,
                "descuento_porcent": descuento_porcent,
                "grupo_descuento": grupo_descuento,
                "limite_credito": cliente.get("CreditLimit", 0) or 0,
                "moneda_limite": moneda_limite,
                "zona_gira": zona_gira,
            },
            "documentos": {"colones": doc_colones, "dolares": doc_dolares},
            "totales": {"colones": total_colones, "dolares": total_dolares},
        }
        resultados.append(perfil_cliente)

    return resultados


def obtener_condicion_pago(conn: ServiceLayerConnection, pay_terms_code: int) -> tuple:
    """Obtiene la descripción de la condición de pago y los días, validando errores de SAP."""
    if not pay_terms_code:
        return "No especificado", 30

    try:
        resultado = conn.get(f"PaymentTermsTypes({pay_terms_code})")
        if resultado:
            nombre = resultado.get("PaymentTermsGroupName", "No especificado")

            # Usar la llave correcta que descubrimos
            dias = int(resultado.get("NumberOfAdditionalDays", 0))

            # =================================================================
            # PARCHE PARA ERROR EN SAP:
            # El ID 3 ("Crédito a 30 días") tiene los días en 0 en la base de datos.
            # =================================================================
            if dias == 0 and "30" in nombre:
                dias = 30

            # Fallback general por si SAP devuelve 0 pero no es de contado
            if dias == 0 and "contado" not in nombre.lower() and pay_terms_code != -1:
                dias = 30

            return nombre, dias
    except:
        pass

    return "No especificado", 30


# =============================================================================
# PROCESO PRINCIPAL
# =============================================================================


def ejecutar_reportes_gira(agente_id: str = None):
    print("=" * 80)
    print("🚗 PROCESO: Reportes de Gira para Agentes - Químicas Unidas")
    print(f"   Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 80)

    inicio = time.time()

    if not verificar_estado_rpa():
        print("🚫 RPA desactivado administrativamente en Supabase.")
        return

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        print("\n📋 Obteniendo listado de Agentes...")
        vendedores_cache = obtener_vendedores(conn)

        print("📋 Obteniendo clientes con saldo...")
        clientes = obtener_clientes_con_saldo(
            conn, limite=20 if "--test" in sys.argv else None
        )
        print(f"   Total clientes extraidos: {len(clientes)}")
        if not clientes:
            return

        print("📋 Obteniendo saldos a favor (consulta masiva)...")
        card_codes = [c.get("CardCode") for c in clientes if c.get("CardCode")]
        saldos_favor_cache = obtener_saldos_favor_masivo(conn, card_codes)

        print("\n🔄 Evaluando facturas y asignando agentes por Zona (Multihilo)...")
        agrupados_por_agente = {}
        total_cli = len(clientes)
        procesados = 0

        # =====================================================================
        # PROCESAMIENTO MULTIHILO (Para mayor velocidad)
        # =====================================================================
        with ThreadPoolExecutor(max_workers=12) as executor:
            futuros = {
                executor.submit(
                    procesar_datos_cliente,
                    conn,
                    cli,
                    saldos_favor_cache,
                ): cli
                for cli in clientes
            }

            for futuro in as_completed(futuros):
                procesados += 1
                cli = futuros[futuro]
                # Barra de carga en la misma línea
                print(
                    f"   ⏳ Progreso: {procesados}/{total_cli} clientes evaluados...",
                    end="\r",
                )

                try:
                    perfiles_vendedores = futuro.result()

                    for perfil in perfiles_vendedores:
                        v_id = perfil.pop("vendedor_asignado")

                        # Validamos si el vendedor tiene correo en SAP
                        info_vendedor = vendedores_cache.get(v_id, {})
                        correo_agente = info_vendedor.get("correo", "")

                        if (
                            v_id == -1
                            or not correo_agente
                            or "@" not in str(correo_agente)
                        ):
                            continue

                        if v_id not in agrupados_por_agente:
                            agrupados_por_agente[v_id] = []
                        agrupados_por_agente[v_id].append(perfil)

                except Exception as e:
                    print(
                        f"\n   ⚠️ Error procesando cliente {cli.get('CardCode')}: {e}"
                    )

        print("\n   ✅ Evaluación completada. Preparando PDFs y correos...")

        # =====================================================================
        # GENERACIÓN DE PDF Y ENVÍO DE CORREOS
        # =====================================================================
        sender = EmailSenderAgente()
        sp_uploader = SharePointUploader()
        resultados = {
            "procesados": 0,
            "enviados": 0,
            "errores": 0,
            "sin_correo": 0,
            "pdfs": 0,
            "fallos_envio": 0,
            "total_docs": 0,
            "monto_usd": 0.0,
            "monto_crc": 0.0,
            "vencido_usd": 0.0,
            "vencido_crc": 0.0,
        }

        for vendedor_id, clientes_del_agente in agrupados_por_agente.items():

            # --- NUEVO FILTRO DE AGENTE ESPECÍFICO ---
            if agente_id and str(vendedor_id) != str(agente_id):
                continue

            info_vendedor = vendedores_cache.get(
                vendedor_id, {"nombre": "No Asignado", "correo": ""}
            )
            nombre_agente = info_vendedor["nombre"]
            correo_agente = info_vendedor["correo"]

            print(f"\n👨‍💼 Procesando Agente: {nombre_agente} (ID: {vendedor_id})")

            # Ordenar clientes para que el agente vea el mismo cliente agrupado junto
            # Primero por Nombre, luego por Zona de Gira
            clientes_del_agente.sort(
                key=lambda c: (
                    c["cliente"].get("nombre", ""),
                    str(c["cliente"].get("zona_gira") or "ZZZ").zfill(3),
                )
            )

            datos_reporte = {
                "agente": {
                    "codigo": str(vendedor_id),
                    "nombre": nombre_agente,
                    "correo": correo_agente,
                    "zonas": set(),
                },
                "totales_agente": {"dolares": 0, "colones": 0},
                "clientes": [],
            }

            # Armar la data limpia para el PDF
            for datos_cli in clientes_del_agente:
                datos_reporte["clientes"].append(datos_cli)
                datos_reporte["totales_agente"]["colones"] += datos_cli["totales"][
                    "colones"
                ]
                datos_reporte["totales_agente"]["dolares"] += datos_cli["totales"][
                    "dolares"
                ]

                zona = datos_cli["cliente"]["zona_gira"]
                if zona and zona != "N/A":
                    datos_reporte["agente"]["zonas"].add(str(zona))

            if not datos_reporte["clientes"]:
                print("   ⏭️ Sin documentos pendientes para este agente.")
                continue

            zonas_list = list(datos_reporte["agente"]["zonas"])
            datos_reporte["agente"]["zonas"] = (
                ", ".join(zonas_list) if zonas_list else "Múltiples/No Definida"
            )
            resultados["procesados"] += 1

            # Métricas: documentos y montos de este agente
            resultados["monto_usd"] += datos_reporte["totales_agente"]["dolares"]
            resultados["monto_crc"] += datos_reporte["totales_agente"]["colones"]
            for datos_cli in datos_reporte["clientes"]:
                docs_cli = (
                    datos_cli["documentos"]["colones"]
                    + datos_cli["documentos"]["dolares"]
                )
                resultados["total_docs"] += len(docs_cli)
                for d in docs_cli:
                    if d.get("esta_vencido") and d["saldo"] > 0:
                        if d["moneda"] == "USD":
                            resultados["vencido_usd"] += d["saldo"]
                        else:
                            resultados["vencido_crc"] += d["saldo"]

            try:
                pdf_path = generar_pdf_reporte_gira(datos_reporte)
                print(f"   📄 PDF Generado: {pdf_path}")
                resultados["pdfs"] += 1
                sp_uploader.upload_reporte(pdf_path, "Giras")

                correo_sap = info_vendedor.get("correo", "")

                if MODO_PRUEBA:
                    destinatario = EMAIL_PRUEBA
                    print(
                        f"   📧 MODO PRUEBA: Direccionando a {EMAIL_PRUEBA} (En SAP: '{correo_sap or 'VACÍO'}')"
                    )
                else:
                    destinatario = correo_sap

                if not destinatario or "@" not in str(destinatario):
                    print(f"   ⚠️ Agente {nombre_agente} sin correo. Saltando envío.")
                    resultados["sin_correo"] += 1
                    continue

                exito = sender.enviar_reporte_gira(
                    destinatario, nombre_agente, pdf_path, cc=CORREOS_CC
                )

                if exito:
                    print(f"   ✅ Reporte enviado con éxito.")
                    resultados["enviados"] += 1
                else:
                    print(f"   ❌ Error al enviar el correo.")
                    resultados["errores"] += 1
                    resultados["fallos_envio"] += 1

            except Exception as e:
                print(f"   ❌ Error procesando agente {nombre_agente}: {str(e)}")
                resultados["errores"] += 1

        print("\n" + "=" * 80)
        print("📊 RESUMEN DEL PROCESO DE GIRAS")
        print("=" * 80)
        print(f"   Agentes procesados: {resultados['procesados']}")
        print(f"   Reportes enviados: {resultados['enviados']}")
        print(f"   Agentes sin correo: {resultados['sin_correo']}")
        print(f"   Errores: {resultados['errores']}")
        print("=" * 80)

        # === Consolidar métricas y reportar a Supabase (proceso Giras) ===
        status_global_giras["tiempo_ejecucion"] = round(time.time() - inicio, 2)
        status_global_giras["total_clientes"] = len(clientes)
        status_global_giras["clientes_evaluados"] = procesados
        status_global_giras["total_agentes"] = len(agrupados_por_agente)
        status_global_giras["agentes_procesados"] = resultados["procesados"]
        status_global_giras["reportes_generados"] = resultados["pdfs"]
        status_global_giras["total_documentos_procesados"] = resultados["total_docs"]
        status_global_giras["emails_exitosos"] = resultados["enviados"]
        status_global_giras["emails_fallidos"] = resultados["fallos_envio"]
        status_global_giras["monto_total_usd"] = round(resultados["monto_usd"], 2)
        status_global_giras["monto_total_colones"] = round(resultados["monto_crc"], 2)
        status_global_giras["monto_vencido_usd"] = round(resultados["vencido_usd"], 2)
        status_global_giras["monto_vencido_colones"] = round(
            resultados["vencido_crc"], 2
        )

        errores_gen = resultados["errores"] - resultados["fallos_envio"]
        if errores_gen > 0:
            status_global_giras["observaciones"] = (
                f"{errores_gen} error(es) de generación/proceso"
            )

        finalizar_y_reportar(
            status_global_giras,
            None,
            automatizacion_id=ID_RPA_QU_GIRAS,
            subcarpeta="giras",
        )

    finally:
        conn.logout()


# =============================================================================
# GIRA SELECTIVA (por zona / clientes puntuales)
# =============================================================================
# Bloque AGREGADO por el módulo "Giras por Zona" (ver PLAN_GIRAS_POR_ZONA.md,
# secciones 6 y 7.1). Todo lo que está por encima de esta línea queda intacto:
# estas funciones solo LLAMAN a las existentes, no cambian ninguna firma ni
# ningún comportamiento de ejecutar_reportes_gira().

import re  # solo lo usa _nombre_archivo_gira_zona()

# -----------------------------------------------------------------------------
# Interruptores de este módulo
# -----------------------------------------------------------------------------
#
# Los tres frenos salen del .env, no de una edición al archivo. Antes había que
# editar agentes.py en el VPS para bajar el dry run, y eso dejaba el repo del VPS
# con una modificación local que el siguiente `git pull` iba a pelear. Así el
# código queda idéntico en las dos máquinas y solo cambia el .env.
#
# Todos los defaults son el lado seguro: sin variable, el módulo frena.


def _interruptor_env(nombre: str, por_defecto: bool) -> bool:
    """
    Lee un interruptor del .env sin poder tumbar la API.

    El `cast=bool` de decouple usa strtobool, que revienta con un valor que no
    reconoce ("Falso", "Si", un espacio de más). Sin este try, un dedazo en el
    .env impediría que arranque api.py y se caería también la gira de los
    martes, que no tiene nada que ver con este módulo. Ante un valor inválido se
    usa el default, que siempre es el lado seguro, y se avisa en consola.
    """
    try:
        return bool(config(nombre, default=por_defecto, cast=bool))
    except Exception as e:
        # Sin emoji y sin acentos A PROPOSITO: esto corre en tiempo de import,
        # antes de que api.py reconfigure stdout a utf-8. Con un emoji, la consola
        # cp1252 de Windows lanza UnicodeEncodeError y la red de seguridad tumba
        # el import que venia a proteger. Ya paso una vez.
        print(
            f"ADVERTENCIA: {nombre} tiene un valor invalido en .env ({e}). "
            f"Se usa el default seguro: {por_defecto}"
        )
        return por_defecto


# 🚦 INTERRUPTOR DE SEGURIDAD DE LA ETAPA DE PRUEBAS.
# Con True, ejecutar_gira_selectiva() genera el PDF y se detiene: NO sube a
# SharePoint y NO envía correo, sin importar lo que pida quien la llame.
# Está para que un POST accidental al endpoint no dispare un envío real
# mientras el módulo está a medio probar.
#
# En el VPS hay que poner GIRA_ZONA_DRY_RUN=False en el .env: con el freno puesto
# el módulo genera el PDF y no le llega a nadie.
GIRA_ZONA_FORZAR_DRY_RUN = _interruptor_env("GIRA_ZONA_DRY_RUN", True)

# Copia a gerencia SOLO para la gira selectiva.
# Es una constante propia y NO la de la corrida de los martes a propósito:
# apagarla para probar no puede afectar a ejecutar_reportes_gira(), que sigue
# usando CORREOS_CC directamente (ver sección 4 del plan).
GIRA_ZONA_CC_ACTIVO = True

# Red de seguridad para la ventana de pruebas de envio, cuando
# GIRA_ZONA_FORZAR_DRY_RUN esta en False. Con True, una gira en modo REAL (directo
# al correo del agente, con copia a CORREOS_CC) se bloquea despues de generar el
# PDF: solo pasa el modo revision, que va a un correo puntual y sin copias.
#
# Existe porque bajar el dry run deja un solo clic entre una prueba y un envio a
# los 5 correos de gerencia: basta equivocarse en el desplegable "Metodo" del
# panel. Como los demas interruptores del modulo, solo puede IMPEDIR.
#
# EN PRODUCCION TIENE QUE QUEDAR EN False: con True, Tania no puede mandarle la
# gira al agente, que es justamente para lo que sirve el modulo. Por eso el
# default es False y se sube a True solo durante una ventana de pruebas.
GIRA_ZONA_SOLO_REVISION = _interruptor_env("GIRA_ZONA_SOLO_REVISION", False)

# Subida a SharePoint SOLO de la gira selectiva. Es un interruptor aparte de
# GIRA_ZONA_FORZAR_DRY_RUN porque son dos cosas distintas: se puede querer probar
# un envio de correo real sin dejar un PDF de prueba en la carpeta de produccion.
# Mismo criterio que los otros frenos del modulo: solo puede IMPEDIR. Con False no
# se sube nunca; con True se sigue respetando el dry run, que frena todo antes.
GIRA_ZONA_SUBIR_SHAREPOINT = _interruptor_env("GIRA_ZONA_SUBIR_SHAREPOINT", True)

# Hilos para procesar los clientes seleccionados. Mismo criterio que la corrida
# completa, que usa ThreadPoolExecutor(max_workers=12) sobre la misma conexión.
GIRA_ZONA_MAX_WORKERS = 12

# Techo de espera para las consultas del mapa de ruteo.
#
# Es BAJO a proposito, y mas bajo que los 120s de SQL_TIMEOUT_SEGS. El query
# sano tarda 0,3s; con el servidor cargado, 25-30s. Asi que 60s es holgado.
#
# Primero se habia puesto en 300s, pensando que el problema era falta de
# paciencia. Es al revés: cuando el cliente se rinde por timeout, la consulta
# SIGUE corriendo del lado del Service Layer. Un timeout largo solo alarga el
# rato en que una consulta zombi le ocupa el servidor a todo el mundo —
# incluida la web de produccion y los estados de cuenta, que salen por el
# mismo camino.
GIRA_ZONA_SQL_TIMEOUT = 60

# Carpeta local separada: el nombre del PDF de la gira completa no lleva hora,
# así que compartir carpeta haría que una gira pisara a la otra el mismo día.
GIRA_ZONA_OUTPUT_DIR = "data/reportes_gira_zona"


def obtener_clientes_por_codigos(
    conn: ServiceLayerConnection, card_codes: List[str], lote: int = 15
) -> List[Dict]:
    """
    Trae los clientes indicados con EXACTAMENTE el mismo $select que
    obtener_clientes_con_saldo(), para que procesar_datos_cliente() reciba la
    misma forma de dato y el PDF salga idéntico al de la gira completa.

    Ojo con el $select: si acá se agregara GroupCode, el PDF de la gira por zona
    mostraría un grupo real mientras el de la gira completa sigue mostrando -1,
    y los dos reportes dejarían de coincidir (sección 6.3 del plan).

    Usa lotes con OR en vez de un GET por cliente: menos peticiones y devuelve
    la misma estructura que la corrida normal.
    """
    campos = (
        "CardCode,CardName,Phone1,Phone2,Cellular,CurrentAccountBalance,"
        "SalesPersonCode,U_ZGIRA,CreditLimit,ContactPerson,Address,Currency,"
        "FatherCard,PayTermsGrpCode"
    )

    encontrados: List[Dict] = []
    codigos = [c for c in card_codes if c]

    for i in range(0, len(codigos), lote):
        bloque = codigos[i : i + lote]
        filtro_or = " or ".join([f"CardCode eq '{c}'" for c in bloque])
        encontrados.extend(
            obtener_todos_paginado(
                conn,
                "BusinessPartners",
                {"$filter": f"({filtro_or})", "$select": campos},
                "CardCode",
            )
        )

    return encontrados


# =============================================================================
# PASO 1 DEL PREFILTRO - MAPA DE RUTEO MASIVO
#
# Por qué existe: el árbol de la pantalla filtraba por SalesPersonCode de la
# FICHA del cliente, mientras el PDF rutea por U_CODV de la DIRECCIÓN del
# documento. Son dos universos distintos, y de ahí venía el reclamo: la
# pantalla ofrecía clientes que nunca salían en el PDF (entre 25% y 40% de lo
# que mostraba) y además le faltaban otros que sí salen. Este mapa construye el
# universo con el MISMO criterio del PDF, para que la pantalla solo ofrezca
# clientes que de verdad van a aportar algo.
#
# Columnas y joins verificados contra producción el 30/09/2026 en el Paso 0
# (scripts_investigacion/validar_mapa_ruteo_sql.py). Son columnas planas a
# propósito: el parser de /SQLQueries no acepta aritmética en el SELECT, ni
# funciones escalares, ni CASE, ni subqueries. Todo el cálculo se hace acá en
# Python, con calcular_saldo_documento(), que es la misma regla que usa el PDF.
#
# SOBRE LOS MONTOS (decisión del 01/10/2026, sección 17.14.10 del plan): la
# precisión de /SQLQueries depende de la SESIÓN y redondea a 6 cifras
# significativas, así que los montos de este mapa son APROXIMADOS y la pantalla
# debe mostrarlos como tales. La ELEGIBILIDAD no se decide por monto sino por
# ruteo y conteo de documentos, que de acá salen exactos — así un neto cercano
# a cero no puede cambiar de lado por el redondeo de la sesión. El PDF sigue
# siendo el documento autoritativo.
# =============================================================================

_SQL_COLUMNAS_DOC = (
    'T0."DocEntry", T0."CardCode", T0."ShipToCode", T0."DocCur", '
    'T0."DocTotal", T0."PaidToDate", T0."DocTotalFC", T0."PaidFC", '
    'T0."U_TDOC", T2."U_CODV", T1."SlpCode", T1."CardName", T1."U_ZGIRA", '
    'T1."FatherCard", T1."Phone1", T1."Phone2", T1."Cellular"'
)

# El LEFT JOIN con CRD1 es el que trae el ruteo real del documento. El Paso 0
# comprobó que no duplica filas (1.091 = 1.091), pero duplicaría si un cliente
# tuviera dos direcciones ShipTo del mismo nombre, así que abajo se deduplica
# por DocEntry igual y se avisa si llega a pasar.
_SQL_JOINS_DOC = (
    'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."CardCode" '
    'LEFT JOIN "CRD1" T2 ON T2."CardCode" = T0."CardCode" '
    'AND T2."Address" = T0."ShipToCode" AND T2."AdresType" = \'S\''
)

# El universo de acá es CardType = 'C' (8.036 clientes), y es a propósito MÁS
# ancho que el de obtener_clientes_con_saldo() (427), que además pide
# "CurrentAccountBalance ne 0 or FatherCard ne null". El Paso 0 midió los dos y
# NO coinciden.
#
# No es un problema para este mapa, por dos razones: acá se exige además al
# menos un documento abierto con saldo no despreciable, y la gira por zona
# arma el PDF con obtener_clientes_por_codigos(), que trae al cliente por
# código y no filtra por saldo. O sea, el mapa coincide con el camino que de
# verdad genera el PDF de la gira selectiva.
#
# El caso de borde que esto deja: un cliente cuyo saldo total queda en cero
# porque una factura de un vendedor se cancela contra una NC de otro. Ese
# cliente SÍ aparece en el árbol (y su PDF saldría), pero la gira completa de
# los martes no lo incluye, porque esa sí arranca del universo de 427.
_SQL_FILTRO_CLIENTE = 'T1."CardType" = \'C\''

# Campos de la ficha que la pantalla necesita para dibujar la fila del cliente
_SQL_COLUMNAS_FICHA = (
    'T0."CardCode", T0."CardName", T0."SlpCode", T0."U_ZGIRA", '
    'T0."FatherCard", T0."Phone1", T0."Phone2", T0."Cellular"'
)


def normalizar_codigo_zona(valor) -> str:
    """
    Misma normalización que normalizarCodigoZona() de sap.ts: en SAP hay
    clientes con U_ZGIRA = "06" mientras la UDT U_GIRAS guarda "6". Sin esto,
    esos clientes caen en una zona que no existe.
    """
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return ""
    return str(int(texto)) if texto.isdigit() else texto


def _vendedor_de_fila(fila: Dict) -> int:
    """
    El ruteo de un documento: U_CODV de su dirección de envío y, si no hay, el
    SalesPersonCode de la ficha.

    Replica obtener_mapeo_direcciones() más el mapeo.get(destino,
    vendedor_general) de obtener_documentos_cliente(): ahí solo entran al mapeo
    las direcciones cuyo U_CODV no es None ni cadena vacía, así que una
    dirección sin U_CODV cae al vendedor del cliente igual que una inexistente.
    """
    u_codv = fila.get("U_CODV")
    if u_codv is not None and str(u_codv).strip() != "":
        try:
            return int(u_codv)
        except (TypeError, ValueError):
            pass
    try:
        return int(fila.get("SlpCode") or -1)
    except (TypeError, ValueError):
        return -1


def _datos_ficha(fila: Dict) -> Dict:
    """
    Los campos de la ficha que viajan en el mapa, con el mismo orden de
    preferencia de teléfono que usa procesar_datos_cliente().
    """
    return {
        "nombre": fila.get("CardName", "") or "",
        "telefono": (
            fila.get("Phone1", "")
            or fila.get("Phone2", "")
            or fila.get("Cellular", "")
            or ""
        ),
        "zona": normalizar_codigo_zona(fila.get("U_ZGIRA")),
        "father_card": fila.get("FatherCard") or None,
    }


def obtener_fichas_sql(
    conn: ServiceLayerConnection,
    card_codes: List[str] = None,
    vendedores: List[int] = None,
) -> Dict[str, Dict]:
    """
    Fichas de clientes por SQL, para dos usos distintos:

    - por `card_codes`: completar la ficha de un cliente que llegó al mapa solo
      por saldos a favor, porque la consulta de JDT1 no trae esos campos.
    - por `vendedores`: traer los clientes que el árbol viejo ofrece por
      SalesPersonCode. Son los NO elegibles que la pantalla va a seguir
      mostrando en gris, para que nadie pregunte "¿y dónde está C0037, que yo
      sé que existe?".

    Devuelve {card_code: {nombre, telefono, zona, father_card, slp_code}}.
    """
    condiciones = [_SQL_FILTRO_CLIENTE.replace("T1.", "T0.")]

    if card_codes is not None:
        codigos = sorted({c for c in card_codes if c})
        if not codigos:
            return {}
        lista = ", ".join(["'%s'" % c for c in codigos])
        condiciones.append('T0."CardCode" IN (%s)' % lista)

    if vendedores is not None:
        codigos_v = sorted({int(v) for v in vendedores if v is not None})
        if not codigos_v:
            return {}
        lista_v = ", ".join([str(v) for v in codigos_v])
        condiciones.append('T0."SlpCode" IN (%s)' % lista_v)

    sql = 'SELECT %s FROM "OCRD" T0 WHERE %s' % (
        _SQL_COLUMNAS_FICHA,
        " AND ".join(condiciones),
    )

    fichas: Dict[str, Dict] = {}
    for fila in ejecutar_sql_sl(conn, sql):
        codigo = str(fila.get("CardCode") or "")
        if not codigo:
            continue
        datos = _datos_ficha(fila)
        try:
            datos["slp_code"] = int(fila.get("SlpCode") or -1)
        except (TypeError, ValueError):
            datos["slp_code"] = -1
        fichas[codigo] = datos

    return fichas


def obtener_mapa_ruteo_masivo(
    conn: ServiceLayerConnection,
    solo_vendedores: List[int] = None,
    solo_clientes: List[str] = None,
) -> Dict[Tuple[str, int], Dict]:
    """
    El universo real de la gira, calculado de una sola vez para toda la
    empresa: qué clientes aportarían algo al PDF de cada vendedor.

    Tres consultas de columnas planas (facturas abiertas, notas de crédito
    abiertas desde 2022, y saldos a favor colapsados), más una cuarta para
    completar las fichas que la de saldos a favor no trae. El saldo, el signo y
    el ruteo se calculan acá, reusando calcular_saldo_documento().

    `solo_vendedores` recorta el resultado al final; el cálculo se hace completo
    igual, porque descartar un grupo que queda en cero depende de TODOS los
    documentos del par (cliente, vendedor).

    `solo_clientes` es distinto: acota las CONSULTAS a esos códigos, así que
    las vuelve chicas y rápidas. Es para diagnóstico — comparar unos pocos
    clientes contra el PDF sin barrer la empresa entera, que de día no se
    puede porque cada llamada a /SQLQueries cuesta 25-30s. **No sirve para
    construir el árbol**: ahí hace falta el universo completo, porque el árbol
    tiene que mostrar todos los clientes con carga del agente.

    Devuelve:
        {(card_code, vendedor): {
            "docs": 12, "crc": 1240500.0, "usd": 0.0,
            "nombre": "...", "telefono": "...", "zona": "6",
            "father_card": None,
        }}

    Los montos son aproximados; ver el encabezado de esta sección.
    """
    inicio = time.time()

    # El recorte por cliente, cuando se pide. Los documentos filtran por
    # CardCode y las filas PR por ShortName, que es el mismo código de BP. Se
    # concatena al final del WHERE en vez de meterlo en los literales, para no
    # tocar los queries que el Paso 0 ya verificó.
    filtro_docs = ""
    filtro_pr = ""
    if solo_clientes is not None:
        codigos_cliente = sorted({c for c in solo_clientes if c})
        if not codigos_cliente:
            return {}
        lista_cli = ", ".join(["'%s'" % c for c in codigos_cliente])
        filtro_docs = ' AND T0."CardCode" IN (%s)' % lista_cli
        filtro_pr = ' AND T0."ShortName" IN (%s)' % lista_cli

    sql_facturas = (
        'SELECT %s FROM "OINV" T0 %s WHERE T0."DocStatus" = \'O\' AND %s'
        % (_SQL_COLUMNAS_DOC, _SQL_JOINS_DOC, _SQL_FILTRO_CLIENTE)
    )

    # Las notas de crédito sí llevan filtro de fecha, igual que
    # obtener_documentos_cliente(): evita la basura de antes del 2022. Las
    # facturas no, porque la deuda vieja sigue siendo deuda.
    sql_notas = (
        'SELECT %s FROM "ORIN" T0 %s WHERE T0."DocStatus" = \'O\' AND %s '
        'AND T0."DocDate" >= \'20220101\''
        % (_SQL_COLUMNAS_DOC, _SQL_JOINS_DOC, _SQL_FILTRO_CLIENTE)
    )

    # Saldos a favor. Se rutean por el SlpCode del cliente, NO por dirección
    # (en obtener_documentos_cliente() el doc PR lleva vendedor_general), y
    # siempre restan, así que un SUM alcanza y no hace falta lógica por fila.
    #
    # El INNER JOIN con OCRD no es decorativo: JDT1."ShortName" mezcla códigos
    # de BP con cuentas de mayor, y las cuentas contables tienen decenas de
    # miles de filas. Producción solo consulta códigos de BP.
    sql_saldos_favor = (
        'SELECT T0."ShortName", T0."FCCurrency", COUNT(*) AS "N", '
        'SUM(T0."BalDueCred") AS "CRC", SUM(T0."BalFcCred") AS "USD", '
        'T1."SlpCode" '
        'FROM "JDT1" T0 '
        'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."ShortName" '
        'WHERE T0."BalDueCred" > 0 AND T0."RefDate" >= \'20220101\' '
        'AND T0."TransType" NOT IN (\'13\', \'14\', \'30\') '
        'AND %s '
        'GROUP BY T0."ShortName", T0."FCCurrency", T1."SlpCode"'
        % _SQL_FILTRO_CLIENTE
    )

    # Las tres consultas van con estricto=True y con tres intentos. Esto NO es
    # paranoia, es la lección del 01/10/2026: la consulta de facturas se cayó
    # por timeout, volvió [], y el mapa se armó solo con notas de crédito y
    # saldos a favor — 120 clientes en vez de cientos. Como árbol, eso habría
    # escondido de la pantalla a casi todos los clientes con carga, que es
    # exactamente el daño que este módulo viene a evitar. Un query que falla
    # no es un query sin resultados.
    #
    # El timeout largo tiene la misma raíz: medido ese día en horario de
    # oficina, CADA viaje a /SQLQueries cuesta 25-30s, hasta un COUNT(*) sin
    # joins. El query no es el problema — con DocEntry o sin él, con el join
    # de CRD1 o sin él, tarda lo mismo. De noche corre en 0,3s.
    def consultar(etiqueta: str, sql: str) -> List[Dict]:
        """
        Corre una consulta del universo, con UN reintento y solo cuando vale.

        La regla de cuando reintentar es lo importante acá:

        - Si fue **timeout**, NO se reintenta. El query sigue corriendo del
          lado del Service Layer; mandarle otro le apila una segunda consulta
          de mil facturas encima de la que ya está trabajando. Eso no es
          insistir, es empujar al servidor para abajo.
        - Si el fallo dice que el query **no corrió** (sesión muerta, rechazo
          del SLD, corte al crearlo), reintentar es gratis y vale la pena.
          Cuando fue de sesión se reloguea antes, porque si no el reintento
          vuelve a fallar con 401 sin llegar a correr nada.
        """
        print(f"   [mapa] {etiqueta}...")
        for intento in (1, 2):
            try:
                return ejecutar_sql_sl(
                    conn, sql, estricto=True, timeout_segs=GIRA_ZONA_SQL_TIMEOUT
                )
            except ErrorSqlSl as e:
                tipo = getattr(e, "tipo", "rechazo")

                if intento == 2 or tipo in ("timeout", "tope"):
                    if tipo == "timeout":
                        print(
                            f"   [mapa] {etiqueta}: timeout. NO se reintenta: "
                            f"el query sigue corriendo en SAP y reinsistir le "
                            f"apila otro encima."
                        )
                    raise

                print(
                    f"   [mapa] {etiqueta}: fallo ({tipo}) y el query no "
                    f"corrio. Esperando 15s y reintentando una vez..."
                )
                time.sleep(15)

                if tipo == "auth":
                    try:
                        conn.login()
                    except Exception as e_login:
                        print(f"   [mapa] no se pudo reloguear: {e_login}")
        return []

    if filtro_docs:
        sql_facturas += filtro_docs
        sql_notas += filtro_docs
        # En el de saldos a favor el filtro va antes del GROUP BY, no al final
        sql_saldos_favor = sql_saldos_favor.replace(
            ' GROUP BY ', filtro_pr + ' GROUP BY ', 1
        )

    facturas = consultar("facturas abiertas", sql_facturas)
    notas = consultar("notas de credito", sql_notas)
    filas_pr = consultar("saldos a favor", sql_saldos_favor)

    # Las facturas son el grueso del universo: si vuelven cero, no es que la
    # empresa no tenga deuda, es que algo salió mal. Con solo_clientes no
    # aplica: un puñado de clientes bien puede no tener ninguna factura
    # abierta y tener solo notas de crédito o saldo a favor.
    if not facturas and solo_clientes is None:
        raise RuntimeError(
            "obtener_mapa_ruteo_masivo: la consulta de facturas abiertas "
            "volvio cero filas. El universo de la gira no puede ser vacio."
        )

    acumulado: Dict[Tuple[str, int], Dict] = {}
    fichas_vistas: Dict[str, Dict] = {}

    def acumular(card_code: str, vendedor: int, saldo: float, moneda: str, docs: int):
        entrada = acumulado.setdefault(
            (card_code, vendedor), {"docs": 0, "crc": 0.0, "usd": 0.0}
        )
        entrada["docs"] += docs
        entrada["usd" if moneda == "USD" else "crc"] += saldo

    duplicados = 0

    for filas, es_nota_credito in ((facturas, False), (notas, True)):
        vistos = set()
        for fila in filas:
            # Defensa contra el LEFT JOIN con CRD1: dos direcciones ShipTo del
            # mismo nombre contarían el documento dos veces.
            doc_entry = fila.get("DocEntry")
            if doc_entry is not None:
                if doc_entry in vistos:
                    duplicados += 1
                    continue
                vistos.add(doc_entry)

            card_code = str(fila.get("CardCode") or "")
            if not card_code:
                continue

            calculo = calcular_saldo_documento(
                fila.get("DocCur"),
                fila.get("DocTotalFC"),
                fila.get("PaidFC"),
                fila.get("DocTotal"),
                fila.get("PaidToDate"),
                fila.get("U_TDOC"),
                es_nota_credito,
            )
            if calculo is None:
                continue

            saldo, _total, moneda = calculo
            fichas_vistas.setdefault(card_code, _datos_ficha(fila))
            acumular(card_code, _vendedor_de_fila(fila), saldo, moneda, 1)

    # Un cliente con SOLO saldo a favor queda en negativo, no en cero: SÍ sale
    # en el PDF. Si estas filas se omitieran, el prefiltro esconderia clientes
    # que hoy aparecen.
    for fila in filas_pr:
        card_code = str(fila.get("ShortName") or "")
        if not card_code:
            continue

        try:
            vendedor = int(fila.get("SlpCode") or -1)
        except (TypeError, ValueError):
            vendedor = -1

        es_usd = str(fila.get("FCCurrency") or "") in ["USD", "US$", "DOL"]
        sobrante = float(fila.get("USD" if es_usd else "CRC") or 0)

        # Mismo umbral que obtener_documentos_cliente() para las filas PR
        if sobrante <= 0.05:
            continue

        try:
            cantidad = int(fila.get("N") or 0)
        except (TypeError, ValueError):
            cantidad = 0

        acumular(
            card_code, vendedor, -abs(sobrante), "USD" if es_usd else "CRC", cantidad
        )

    # Los que llegaron solo por saldos a favor no traen ficha: la consulta de
    # JDT1 no selecciona esos campos.
    faltantes = [cc for (cc, _v) in acumulado if cc not in fichas_vistas]
    if faltantes:
        print(
            "   [mapa] fichas de %d cliente(s) sin documentos..."
            % len(faltantes)
        )
        for codigo, datos in obtener_fichas_sql(conn, card_codes=faltantes).items():
            fichas_vistas.setdefault(codigo, datos)

    # Última regla, la de procesar_datos_cliente(): un par (cliente, vendedor)
    # cuyos totales quedan en cero en las dos monedas NO genera perfil, así que
    # tampoco sale en el PDF.
    permitidos = (
        {int(v) for v in solo_vendedores if v is not None}
        if solo_vendedores is not None
        else None
    )

    mapa: Dict[Tuple[str, int], Dict] = {}
    descartados_en_cero = 0

    for (card_code, vendedor), totales in acumulado.items():
        if totales["crc"] == 0 and totales["usd"] == 0:
            descartados_en_cero += 1
            continue
        if permitidos is not None and vendedor not in permitidos:
            continue

        ficha = fichas_vistas.get(
            card_code,
            {"nombre": "", "telefono": "", "zona": "", "father_card": None},
        )
        mapa[(card_code, vendedor)] = {
            "docs": totales["docs"],
            "crc": totales["crc"],
            "usd": totales["usd"],
            "nombre": ficha["nombre"],
            "telefono": ficha["telefono"],
            "zona": ficha["zona"],
            "father_card": ficha["father_card"],
        }

    if duplicados:
        print(
            "   [mapa] AVISO: %d fila(s) duplicadas por el join con CRD1, "
            "descartadas por DocEntry." % duplicados
        )

    clientes = len({cc for (cc, _v) in mapa})
    print(
        "   [mapa] %d par(es) cliente-vendedor, %d cliente(s), en "
        "%.1fs (%d facturas, %d NC, %d filas PR, %d descartado(s) por quedar "
        "en cero)"
        % (
            len(mapa),
            clientes,
            time.time() - inicio,
            len(facturas),
            len(notas),
            len(filas_pr),
            descartados_en_cero,
        )
    )

    return mapa


# =============================================================================
# PASO 3 DEL PREFILTRO - CACHE DEL MAPA Y DE LAS ZONAS
#
# El mapa de ruteo es de toda la empresa, no de un agente, y Tania genera
# varias giras seguidas. Sin cache, cada vez que elige un agente paga el
# barrido completo.
#
# Y no es un lujo: medido el 01/10/2026 en horario de oficina, CADA viaje a
# /SQLQueries cuesta 25-30s, asi que las cuatro consultas del mapa son ~100s.
# De noche son 2s. O sea que el cache es lo que hace usable la pantalla de dia.
#
# Vive en memoria del proceso y se pierde al reiniciar PM2, igual que
# estados_gira_zona de api.py. No hace falta persistirlo: reconstruirlo es
# lento pero no es grave, y un dato viejo de mas de la cuenta es peor que uno
# recalculado.
# =============================================================================

GIRA_ZONA_CACHE_TTL_SEGS = 12 * 60

# El candado evita la estampida: si llegan tres pedidos juntos con el cache
# frio, uno construye el mapa y los otros dos esperan, en vez de barrer SAP
# tres veces en paralelo.
_cache_lock = threading.Lock()
_cache_mapa = {"datos": None, "cuando": 0.0}
_cache_zonas = {"datos": None, "cuando": 0.0}


def _cache_vigente(entrada: Dict) -> bool:
    return (
        entrada["datos"] is not None
        and (time.time() - entrada["cuando"]) < GIRA_ZONA_CACHE_TTL_SEGS
    )


def obtener_nombres_zonas(
    conn: ServiceLayerConnection, refrescar: bool = False
) -> Dict[str, str]:
    """
    Los nombres de las zonas de la UDT U_GIRAS, indexados por codigo
    normalizado: {"6": "SUR SHINDAIWA", "15": "INACTIVAS", ...}.

    Son 19 zonas y casi nunca cambian, asi que entran al mismo cache. La
    normalizacion del codigo no es opcional: en SAP hay clientes con
    U_ZGIRA = "06" mientras U_GIRAS guarda "6", y sin normalizar la pantalla
    mostraria dos zonas distintas para la misma zona real.
    """
    with _cache_lock:
        if not refrescar and _cache_vigente(_cache_zonas):
            return _cache_zonas["datos"]

        nombres: Dict[str, str] = {}
        for z in obtener_todos_paginado(conn, "U_GIRAS", {}, "Code"):
            codigo = normalizar_codigo_zona(z.get("Code"))
            if codigo:
                nombres[codigo] = z.get("Name") or f"Zona {codigo}"

        _cache_zonas["datos"] = nombres
        _cache_zonas["cuando"] = time.time()
        return nombres


def obtener_mapa_ruteo_cacheado(
    conn: ServiceLayerConnection, refrescar: bool = False
) -> Dict[Tuple[str, int], Dict]:
    """
    El mapa de ruteo, construido una vez y reusado hasta que venza el TTL.

    Si falla la construccion, NO se cachea nada y la excepcion sale para
    arriba: el modo estricto de obtener_mapa_ruteo_masivo() existe justamente
    para que un mapa incompleto no llegue a la pantalla, y cachearlo seria
    sostener el error durante doce minutos.
    """
    with _cache_lock:
        if not refrescar and _cache_vigente(_cache_mapa):
            edad = int(time.time() - _cache_mapa["cuando"])
            print(f"   [cache] mapa de ruteo servido del cache ({edad}s de edad)")
            return _cache_mapa["datos"]

        mapa = obtener_mapa_ruteo_masivo(conn)
        _cache_mapa["datos"] = mapa
        _cache_mapa["cuando"] = time.time()
        return mapa


def invalidar_cache_gira_zona():
    """Tira el cache. Para usar desde el endpoint con ?refrescar=1."""
    with _cache_lock:
        _cache_mapa["datos"] = None
        _cache_zonas["datos"] = None


# =============================================================================
# PASO 2 DEL PREFILTRO - EL ARBOL QUE VE LA PANTALLA
#
# Devuelve la MISMA forma que obtenerArbolAgente() de sap.ts, para que el
# frontend solo tenga que agregar campos y no rehacer la pantalla:
#
#   {"agente": {...}, "zonas": [{"zona": {...}, "clientes": [...]}],
#    "sinZona": [...]}
#
# Lo que cambia es de donde sale cada cliente. Antes el arbol se armaba con
# los clientes cuya FICHA tenia SalesPersonCode = agente, y eso no es lo que
# el PDF usa: el PDF rutea por U_CODV de la direccion del documento. De ahi
# venia el reclamo (clientes que se podian marcar y no salian) y tambien un
# faltante que nadie habia reportado.
#
# Ahora los ELEGIBLES salen del mapa de ruteo, o sea del mismo criterio del
# PDF. Los NO ELEGIBLES son los que el arbol viejo ofrecia y no aportan nada:
# se siguen mostrando, en gris y con el motivo, detras de un switch apagado
# por defecto. Mostrarlos no es capricho: evita la pregunta "y donde esta
# C0037, que yo se que existe".
# =============================================================================


def obtener_clientes_del_arbol_viejo(
    conn: ServiceLayerConnection, agente_id: int
) -> List[Dict]:
    """
    Los clientes que la pantalla ofrece HOY para ese agente.

    Es la misma consulta que corre obtenerArbolAgente() en sap.ts: filtra por
    SalesPersonCode de la ficha mas el universo de obtener_clientes_con_saldo().

    El "or FatherCard ne null" NO es opcional: el saldo de una sucursal se
    consolida en la cuenta padre, asi que la sucursal reporta
    CurrentAccountBalance = 0 aunque tenga decenas de facturas abiertas. Sin esa
    clausula se pierden 599 documentos de 50 sucursales, incluida toda la cuenta
    EL COLONO, que es el cliente mas grande de la cartera.

    Se usa solo para saber a quien mostrar en gris. Son ~60-75 filas por agente,
    acotadas por agente, asi que no corre el riesgo de timeout del barrido
    completo.
    """
    return obtener_todos_paginado(
        conn,
        "BusinessPartners",
        {
            "$filter": (
                "CardType eq 'cCustomer' and "
                "(CurrentAccountBalance ne 0 or FatherCard ne null) and "
                f"SalesPersonCode eq {int(agente_id)}"
            ),
            "$select": (
                "CardCode,CardName,U_ZGIRA,SalesPersonCode,Phone1,Phone2,"
                "Cellular,FatherCard"
            ),
        },
        "CardCode",
    )


def construir_arbol_gira_zona(
    conn: ServiceLayerConnection,
    agente_id: int,
    refrescar: bool = False,
) -> Dict:
    """
    El arbol de zonas y clientes de un agente, con la elegibilidad resuelta.

    Cada cliente viene con:
      - elegible: si aportaria algo al PDF de ese agente
      - docs, crc, usd: cuantos documentos y por cuanto (montos APROXIMADOS,
        ver el encabezado del Paso 1; el PDF sigue siendo el autoritativo)
      - motivo y vendedorNombre: solo en los no elegibles

    Dos motivos posibles, que es exactamente lo que el usuario necesita saber
    para no quedarse con la duda:
      - "otro_vendedor": el cliente tiene documentos abiertos, pero rutean a
        otro agente. Va con el nombre de ese agente.
      - "sin_documentos": no tiene nada abierto que sumar.
    """
    agente_id = int(agente_id)

    mapa = obtener_mapa_ruteo_cacheado(conn, refrescar=refrescar)
    nombres_zona = obtener_nombres_zonas(conn, refrescar=refrescar)
    vendedores = obtener_vendedores(conn)

    if agente_id not in vendedores:
        raise ValueError(f"El agente {agente_id} no existe en SAP")

    # 1. Los elegibles: del mapa, o sea del criterio del PDF
    clientes: Dict[str, Dict] = {}
    for (card_code, vendedor), datos in mapa.items():
        if vendedor != agente_id:
            continue
        clientes[card_code] = {
            "cardCode": card_code,
            "cardName": datos["nombre"],
            "telefono": datos["telefono"],
            # Normalizar de nuevo, aunque el mapa ya lo haga: es idempotente
            # y asi la agrupacion por zona no depende de un invariante de
            # otra funcion. Confiar en que "alguien mas ya lo hizo" es el tipo
            # de acoplamiento que causo el desfase que este modulo corrige.
            "zonaCode": normalizar_codigo_zona(datos["zona"]),
            "vendedorCode": agente_id,
            "fatherCard": datos["father_card"],
            "elegible": True,
            "docs": datos["docs"],
            "crc": datos["crc"],
            "usd": datos["usd"],
        }

    # 2. Los no elegibles: los que el arbol viejo ofrece y no quedaron arriba.
    #    Para el motivo hace falta saber si sus documentos se los lleva otro.
    otros_vendedores: Dict[str, List[int]] = {}
    for (card_code, vendedor) in mapa:
        if vendedor != agente_id:
            otros_vendedores.setdefault(card_code, []).append(vendedor)

    for cliente in obtener_clientes_del_arbol_viejo(conn, agente_id):
        card_code = cliente.get("CardCode")
        if not card_code or card_code in clientes:
            continue

        duenos = sorted(otros_vendedores.get(card_code, []))
        if duenos:
            motivo = "otro_vendedor"
            nombres = [
                vendedores.get(v, {}).get("nombre") or f"Vendedor {v}"
                for v in duenos
            ]
            vendedor_nombre = ", ".join(nombres)
        else:
            motivo = "sin_documentos"
            vendedor_nombre = None

        clientes[card_code] = {
            "cardCode": card_code,
            "cardName": cliente.get("CardName") or "",
            "telefono": (
                cliente.get("Phone1")
                or cliente.get("Phone2")
                or cliente.get("Cellular")
                or ""
            ),
            "zonaCode": normalizar_codigo_zona(cliente.get("U_ZGIRA")),
            "vendedorCode": cliente.get("SalesPersonCode"),
            "fatherCard": cliente.get("FatherCard") or None,
            "elegible": False,
            "docs": 0,
            "crc": 0.0,
            "usd": 0.0,
            "motivo": motivo,
            "vendedorNombre": vendedor_nombre,
        }

    # 3. Agrupar por zona, con el nombre resuelto
    por_zona: Dict[str, List[Dict]] = {}
    sin_zona: List[Dict] = []

    for cliente in clientes.values():
        codigo = cliente["zonaCode"]
        cliente["zonaNombre"] = (
            nombres_zona.get(codigo, f"Zona {codigo}")
            if codigo
            else "Sin zona asignada"
        )
        if codigo:
            por_zona.setdefault(codigo, []).append(cliente)
        else:
            sin_zona.append(cliente)

    # 4. Ordenar igual que hoy: clientes por nombre, zonas por cantidad.
    #    Las zonas se ordenan por cantidad de ELEGIBLES, no por el total: lo
    #    que le importa a quien arma la gira es donde hay trabajo, y con el
    #    switch apagado el total es invisible.
    def orden_cliente(c):
        return (c["cardName"] or "").upper()

    zonas = []
    for codigo, lista in por_zona.items():
        lista.sort(key=orden_cliente)
        elegibles = sum(1 for c in lista if c["elegible"])
        zonas.append(
            {
                "zona": {
                    "codigo": codigo,
                    "nombre": nombres_zona.get(codigo, f"Zona {codigo}"),
                },
                "clientes": lista,
                "totalElegibles": elegibles,
                "totalNoElegibles": len(lista) - elegibles,
            }
        )

    zonas.sort(key=lambda z: (-z["totalElegibles"], z["zona"]["nombre"]))
    sin_zona.sort(key=orden_cliente)

    total_elegibles = sum(z["totalElegibles"] for z in zonas) + sum(
        1 for c in sin_zona if c["elegible"]
    )
    total_no_elegibles = sum(z["totalNoElegibles"] for z in zonas) + sum(
        1 for c in sin_zona if not c["elegible"]
    )

    return {
        "agente": {
            "codigo": agente_id,
            "nombre": vendedores[agente_id].get("nombre", "No asignado"),
            "correo": vendedores[agente_id].get("correo", ""),
        },
        "zonas": zonas,
        "sinZona": sin_zona,
        "totalElegibles": total_elegibles,
        "totalNoElegibles": total_no_elegibles,
        # Que la pantalla pueda decir "montos aproximados" sin hardcodearlo
        "montosAproximados": True,
    }


def _nombre_archivo_gira_zona(
    pdf_path: str,
    codigo_agente: str,
    nombre_agente: str,
    zona_nombre: str = None,
) -> str:
    """
    Renombra el PDF para que no colisione con el de la gira completa.

    Gira completa:  GIRA_{codigo}_{nombre}_{YYYYMMDD}.pdf
    Gira por zona:  GIRA_{codigo}_{nombre}_{ZONA}_{YYYYMMDD_HHMM}.pdf

    Sin esto, en SharePoint el PDF parcial sobrescribe el reporte oficial del día
    (mismo nombre, misma carpeta). La hora va además de la zona porque dos giras
    de la misma zona el mismo día también se pisarían entre sí.

    Decisión de Irving (sección 15.1 del plan): mismo SharePoint, misma carpeta,
    nombre distinto. Por eso NO se toca sharepoint_qu.py.
    """
    carpeta = os.path.dirname(pdf_path)

    zona = zona_nombre or "SELECCION"
    # Caracteres que SharePoint no acepta en un nombre de archivo
    zona = re.sub(r'[\\/:*?"<>|,]', "", str(zona)).strip().replace(" ", "_")[:28]
    if not zona:
        zona = "SELECCION"

    agente = str(nombre_agente).replace(" ", "_")[:20]
    sello = datetime.now().strftime("%Y%m%d_%H%M")

    nuevo = os.path.join(carpeta, f"GIRA_{codigo_agente}_{agente}_{zona}_{sello}.pdf")

    try:
        os.replace(pdf_path, nuevo)
        return nuevo
    except OSError as e:
        # Si el renombrado falla es preferible seguir con el nombre original
        # que abortar la gira: el riesgo es solo de colisión en SharePoint.
        print(f"   ⚠️ No se pudo renombrar el PDF ({e}). Se usa: {pdf_path}")
        return pdf_path


# Cuanto texto entra en la banda azul del encabezado del PDF. La banda se dibuja
# con cell() en agentepdf.py:122, que NO parte la linea: lo que no entra no baja
# de renglon, se sale de la pagina. Con 1008 pt de ancho y Arial Bold 12 entran
# unos 125 caracteres contando " AGENTE: <nombre> | ZONAS: ".
GIRA_ZONA_MAX_CHARS_ZONAS = 85


def _normalizar_destino(destino: str) -> str:
    """
    Llave con la que se comparan dos destinos para decidir si son el mismo
    lugar: sin tildes, en mayúsculas y con los espacios colapsados.

    Hace falta porque SAP devuelve el mismo destino escrito de varias formas
    según quién cargó la dirección. En la corrida del 02/10/2026 "GUAPILES" y
    "Guápiles" se contaron como dos destinos distintos, y son uno.

    Solo sirve para COMPARAR. Lo que se muestra es siempre el texto original,
    porque "CAÑAS" tiene que seguir saliendo con eñe.
    """
    base = unicodedata.normalize("NFKD", str(destino))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return " ".join(base.upper().split())


def _encabezado_zonas_calculado(destinos_por_cliente) -> str:
    """
    Texto del "ZONAS:" del PDF cuando el usuario NO eligió una zona, es decir
    cuando la selección es mixta y hay que deducirla de los documentos.

    Recibe los destinos YA SEPARADOS, uno por elemento del conjunto.

    Antes recibía el `zona_gira` de cada cliente —que es la lista de destinos
    de ese cliente unida por ", "— y los volvía a partir por coma acá. Eso
    contaba mal todo destino que trae coma propia: el 02/10/2026 el destino
    "Jicaral, Puntarenas" se partió en "Jicaral" y "Puntarenas", y el
    encabezado anunció 15 destinos donde había 14. Desde el string ya unido el
    caso es indecidible, porque el separador y la coma interna son el mismo
    ", "; por eso el que llama junta los destinos de los documentos de a uno y
    no los une nunca.

    Hace dos cosas más que el cálculo crudo no hacía:

    1. Deduplica destino por destino, comparando con _normalizar_destino(): en
       la prueba del 28/09 con 43 clientes salieron 82 entradas para 49
       destinos reales, GUAPILES cuatro veces.
    2. Recorta. Esas 82 entradas eran 833 caracteres en una sola línea: se veía
       el primer 18% y el resto se salía de la página, cortado a media palabra.

    Cuando no cabe se pone el conteo y se manda al detalle, que igual está en la
    columna "Destino" de cada fila del reporte.

    Solo lo usa la gira selectiva. La corrida de los martes sigue armando su
    encabezado como siempre (mismo defecto, pero es código existente que no se
    toca sin autorización).
    """
    # Un solo destino por llave normalizada. De las variantes que escriben el
    # mismo lugar se queda la menor alfabéticamente, para que el encabezado no
    # cambie de una corrida a otra según el orden en que llegaron los
    # documentos.
    unicos: Dict[str, str] = {}
    for destino in destinos_por_cliente or ():
        texto = str(destino).strip()
        if not texto:
            continue
        llave = _normalizar_destino(texto)
        if not llave:
            continue
        if llave not in unicos or texto < unicos[llave]:
            unicos[llave] = texto

    if not unicos:
        return "Selección manual"

    destinos = [unicos[llave] for llave in sorted(unicos)]

    texto = ", ".join(destinos)
    if len(texto) <= GIRA_ZONA_MAX_CHARS_ZONAS:
        return f"Selección manual · {texto}"

    return (
        f"Selección manual · {len(destinos)} destinos "
        "(ver la columna Destino de cada fila)"
    )


# Endpoints cuyo fallo invalida la evaluacion de un cliente.
#
# No es "cualquier fallo": si se cae PaymentTermsTypes, el PDF sale sin la
# condicion de pago y es un defecto cosmetico. Pero si se cae alguno de estos
# tres, lo que sale mal es el dinero o el ruteo:
#
#   Invoices / CreditNotes -> los documentos que se cobran
#   BusinessPartners(...)  -> obtener_mapeo_direcciones lee de ahi el U_CODV de
#                             cada direccion. Si falla, devuelve {} y TODOS los
#                             documentos caen al SlpCode del cliente, o sea el
#                             cliente puede quedar atribuido al agente
#                             equivocado sin que nada avise.
_ENDPOINTS_CRITICOS = ("Invoices", "CreditNotes", "BusinessPartners")

# Los fallos se cuentan por hilo, porque cada cliente se evalua en un hilo del
# ThreadPoolExecutor. Asi se sabe cual cliente quedo sin datos confiables, en
# vez de saber solo que "hubo errores en algun lado".
_fallos_hilo = threading.local()


def _es_endpoint_critico(endpoint: str) -> bool:
    return str(endpoint or "").split("(")[0].split("?")[0] in _ENDPOINTS_CRITICOS


def _instrumentar_get(conn) -> callable:
    """
    Envuelve conn.get para contar los fallos de esta corrida, y devuelve la
    funcion original para poder restaurarla.

    No se toca conexion.py a proposito: ese archivo lo comparten la gira de los
    martes y los estados de cuenta, y cambiarle el contrato es una decision
    aparte (ver PLAN_GIRAS_POR_ZONA.md 17.14.18, arreglo 1).

    conn.get() devuelve None SOLO cuando algo fallo: una respuesta vacia
    legitima vuelve como dict con "value": []. Asi que None == fallo, sin
    ambiguedad.
    """
    original = conn.get

    def get_contado(endpoint, params=None):
        respuesta = original(endpoint, params)
        if respuesta is None and _es_endpoint_critico(endpoint):
            _fallos_hilo.n = getattr(_fallos_hilo, "n", 0) + 1
        return respuesta

    conn.get = get_contado
    return original


def _evaluar_cliente_contando(conn, cliente, saldos_favor_cache):
    """
    Corre procesar_datos_cliente y devuelve (perfiles, fallos_de_SAP).

    El contador se pone en cero al entrar porque los hilos del pool se reusan:
    sin esto, un cliente heredaria los fallos del anterior que le toco el mismo
    hilo.
    """
    _fallos_hilo.n = 0
    perfiles = procesar_datos_cliente(conn, cliente, saldos_favor_cache)
    return perfiles, getattr(_fallos_hilo, "n", 0)


def ejecutar_gira_selectiva(
    agente_id: str,
    card_codes: List[str],
    modo_prueba: bool = False,
    email_prueba: str = None,
    zona_nombre: str = None,
    dry_run: bool = False,
) -> Dict:
    """
    Genera la gira SOLO para los clientes indicados del agente indicado.

    Reutiliza las mismas funciones que la corrida completa, así que el PDF sale
    con el mismo formato y los mismos datos.

    IMPORTANTE: modo_prueba y email_prueba son PARÁMETROS, no globals. Leer
    agentes.MODO_PRUEBA acá produciría una race condition con la cola de la gira
    completa, que escribe ese mismo global desde otro hilo: una gira de revisión
    lanzada 30 segundos antes podría terminar enviándose a los agentes reales
    (sección 6.1 del plan).

    Args:
        agente_id:    código del vendedor (str o int)
        card_codes:   CardCodes seleccionados por el usuario
        modo_prueba:  True = enviar a email_prueba en vez de al agente
        email_prueba: destino cuando modo_prueba=True
        zona_nombre:  nombre de zona para el encabezado del PDF y el archivo
        dry_run:      True = genera el PDF pero NO sube a SharePoint ni envía

    Returns:
        dict con el resultado real, para que la interfaz pueda informarlo:
        {
            "ok": bool,
            "solicitados": int,       # cuántos pidió el usuario
            "procesados": int,        # cuántos llegaron al PDF
            "omitidos": list,         # sin documentos, inexistentes u otro vendedor
            "omitidos_detalle": dict, # los omitidos separados por motivo
            "pdf": str | None,
            "enviado_a": str | None,
            "dry_run": bool,          # si terminó sin enviar
            "mensaje": str,
        }
    """
    # El interruptor de módulo manda sobre lo que pida quien llama: nunca puede
    # habilitar un envío, solo impedirlo.
    dry_run_efectivo = bool(dry_run) or GIRA_ZONA_FORZAR_DRY_RUN

    resultado = {
        "ok": False,
        "solicitados": len(card_codes or []),
        "procesados": 0,
        "omitidos": [],
        "omitidos_detalle": {
            "sin_documentos": [],
            "otro_vendedor": [],
            "inexistentes": [],
        },
        "pdf": None,
        "enviado_a": None,
        "dry_run": dry_run_efectivo,
        "mensaje": "",
    }

    if not card_codes:
        resultado["mensaje"] = "No se recibió ningún cliente seleccionado"
        print(f"⚠️ {resultado['mensaje']}")
        return resultado

    # Mismo kill-switch administrativo que respeta la corrida completa.
    if not verificar_estado_rpa():
        resultado["mensaje"] = "RPA desactivado administrativamente en Supabase"
        print(f"🚫 {resultado['mensaje']}")
        return resultado

    print("=" * 80)
    print("🎯 GIRA SELECTIVA POR ZONA")
    print(f"   Agente: {agente_id} · Clientes solicitados: {len(card_codes)}")
    print(f"   Zona: {zona_nombre or '(selección mixta)'}")
    if dry_run_efectivo:
        motivo = "interruptor del módulo" if GIRA_ZONA_FORZAR_DRY_RUN else "petición"
        print(f"   🧪 DRY RUN activo por {motivo}: no se sube ni se envía nada")
    print("=" * 80)

    inicio = time.time()

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        resultado["mensaje"] = "No se pudo conectar a SAP Service Layer"
        print(f"❌ {resultado['mensaje']}")
        return resultado

    # Contar los fallos de SAP de esta corrida. Se restaura en el finally.
    get_original = _instrumentar_get(conn)

    try:
        try:
            agente_key = int(agente_id)
        except (TypeError, ValueError):
            resultado["mensaje"] = f"Código de agente inválido: {agente_id!r}"
            print(f"❌ {resultado['mensaje']}")
            return resultado

        vendedores_cache = obtener_vendedores(conn)
        info_agente = vendedores_cache.get(agente_key)
        if not info_agente:
            resultado["mensaje"] = f"Agente {agente_id} no encontrado en SAP"
            print(f"❌ {resultado['mensaje']}")
            return resultado

        # ------------------------------------------------------------------
        # 1. Clientes solicitados (mismo $select que la corrida completa)
        # ------------------------------------------------------------------
        print("📋 Trayendo los clientes seleccionados...")
        clientes = obtener_clientes_por_codigos(conn, card_codes)
        if not clientes:
            resultado["mensaje"] = "Ninguno de los clientes solicitados existe en SAP"
            print(f"⚠️ {resultado['mensaje']}")
            return resultado

        encontrados = {c.get("CardCode") for c in clientes if c.get("CardCode")}
        print(f"   {len(encontrados)} de {len(card_codes)} clientes encontrados")

        inexistentes = set(card_codes) - encontrados

        # ------------------------------------------------------------------
        # 2. Saldos a favor solo de estos clientes
        # ------------------------------------------------------------------
        print("📋 Consultando saldos a favor...")
        saldos_favor_cache = obtener_saldos_favor_masivo(conn, sorted(encontrados))

        # ------------------------------------------------------------------
        # 3. Procesar cada cliente con la MISMA lógica de la corrida normal
        #    (mismo patrón multihilo que ejecutar_reportes_gira)
        # ------------------------------------------------------------------
        print(f"\n🔄 Evaluando documentos de {len(clientes)} clientes...")
        agrupados = []
        con_documentos = set()
        # Clientes que SI tienen documentos abiertos, pero todos rutean a otro
        # vendedor. Se separan de los que no tienen nada: para el usuario son dos
        # situaciones distintas y el mensaje viejo las mezclaba (hallazgo 10).
        ruteados_a_otro = set()
        otros_vendedores = set()
        # Clientes cuya evaluación no se puede creer porque SAP falló mientras
        # se los consultaba. NO son clientes sin deuda: son clientes sin
        # respuesta. Mezclarlos con los que no tienen nada es afirmar un hecho
        # del negocio a partir de un error técnico, y es exactamente lo que
        # pasó el 01/10/2026 (plan 17.14.18): la pantalla dijo "no hay nada que
        # cobrar" de cinco clientes que entre todos tenían 68 documentos.
        no_evaluables = set()
        procesados_cont = 0
        total_cli = len(clientes)

        with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as executor:
            futuros = {
                executor.submit(
                    _evaluar_cliente_contando, conn, cli, saldos_favor_cache
                ): cli
                for cli in clientes
            }

            for futuro in as_completed(futuros):
                procesados_cont += 1
                cli = futuros[futuro]
                print(
                    f"   ⏳ Progreso: {procesados_cont}/{total_cli} clientes evaluados...",
                    end="\r",
                )

                try:
                    perfiles, fallos_sap = futuro.result()
                except Exception as e:
                    # Una excepción tampoco es "no tiene deuda".
                    print(f"\n   ⚠️ Error procesando {cli.get('CardCode')}: {e}")
                    no_evaluables.add(cli.get("CardCode"))
                    continue

                if fallos_sap:
                    # Acá está el caso que se nos escapó: estos clientes NO
                    # tiran excepción. conn.get() devuelve None ante un error y
                    # obtener_todos_paginado lo trata igual que "no hay más
                    # páginas", así que procesar_datos_cliente devuelve [] o una
                    # lista PARCIAL sin avisar. Con una lista parcial el cliente
                    # entraría al PDF con facturas de menos y totales mal, que
                    # es peor que no entrar.
                    print(
                        f"\n   ⚠️ {cli.get('CardCode')}: {fallos_sap} consulta(s) "
                        f"a SAP fallaron. No se puede saber qué debe; queda fuera."
                    )
                    no_evaluables.add(cli.get("CardCode"))
                    continue

                # perfiles no vacío = el cliente tiene documentos abiertos,
                # aunque no necesariamente de este agente.
                ajenos = set()
                for perfil in perfiles:
                    v_id = perfil.pop("vendedor_asignado")
                    # El documento pertenece a este agente según BPAddresses.U_CODV,
                    # no según el SalesPersonCode del cliente: un cliente puede
                    # tener direcciones ruteadas a otro vendedor.
                    if str(v_id) == str(agente_key):
                        agrupados.append(perfil)
                        con_documentos.add(cli.get("CardCode"))
                    else:
                        ajenos.add(v_id)

                if perfiles and cli.get("CardCode") not in con_documentos:
                    ruteados_a_otro.add(cli.get("CardCode"))
                    otros_vendedores.update(ajenos)

        print("\n   ✅ Evaluación completada.")

        # Arreglo 3: no construir un PDF sobre SAP caído. Si NINGÚN cliente se
        # pudo evaluar, no hay documento que generar — generarlo igual produce
        # un PDF que se ve normal y no lo es.
        if no_evaluables and not con_documentos:
            resultado["omitidos"] = sorted(set(card_codes))
            resultado["omitidos_detalle"] = {
                "sin_documentos": [],
                "otro_vendedor": [],
                "inexistentes": sorted(inexistentes),
                "no_evaluables": sorted(no_evaluables),
            }
            resultado["mensaje"] = (
                f"SAP no respondió: fallaron las consultas de "
                f"{len(no_evaluables)} cliente(s) y no se pudo evaluar a "
                f"ninguno. NO se generó PDF. Reintentá en un rato."
            )
            print(f"❌ {resultado['mensaje']}")
            return resultado

        sin_documentos = encontrados - con_documentos - no_evaluables
        # Sin ningún documento abierto en SAP: ni propio ni de otro vendedor.
        sin_nada = sin_documentos - ruteados_a_otro

        resultado["omitidos"] = sorted(inexistentes | sin_documentos | no_evaluables)
        resultado["procesados"] = len(con_documentos)

        # Por qué quedó fuera cada uno. `omitidos` se deja igual para no cambiar
        # el contrato que ya consume la web; esto se agrega al lado.
        resultado["omitidos_detalle"] = {
            "sin_documentos": sorted(sin_nada),
            "otro_vendedor": sorted(ruteados_a_otro),
            "inexistentes": sorted(inexistentes),
            # Clave nueva. La web la muestra aparte: no es lo mismo "este
            # cliente no debe nada" que "no pudimos averiguar qué debe".
            "no_evaluables": sorted(no_evaluables),
        }

        # Frase que explica POR QUE quedaron fuera, para reusarla en los mensajes.
        # El mensaje viejo decía "no tiene documentos pendientes asignados a X", que
        # es cierto pero se lee como si todos fueran del otro caso (hallazgo 10).
        motivos = []
        if sin_nada:
            motivos.append(
                f"{len(sin_nada)} sin ningún documento abierto en SAP"
            )
        if ruteados_a_otro:
            nombres_otros = sorted(
                vendedores_cache.get(v, {}).get("nombre") or f"vendedor {v}"
                for v in otros_vendedores
            )
            motivos.append(
                f"{len(ruteados_a_otro)} con documentos abiertos que rutean a "
                f"otro vendedor ({', '.join(nombres_otros)})"
            )
        if inexistentes:
            motivos.append(f"{len(inexistentes)} sin ficha en SAP")
        if no_evaluables:
            motivos.append(
                f"{len(no_evaluables)} que SAP no pudo responder (reintentá)"
            )
        desglose_omitidos = "; ".join(motivos)

        if not agrupados:
            resultado["mensaje"] = (
                f"No hay nada que cobrar para {info_agente['nombre']} en esta "
                f"selección: de {len(card_codes)} clientes, {desglose_omitidos}."
            )
            print(f"⏭️ {resultado['mensaje']}")
            return resultado

        # ------------------------------------------------------------------
        # 4. Mismo orden que la corrida normal
        # ------------------------------------------------------------------
        # El código va de tercer criterio para que el orden sea reproducible.
        # Sin él, dos clientes con el MISMO nombre y la misma zona empatan la
        # llave entera, y como sort() es estable el orden que queda es el que
        # trajo as_completed(), o sea cuál de los dos contestó primero SAP. El
        # 02/10/2026 dos corridas de los mismos 10 clientes sacaron C0076 y
        # C0077 ("CENTRO AGRIC.CANTONAL DE PUNTARENAS", el nombre repetido en
        # SAP) intercambiados entre un PDF y el otro.
        agrupados.sort(
            key=lambda c: (
                c["cliente"].get("nombre", ""),
                str(c["cliente"].get("zona_gira") or "ZZZ").zfill(3),
                c["cliente"].get("codigo", ""),
            )
        )

        # ------------------------------------------------------------------
        # 5. Estructura idéntica a la que espera generar_pdf_reporte_gira
        # ------------------------------------------------------------------
        datos_reporte = {
            "agente": {
                "codigo": str(agente_key),
                "nombre": info_agente["nombre"],
                "correo": info_agente.get("correo", ""),
                "zonas": set(),
            },
            "totales_agente": {"dolares": 0, "colones": 0},
            "clientes": [],
        }

        for datos_cli in agrupados:
            datos_reporte["clientes"].append(datos_cli)
            datos_reporte["totales_agente"]["colones"] += datos_cli["totales"]["colones"]
            datos_reporte["totales_agente"]["dolares"] += datos_cli["totales"]["dolares"]
            # Los destinos se juntan de los documentos, de a uno, y NO del
            # `zona_gira` del cliente: ese ya viene unido por ", " y un destino
            # con coma propia ("Jicaral, Puntarenas") no se puede volver a
            # separar sin partirlo en dos. Ver _encabezado_zonas_calculado().
            destinos_cli = {
                (doc.get("destino") or "").strip()
                for doc in datos_cli["documentos"]["colones"]
                + datos_cli["documentos"]["dolares"]
            }
            destinos_cli = {d for d in destinos_cli if d and d != "N/A"}
            if destinos_cli:
                datos_reporte["agente"]["zonas"].update(destinos_cli)
            else:
                # Si ningún documento trae destino, procesar_datos_cliente deja
                # en zona_gira el U_ZGIRA de la ficha, que es un valor suelto.
                zona = datos_cli["cliente"].get("zona_gira")
                if zona and zona != "N/A":
                    datos_reporte["agente"]["zonas"].add(str(zona))

        # El nombre de zona que eligió el usuario manda sobre el calculado, porque
        # zona_gira sale del ShipToCode del documento y no de U_ZGIRA.
        if zona_nombre:
            datos_reporte["agente"]["zonas"] = zona_nombre
        else:
            datos_reporte["agente"]["zonas"] = _encabezado_zonas_calculado(
                datos_reporte["agente"]["zonas"]
            )

        # ------------------------------------------------------------------
        # 6. PDF en carpeta y con nombre propios: no pisar la gira completa
        # ------------------------------------------------------------------
        pdf_path = generar_pdf_reporte_gira(
            datos_reporte, output_dir=GIRA_ZONA_OUTPUT_DIR
        )
        pdf_path = _nombre_archivo_gira_zona(
            pdf_path, str(agente_key), info_agente["nombre"], zona_nombre
        )
        resultado["pdf"] = pdf_path
        print(f"📄 PDF generado: {pdf_path}")
        print(
            f"   {resultado['procesados']} clientes · "
            f"{len(datos_reporte['clientes'])} bloques · "
            f"{round(time.time() - inicio, 1)}s"
        )

        # El motivo de las omisiones va en el mensaje aunque SI se haya generado el
        # PDF: es el caso normal (43 de 65) y el usuario necesita saber por qué.
        cola = f" Quedaron fuera {desglose_omitidos}." if desglose_omitidos else ""

        if dry_run_efectivo:
            resultado["ok"] = True
            resultado["mensaje"] = (
                f"DRY RUN: PDF generado con {resultado['procesados']} de "
                f"{len(card_codes)} clientes. No se subió a SharePoint ni se "
                f"envió correo.{cola}"
            )
            print(f"🧪 {resultado['mensaje']}")
            return resultado

        # ------------------------------------------------------------------
        # 7. SharePoint — misma carpeta "Giras", nombre distinto (ver 15.1)
        # ------------------------------------------------------------------
        if GIRA_ZONA_SUBIR_SHAREPOINT:
            try:
                SharePointUploader().upload_reporte(pdf_path, "Giras")
            except Exception as e:
                # Que falle el respaldo no debe impedir que el agente reciba su gira
                print(f"   ⚠️ Error subiendo a SharePoint: {e}")
        else:
            print(
                "   ☁️ SharePoint: NO se sube "
                "(GIRA_ZONA_SUBIR_SHAREPOINT = False)"
            )

        # ------------------------------------------------------------------
        # 8. Envío
        # ------------------------------------------------------------------
        destinatario = email_prueba if modo_prueba else info_agente.get("correo", "")

        if GIRA_ZONA_SOLO_REVISION and not modo_prueba:
            resultado["mensaje"] = (
                "Bloqueado por GIRA_ZONA_SOLO_REVISION: esta gira iba en modo REAL "
                "(directo al agente, con copia a gerencia) y el módulo está en "
                "ventana de pruebas. El PDF se generó pero no se envió nada."
            )
            print(f"🛑 {resultado['mensaje']}")
            return resultado

        if not destinatario or "@" not in str(destinatario):
            resultado["mensaje"] = (
                "El PDF se generó pero no hay un destinatario válido para el envío"
            )
            print(f"⚠️ {resultado['mensaje']}")
            return resultado

        if modo_prueba:
            print(f"📧 MODO REVISIÓN → {destinatario}")
        else:
            print(f"📧 MODO REAL → {destinatario}")

        # El CC a gerencia NUNCA se aplica en modo revisión: una gira dirigida a
        # un correo puntual es una prueba, y no tiene por qué llegarles a los 5
        # correos de CORREOS_CC (cuatro de ellos de Químicas Unidas). Así, bajar
        # GIRA_ZONA_FORZAR_DRY_RUN para probar un envío no puede filtrar nada:
        # no hay que acordarse de bajar también GIRA_ZONA_CC_ACTIVO.
        copias = CORREOS_CC if (GIRA_ZONA_CC_ACTIVO and not modo_prueba) else None
        if copias:
            print(f"   CC: {', '.join(copias)}")
        elif modo_prueba:
            print("   CC: desactivado (modo revisión: nunca se copia a gerencia)")
        else:
            print("   CC: desactivado (GIRA_ZONA_CC_ACTIVO = False)")

        exito = EmailSenderAgente().enviar_reporte_gira(
            destinatario,
            info_agente["nombre"],
            pdf_path,
            cc=copias,
        )

        resultado["ok"] = bool(exito)
        resultado["enviado_a"] = destinatario if exito else None
        resultado["mensaje"] = (
            f"Gira enviada a {destinatario} con {resultado['procesados']} de "
            f"{len(card_codes)} clientes.{cola}"
            if exito
            else "El PDF se generó pero el correo no pudo enviarse."
        )
        print(("✅ " if exito else "❌ ") + resultado["mensaje"])

    except Exception as e:
        resultado["mensaje"] = f"Error inesperado: {e}"
        print(f"❌ {resultado['mensaje']}")

    finally:
        # Devolver conn.get como estaba: la conexión se cierra acá abajo, pero
        # dejarla envuelta sería dejar un contador global activo sin dueño.
        conn.get = get_original
        conn.logout()

    return resultado


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Automatización de Reportes de Gira - Químicas Unidas"
    )
    parser.add_argument(
        "--agente",
        type=str,
        help="Ejecutar reporte solo para un agente específico. Ej: --agente 9",
    )

    # Mantenemos el soporte de --test por si lo estabas usando
    if "--test" in sys.argv and not hasattr(parser.parse_args(), "test"):
        pass  # Por si tienes lógica extra de --test en sys.argv

    args, unknown = parser.parse_known_args()

    # Tipo de ejecución para métricas
    if args.agente:
        status_global_giras["tipo_ejecucion"] = "Personalizada"
    elif "--test" in sys.argv:
        status_global_giras["tipo_ejecucion"] = "Prueba"

    try:
        ejecutar_reportes_gira(agente_id=args.agente)
    except Exception as e:
        print(f"❌ Error crítico en ejecución general: {e}")
        status_global_giras["error_critico"] = True
        status_global_giras["observaciones"] = f"Falla de sistema: {str(e)}"
        finalizar_y_reportar(
            status_global_giras,
            None,
            automatizacion_id=ID_RPA_QU_GIRAS,
            subcarpeta="giras",
        )
