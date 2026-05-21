"""
consignaciones_v3.py - Químicas Unidas

REPORTE DE TOMA FÍSICA DE INVENTARIO (Consignaciones) — VERSIÓN DEFINITIVA

Reemplaza a consignaciones.py. Esta versión es estructuralmente correcta:

Fuente de datos correcta:
  /StockTransfers (OData) — traslados ABIERTOS hacia bodegas de cliente
  /SerialNumberDetails — para enriquecer con MfrSerialNo si hace falta
  /BusinessPartners — clientes con FatherCard (jerarquía padre/hijo)
  /Warehouses — catálogo de bodegas (124 totales, 112 de consignación)
  /SalesPersons — agentes con correo

Lógica:
  1. Trae traslados abiertos (DocumentStatus=bost_Open) hacia bodegas de cons.
  2. De cada línea, extrae los números de serie (lista SerialNumbers).
  3. Resuelve bodega → cliente, cliente hijo → cliente padre (jerarquía).
  4. Agrupa por agente del cliente padre.
  5. Genera un PDF por agente y lo envía por correo.

Modos:
  --test         Procesa solo los primeros 2 agentes
  --refresh      Ignora cache y consulta SAP de nuevo
  --no-email     Solo genera PDFs, no envía correo

Cache de datos:
  data/cache_consignaciones_v3.json (válido 30 minutos)
"""

import sys
import os
import time
import json
from datetime import datetime
from collections import defaultdict
from fpdf import FPDF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection
from sendemailCXC import EmailSenderAgente

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

EMAIL_PRUEBA = "devs@techconnectors.co"
MODO_PRUEBA = True

AZUL_OSCURO = (11, 17, 75)
AZUL_CLARO = (40, 143, 204)
AZUL_FOOTER = (71, 93, 164)

CACHE_FILE = "data/cache_consignaciones_v3.json"
CACHE_MAX_AGE_MIN = 30

# Bodegas internas de Químicas Unidas (NO de consignación)
BODEGAS_INTERNAS = {
    "-1",
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
}


# =============================================================================
# UTILIDADES DE EXTRACCIÓN
# =============================================================================


def odata_paginado(conn, entidad, params=None, page_size=500, silencioso=False):
    """Paginación con header Prefer maxpagesize=500."""
    if params is None:
        params = {}
    todos = []
    skip = 0
    headers = {"Prefer": f"odata.maxpagesize={page_size}"}

    while True:
        params["$skip"] = skip
        url = f"{conn.base_url}/{entidad}"
        res_http = conn.session.get(url, params=params, headers=headers)
        if res_http.status_code != 200:
            if not silencioso:
                print(f"   ❌ HTTP {res_http.status_code}: {res_http.text[:200]}")
            break
        res = res_http.json()
        if not res or "value" not in res or not res["value"]:
            break
        todos.extend(res["value"])
        recibidos = len(res["value"])
        if recibidos < 20:
            break
        skip += recibidos
        if skip > 100000:
            if not silencioso:
                print(f"   ⚠️  Cortado en {skip}")
            break
    return todos


# =============================================================================
# CACHE
# =============================================================================


def cache_valido():
    if not os.path.exists(CACHE_FILE):
        return False
    age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
    return age_min < CACHE_MAX_AGE_MIN


def guardar_cache(data):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def leer_cache():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# EXTRACCIÓN DE DATOS
# =============================================================================


def obtener_bodegas(conn):
    """Catálogo completo de bodegas vía /Warehouses."""
    print("📥 Bodegas...")
    bodegas = odata_paginado(
        conn, "Warehouses", {"$select": "WarehouseCode,WarehouseName,Inactive"}
    )
    print(f"   {len(bodegas)} bodegas totales")
    return bodegas


