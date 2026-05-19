"""
agente.py - Químicas Unidas
Automatización de Reportes de Gira para Agentes/Vendedores.

Ejecutar los días Martes de cada semana vía Programador de Tareas.

Uso:
    python agente.py              # Ejecutar proceso completo
    python agente.py --test       # Probar con un límite de clientes
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

# EMAIL_PRUEBA = "devs@techconnectors.co" credito@qu.cr
EMAIL_PRUEBA = "credito@qu.cr"
MODO_PRUEBA = True  # True = envía a EMAIL_PRUEBA, False = envía al correo del agente

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
# FUNCIONES DE PAGINACIÓN Y OBTENCIÓN (Reutilizadas de main.py)
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
            print(f"   ⚠️ Límite de seguridad alcanzado en {entidad}")
            break
    return todos


def obtener_clientes_con_saldo(
    conn: ServiceLayerConnection, limite: int = None
) -> List[Dict]:
    params = {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and CurrentAccountBalance ne 0",
        "$select": "CardCode,CardName,Phone1,Phone2,Cellular,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,CreditLimit,ContactPerson,Address",
    }
    if limite:
        params["$top"] = limite
        clientes = conn.get("BusinessPartners", params)
        return clientes.get("value", []) if clientes else []
    else:
        return obtener_todos_paginado(conn, "BusinessPartners", params, "CardCode")


def obtener_vendedores(conn: ServiceLayerConnection) -> Dict[int, Dict]:
    """Obtiene todos los vendedores y sus correos para tenerlos en memoria caché."""
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


def traducir_tipo_documento(tipo: str) -> str:
    if not tipo:
        return "Documento"
    return TRADUCCION_TIPOS.get(tipo.upper(), tipo)


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

    dias_vencido = 0

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

    facturas = obtener_todos_paginado(
        conn,
        "Invoices",
        {
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,DocumentLines",
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
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,DocumentLines",
        },
        "DocDueDate",
    )

    for nc in notas_credito:
        doc = procesar_documento(nc, "creditnote")
        if doc:
            documentos.append(doc)

    return documentos


def separar_por_moneda(documentos: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    colones = [d for d in documentos if d["moneda"] == "CRC"]
    dolares = [d for d in documentos if d["moneda"] == "USD"]
    return colones, dolares


# =============================================================================
# PREPARACIÓN DE DATOS PARA EL REPORTE DE GIRA (POR CLIENTE)
# =============================================================================


def procesar_datos_cliente(
    conn: ServiceLayerConnection, cliente: Dict
) -> Optional[Dict]:
    """Extrae los documentos de un cliente y retorna su estructura si tiene deudas."""
    card_code = cliente.get("CardCode")
    contacto = obtener_contacto_principal(conn, card_code, cliente.get("ContactPerson"))

    # Obtener plazo de pago y descuentos
    condicion_pago, plazo_dias = obtener_condicion_pago(
        conn, cliente.get("PayTermsGrpCode")
    )
    descuento_porcent = float(cliente.get("DiscountPercent", 0) or 0)
    grupo_descuento = cliente.get("GroupCode", -1)

    documentos = obtener_documentos_cliente(conn, card_code)
    if not documentos:
        return None

    doc_colones, doc_dolares = separar_por_moneda(documentos)

    total_colones = sum(d["saldo"] for d in doc_colones)
    total_dolares = sum(d["saldo"] for d in doc_dolares)

    if total_colones == 0 and total_dolares == 0:
        return None

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
            "zona_gira": cliente.get("U_ZGIRA", "N/A"),
        },
        "documentos": {
            "colones": doc_colones,
            "dolares": doc_dolares,
        },
        "totales": {
            "colones": total_colones,
            "dolares": total_dolares,
        },
    }


def obtener_condicion_pago(conn: ServiceLayerConnection, pay_terms_code: int) -> tuple:
    """Obtiene la descripción de la condición de pago y los días."""
    if not pay_terms_code:
        return "No especificado", 30

    try:
        resultado = conn.get(f"PaymentTermsTypes({pay_terms_code})")
        if resultado:
            nombre = resultado.get("PaymentTermsGroupName", "No especificado")
            dias = int(resultado.get("NumberOfDaysForPayment", 30))
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
        # 1. Traer lista de vendedores (caché)
        print("\n📋 Obteniendo listado de Agentes...")
        vendedores_cache = obtener_vendedores(conn)

        # 2. Traer todos los clientes con saldo
        print("📋 Obteniendo clientes con saldo pendiente...")
        # NOTA: Quita el parámetro limite=20 en producción
        clientes = obtener_clientes_con_saldo(
            conn, limite=20 if "--test" in sys.argv else None
        )
        print(f"   Total clientes con saldo: {len(clientes)}")

        if not clientes:
            print("   No hay clientes con saldo pendiente")
            return

        # 3. Agrupar clientes por Agente (SalesPersonCode)
        print("\n🔄 Agrupando clientes por Agente...")
        agrupados_por_agente = {}

        for cli in clientes:
            vendedor_id = cli.get("SalesPersonCode", -1)
            if vendedor_id not in agrupados_por_agente:
                agrupados_por_agente[vendedor_id] = []
            agrupados_por_agente[vendedor_id].append(cli)

        print(
            f"   Se identificaron {len(agrupados_por_agente)} agentes con cobros pendientes."
        )

        # ================================================================
        # IMPORTANTE: Inicializar la clase que envía los correos
        # ================================================================
        sender = EmailSenderAgente()
        sp_uploader = SharePointUploader()

        # 4. Procesar y generar documento por cada Agente
        resultados = {"procesados": 0, "enviados": 0, "errores": 0, "sin_correo": 0}

        for vendedor_id, clientes_del_agente in agrupados_por_agente.items():
            info_vendedor = vendedores_cache.get(
                vendedor_id, {"nombre": "No Asignado", "correo": ""}
            )
            nombre_agente = info_vendedor["nombre"]
            correo_agente = info_vendedor["correo"]

            print(f"\n👨‍💼 Procesando Agente: {nombre_agente} (ID: {vendedor_id})")

            # ================================================================
            # NUEVO: Ordenar los clientes del agente por ZONA y luego por Nombre
            # ================================================================
            # Usamos 'ZZZ' por si algún cliente no tiene zona, para que quede al final del reporte
            clientes_del_agente.sort(
                key=lambda c: (
                    str(c.get("U_ZGIRA") or "ZZZ").zfill(3),
                    c.get("CardName", ""),
                )
            )

            print(f"   Clientes asignados con saldo: {len(clientes_del_agente)}")

            datos_reporte = {
                "agente": {
                    "codigo": str(vendedor_id),
                    "nombre": nombre_agente,
                    "correo": correo_agente,
                    "zonas": set(),  # Se llenará dinámicamente
                },
                "totales_agente": {"dolares": 0, "colones": 0},
                "clientes": [],
            }

            # Procesar cada cliente del agente (ahora ya vienen ordenados por zona)
            for i, cli in enumerate(clientes_del_agente, 1):
                datos_cli = procesar_datos_cliente(conn, cli)
                if datos_cli:
                    datos_reporte["clientes"].append(datos_cli)
                    # Sumar a los totales del agente
                    datos_reporte["totales_agente"]["colones"] += datos_cli["totales"][
                        "colones"
                    ]
                    datos_reporte["totales_agente"]["dolares"] += datos_cli["totales"][
                        "dolares"
                    ]
                    # Registrar la zona
                    zona = datos_cli["cliente"]["zona_gira"]
                    if zona:
                        datos_reporte["agente"]["zonas"].add(str(zona))

            # Si después de procesar resultó que nadie tenía documentos válidos, saltar
            if not datos_reporte["clientes"]:
                print("   ⏭️ Sin documentos finales pendientes para este agente.")
                continue

            # Formatear zonas como string
            zonas_list = list(datos_reporte["agente"]["zonas"])
            datos_reporte["agente"]["zonas"] = (
                ", ".join(zonas_list) if zonas_list else "Múltiples/No Definida"
            )

            resultados["procesados"] += 1

            print(f"   ✅ Clientes con documentos: {len(datos_reporte['clientes'])}")
            print(
                f"   💰 Total a cobrar USD: ${datos_reporte['totales_agente']['dolares']:,.2f}"
            )
            print(
                f"   💰 Total a cobrar CRC: ₡{datos_reporte['totales_agente']['colones']:,.2f}"
            )

            # Generar PDF
            try:
                pdf_path = generar_pdf_reporte_gira(datos_reporte)
                print(f"   📄 PDF Generado: {pdf_path}")

                sp_uploader.upload_reporte(pdf_path, "Giras")

                # 2. Determinar destinatario según MODO_PRUEBA
                correo_sap = info_vendedor.get("correo", "")

                if MODO_PRUEBA:
                    destinatario = EMAIL_PRUEBA
                    print(
                        f"   📧 MODO PRUEBA: Direccionando a {EMAIL_PRUEBA} (En SAP: '{correo_sap or 'VACÍO'}')"
                    )
                else:
                    destinatario = correo_sap

                # 3. Validar y Enviar
                if not destinatario or "@" not in str(destinatario):
                    print(
                        f"   ⚠️ Agente {nombre_agente} no tiene correo asignado. Saltando envío."
                    )
                    resultados["sin_correo"] += 1
                    continue

                exito = sender.enviar_reporte_gira(
                    destinatario, nombre_agente, pdf_path
                )

                if exito:
                    print(f"   ✅ Reporte enviado con éxito.")
                    resultados["enviados"] += 1
                else:
                    print(f"   ❌ Error al enviar el correo vía Graph API.")
                    resultados["errores"] += 1

            except Exception as e:
                print(f"   ❌ Error procesando agente {nombre_agente}: {str(e)}")
                resultados["errores"] += 1

        # 5. Resumen final
        print("\n" + "=" * 80)
        print("📊 RESUMEN DEL PROCESO DE GIRAS")
        print("=" * 80)
        print(f"   Agentes procesados: {resultados['procesados']}")
        print(f"   Reportes enviados: {resultados['enviados']}")
        print(f"   Agentes sin correo: {resultados['sin_correo']}")
        print(f"   Errores de generación/envío: {resultados['errores']}")
        print("=" * 80)

    finally:
        conn.logout()


if __name__ == "__main__":
    ejecutar_reportes_gira()
