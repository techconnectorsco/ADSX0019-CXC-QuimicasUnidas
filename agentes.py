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

# =============================================================================
# CONSTANTES
# =============================================================================

EMAIL_PRUEBA = "devs@techconnectors.co"
# EMAIL_PRUEBA = "credito@qu.cr"
MODO_PRUEBA = True  # True = envía a EMAIL_PRUEBA, False = envía al correo del agente

# AGENTES PERMITIDOS: Siviany (6), Berny (7), José (9)
AGENTES_VALIDOS = {6, 7, 9}

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
    # NUEVO FILTRO: Trae clientes con saldo != 0, O cuentas hijas, O Colonos/Gollos
    filtro = "CardType eq 'cCustomer' and Valid eq 'tYES' and (CurrentAccountBalance ne 0 or FatherCard ne null or contains(CardName, 'COLONO') or contains(CardName, 'GOLLO') or contains(CardName, 'GOLLOS'))"
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


def obtener_documentos_cliente(
    conn: ServiceLayerConnection, card_code: str
) -> List[Dict]:
    documentos = []
    # Se agregó ShipToCode a la consulta
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
            documentos.append(doc)

    notas_credito = obtener_todos_paginado(
        conn,
        "CreditNotes",
        {
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,ShipToCode,DocumentLines",
        },
        "DocDueDate",
    )
    for nc in notas_credito:
        doc = procesar_documento(nc, "creditnote")
        if doc:
            documentos.append(doc)

    # -------------------------------------------------------------------------
    # PAGOS RECIBIDOS CON SOBRANTE (PR) - Filtro < 2024
    # -------------------------------------------------------------------------
    pagos = obtener_todos_paginado(
        conn,
        "IncomingPayments",
        {
            "$filter": f"CardCode eq '{card_code}' and Cancelled eq 'tNO'",
            "$select": "DocNum,DocDate,TransferSum,CashSum,DocCurrency,PaymentInvoices,PaymentChecks,Remarks,Reference1",
        },
        "DocDate",
    )

    for p in pagos:
        # Sumar Efectivo + Transferencia + Cheques
        efectivo = float(p.get("CashSum", 0) or 0)
        transferencia = float(p.get("TransferSum", 0) or 0)
        cheques = sum(
            float(chk.get("CheckSum", 0) or 0) for chk in p.get("PaymentChecks", [])
        )

        total_pagado = efectivo + transferencia + cheques

        # Sumar lo aplicado a facturas
        suma_aplicada = sum(
            float(inv.get("SumApplied", 0) or 0) for inv in p.get("PaymentInvoices", [])
        )

        # Diferencia
        sobrante = round(total_pagado - suma_aplicada, 2)

        # Si hay sobrante real
        if sobrante > 0.05:
            fecha_pago = str(p.get("DocDate", ""))[:10]
            anio_pago = int(fecha_pago[:4])

            # EXCLUIR SOBRANTES ANTERIORES A 2024
            if anio_pago < 2024:
                continue

            moneda_pago = "CRC" if p.get("DocCurrency") in ["COL", "CRC"] else "USD"

            doc_pr = {
                "doc_num": p.get("DocNum"),
                "consecutivo_fe": p.get("Reference1", ""),
                "tipo_codigo": "PR",
                "destino": "N/A",  # Los pagos no suelen tener destino/zona de envío
                "descripcion": p.get("Remarks", "Saldo a favor no aplicado"),
                "fecha": fecha_pago,
                "fecha_vence": fecha_pago,
                "total": -abs(sobrante),
                "saldo": -abs(sobrante),
                "moneda": moneda_pago,
                "esta_vencido": False,
                "dias_vencido": 0,
                "orden_compra": "",
            }
            documentos.append(doc_pr)

    return documentos


def procesar_datos_cliente(
    conn: ServiceLayerConnection, cliente: Dict
) -> Optional[Dict]:
    card_code = cliente.get("CardCode")
    contacto = obtener_contacto_principal(conn, card_code, cliente.get("ContactPerson"))

    condicion_pago, plazo_dias = obtener_condicion_pago(
        conn, cliente.get("PayTermsGrpCode")
    )
    descuento_porcent = float(cliente.get("DiscountPercent", 0) or 0)
    grupo_descuento = cliente.get("GroupCode", -1)

    documentos = obtener_documentos_cliente(conn, card_code)
    if not documentos:
        return None

    doc_colones = [d for d in documentos if d["moneda"] == "CRC"]
    doc_dolares = [d for d in documentos if d["moneda"] == "USD"]

    total_colones = sum(d["saldo"] for d in doc_colones)
    total_dolares = sum(d["saldo"] for d in doc_dolares)

    if total_colones == 0 and total_dolares == 0:
        return None

    # LÓGICA DE MONEDA PARA LÍMITE DE CRÉDITO
    moneda_bp = cliente.get("Currency", "CRC")
    moneda_limite = "USD" if moneda_bp in ["USD", "US$"] else "CRC"

    return {
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
            "zona_gira": cliente.get("U_ZGIRA", "N/A"),
        },
        "documentos": {"colones": doc_colones, "dolares": doc_dolares},
        "totales": {"colones": total_colones, "dolares": total_dolares},
    }


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


def ejecutar_reportes_gira():
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

        print("📋 Obteniendo clientes...")
        clientes = obtener_clientes_con_saldo(
            conn, limite=20 if "--test" in sys.argv else None
        )
        print(f"   Total clientes extraidos: {len(clientes)}")
        if not clientes:
            return

        print("\n🔄 Agrupando clientes por Agente...")
        agrupados_por_agente = {}

        for cli in clientes:
            vendedor_id = cli.get("SalesPersonCode", -1)
            # FILTRO CRÍTICO: Solo procesar los agentes válidos indicados por Tania
            if vendedor_id not in AGENTES_VALIDOS:
                continue

            if vendedor_id not in agrupados_por_agente:
                agrupados_por_agente[vendedor_id] = []
            agrupados_por_agente[vendedor_id].append(cli)

        sender = EmailSenderAgente()
        sp_uploader = SharePointUploader()
        resultados = {"procesados": 0, "enviados": 0, "errores": 0, "sin_correo": 0}

        for vendedor_id, clientes_del_agente in agrupados_por_agente.items():
            info_vendedor = vendedores_cache.get(
                vendedor_id, {"nombre": "No Asignado", "correo": ""}
            )
            nombre_agente = info_vendedor["nombre"]
            correo_agente = info_vendedor["correo"]

            print(f"\n👨‍💼 Procesando Agente: {nombre_agente} (ID: {vendedor_id})")

            clientes_del_agente.sort(
                key=lambda c: (
                    str(c.get("U_ZGIRA") or "ZZZ").zfill(3),
                    c.get("CardName", ""),
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

            for i, cli in enumerate(clientes_del_agente, 1):
                datos_cli = procesar_datos_cliente(conn, cli)
                if datos_cli:
                    datos_reporte["clientes"].append(datos_cli)
                    datos_reporte["totales_agente"]["colones"] += datos_cli["totales"][
                        "colones"
                    ]
                    datos_reporte["totales_agente"]["dolares"] += datos_cli["totales"][
                        "dolares"
                    ]
                    zona = datos_cli["cliente"]["zona_gira"]
                    if zona:
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

                # AQUÍ SE PASA LA LISTA CC A LA FUNCIÓN DE CORREO
                # (Asegúrate de que tu función en sendemailCXC acepte un parámetro extra para CC)
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
    ejecutar_reportes_gira()
