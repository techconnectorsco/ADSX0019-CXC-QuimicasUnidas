"""
main.py - Químicas Unidas
Automatización de Estados de Cuenta (CXC)

Ejecutar los días 15 y 30 de cada mes vía Programador de Tareas.

Uso:
    python main.py              # Ejecutar proceso completo
    python main.py --test       # Probar con 2 clientes
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from sharepoint_qu import SharePointUploader

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection
from generarpdf import generar_pdf_estado_cuenta
from sendemailCXC import enviar_estado_cuenta
from logcontrolcxc import ControlCXC
from Generarexcel import generar_excel_estado_cuenta
import uuid

# =============================================================================
# CONSTANTES
# =============================================================================

# Email para pruebas (comentar en producción)
# EMAIL_PRUEBA = "credito@qu.cr"
EMAIL_PRUEBA = "devs@techconnectors.co"
MODO_PRUEBA = True  # True = envía a EMAIL_PRUEBA, False = envía al cliente real

# Email para enviar el log de control (en producción: encargada de CXC)
# EMAIL_LOG_CONTROL = "credito@qu.cr"  # "devs@techconnectors.co"  # Cambiar en producción
EMAIL_LOG_CONTROL = "devs@techconnectors.co"  # Cambiar en producción

# Tipos de documento que RESTAN al saldo (pagos, notas de crédito)
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

# Traducción de tipos de documento
""" TRADUCCION_TIPOS = {
    'FRM': 'Factura',
    'FRT': 'Factura',
    'FEC': 'Fact. Equipo',
    'FEM': 'Fact. Equipo',
    'NC': 'Nota Crédito',
    'NCM': 'Nota Crédito',
    'N/C': 'Nota Crédito',
    'RC': 'Pago Recibido',
    'REM': 'Pago Recibido',
    'PR': 'Pago Recibido',
    'ND': 'Nota Débito',
    'NDM': 'Nota Débito',
    'N/D': 'Nota Débito',
    'AS': 'Asiento',
} """

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
# FUNCIONES DE PAGINACIÓN
# =============================================================================


def obtener_todos_paginado(
    conn: ServiceLayerConnection,
    entidad: str,
    params: dict,
    campo_orden: str = "DocNum",
) -> List[Dict]:
    """
    Obtiene todos los registros usando paginación.
    El Service Layer tiene un límite de 20 registros por request.
    """
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

        # Si devolvió menos del page_size, ya no hay más
        if len(resultado["value"]) < page_size:
            break

        skip += page_size

        # Límite de seguridad
        if skip >= 10000:
            print(f"   ⚠️ Límite de seguridad alcanzado en {entidad}")
            break

    return todos


# =============================================================================
# FUNCIONES DE OBTENCIÓN DE DATOS
# =============================================================================


def obtener_clientes_con_saldo(
    conn: ServiceLayerConnection, limite: int = None, lista_codigos: List[str] = None
) -> List[Dict]:
    """
    Obtiene clientes activos con saldo pendiente > 0.
    Si se pasa lista_codigos, filtra estrictamente por esos CardCodes.
    """
    filtro_base = (
        "CardType eq 'cCustomer' and Valid eq 'tYES' and CurrentAccountBalance ne 0"
    )

    # Si vienen clientes específicos desde la API o la consola
    if lista_codigos:
        # Crear filtro dinámico: (CardCode eq 'C0223' or CardCode eq 'C0250')
        codigos_limpios = [c.strip() for c in lista_codigos if c.strip()]
        filtro_extra = " or ".join([f"CardCode eq '{c}'" for c in codigos_limpios])
        filtro_base += f" and ({filtro_extra})"

    params = {
        "$filter": filtro_base,
        "$select": "CardCode,CardName,EmailAddress,Phone1,Phone2,Cellular,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,U_NVT_CorreoEstadoCuenta,U_NTV_EnvioAutomatico,CreditLimit,ContactPerson,Address,PayTermsGrpCode,FreeText,Currency",
        "$orderby": "CardCode",
    }

    if limite:
        params["$top"] = limite
        clientes = conn.get("BusinessPartners", params)
        return clientes.get("value", []) if clientes else []
    else:
        return obtener_todos_paginado(conn, "BusinessPartners", params, "CardCode")


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


def obtener_nombre_vendedor(
    conn: ServiceLayerConnection, sales_person_code: int
) -> str:
    """Obtiene el nombre del vendedor."""
    if not sales_person_code or sales_person_code == -1:
        return "No asignado"

    try:
        resultado = conn.get(f"SalesPersons({sales_person_code})")
        if resultado:
            return resultado.get("SalesEmployeeName", "No asignado")
    except:
        pass

    return "No asignado"


def obtener_contacto_principal(
    conn: ServiceLayerConnection, card_code: str, contact_code: int
) -> Dict:
    """Obtiene información del contacto principal."""
    if not contact_code:
        return {"nombre": "", "telefono": "", "email": ""}

    try:
        # Los contactos están en BusinessPartners -> ContactEmployees
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


def ejecutar_sql_sl(conn: ServiceLayerConnection, sql: str) -> List[Dict]:
    """
    Ejecuta un query SQL crudo en Service Layer mediante el endpoint SQLQueries.
    Versión segura: Usa UUID para evitar conflictos de nombres en ejecuciones concurrentes.
    """
    code = f"QU_PR_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"

    # Crear la consulta con un nombre único temporal
    resp = conn.session.post(
        url, json={"SqlCode": code, "SqlName": "Query Temporal PR", "SqlText": sql}
    )

    if resp.status_code not in (200, 201):
        return []

    # Ejecutar y obtener resultados
    res = conn.get(f"SQLQueries('{code}')/List", {})

    # Limpiar inmediatamente la consulta de SAP
    conn.session.delete(f"{url}('{code}')")

    return res.get("value", []) if res else []


def obtener_codigos_familia(conn: ServiceLayerConnection, card_code: str) -> List[str]:
    """Obtiene el código padre y los códigos de todas sus cuentas hijas."""
    codigos = [card_code]
    params = {"$filter": f"FatherCard eq '{card_code}'", "$select": "CardCode"}
    hijas = obtener_todos_paginado(conn, "BusinessPartners", params, "CardCode")
    for h in hijas:
        codigos.append(h["CardCode"])
    return codigos


def obtener_documentos_cliente(
    conn: ServiceLayerConnection, card_code: str
) -> List[Dict]:
    """
    Obtiene TODOS los documentos pendientes de un cliente y sus sucursales (hijas),
    filtrando duplicados contables, basura histórica y aplicando formato correcto de fechas.
    """
    documentos = []

    # 1. Obtener Padre e Hijas
    codigos_familia = obtener_codigos_familia(conn, card_code)
    filtro_codigos = " or ".join([f"CardCode eq '{c}'" for c in codigos_familia])

    # 2. FACTURAS (Invoices) - La deuda real vieja se mantiene intacta
    facturas = obtener_todos_paginado(
        conn,
        "Invoices",
        {
            "$filter": f"({filtro_codigos}) and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,DocumentLines",
        },
        "DocDueDate",
    )

    for f in facturas:
        doc = procesar_documento(f, "invoice")
        if doc:
            documentos.append(doc)

    # 3. NOTAS DE CRÉDITO (CreditNotes) - FILTRADAS DESDE 2024 PARA EVITAR RECLAMOS VIEJOS
    notas_credito = obtener_todos_paginado(
        conn,
        "CreditNotes",
        {
            # AÑADIDO: and DocDate ge '2024-01-01' para enterrar los casos 2018-2022 que mencionó Tania
            "$filter": f"({filtro_codigos}) and DocumentStatus eq 'bost_Open' and DocDate ge '2024-01-01'",
            "$select": "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,NumAtCard,Comments,DocumentLines",
        },
        "DocDueDate",
    )

    for nc in notas_credito:
        doc = procesar_documento(nc, "creditnote")
        if doc:
            documentos.append(doc)

    # -------------------------------------------------------------------------
    # 4. SALDOS A FAVOR NO APLICADOS (Lectura directa de Asientos - JDT1)
    # -------------------------------------------------------------------------
    lista_in = ", ".join([f"'{c}'" for c in codigos_familia])

    # CONTROLES CRÍTICOS AÑADIDOS:
    # - Filtro de fecha cambiado a >= '20240101'
    # - TransType NOT IN ('13', '14') para que no jale los asientos de Facturas ni NCs (Cero Duplicados)
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
        WHERE T0."ShortName" IN ({lista_in}) 
          AND T0."BalDueCred" > 0 
          AND T0."RefDate" >= '20240101'
          AND T0."TransType" NOT IN ('13', '14')
    """

    filas_pr = ejecutar_sql_sl(conn, sql_pr)

    for r in filas_pr:
        # print(
        #     f"   🔍 RAW SAP -> Asiento: {r.get('DocNum')} | Trans: {r.get('TransType')} | Moneda: {r.get('FCCurrency')} | Saldo CRC: {r.get('BalDueCred')} | Saldo USD: {r.get('BalFcCred')}"
        # )
        moneda_linea = r.get("FCCurrency")

        if moneda_linea in ["USD", "US$", "DOL"]:
            moneda_pago = "USD"
            sobrante = round(float(r.get("BalFcCred", 0) or 0), 2)
        else:
            moneda_pago = "CRC"
            sobrante = round(float(r.get("BalDueCred", 0) or 0), 2)

        if sobrante > 0.05:
            # FIX DE FECHAS: Convierte de forma segura el formato plano de SAP '20260526' a '2026-05-26'
            raw_date = str(r.get("RefDate", ""))[:10]
            if raw_date and "-" not in raw_date and len(raw_date) >= 8:
                fecha_pago = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            else:
                fecha_pago = raw_date

            memo = r.get("LineMemo") or "Saldo a favor no aplicado"

            doc_pr = {
                "doc_num": r.get("DocNum"),
                "doc_entry": r.get("DocNum"),
                "consecutivo_fe": "",
                "tipo_codigo": "PR",
                "tipo_texto": "Pago a Favor (Sobrante)",
                "descripcion": memo[:76],
                "series": [],
                "fecha": fecha_pago,
                "fecha_vence": fecha_pago,
                "total": -abs(sobrante),
                "saldo": -abs(sobrante),
                "moneda": moneda_pago,
                "dias_vencido": 0,
                "esta_vencido": False,
                "orden_compra": "",
            }
            documentos.append(doc_pr)

    return documentos


