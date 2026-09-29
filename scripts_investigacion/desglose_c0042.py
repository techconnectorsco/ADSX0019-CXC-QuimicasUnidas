r"""
desglose_c0042.py - Quimicas Unidas / ADSX0019

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA. Unicamente GET contra SAP Service Layer (mas /Login y /Logout,
que es como autentica el Service Layer). No escribe, no edita, no elimina,
no envia correo, no genera PDF, no toca SharePoint ni Supabase.
No importa api.py. De agentes.py importa SOLO funciones de lectura.

PREGUNTA QUE RESPONDE
---------------------
Verificacion_Sucursales_Pendientes.txt (19/09/2026) reporto 69 facturas
abiertas para C0042. El PDF de la gira por zona del agente 7 generado el
27/09/2026 trae 44 filas. De donde sale la diferencia?

Dos causas candidatas, y este script las separa:

  a) PAGOS. Facturas que se pagaron o cerraron en los 8 dias transcurridos.
     Se mide comparando el total de hoy contra las 69 del reporte anterior.

  b) RUTEO DE VENDEDOR. El reporte anterior conto TODOS los documentos
     abiertos de C0042, sin mirar a que vendedor apunta cada uno. La gira del
     agente 7 solo incluye los documentos cuya direccion de entrega
     (ShipToCode) rutea al vendedor 7 via BPAddresses.U_CODV. Los demas se
     omiten, y es el comportamiento correcto: son de otro agente.

  Una tercera, SALDO CERO, queda descartada de antemano: el script del 19/09
  ya aplicaba el mismo criterio (abs(saldo) < 0.005 -> se descarta) que
  procesar_documento(). Se recalcula igual para confirmarlo.

METODO
------
Replica la logica de agentes.py reutilizando sus propias funciones de lectura,
para que no haya duda de que mide lo mismo:

  - Consulta de documentos: mismo $filter que obtener_documentos_cliente()
  - Saldo por documento: procesar_documento(), importada tal cual
  - Ruteo: obtener_mapeo_direcciones(), importada tal cual

Genera: Verificacion_Desglose_C0042.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/desglose_c0042.py
"""

import os
import sys
from collections import defaultdict
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection
from agentes import (
    obtener_mapeo_direcciones,
    obtener_todos_paginado,
    procesar_documento,
)

CLIENTE = "C0042"
AGENTE = 7
CONTEO_ANTERIOR = 69  # facturas con saldo segun el reporte del 19/09
CONTEO_PDF = 44       # filas de documento contadas en el PDF del 27/09 21:14

REPORTE = os.path.join(BASE_DIR, "Verificacion_Desglose_C0042.txt")

CAMPOS = (
    "DocNum,DocEntry,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,"
    "PaidToDateFC,DocCurrency,U_TDOC,U_NVT_ConsecutivoFE,U_NUM_CONSE,"
    "NumAtCard,Comments,ShipToCode,DocumentLines"
)

_lineas = []


def log(texto=""):
    print(texto)
    _lineas.append(texto)


def titulo(t):
    log("")
    log("=" * 78)
    log(t)
    log("=" * 78)


def guardar():
    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lineas))
    print("")
    print(f"Reporte guardado en: {REPORTE}")


