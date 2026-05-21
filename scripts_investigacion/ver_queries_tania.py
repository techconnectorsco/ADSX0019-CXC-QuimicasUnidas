"""
ver_queries_tania.py - Químicas Unidas

Extrae el SQL completo de los queries que Tania confirmó como "fuente de verdad"
para el reporte de consignaciones:

  1. bodega_series        (categoría INVENTARIOS)
  2. REVISION_CLIENTE     (categoría SOLICITUD_INVENTARIO DSM)

Y mientras estamos en eso, también extraemos otros que pueden tener pistas:
  - SERIES POR ENTREGA
  - SERIES POR DOCUMENTO
  - CONSIGNACIONES TOTAL QU
  - CONSIGNACIONES TOTAL QU / SN
  - REPORTE CONSIGNACIONES

NO ejecuta nada, solo lee los SQL del Query Manager y los imprime.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

# Nombres de los queries que queremos extraer (insensibles a may/min)
NOMBRES_BUSCADOS = [
    "bodega_series",
    "REVISION_CLIENTE",
    "SERIES POR ENTREGA",
    "SERIES POR DOCUMENTO",
    "CONSIGNACIONES TOTAL QU",
    "CONSIGNACIONES TOTAL QU / SN",
    "REPORTE CONSIGNACIONES",
    "REPORTE CONSIGNACIONES V2",
    "inventario_entre_bodegas",  # ya lo conocíamos, por completitud
]


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    print("=" * 80)
    print("🔍 EXTRACCIÓN DE QUERIES DEL QUERY MANAGER")
    print("=" * 80)

    # Convertimos a lower para búsqueda
    buscados_lower = {n.lower(): n for n in NOMBRES_BUSCADOS}
    encontrados = {}

    try:
        skip = 0
        total_revisado = 0

        while True:
            res = conn.get("UserQueries", {"$skip": skip})

            if not res or "value" not in res or len(res["value"]) == 0:
                break

            for q in res["value"]:
                total_revisado += 1
                nombre = q.get("QueryDescription", "")
                nombre_lower = nombre.lower()

                # ¿Coincide con alguno de los buscados?
                if nombre_lower in buscados_lower:
                    key = nombre_lower
                    encontrados[key] = q

            if len(encontrados) == len(buscados_lower):
                break  # ya tenemos todos, paramos

            if len(res["value"]) < 20:
                break

            skip += 20
            if skip > 5000:
                break

        print(f"\n📊 Revisé {total_revisado} queries en total.")
        print(f"   Encontrados: {len(encontrados)} de {len(buscados_lower)}\n")

        # =====================================================================
        # Imprimir cada query encontrado con su SQL completo
        # =====================================================================
        for buscado_lower, buscado_original in buscados_lower.items():
            print("\n" + "=" * 80)
            if buscado_lower not in encontrados:
                print(f"❌ NO ENCONTRADO: {buscado_original}")
                continue

            q = encontrados[buscado_lower]
            print(f"✅ ENCONTRADO: {q.get('QueryDescription')}")
            print(f"   InternalKey:   {q.get('InternalKey')}")
            print(f"   Categoría:     {q.get('QueryCategory')}")
            print(f"   Tipo:          {q.get('QueryType')}")
            print("=" * 80)
            sql = q.get("Query", "") or q.get("QueryString", "")
            print(sql)
            print()

        # =====================================================================
        # Reporte final
        # =====================================================================
        print("\n" + "=" * 80)
        print("📋 RESUMEN")
        print("=" * 80)
        for buscado_lower, buscado_original in buscados_lower.items():
            estado = "✅" if buscado_lower in encontrados else "❌"
            print(f"   {estado} {buscado_original}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