def obtener_traslados_abiertos(conn, codigos_bodega_destino):
    """
    Trae traslados abiertos cuyo destino esté en la lista de bodegas.

    Para evitar URLs gigantes, paginamos en lotes de 30 destinos por filtro.
    """
    print(f"📥 StockTransfers abiertos hacia {len(codigos_bodega_destino)} bodegas...")

    # =========================================================================
    # FILTRO OPCIONAL POR AÑO
    # =========================================================================
    # Descomentar la línea siguiente para traer SOLO traslados desde un año.
    # Útil para validar contra la encargada (ej: solo 2025) y excluir documentos
    # muy antiguos que quizá quedaron mal cerrados en SAP.
    # Dejar como None para traer TODO el histórico abierto.

    # AÑO_DESDE = None       # ← sin filtro de fecha (TODO)
    AÑO_DESDE = 2025  # ← solo desde el 1-ene-2025 (recomendado para validar)
    # =========================================================================

    filtro_fecha = ""
    if AÑO_DESDE:
        filtro_fecha = f" and DocDate ge '{AÑO_DESDE}-01-01T00:00:00Z'"
        print(f"   📅 Filtro adicional: solo desde {AÑO_DESDE}-01-01")

    traslados = []
    LOTE = 30
    t0 = time.time()

    for i in range(0, len(codigos_bodega_destino), LOTE):
        chunk = codigos_bodega_destino[i : i + LOTE]
        cond_to = " or ".join(f"ToWarehouse eq '{c}'" for c in chunk)
        filtro = f"DocumentStatus eq 'bost_Open' and ({cond_to}){filtro_fecha}"
        lote = odata_paginado(
            conn,
            "StockTransfers",
            {
                "$filter": filtro,
                "$select": "DocEntry,DocNum,DocDate,CardCode,CardName,ToWarehouse,FromWarehouse",
            },
        )
        traslados.extend(lote)
        print(
            f"   Lote {i//LOTE + 1}/{(len(codigos_bodega_destino)-1)//LOTE + 1}: "
            f"+{len(lote):4} | total: {len(traslados):5} | {time.time()-t0:.1f}s"
        )

    print(f"   ✅ {len(traslados)} traslados abiertos")
    return traslados


def obtener_detalle_traslado(conn, doc_entry):
    """Trae un traslado completo con sus líneas y series."""
    res_http = conn.session.get(f"{conn.base_url}/StockTransfers({doc_entry})")
    if res_http.status_code != 200:
        return None
    return res_http.json()


def extraer_series_de_traslados(conn, traslados):
    """
    Para cada traslado, descarga sus líneas y extrae las series.

    Devuelve una lista plana de equipos con todos los datos para el reporte.
    """
    print(f"📥 Detalles de {len(traslados)} traslados (líneas + series)...")
    equipos = []
    t0 = time.time()

    for i, t in enumerate(traslados, 1):
        doc = obtener_detalle_traslado(conn, t["DocEntry"])
        if not doc:
            continue

        lineas = doc.get("StockTransferLines", [])
        for ln in lineas:
            series_list = ln.get("SerialNumbers", [])
            if not series_list:
                continue
            for s in series_list:
                equipos.append(
                    {
                        "DocNum": t.get("DocNum"),
                        "DocDate": t.get("DocDate", "")[:10],  # solo fecha
                        "ToWarehouse": t.get("ToWarehouse"),
                        "CardCodeTraslado": t.get("CardCode"),
                        "ItemCode": ln.get("ItemCode"),
                        "ItemDescription": ln.get("ItemDescription", ""),
                        "WarehouseCodeLinea": ln.get("WarehouseCode"),
                        "SystemSerialNumber": s.get("SystemSerialNumber"),
                        "InternalSerialNumber": s.get("InternalSerialNumber"),
                        "ManufacturerSerialNumber": s.get("ManufacturerSerialNumber"),
                        "BatchID": s.get("BatchID"),
                    }
                )

        if i % 20 == 0 or i == len(traslados):
            tasa = i / max(time.time() - t0, 0.1)
            eta = (len(traslados) - i) / max(tasa, 0.1)
            print(
                f"   [{i:4}/{len(traslados)}] series acum: {len(equipos):5} | ETA: {eta:.0f}s"
            )

    print(f"   ✅ {len(equipos)} series extraídas en {time.time()-t0:.1f}s")
    return equipos


