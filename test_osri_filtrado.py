"""
test_osri_filtrado.py - Químicas Unidas

Test de 10 segundos: confirma que OSRI sí se puede consultar vía /SQLQueries
SIEMPRE Y CUANDO tenga WHERE específico (como hace el query bodega_series).
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def probar_sql(conn, descripcion, sql):
    """Crea una query temporal, la ejecuta y reporta."""
    query_code = f"TST_OSRI_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"

    print(f"\n🧪 {descripcion}")
    print(f"   SQL: {sql[:120]}{'...' if len(sql) > 120 else ''}")

    try:
        resp = conn.session.post(
            url_post, json={"SqlCode": query_code, "SqlName": "TST", "SqlText": sql}
        )
        if resp.status_code not in (200, 201):
            err = ""
            try:
                err = (
                    resp.json()
                    .get("error", {})
                    .get("message", {})
                    .get("value", "")[:200]
                )
            except Exception:
                err = resp.text[:200]
            print(f"   ❌ Falló al crear ({resp.status_code}): {err}")
            return False

        # Ejecutar y traer primeras filas
        res = conn.get(f"SQLQueries('{query_code}')/List", {"$top": 5})
        if res and "value" in res:
            n = len(res["value"])
            print(f"   ✅ OK — devolvió {n} fila(s) (top 5)")
            if res["value"]:
                print(f"      Campos: {list(res['value'][0].keys())}")
                print(f"      Ejemplo: {res['value'][0]}")
            return True
        else:
            print(f"   ⚠️  Creó pero ejecución devolvió vacío o error")
            return False
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    print("=" * 80)
    print("🔍 ¿Funciona OSRI con WHERE específico?")
    print("=" * 80)

    try:
        # Test 1: query exacto de Tania (bodega_series)
        # Usamos una bodega que sabemos que existe (0180 = EL COLONO ZONA NORTE)
        sql1 = (
            'SELECT T0."ItemCode", T0."ItemName", T0."SuppSerial", '
            'T0."Status", T0."WhsCode" '
            "FROM OSRI T0 "
            'WHERE T0."WhsCode"=\'0180\' AND T0."Status"=0'
        )
        ok1 = probar_sql(
            conn, "Test 1: bodega_series literal (WhsCode='0180', Status=0)", sql1
        )

        # Test 2: variante con LIKE en vez de igualdad
        sql2 = (
            'SELECT COUNT(*) AS "Total" '
            "FROM OSRI T0 "
            'WHERE T0."WhsCode"=\'0180\' AND T0."Status"=0'
        )
        ok2 = probar_sql(conn, "Test 2: COUNT para ver volumen de C0180", sql2)

        # Test 3: con IntrSerial (por si SuppSerial está vacío en algunos)
        sql3 = (
            'SELECT T0."ItemCode", T0."ItemName", '
            'T0."IntrSerial", T0."SuppSerial", '
            'T0."Status", T0."WhsCode" '
            "FROM OSRI T0 "
            'WHERE T0."WhsCode"=\'0180\' AND T0."Status"=0'
        )
        ok3 = probar_sql(conn, "Test 3: agregando IntrSerial al SELECT", sql3)

        # Test 4: con JOIN a OCRD para traer zona en una sola consulta
        sql4 = (
            'SELECT T0."ItemCode", T0."ItemName", T0."SuppSerial", '
            'T0."WhsCode", T1."CardCode", T1."CardName", T1."U_ZGIRA", '
            'T1."SlpCode", T1."FatherCard" '
            "FROM OSRI T0 "
            'INNER JOIN OCRD T1 ON T1."CardCode"=CONCAT(\'C\', T0."WhsCode") '
            'WHERE T0."WhsCode"=\'0180\' AND T0."Status"=0'
        )
        ok4 = probar_sql(
            conn, "Test 4: JOIN con OCRD para traer zona/agente/padre", sql4
        )

        print("\n" + "=" * 80)
        print("📋 RESUMEN")
        print("=" * 80)
        print(f"   {'✅' if ok1 else '❌'} Test 1 — query bodega_series literal")
        print(f"   {'✅' if ok2 else '❌'} Test 2 — COUNT para volumen")
        print(f"   {'✅' if ok3 else '❌'} Test 3 — con IntrSerial")
        print(f"   {'✅' if ok4 else '❌'} Test 4 — JOIN OSRI + OCRD (ideal)")

        if ok4:
            print(
                "\n   🎯 ¡PERFECTO! Podemos hacer todo en una sola consulta por bodega."
            )
        elif ok1:
            print("\n   ✅ OSRI funciona. Cruzaremos con OCRD vía OData/Python.")
        else:
            print("\n   ⚠️  OSRI bloqueada. Hay que repensar.")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
