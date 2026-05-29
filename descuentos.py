"""
investigar_descuentos.py
Explorador de Descuentos basado en el Historial de Facturas (INV1)
"""

import sys
import os
import uuid
import json

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def ejecutar_sql_sl(conn: ServiceLayerConnection, sql: str) -> list:
    code = f"QU_PR_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"

    resp = conn.session.post(
        url,
        json={"SqlCode": code, "SqlName": "Query Explorador Invoices", "SqlText": sql},
    )

    if resp.status_code not in (200, 201):
        print(f"❌ Error SQL: {resp.text}")
        return []

    res = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{url}('{code}')")
    return res.get("value", []) if res else []


def investigar():
    print("=" * 70)
    print("🕵️‍♂️ EXPLORADOR EMPÍRICO - DESCUENTOS REALES FACTURADOS (C0224)")
    print("=" * 70)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        print("\n🔍 Analizando las facturas emitidas a C0224 desde el 2024...")

        # Le pedimos a SAP que cuente cuántas veces se ha aplicado cada descuento en la realidad
        sql = """
            SELECT 
                T1."DiscPrcnt" AS "Descuento", 
                COUNT(T1."DiscPrcnt") AS "Frecuencia_Uso"
            FROM "OINV" T0
            INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
            WHERE T0."CardCode" = 'C0224' 
              AND T1."DiscPrcnt" > 0 
              AND T0."DocDate" >= '20240101'
            GROUP BY T1."DiscPrcnt"
        """

        resultados = ejecutar_sql_sl(conn, sql)

        if resultados:
            # ORDENAMOS USANDO PYTHON (De mayor a menor frecuencia)
            resultados.sort(key=lambda x: int(x.get("Frecuencia_Uso", 0)), reverse=True)

            print(json.dumps(resultados, indent=4))
            ganador = resultados[0]
            print(
                f"\n🏆 EL DESCUENTO GANADOR ES: {ganador['Descuento']}% (Usado {ganador['Frecuencia_Uso']} veces)"
            )
        else:
            print(
                "\n⚠️ No se encontraron descuentos aplicados en facturas recientes para este cliente."
            )
        print(json.dumps(resultados, indent=4))

        if resultados:
            ganador = resultados[0]
            print(
                f"\n🏆 EL DESCUENTO GANADOR ES: {ganador['Descuento']}% (Usado {ganador['Frecuencia_Uso']} veces)"
            )
        else:
            print(
                "\n⚠️ No se encontraron descuentos aplicados en facturas recientes para este cliente."
            )

    finally:
        conn.logout()
        print("\n✅ Exploración terminada.")


if __name__ == "__main__":
    investigar()