def obtener_clientes(conn, card_codes_necesarios):
    """Trae solo los clientes que aparecen como CardCode en los traslados, más sus padres."""
    print(f"📥 Clientes ({len(card_codes_necesarios)} necesarios)...")

    candidatos = list(card_codes_necesarios)
    todos_clientes = []
    LOTE = 50

    for i in range(0, len(candidatos), LOTE):
        chunk = candidatos[i : i + LOTE]
        filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
        clientes_chunk = odata_paginado(
            conn,
            "BusinessPartners",
            {
                "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                "$filter": filtro,
            },
        )
        todos_clientes.extend(clientes_chunk)

    # Traer padres faltantes
    cards_ya = {c["CardCode"] for c in todos_clientes}
    padres = {
        c["FatherCard"]
        for c in todos_clientes
        if c.get("FatherCard") and c["FatherCard"] not in cards_ya
    }

    if padres:
        padres_list = list(padres)
        for i in range(0, len(padres_list), LOTE):
            chunk = padres_list[i : i + LOTE]
            filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
            todos_clientes.extend(
                odata_paginado(
                    conn,
                    "BusinessPartners",
                    {
                        "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                        "$filter": filtro,
                    },
                )
            )

    print(f"   ✅ {len(todos_clientes)} clientes (incl. padres)")
    return todos_clientes


def obtener_vendedores(conn):
    print("📥 Vendedores...")
    vs = odata_paginado(
        conn, "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"}
    )
    print(f"   ✅ {len(vs)} vendedores")
    return {v["SalesEmployeeCode"]: v for v in vs}


# =============================================================================
# CRUCE Y AGRUPACIÓN
# =============================================================================


def cruzar_datos(equipos, clientes, bodegas):
    """
    Para cada equipo:
      - Encuentra cliente dueño (vía CardCode del traslado)
      - Si cliente tiene FatherCard, usa el padre como cliente "principal"
      - El cliente hijo queda como "tienda / Enviado a"
    """
    print("🔀 Cruzando datos...")

    clientes_dict = {c["CardCode"]: c for c in clientes}
    bodegas_dict = {b["WarehouseCode"]: b.get("WarehouseName", "?") for b in bodegas}

    resultado = []
    for e in equipos:
        cc = e["CardCodeTraslado"]
        if not cc or cc not in clientes_dict:
            continue

        cli = clientes_dict[cc]
        father = cli.get("FatherCard")

        if father and father in clientes_dict:
            cli_principal = clientes_dict[father]
            tienda_card = cli["CardCode"]
            tienda_nombre = bodegas_dict.get(e["ToWarehouse"], cli.get("CardName", "?"))
        else:
            cli_principal = cli
            tienda_card = ""
            tienda_nombre = bodegas_dict.get(e["ToWarehouse"], "")

        resultado.append(
            {
                **e,
                "ClienteCardCode": cli_principal["CardCode"],
                "ClienteNombre": cli_principal.get("CardName", "?"),
                "TiendaCardCode": tienda_card,
                "TiendaNombre": tienda_nombre,
                "SalesPersonCode": cli_principal.get("SalesPersonCode", -1),
                "Zona": cli_principal.get("U_ZGIRA", ""),
            }
        )

    print(f"   ✅ {len(resultado)} equipos con cliente identificado")
    return resultado


# =============================================================================
# PDF
# =============================================================================


