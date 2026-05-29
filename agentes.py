"""
agente.py - Químicas Unidas
Automatización de Reportes de Gira para Agentes/Vendedores.
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional

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
MODO_PRUEBA = True  # True = envía a EMAIL_PRUEBA, False = envía al correo del agente

# AGENTES PERMITIDOS: Siviany (6), Berny (7), José (9)
# AGENTES_VALIDOS = {6, 7, 9}

# CORREOS EN COPIA (CC) SOLICITADOS POR TANIA
CORREOS_CC = [
    "dev@soportexperto.com",
    # "erich.hoepker@qu.cr",
    # "apuschendorf@qu.cr",
    # "creditodenis@qu.cr",
    # "credito@qu.cr",
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
        "$select": "CardCode,CardName,Phone1,Phone2,Cellular,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,CreditLimit,ContactPerson,Address,Currency,FatherCard",
    }

    if limite:
        params["$top"] = limite
        clientes = conn.get("BusinessPartners", params)
        return clientes.get("value", []) if clientes else []
    else:
        return obtener_todos_paginado(conn, "BusinessPartners", params, "CardCode")


def obtener_descuentos_frecuentes(conn: ServiceLayerConnection) -> Dict[str, float]:
    """
    Obtiene el descuento más frecuente (la moda) mayor a 0 para cada cliente
    basado en su historial REAL de facturación desde 2024.
    """
    # Consulta masiva: agrupamos por Cliente y por Porcentaje de Descuento
    sql = """
        SELECT 
            T0."CardCode",
            T1."DiscPrcnt" AS "Descuento", 
            COUNT(T1."DiscPrcnt") AS "Freq"
        FROM "OINV" T0
        INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
        WHERE T1."DiscPrcnt" > 0 
          AND T0."DocDate" >= '20240101'
        GROUP BY T0."CardCode", T1."DiscPrcnt"
    """
    resultados = ejecutar_sql_sl(conn, sql)

    temp_dict = {}
    for r in resultados:
        code = str(r.get("CardCode", ""))
        disc = float(r.get("Descuento", 0))
        freq = int(r.get("Freq", 0))

        if code not in temp_dict:
            temp_dict[code] = []
        temp_dict[code].append((disc, freq))

    descuentos_final = {}
    for code, values in temp_dict.items():
        # Ordenamos por frecuencia (mayor a menor) usando Python
        values.sort(key=lambda x: (x[1], x[0]), reverse=True)
        # Tomamos el descuento que más se ha usado (el primer elemento)
        descuentos_final[code] = values[0][0]

    return descuentos_final


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


def obtener_contacto_principal(
    conn: ServiceLayerConnection, card_code: str, contact_code: int
) -> Dict:
    if not contact_code:
        return {"nombre": "", "telefono": "", "email": ""}
    try:
        bp = conn.get(
            f"BusinessPartners('{card_code}')", {"$select": "ContactEmployees"}
        )
        if bp and "ContactEmployees" in bp:
            for contacto in bp["ContactEmployees"]:
                if contacto.get("InternalCode") == contact_code:
                    return {
                        "nombre": contacto.get("Name", ""),
                        "telefono": contacto.get("Phone1", "")
                        or contacto.get("MobilePhone", ""),
                        "email": contacto.get("E_Mail", ""),
                    }
    except:
        pass
    return {"nombre": "", "telefono": "", "email": ""}


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
    if abs(saldo) < 0.01:
        return None

    tipo_doc = doc.get("U_TDOC", "") or ""
    if tipo_origen == "creditnote" or tipo_doc.upper() in TIPOS_QUE_RESTAN:
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


def obtener_documentos_cliente(
    conn: ServiceLayerConnection, cliente_info: Dict
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
        "DocDueDate",
    )
    for f in facturas:
        doc = procesar_documento(f, "invoice")
        if doc:
            destino = doc["destino"]
            doc["vendedor_final"] = mapeo_dir.get(destino, vendedor_general)
            documentos.append(doc)

    # 2. NOTAS DE CRÉDITO (CreditNotes) - AHORA CON FILTRO DESDE EL 2024
    notas_credito = obtener_todos_paginado(
        conn,
        "CreditNotes",
        {
            # AÑADIDO: DocDate ge '2024-01-01' para evitar la basura vieja del 2019
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open' and DocDate ge '2024-01-01'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,ShipToCode,DocumentLines",
        },
        "DocDueDate",
    )
    for nc in notas_credito:
        doc = procesar_documento(nc, "creditnote")
        if doc:
            destino = doc["destino"]
            doc["vendedor_final"] = mapeo_dir.get(destino, vendedor_general)
            documentos.append(doc)

    # 3. SALDOS A FAVOR (Lectura directa de JDT1 - Pagos y Asientos Manuales)
    # AÑADIDO: T0."TransType" NOT IN ('13', '14') para evitar duplicar las Notas de Crédito
    sql_pr = f"""
        SELECT 
            T0."RefDate", 
            T0."BaseRef" AS "DocNum", 
            T0."TransType", 
            T0."BalDueCred", 
            T0."BalFcCred", 
            T0."FCCurrency", 
            T0."LineMemo" 
        FROM "JDT1" T0 
        WHERE T0."ShortName" = '{card_code}' 
          AND T0."BalDueCred" > 0 
          AND T0."RefDate" >= '20240101'
          AND T0."TransType" NOT IN ('13', '14')
    """

    filas_pr = ejecutar_sql_sl(conn, sql_pr)

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
    conn: ServiceLayerConnection, cliente: Dict, descuentos_cache: Dict
) -> List[Dict]:
    """
    Procesa un cliente y devuelve UNA LISTA de diccionarios,
    uno por cada vendedor que tenga facturas en este cliente.
    """
    card_code = cliente.get("CardCode")
    contacto = obtener_contacto_principal(conn, card_code, cliente.get("ContactPerson"))

    condicion_pago, plazo_dias = obtener_condicion_pago(
        conn, cliente.get("PayTermsGrpCode")
    )

    descuento_general = float(cliente.get("DiscountPercent", 0) or 0)
    # Busca la "moda" del descuento. Si no tiene, usa el general
    descuento_porcent = descuentos_cache.get(card_code, descuento_general)
    # ---------------------------------------------------------

    grupo_descuento = cliente.get("GroupCode", -1)

    moneda_bp = cliente.get("Currency", "CRC")
    moneda_limite = "USD" if moneda_bp in ["USD", "US$"] else "CRC"

    todos_docs = obtener_documentos_cliente(conn, cliente)
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

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        print("\n📋 Obteniendo listado de Agentes...")
        vendedores_cache = obtener_vendedores(conn)

        print("📋 Obteniendo matriz de descuentos frecuentes...")
        descuentos_cache = obtener_descuentos_frecuentes(conn)

        print("📋 Obteniendo clientes con saldo...")
        clientes = obtener_clientes_con_saldo(
            conn, limite=20 if "--test" in sys.argv else None
        )
        print(f"   Total clientes extraidos: {len(clientes)}")
        if not clientes:
            return

        print("\n🔄 Evaluando facturas y asignando agentes por Zona (Multihilo)...")
        agrupados_por_agente = {}
        total_cli = len(clientes)
        procesados = 0

        # =====================================================================
        # PROCESAMIENTO MULTIHILO (Para mayor velocidad)
        # =====================================================================
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Lanzamos todas las peticiones a SAP en paralelo
            futuros = {
                executor.submit(
                    procesar_datos_cliente, conn, cli, descuentos_cache
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
        resultados = {"procesados": 0, "enviados": 0, "errores": 0, "sin_correo": 0}

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

            try:
                pdf_path = generar_pdf_reporte_gira(datos_reporte)
                print(f"   📄 PDF Generado: {pdf_path}")
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

    finally:
        conn.logout()


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

    ejecutar_reportes_gira(agente_id=args.agente)
