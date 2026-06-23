"""
investigar_descuentos_v2.py
Compara qué devuelve SAP para los clientes que salieron "chicos" en el cache.
"""

import sys, os, uuid, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def ejecutar_sql_sl(conn, sql):
    code = f"QU_PR_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url, json={"SqlCode": code, "SqlName": "Inv", "SqlText": sql}
    )
    if resp.status_code not in (200, 201):
        print(f"❌ {resp.text}")
        return []
    res = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{url}('{code}')")
    return res.get("value", []) if res else []


def investigar():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    # Los códigos que salieron "chicos" en el cache de producción
    sospechosos = ["C0181", "CC100174", "CC7806", "CC100109", "CC5657"]

    try:
        for code in sospechosos:
            print("\n" + "=" * 60)
            print(f"CLIENTE: {code}")
            print("=" * 60)
            sql = f"""
                SELECT 
                    T1."DiscPrcnt" AS "Descuento", 
                    COUNT(T1."DiscPrcnt") AS "Freq"
                FROM "OINV" T0
                INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
                WHERE T0."CardCode" = '{code}'
                  AND T1."DiscPrcnt" > 0 
                  AND T0."DocDate" >= '20220101'
                GROUP BY T1."DiscPrcnt"
            """
            filas = ejecutar_sql_sl(conn, sql)
            filas.sort(key=lambda x: int(x.get("Freq", 0)), reverse=True)
            print(json.dumps(filas, indent=2))
    finally:
        conn.logout()


if __name__ == "__main__":
    investigar()