class PDFConsignacion(FPDF):
    def __init__(self, agente_nombre):
        super().__init__(orientation="L", unit="mm", format="Legal")
        self.agente_nombre = agente_nombre
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 15, 10)

    def header(self):
        self.set_font("Arial", "B", 16)
        self.set_text_color(*AZUL_OSCURO)
        self.cell(0, 8, "DETALLE DE INVENTARIO - CONSIGNACIONES", 0, 1, "L")

        self.set_font("Arial", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f"Agente / Vendedor: {self.agente_nombre}", 0, 1, "L")

        self.set_xy(-60, 15)
        self.cell(50, 5, f'Fecha: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, "R")
        self.set_xy(-60, 20)
        self.cell(50, 5, f'Hora: {datetime.now().strftime("%I:%M %p")}', 0, 1, "R")

        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.8)
        self.line(10, 28, self.w - 10, 28)
        self.set_y(32)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "R")

    def agregar_tabla(self, equipos):
        # Columnas: Cliente | Custodio | Enviado a | Fecha | Documento | Cód Art | Descripción | N° Serie
        anchos = [20, 55, 35, 22, 22, 30, 90, 45]
        headers = [
            "Cliente",
            "Nombre del Custodio",
            "Enviado a",
            "Fecha",
            "Documento",
            "Cód. Artículo",
            "Descripción",
            "Número de Serie",
        ]

        def render_headers():
            self.set_fill_color(*AZUL_FOOTER)
            self.set_text_color(255, 255, 255)
            self.set_font("Arial", "B", 9)
            for i, h in enumerate(headers):
                self.cell(anchos[i], 7, h, 1, 0, "C", True)
            self.ln()
            self.set_text_color(0, 0, 0)
            self.set_font("Arial", "", 8)

        render_headers()
        fill = False

        for e in equipos:
            if self.get_y() > self.h - 40:
                self.add_page()
                render_headers()

            (
                self.set_fill_color(245, 245, 245)
                if fill
                else self.set_fill_color(255, 255, 255)
            )

            # Formatear fecha YYYY-MM-DD a DD/MM/YY
            fecha = e.get("DocDate", "")
            if len(fecha) >= 10:
                fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[2:4]}"

            # Serie: preferir ManufacturerSerialNumber, luego InternalSerialNumber
            serie = (
                e.get("ManufacturerSerialNumber")
                or e.get("InternalSerialNumber")
                or str(e.get("SystemSerialNumber", ""))
            )

            self.cell(
                anchos[0], 6, str(e.get("ClienteCardCode", ""))[:10], 1, 0, "C", fill
            )
            self.cell(
                anchos[1], 6, str(e.get("ClienteNombre", ""))[:35], 1, 0, "L", fill
            )
            self.cell(
                anchos[2], 6, str(e.get("TiendaNombre", ""))[:22], 1, 0, "L", fill
            )
            self.cell(anchos[3], 6, fecha, 1, 0, "C", fill)
            self.cell(anchos[4], 6, str(e.get("DocNum", "")), 1, 0, "C", fill)
            self.cell(anchos[5], 6, str(e.get("ItemCode", ""))[:15], 1, 0, "C", fill)
            self.cell(
                anchos[6], 6, str(e.get("ItemDescription", ""))[:55], 1, 0, "L", fill
            )
            self.cell(anchos[7], 6, str(serie)[:25], 1, 1, "C", fill)

            fill = not fill

    def agregar_firmas(self):
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(20)
        self.set_font("Arial", "", 10)
        self.cell(
            0,
            6,
            "El custodio da por aceptada la toma física de inventario realizado el "
            "____________________ a las _____________.",
            0,
            1,
        )
        self.ln(15)
        self.cell(100, 5, "_________________________________________________", 0, 0)
        self.cell(100, 5, "_________________________________________________", 0, 1)
        self.cell(100, 5, "Custodio:", 0, 0)
        self.cell(100, 5, "Hecho por:", 0, 1)


# =============================================================================
# PROCESO PRINCIPAL
# =============================================================================


def descargar_datos_de_sap(conn):
    """Descarga todo y devuelve un dict listo para guardar en cache."""
    # 1. Bodegas
    bodegas = obtener_bodegas(conn)
    bodegas_cons = [
        b["WarehouseCode"]
        for b in bodegas
        if b["WarehouseCode"] not in BODEGAS_INTERNAS
    ]
    print(f"   → {len(bodegas_cons)} de consignación")

    # 2. Traslados abiertos
    traslados = obtener_traslados_abiertos(conn, bodegas_cons)

    if not traslados:
        return None

    # 3. Series de cada traslado
    equipos = extraer_series_de_traslados(conn, traslados)

    if not equipos:
        print("⚠️  No hay equipos con series en los traslados")
        return None

    # 4. Clientes (solo los necesarios + padres)
    card_codes = {e["CardCodeTraslado"] for e in equipos if e.get("CardCodeTraslado")}
    clientes = obtener_clientes(conn, card_codes)

    # 5. Vendedores
    vendedores = obtener_vendedores(conn)

    # 6. Cruce
    equipos_finales = cruzar_datos(equipos, clientes, bodegas)

    return {
        "timestamp": datetime.now().isoformat(),
        "equipos": equipos_finales,
        "vendedores": {str(k): v for k, v in vendedores.items()},
    }


