"""
validar_traslados.py - Químicas Unidas

OBJETIVO: Validar en ~1 minuto que filtrar /StockTransfers por
DocumentStatus=Open + ToWarehouse en bodegas de consignación da números
razonables (cientos, no decenas de miles).

NO genera PDFs, NO envía correos. Solo cuenta y muestra ejemplos.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

# Bodegas internas conocidas (NO de consignación)
INTERNAS = {"-1", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"}


def odata_paginado(conn, entidad, params=None, page_size=500):
    """Paginación rápida con header Prefer."""
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
        if skip > 50000:
            print(f"   ⚠️  Cortado en {skip}")
            break
    return todos


def main():
    print("=" * 80)
    print("🔍 VALIDACIÓN: traslados abiertos hacia bodegas de consignación")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        t0 = time.time()

        # =====================================================================
        # 1. Bodegas de consignación
        # =====================================================================
        print("\n📥 Bodegas...")
        bodegas = odata_paginado(
            conn, "Warehouses", {"$select": "WarehouseCode,WarehouseName"}
        )
        bodegas_cons = [
            b["WarehouseCode"] for b in bodegas if b["WarehouseCode"] not in INTERNAS
        ]
        print(f"   {len(bodegas_cons)} bodegas de consignación")

        # =====================================================================
        # 2. Traslados ABIERTOS hacia esas bodegas
        # =====================================================================
        print("\n📥 StockTransfers abiertos hacia bodegas de consignación...")
        print(f"   Filtro: DocumentStatus=bost_Open AND ToWarehouse en bodegas_cons")

        # OData no permite IN con cientos de valores en URL, lo hacemos en lotes
        traslados_total = []
        LOTE = 30  # 30 bodegas por filtro
        t_inicio = time.time()

        for i in range(0, len(bodegas_cons), LOTE):
            chunk = bodegas_cons[i : i + LOTE]
            condiciones_to = " or ".join(f"ToWarehouse eq '{c}'" for c in chunk)
            filtro = f"DocumentStatus eq 'bost_Open' and ({condiciones_to})"

            params = {
                "$select": "DocEntry,DocNum,DocDate,CardCode,CardName,ToWarehouse,DocumentStatus",
                "$filter": filtro,
            }
            lote_traslados = odata_paginado(conn, "StockTransfers", params)
            traslados_total.extend(lote_traslados)
            print(
                f"   Lote {i//LOTE + 1}/{(len(bodegas_cons)-1)//LOTE + 1}: "
                f"+{len(lote_traslados):4} traslados | acum: {len(traslados_total):5} | "
                f"{time.time()-t_inicio:.1f}s"
            )

        print(f"\n   ✅ Total traslados abiertos: {len(traslados_total)}")

        if not traslados_total:
            print("\n⚠️  Cero traslados. Algo está mal con el filtro.")
            return

        # =====================================================================
        # 3. Análisis rápido por destino
        # =====================================================================
        print("\n📊 Distribución por bodega destino (top 10):")
        print("-" * 80)
        from collections import defaultdict

        por_destino = defaultdict(int)
        for t in traslados_total:
            por_destino[t["ToWarehouse"]] += 1

        bodegas_dict = {
            b["WarehouseCode"]: b.get("WarehouseName", "?") for b in bodegas
        }
        for code, count in sorted(por_destino.items(), key=lambda x: -x[1])[:10]:
            nombre = bodegas_dict.get(code, "?")
            print(f"   {code:10} {nombre[:50]:50} {count:5} traslados")

        # =====================================================================
        # 4. Tomar 1 traslado y descargarlo COMPLETO para ver sus series
        # =====================================================================
        print("\n📋 Inspección de 1 traslado completo (para ver SerialNumbers):")
        print("-" * 80)

        muestra = traslados_total[0]
        doc_entry = muestra["DocEntry"]
        print(
            f"   DocEntry={doc_entry}, ToWarehouse={muestra['ToWarehouse']}, "
            f"Cliente={muestra.get('CardCode')}"
        )

        # Traer el traslado completo
        res_http = conn.session.get(f"{conn.base_url}/StockTransfers({doc_entry})")
        if res_http.status_code == 200:
            t_full = res_http.json()
            lineas = t_full.get("StockTransferLines", [])
            print(f"   Líneas: {len(lineas)}")

            con_series = 0
            total_series_doc = 0
            for ln in lineas:
                series_ln = ln.get("SerialNumbers", [])
                if series_ln:
                    con_series += 1
                    total_series_doc += len(series_ln)

            print(f"   Líneas con series: {con_series}/{len(lineas)}")
            print(f"   Total series en este documento: {total_series_doc}")

            # Mostrar una línea con series si existe
            for ln in lineas:
                if ln.get("SerialNumbers"):
                    print(f"\n   Ejemplo de línea con series:")
                    print(f"      ItemCode: {ln['ItemCode']}")
                    print(f"      ItemDescription: {ln.get('ItemDescription', '?')}")
                    print(f"      Quantity: {ln.get('Quantity')}")
                    print(f"      WarehouseCode: {ln.get('WarehouseCode')}")
                    print(f"      Series (primeras 3 de {len(ln['SerialNumbers'])}):")
                    for s in ln["SerialNumbers"][:3]:
                        print(f"         {s}")
                    break
            else:
                print(
                    "\n   ⚠️  Ninguna línea de este traslado tiene series (es de items no serializados)"
                )
        else:
            print(f"   ❌ Error trayendo detalle: {res_http.status_code}")

        # =====================================================================
        # 5. Estimación del volumen final
        # =====================================================================
        print("\n📊 Estimación de volumen total:")
        print("-" * 80)
        print(
            f"   Traslados abiertos a bodegas de consignación: {len(traslados_total)}"
        )
        print(f"   Si en promedio cada uno tiene 5-15 series de items serializados,")
        print(
            f"   el total final estaría entre {len(traslados_total)*5} y {len(traslados_total)*15} series."
        )
        print(f"   (Comparar con los 137,543 incorrectos de antes)")

        print(f"\n⏱️  Tiempo total: {time.time()-t0:.1f}s")
        print("\n" + "=" * 80)
        print("✅ VALIDACIÓN COMPLETADA")
        print("=" * 80)

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