def main():
    inicio = datetime.now()

    log("=" * 78)
    log(f"DESGLOSE {CLIENTE} - por que el PDF trae {CONTEO_PDF} y no {CONTEO_ANTERIOR}")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("Script de SOLO LECTURA. Unicamente GET (mas Login/Logout).")
    log("No escribe, no edita, no elimina, no envia.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION (solo lectura)...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return

    try:
        # ------------------------------------------------------------------
        # 1. Ruteo de direcciones (la misma funcion que usa la gira)
        # ------------------------------------------------------------------
        titulo("PASO 1 - Ruteo de direcciones de entrega (BPAddresses.U_CODV)")

        mapeo = obtener_mapeo_direcciones(conn, CLIENTE)
        log("")
        log(f"   Direcciones de entrega con vendedor asignado: {len(mapeo)}")

        por_vendedor = defaultdict(list)
        for direccion, vendedor in sorted(mapeo.items()):
            por_vendedor[vendedor].append(direccion)

        for vendedor in sorted(por_vendedor):
            marca = "   <-- el agente de la prueba" if vendedor == AGENTE else ""
            log("")
            log(f"   Vendedor {vendedor}: {len(por_vendedor[vendedor])} direcciones{marca}")
            log(f"      {', '.join(por_vendedor[vendedor])}")

        # ------------------------------------------------------------------
        # 2. Documentos abiertos hoy (mismo filtro que la gira)
        # ------------------------------------------------------------------
        titulo("PASO 2 - Documentos abiertos hoy (mismo filtro que la gira)")

        facturas = obtener_todos_paginado(
            conn,
            "Invoices",
            {
                "$filter": f"CardCode eq '{CLIENTE}' and DocumentStatus eq 'bost_Open'",
                "$select": CAMPOS,
            },
            "DocEntry",
        )
        notas = obtener_todos_paginado(
            conn,
            "CreditNotes",
            {
                "$filter": (
                    f"CardCode eq '{CLIENTE}' and DocumentStatus eq 'bost_Open' "
                    "and DocDate ge '2022-01-01'"
                ),
                "$select": CAMPOS,
            },
            "DocEntry",
        )

        log("")
        log(f"   Facturas con estado abierto en SAP : {len(facturas)}")
        log(f"   Notas de credito abiertas (>= 2022): {len(notas)}")

        # ------------------------------------------------------------------
        # 3. Los dos filtros de la gira, aplicados por separado
        # ------------------------------------------------------------------
        titulo("PASO 3 - Los dos filtros de la gira, uno por uno")

        vendedor_general = -1
        bp = conn.get(f"BusinessPartners('{CLIENTE}')", {"$select": "SalesPersonCode"})
        if bp:
            vendedor_general = bp.get("SalesPersonCode", -1)

        log("")
        log(f"   SalesPersonCode de la ficha del cliente: {vendedor_general}")
        log("   (es el vendedor por defecto cuando una direccion no tiene U_CODV)")

        saldo_cero_fac = 0
        saldo_cero_nc = 0
        con_saldo = []

        for f in facturas:
            doc = procesar_documento(f, "invoice")
            if doc is None:
                saldo_cero_fac += 1
                continue
            doc["vendedor_final"] = mapeo.get(doc["destino"], vendedor_general)
            con_saldo.append(doc)

        for n in notas:
            doc = procesar_documento(n, "creditnote")
            if doc is None:
                saldo_cero_nc += 1
                continue
            doc["vendedor_final"] = mapeo.get(doc["destino"], vendedor_general)
            con_saldo.append(doc)

        log("")
        log("   FILTRO 1 - saldo despreciable, abs(saldo) < 0.005:")
        log(f"      facturas descartadas         : {saldo_cero_fac}")
        log(f"      notas de credito descartadas : {saldo_cero_nc}")
        log(f"      quedan con saldo real        : {len(con_saldo)}")

        del_agente = [d for d in con_saldo if str(d["vendedor_final"]) == str(AGENTE)]
        de_otros = [d for d in con_saldo if str(d["vendedor_final"]) != str(AGENTE)]

        log("")
        log(f"   FILTRO 2 - ruteo al vendedor {AGENTE}:")
        log(f"      del agente {AGENTE}, van al PDF : {len(del_agente)}")
        log(f"      de otros vendedores, omitidos : {len(de_otros)}")

        if de_otros:
            reparto = defaultdict(int)
            for d in de_otros:
                reparto[d["vendedor_final"]] += 1
            log("")
            log("      Reparto de los omitidos:")
            for vendedor in sorted(reparto, key=lambda v: -reparto[v]):
                destinos = sorted(
                    {d["destino"] for d in de_otros if d["vendedor_final"] == vendedor}
                )
                log(
                    f"         vendedor {vendedor}: {reparto[vendedor]} docs"
                    f"   ({', '.join(destinos) or 'sin destino'})"
                )

        # ------------------------------------------------------------------
        # 4. Cuadre
        # ------------------------------------------------------------------
        titulo("PASO 4 - Cuadre de la diferencia")

        con_saldo_hoy = len(facturas) - saldo_cero_fac
        pagadas = CONTEO_ANTERIOR - con_saldo_hoy

        log("")
        log(f"   Facturas con saldo el 19/09, todos los vendedores : {CONTEO_ANTERIOR}")
        log(f"   Facturas con saldo hoy, todos los vendedores      : {con_saldo_hoy}")
        log(f"   -> pagadas o cerradas en 8 dias                   : {pagadas}")
        log("")
        log(f"   De las de hoy, ruteadas al vendedor {AGENTE}           : {len(del_agente)}")
        log(f"   Filas de documento contadas en el PDF del 27/09   : {CONTEO_PDF}")

        log("")
        if len(del_agente) == CONTEO_PDF:
            log("   [OK] CUADRA EXACTO. El PDF trae lo que debe traer:")
            log(
                f"        {CONTEO_ANTERIOR} - {pagadas} pagadas"
                f" - {len(de_otros)} de otros vendedores = {CONTEO_PDF}"
            )
        else:
            log(f"   [REVISAR] El calculo da {len(del_agente)} y el PDF tiene {CONTEO_PDF}.")
            log(f"        Diferencia sin explicar: {abs(len(del_agente) - CONTEO_PDF)} documentos.")
            log("        Nota: el PDF puede incluir lineas de saldo a favor (tipo PR),")
            log("        que este script no consulta. Revisar si la diferencia va por ahi.")

        crc = sum(d["saldo"] for d in del_agente if d["moneda"] == "CRC")
        usd = sum(d["saldo"] for d in del_agente if d["moneda"] == "USD")
        log("")
        log(f"   Saldo de los documentos del vendedor {AGENTE}:")
        log(f"      CRC {crc:>16,.2f}")
        log(f"      USD {usd:>16,.2f}")
        log("   Encabezado del PDF generado:  CRC 286,223.02  |  USD 11,484.52")
        log("   (los montos del PDF no incluyen saldos a favor tipo PR)")

    finally:
        conn.logout()
        log("")
        log(f"Duracion: {(datetime.now() - inicio).seconds}s")
        guardar()


if __name__ == "__main__":
    main()