def ejecutar():
    print("=" * 80)
    print("📦 REPORTES DE CONSIGNACIÓN (TOMA FÍSICA) — VERSIÓN 3")
    print("=" * 80)

    # ¿Cache o SAP?
    if cache_valido() and "--refresh" not in sys.argv:
        print(f"\n💾 Usando cache ({CACHE_FILE})")
        print("   Usá --refresh para forzar consulta a SAP")
        data = leer_cache()
    else:
        conn = ServiceLayerConnection(use_test_db=False)
        if not conn.login():
            return
        try:
            t0 = time.time()
            data = descargar_datos_de_sap(conn)
            if data is None:
                return
            guardar_cache(data)
            print(f"\n💾 Cache guardado | ⏱️  Total: {time.time()-t0:.1f}s")
        finally:
            conn.logout()

    equipos = data["equipos"]
    vendedores = {
        int(k) if str(k).lstrip("-").isdigit() else k: v
        for k, v in data["vendedores"].items()
    }

    # =====================================================================
    # Agrupar por agente y generar PDFs
    # =====================================================================
    por_agente = defaultdict(list)
    for e in equipos:
        por_agente[e["SalesPersonCode"]].append(e)

    print("\n" + "=" * 80)
    print(f"📊 {len(equipos)} equipos en {len(por_agente)} agentes")
    print("=" * 80)
    print(f"\n{'SlpCode':<10} {'Agente':<40} {'Equipos':<10} {'Clientes':<10}")
    print("-" * 72)
    for slp, eqs in sorted(por_agente.items(), key=lambda x: -len(x[1])):
        nombre = vendedores.get(slp, {}).get("SalesEmployeeName", "?")
        clientes_unicos = len(set(e["ClienteCardCode"] for e in eqs))
        print(f"{str(slp):<10} {nombre[:39]:<40} {len(eqs):<10} {clientes_unicos:<10}")

    # =====================================================================
    # Generación de PDFs y envío
    # =====================================================================
    if "--no-email" in sys.argv and "--test" not in sys.argv:
        print("\n   (modo --no-email: solo genera PDFs)")
    print("\n" + "=" * 80)
    print("📄 Generando PDFs...")
    print("=" * 80)

    sender = EmailSenderAgente() if "--no-email" not in sys.argv else None
    os.makedirs("data/consignaciones", exist_ok=True)
    resultados = {"procesados": 0, "enviados": 0, "errores": 0, "sin_correo": 0}

    for slp, lista in por_agente.items():
        if "--test" in sys.argv and resultados["procesados"] >= 2:
            break

        info = vendedores.get(slp, {})
        nombre = info.get("SalesEmployeeName", f"(Agente {slp})")
        correo = info.get("Email", "")

        # Ordenar: por zona, cliente, tienda, fecha
        lista.sort(
            key=lambda x: (
                str(x.get("Zona", "")).zfill(3),
                x.get("ClienteNombre", ""),
                x.get("TiendaNombre", ""),
                x.get("DocDate", ""),
            )
        )

        print(f"\n👨‍💼 {nombre} | {len(lista)} equipos")

        pdf = PDFConsignacion(nombre)
        pdf.add_page()
        pdf.agregar_tabla(lista)
        pdf.agregar_firmas()

        pdf_path = f"data/consignaciones/TomaFisica_{slp}_{datetime.now().strftime('%Y%m%d')}.pdf"
        pdf.output(pdf_path)
        print(f"   📄 PDF: {pdf_path}")

        # Envío
        if sender is None:
            resultados["procesados"] += 1
            continue

        destinatario = EMAIL_PRUEBA if MODO_PRUEBA else correo
        if not destinatario or "@" not in str(destinatario):
            print(f"   ⚠️  Sin correo")
            resultados["sin_correo"] += 1
            continue

        if sender.enviar_reporte_gira(destinatario, nombre, pdf_path):
            print(f"   ✅ Enviado a {destinatario}")
            resultados["enviados"] += 1
        else:
            resultados["errores"] += 1
        resultados["procesados"] += 1

    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL")
    print(f"   Agentes procesados: {resultados['procesados']}")
    print(f"   Correos enviados:   {resultados['enviados']}")
    print(f"   Sin correo:         {resultados['sin_correo']}")
    print(f"   Errores:            {resultados['errores']}")
    print("=" * 80)


if __name__ == "__main__":
    ejecutar()