def procesar_documento(doc: Dict, tipo_origen: str) -> Optional[Dict]:
    """
    Procesa un documento (factura o nota de crédito) y extrae todos los campos necesarios.
    """
    hoy = datetime.now().date()

    # Calcular saldo
    if doc.get("DocCurrency") in ["USD", "US$", "DOL"]:
        total = doc.get("DocTotalFc", 0) or doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDateFC", 0) or doc.get("PaidToDate", 0) or 0
        moneda = "USD"
    else:
        total = doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDate", 0) or 0
        moneda = "CRC"

    saldo = total - pagado

    # Si saldo es 0, no incluir
    if abs(saldo) < 0.01:
        return None

    # Tipo de documento
    tipo_doc = doc.get("U_TDOC", "") or ""

    # Para notas de crédito, el saldo es negativo
    if tipo_origen == "creditnote" or tipo_doc.upper() in TIPOS_QUE_RESTAN:
        saldo = -abs(saldo)
        total = -abs(total)

    # Calcular días vencido
    fecha_vence_str = doc.get("DocDueDate", "")
    dias_vencido = 0
    esta_vencido = False

    if fecha_vence_str:
        try:
            fecha_vence = datetime.strptime(
                str(fecha_vence_str)[:10], "%Y-%m-%d"
            ).date()
            dias_vencido = (hoy - fecha_vence).days
            esta_vencido = dias_vencido > 0 and saldo > 0  # Solo vencido si debe dinero
        except:
            pass

    # Extraer descripción y series de las líneas
    descripcion = ""
    series = []
    lineas = doc.get("DocumentLines", [])

    if lineas:
        # Concatenar todas las descripciones separadas por " | "
        descripciones = [
            l.get("ItemDescription", "") for l in lineas if l.get("ItemDescription")
        ]
        descripcion = " | ".join(descripciones)

        # Extraer números de serie
        for linea in lineas:
            serial = linea.get("SerialNum", "")
            if serial:
                series.append(serial)

            # También revisar el array SerialNumbers
            serial_nums = linea.get("SerialNumbers", [])
            for sn in serial_nums:
                if isinstance(sn, dict):
                    series.append(
                        sn.get("InternalSerialNumber", "")
                        or sn.get("ManufacturerSerialNumber", "")
                    )
                elif isinstance(sn, str):
                    series.append(sn)

    # Si no hay descripción en líneas, usar Comments
    if not descripcion:
        descripcion = doc.get("Comments", "") or ""

    # Truncar a 85 caracteres (lo que cabe en la celda del PDF)
    if len(descripcion) > 79:
        descripcion = descripcion[:76] + "..."

    # Consecutivo FE - priorizar U_NVT_ConsecutivoFE sobre U_NUM_CONSE
    consecutivo = doc.get("U_NVT_ConsecutivoFE", "") or doc.get("U_NUM_CONSE", "") or ""

    return {
        "doc_num": doc.get("DocNum"),
        "doc_entry": doc.get("DocEntry"),
        "consecutivo_fe": consecutivo,
        "tipo_codigo": tipo_doc,
        "tipo_texto": traducir_tipo_documento(tipo_doc),
        "descripcion": descripcion,
        "series": series,
        "fecha": str(doc.get("DocDate", ""))[:10],
        "fecha_vence": str(fecha_vence_str)[:10] if fecha_vence_str else "",
        "total": total,
        "saldo": saldo,
        "moneda": moneda,
        "dias_vencido": dias_vencido,
        "esta_vencido": esta_vencido,
        "orden_compra": doc.get("NumAtCard", "") or "",
    }


