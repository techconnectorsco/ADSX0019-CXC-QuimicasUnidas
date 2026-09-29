"""
agente.py - Químicas Unidas
Automatización de Reportes de Gira para Agentes/Vendedores.
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import time
from collections import Counter
from decouple import config
from supabase_manager import verificar_estado_rpa, finalizar_y_reportar, ID_RPA_QU_GIRAS
from global_status_giras import status_global_giras

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection
from agentepdf import generar_pdf_reporte_gira
from sendemailCXC import EmailSenderAgente
from sharepoint_qu import SharePointUploader
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

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


def procesar_documento(doc: Dict, tipo_origen: str) -> Optional[Dict]:
    hoy = datetime.now().date()

    if doc.get("DocCurrency") in ["USD", "US$", "DOL"]:
        total = doc.get("DocTotalFc", 0) or doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDateFC", 0) or doc.get("PaidToDate", 0) or 0
        moneda = "USD"
    else:
        total = doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDate", 0) or 0
        moneda = "CRC"

    saldo = total - pagado
    if abs(saldo) < 0.005:
        return None

    tipo_doc = str(doc.get("U_TDOC", "") or "").strip().upper()

    # Para notas de crédito O documentos de la lista, el saldo DEBE ser negativo
    if tipo_origen == "creditnote" or tipo_doc in TIPOS_QUE_RESTAN or tipo_doc == "PR":
        saldo = -abs(saldo)
        total = -abs(total)

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


def ejecutar_sql_sl(conn: ServiceLayerConnection, sql: str) -> List[Dict]:
    """
    Ejecuta un query SQL crudo en Service Layer mediante el endpoint SQLQueries.
    Versión Thread-Safe: Usa UUID para que los hilos no choquen entre sí.
    """
    # Generar un código único de 8 caracteres para este hilo específico
    code = f"QU_PR_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"

    resp = conn.session.post(
        url, json={"SqlCode": code, "SqlName": "Query Temporal PR", "SqlText": sql}
    )

    if resp.status_code not in (200, 201):
        # A veces SAP devuelve error si la sesión colapsa, no rompemos el script
        # print(f"   ⚠️ Error creando SQL: {resp.text[:100]}")
        return []

    res = conn.get(f"SQLQueries('{code}')/List", {})

    # Limpiar la consulta temporal de SAP
    conn.session.delete(f"{url}('{code}')")

    return res.get("value", []) if res else []


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


def _encabezado_zonas_calculado(zonas_por_cliente: set) -> str:
    """
    Texto del "ZONAS:" del PDF cuando el usuario NO eligió una zona, es decir
    cuando la selección es mixta y hay que deducirla de los documentos.

    Hace dos cosas que el cálculo crudo no hacía:

    1. Deduplica destino por destino. El `zona_gira` de cada cliente ya es una
       lista de destinos unida por comas (procesar_datos_cliente), así que un
       set de esos strings deja repetidos: en la prueba del 28/09 con 43
       clientes salieron 82 entradas para 49 destinos reales, GUAPILES cuatro
       veces.
    2. Recorta. Esas 82 entradas eran 833 caracteres en una sola línea: se veía
       el primer 18% y el resto se salía de la página, cortado a media palabra.

    Cuando no cabe se pone el conteo y se manda al detalle, que igual está en la
    columna "Destino" de cada fila del reporte.

    Solo lo usa la gira selectiva. La corrida de los martes sigue armando su
    encabezado como siempre (mismo defecto, pero es código existente que no se
    toca sin autorización).
    """
    destinos = sorted(
        {
            parte.strip()
            for zona in zonas_por_cliente
            for parte in str(zona).split(",")
            if parte.strip()
        }
    )

    if not destinos:
        return "Selección manual"

    texto = ", ".join(destinos)
    if len(texto) <= GIRA_ZONA_MAX_CHARS_ZONAS:
        return f"Selección manual · {texto}"

    return (
        f"Selección manual · {len(destinos)} destinos "
        "(ver la columna Destino de cada fila)"
    )


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
        procesados_cont = 0
        total_cli = len(clientes)

        with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as executor:
            futuros = {
                executor.submit(
                    procesar_datos_cliente, conn, cli, saldos_favor_cache
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
                    perfiles = futuro.result()
                except Exception as e:
                    print(f"\n   ⚠️ Error procesando {cli.get('CardCode')}: {e}")
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

        sin_documentos = encontrados - con_documentos
        # Sin ningún documento abierto en SAP: ni propio ni de otro vendedor.
        sin_nada = sin_documentos - ruteados_a_otro

        resultado["omitidos"] = sorted(inexistentes | sin_documentos)
        resultado["procesados"] = len(con_documentos)

        # Por qué quedó fuera cada uno. `omitidos` se deja igual para no cambiar
        # el contrato que ya consume la web; esto se agrega al lado.
        resultado["omitidos_detalle"] = {
            "sin_documentos": sorted(sin_nada),
            "otro_vendedor": sorted(ruteados_a_otro),
            "inexistentes": sorted(inexistentes),
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
        agrupados.sort(
            key=lambda c: (
                c["cliente"].get("nombre", ""),
                str(c["cliente"].get("zona_gira") or "ZZZ").zfill(3),
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
            zona = datos_cli["cliente"]["zona_gira"]
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