def traducir_tipo_documento(tipo: str) -> str:
    """Traduce código de tipo de documento a texto legible."""
    if not tipo:
        return "Documento"
    return TRADUCCION_TIPOS.get(tipo.upper(), tipo)


def separar_por_moneda(documentos: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Separa documentos por moneda."""
    colones = [d for d in documentos if d["moneda"] == "CRC"]
    dolares = [d for d in documentos if d["moneda"] == "USD"]
    return colones, dolares


def extraer_correos_de_texto(texto: str) -> List[str]:
    """
    Extrae correos electrónicos de un texto usando regex.
    Útil para extraer correos del campo FreeText/comentarios.
    """
    import re

    if not texto:
        return []

    patron = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    correos = re.findall(patron, texto)

    # Limpiar, convertir a minúsculas y eliminar duplicados
    return list(set([c.lower().strip() for c in correos if c]))


def parsear_correos_campo(valor: str) -> List[str]:
    """
    Parsea un campo que puede tener múltiples correos separados por:
    coma, punto y coma, o espacio.
    """
    if not valor:
        return []

    # Reemplazar separadores por coma
    valor = valor.replace(";", ",").replace(" ", ",")

    # Separar y limpiar
    correos = []
    for parte in valor.split(","):
        parte = parte.strip().lower()
        if "@" in parte and "." in parte:
            correos.append(parte)

    return list(set(correos))


def determinar_correos_cliente(cliente: Dict) -> List[str]:
    """
    Determina los correos para enviar el estado de cuenta.

    Prioridad:
    1. U_NVT_CorreoEstadoCuenta (puede tener múltiples)
    2. FreeText/comentarios (extraer con regex)
    3. EmailAddress (correo principal)

    Returns:
        Lista de correos únicos
    """
    correos = []

    # 1. Campo específico para CXC (prioridad máxima)
    correo_cxc = cliente.get("U_NVT_CorreoEstadoCuenta", "")
    if correo_cxc and correo_cxc.strip():
        correos.extend(parsear_correos_campo(correo_cxc))

    # 2. Si no hay en campo CXC, buscar en comentarios/FreeText
    if not correos:
        notas = cliente.get("FreeText", "") or ""
        correos_notas = extraer_correos_de_texto(notas)
        if correos_notas:
            correos.extend(correos_notas)

    # 3. Si aún no hay, usar correo principal
    if not correos:
        correo_principal = cliente.get("EmailAddress", "")
        if correo_principal and correo_principal.strip():
            correos.append(correo_principal.strip().lower())

    # Eliminar duplicados y retornar
    return list(set(correos))


def cliente_permite_envio(cliente: Dict) -> bool:
    """
    Verifica si el cliente tiene habilitado el envío automático.
    Maneja variaciones como 'Y', 'S', 'SI', 'SÍ', ignorando mayúsculas y espacios.
    """
    envio_auto = cliente.get("U_NTV_EnvioAutomatico")

    if not envio_auto:
        return False

    # Convertimos a string, quitamos espacios en los bordes y pasamos a mayúsculas
    valor_limpio = str(envio_auto).strip().upper()

    # Aceptamos todas las variaciones válidas de "Sí"
    return valor_limpio in ["Y", "S", "SI", "SÍ"]


def calcular_rangos_vencimiento(documentos: List[Dict]) -> Dict:
    """
    Calcula los totales por rangos de vencimiento.
    Retorna dict con totales por moneda y rango.
    """
    rangos = {
        "USD": {
            "0_30": 0,
            "31_60": 0,
            "61_90": 0,
            "91_120": 0,
            "mas_120": 0,
            "total_vencido": 0,
        },
        "CRC": {
            "0_30": 0,
            "31_60": 0,
            "61_90": 0,
            "91_120": 0,
            "mas_120": 0,
            "total_vencido": 0,
        },
    }

    for doc in documentos:
        moneda = doc["moneda"]
        dias = doc["dias_vencido"]
        saldo = doc["saldo"]

        # Solo contar documentos que suman y que están VENCIDOS (días > 0)
        if saldo <= 0 or dias <= 0:
            continue

        rangos[moneda]["total_vencido"] += saldo

        if dias <= 30:
            rangos[moneda]["0_30"] += saldo
        elif dias <= 60:
            rangos[moneda]["31_60"] += saldo
        elif dias <= 90:
            rangos[moneda]["61_90"] += saldo
        elif dias <= 120:
            rangos[moneda]["91_120"] += saldo
        else:
            rangos[moneda]["mas_120"] += saldo

    return rangos


# =============================================================================
# FUNCIÓN PRINCIPAL - PREPARAR DATOS PARA PDF
# =============================================================================


def preparar_datos_cliente(conn: ServiceLayerConnection, cliente: Dict) -> Dict:
    """
    Prepara todos los datos necesarios para generar el PDF de un cliente.
    """
    card_code = cliente.get("CardCode")

    # Obtener información adicional
    condicion_pago, plazo_dias = obtener_condicion_pago(
        conn, cliente.get("PayTermsGrpCode")
    )
    vendedor = obtener_nombre_vendedor(conn, cliente.get("SalesPersonCode"))
    contacto = obtener_contacto_principal(conn, card_code, cliente.get("ContactPerson"))

    # Obtener documentos
    documentos = obtener_documentos_cliente(conn, card_code)

    # Separar por moneda
    doc_colones, doc_dolares = separar_por_moneda(documentos)

    # Calcular totales
    total_colones = sum(d["saldo"] for d in doc_colones)
    total_dolares = sum(d["saldo"] for d in doc_dolares)

    # Calcular rangos de vencimiento
    rangos = calcular_rangos_vencimiento(documentos)

    # Determinar correos (puede ser múltiples)
    correos = determinar_correos_cliente(cliente)

    # Si en SAP el cliente es explícitamente "USD", su límite es USD.
    # Si es "CRC" o "##" (Multimoneda), SAP obliga a que el límite se guarde en colones.
    # NO miramos los documentos para nada.
    # =========================================================================
    moneda_bp = cliente.get("Currency", "CRC")
    moneda_limite = "USD" if moneda_bp in ["USD", "US$"] else "CRC"

    return {
        "cliente": {
            "codigo": card_code,
            "nombre": cliente.get("CardName", ""),
            "telefono": cliente.get("Phone1", "")
            or cliente.get("Phone2", "")
            or cliente.get("Cellular", ""),
            "correos": correos,  # Lista de correos
            "correo": correos[0] if correos else None,  # Primer correo (compatibilidad)
            "direccion": cliente.get("Address", ""),
            "contacto": contacto.get("nombre", ""),
            "vendedor": vendedor,
            "condicion_pago": condicion_pago,
            "plazo_dias": plazo_dias,
            "limite_credito": cliente.get("CreditLimit", 0) or 0,
            "moneda_limite": moneda_limite,
            "saldo_total": cliente.get("CurrentAccountBalance", 0) or 0,
            "envio_automatico": cliente.get("U_NTV_EnvioAutomatico", ""),
        },
        "documentos": {
            "colones": doc_colones,
            "dolares": doc_dolares,
        },
        "totales": {
            "colones": total_colones,
            "dolares": total_dolares,
        },
        "rangos_vencimiento": rangos,
        "fecha_corte": datetime.now().strftime("%d/%m/%Y"),
        "hora": datetime.now().strftime("%I:%M %p"),
    }


# =============================================================================
# PROCESO PRINCIPAL
# =============================================================================


def ejecutar_proceso_cxc(
    lista_clientes: List[str] = None, modo_test_limite: bool = False
):
    """
    Proceso principal de envío de estados de cuenta.
    Se ejecuta los días 15 y 30 de cada mes.
    """
    print("=" * 80)
    print("📧 PROCESO: Estados de Cuenta - Químicas Unidas")
    print(f"   Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        # Inicializar log de control
        log_control = ControlCXC()

        # 1. Obtener TODOS los clientes con saldo
        print("\n📋 Obteniendo clientes...")
        clientes = obtener_clientes_con_saldo(
            conn, limite=2 if modo_test_limite else None, lista_codigos=lista_clientes
        )
        print(f"   Total clientes a procesar: {len(clientes)}")

        log_control.set_total_clientes(len(clientes))

        # =====================================================================
        # DESARROLLO: Limitar a 2 clientes para pruebas
        # PRODUCCIÓN: Comentar o eliminar la siguiente línea
        # =====================================================================
        # clientes = clientes[:2]
        # print(f"   ⚠️ MODO DESARROLLO: Procesando solo {len(clientes)} clientes")
        # =====================================================================

        if not clientes:
            print("   No hay clientes con saldo pendiente")
            return

        # 2. Procesar cada cliente
        resultados = {
            "procesados": 0,
            "enviados": 0,
            "sin_correo": 0,
            "errores": 0,
        }

        sp_uploader = SharePointUploader()

        for i, cliente in enumerate(clientes, 1):
            card_code = cliente.get("CardCode")
            card_name = cliente.get("CardName")

            print(f"\n[{i}/{len(clientes)}] {card_code} - {card_name}")

            # Verificar si permite envío automático
            # BYPASS: Si pasamos un cliente por consola/API (lista_clientes), ignoramos el bloqueo de SAP.
            if not cliente_permite_envio(cliente) and not lista_clientes:
                print(f"   ⏭️ Envío automático deshabilitado")
                log_control.agregar_registro(
                    codigo=card_code,
                    nombre=card_name,
                    correos=[],
                    docs_usd=0,
                    docs_crc=0,
                    total_usd=0,
                    total_crc=0,
                    vencido_usd=0,
                    vencido_crc=0,
                    pdf_generado=False,
                    email_status="deshabilitado",
                    observacion="Envío automático deshabilitado",
                )
                continue

            # Preparar datos del cliente
            datos = preparar_datos_cliente(conn, cliente)

            # Verificar si tiene documentos
            total_docs = len(datos["documentos"]["colones"]) + len(
                datos["documentos"]["dolares"]
            )
            if total_docs == 0:
                print(f"   ⏭️ Sin documentos pendientes")
                log_control.agregar_registro(
                    codigo=card_code,
                    nombre=card_name,
                    correos=datos["cliente"]["correos"],
                    docs_usd=0,
                    docs_crc=0,
                    total_usd=0,
                    total_crc=0,
                    vencido_usd=0,
                    vencido_crc=0,
                    pdf_generado=False,
                    email_status="pendiente",
                    observacion="Sin documentos pendientes",
                )
                continue

            resultados["procesados"] += 1

            # Verificar correos
            correos = datos["cliente"]["correos"]
            if not correos:
                print(f"   ⚠️ Sin correo electrónico")
                resultados["sin_correo"] += 1
                log_control.agregar_registro(
                    codigo=card_code,
                    nombre=card_name,
                    correos=[],
                    docs_usd=len(datos["documentos"]["dolares"]),
                    docs_crc=len(datos["documentos"]["colones"]),
                    total_usd=datos["totales"]["dolares"],
                    total_crc=datos["totales"]["colones"],
                    vencido_usd=datos["rangos_vencimiento"]["USD"]["total_vencido"],
                    vencido_crc=datos["rangos_vencimiento"]["CRC"]["total_vencido"],
                    pdf_generado=False,
                    email_status="sin_correo",
                    observacion="Cliente sin correo configurado",
                )
                continue

            # Mostrar resumen
            print(f"   Documentos: {total_docs}")
            if datos["totales"]["dolares"] != 0:
                print(f"   Total USD: ${datos['totales']['dolares']:,.2f}")
            if datos["totales"]["colones"] != 0:
                print(f"   Total CRC: ₡{datos['totales']['colones']:,.2f}")
            print(f"   Correo(s): {', '.join(correos)}")

            # Generar PDF
            pdf_generado = False
            excel_path = None

            try:
                pdf_path = generar_pdf_estado_cuenta(datos)
                print(f"   ✅ PDF generado: {pdf_path}")
                pdf_generado = True

                # ☁️ Subir a SharePoint en la carpeta de CXC
                sp_uploader.upload_reporte(pdf_path, "CXC_Clientes")

                # Generar Excel (mismo datos)

                try:
                    excel_path = generar_excel_estado_cuenta(datos)
                    print(f"   ✅ Excel generado: {excel_path}")
                    sp_uploader.upload_reporte(excel_path, "CXC_Clientes")
                except Exception as e:
                    print(f"   ⚠️ Error generando Excel: {str(e)}")
                    # No es crítico, continúa con el PDF
            except Exception as e:
                print(f"   ❌ Error generando PDF: {str(e)}")
                resultados["errores"] += 1
                log_control.agregar_registro(
                    codigo=card_code,
                    nombre=card_name,
                    correos=correos,
                    docs_usd=len(datos["documentos"]["dolares"]),
                    docs_crc=len(datos["documentos"]["colones"]),
                    total_usd=datos["totales"]["dolares"],
                    total_crc=datos["totales"]["colones"],
                    vencido_usd=datos["rangos_vencimiento"]["USD"]["total_vencido"],
                    vencido_crc=datos["rangos_vencimiento"]["CRC"]["total_vencido"],
                    pdf_generado=False,
                    email_status="error",
                    observacion=f"Error PDF: {str(e)[:30]}",
                )
                continue

            # Enviar correo
            # En modo prueba, envía a EMAIL_PRUEBA
            # En producción, envía a los correos reales del cliente
            if MODO_PRUEBA:
                destinatarios = [EMAIL_PRUEBA]
                print(
                    f"   📧 MODO PRUEBA: Enviando a {EMAIL_PRUEBA} (en vez de {', '.join(correos)})"
                )
            else:
                destinatarios = correos

            try:
                # Obtener el plazo dinámico (PayTermsGrpCode se convierte en días)
                plazo_dias = datos["cliente"]["plazo_dias"]

                enviado = enviar_estado_cuenta(
                    destinatarios=destinatarios,
                    nombre_cliente=datos["cliente"]["nombre"],
                    codigo_cliente=datos["cliente"]["codigo"],
                    ruta_pdf=pdf_path,
                    datos=datos,
                    plazo_dias=plazo_dias,
                    ruta_excel=excel_path,
                )
                if enviado:
                    resultados["enviados"] += 1
                    log_control.agregar_registro(
                        codigo=card_code,
                        nombre=card_name,
                        correos=correos,
                        docs_usd=len(datos["documentos"]["dolares"]),
                        docs_crc=len(datos["documentos"]["colones"]),
                        total_usd=datos["totales"]["dolares"],
                        total_crc=datos["totales"]["colones"],
                        vencido_usd=datos["rangos_vencimiento"]["USD"]["total_vencido"],
                        vencido_crc=datos["rangos_vencimiento"]["CRC"]["total_vencido"],
                        pdf_generado=pdf_generado,
                        email_status="enviado",
                        observacion="PDF + Excel enviados OK",
                    )
                else:
                    resultados["errores"] += 1
                    log_control.agregar_registro(
                        codigo=card_code,
                        nombre=card_name,
                        correos=correos,
                        docs_usd=len(datos["documentos"]["dolares"]),
                        docs_crc=len(datos["documentos"]["colones"]),
                        total_usd=datos["totales"]["dolares"],
                        total_crc=datos["totales"]["colones"],
                        vencido_usd=datos["rangos_vencimiento"]["USD"]["total_vencido"],
                        vencido_crc=datos["rangos_vencimiento"]["CRC"]["total_vencido"],
                        pdf_generado=pdf_generado,
                        email_status="error",
                        observacion="Error al enviar correo",
                    )
            except Exception as e:
                print(f"   ❌ Error enviando correo: {str(e)}")
                resultados["errores"] += 1
                log_control.agregar_registro(
                    codigo=card_code,
                    nombre=card_name,
                    correos=correos,
                    docs_usd=len(datos["documentos"]["dolares"]),
                    docs_crc=len(datos["documentos"]["colones"]),
                    total_usd=datos["totales"]["dolares"],
                    total_crc=datos["totales"]["colones"],
                    vencido_usd=datos["rangos_vencimiento"]["USD"]["total_vencido"],
                    vencido_crc=datos["rangos_vencimiento"]["CRC"]["total_vencido"],
                    pdf_generado=pdf_generado,
                    email_status="error",
                    observacion=f"Excepción: {str(e)[:25]}",
                )

        # 3. Resumen final
        print("\n" + "=" * 80)
        print("📊 RESUMEN DEL PROCESO")
        print("=" * 80)
        print(f"   Clientes procesados: {resultados['procesados']}")
        print(f"   Correos enviados: {resultados['enviados']}")
        print(f"   Sin correo: {resultados['sin_correo']}")
        print(f"   Errores: {resultados['errores']}")
        print("=" * 80)

        # 4. Generar y enviar log de control
        print("\n[LOG] Generando log de control...")
        try:
            log_path = log_control.generar_pdf()
            print(f"   [OK] Log generado: {log_path}")

            sp_uploader.upload_reporte(log_path, "Logs_de_CXC")

            # Enviar log por correo
            print(f"   Enviando log a {EMAIL_LOG_CONTROL}...")
            from sendemailCXC import EmailSenderCXC

            sender = EmailSenderCXC()
            enviado_log = sender.enviar_control_interno(
                destinatarios=[EMAIL_LOG_CONTROL],
                archivos=[log_path],
                stats=log_control.stats,
            )

            if enviado_log:
                print(f"   [OK] Log enviado correctamente")
            else:
                print(f"   [!] No se pudo enviar el log por correo")

        except Exception as e:
            print(f"   [ERROR] Error generando/enviando log: {str(e)}")

        print("\n" + "=" * 80)
        print("✅ PROCESO FINALIZADO")
        print("=" * 80)

    finally:
        conn.logout()


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Automatización de Estados de Cuenta (CXC) - Químicas Unidas"
    )
    parser.add_argument(
        "--test", action="store_true", help="Limitar a 2 clientes (modo desarrollo)"
    )
    parser.add_argument(
        "--clientes",
        type=str,
        help="Ejecutar clientes específicos separados por coma. Ej: --clientes C0223,C0250",
    )

    args = parser.parse_args()

    codigos = args.clientes.split(",") if args.clientes else None

    ejecutar_proceso_cxc(lista_clientes=codigos, modo_test_limite=args.test)
