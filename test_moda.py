import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import (
    ServiceLayerConnection,
    ejecutar_sql_sl,
)


conn = ServiceLayerConnection(use_test_db=False)
if conn.login():
    sql = """
        SELECT "CardCode", "DiscPrcnt"
        FROM (
            SELECT
                T0."CardCode",
                T1."DiscPrcnt",
                ROW_NUMBER() OVER (
                    PARTITION BY T0."CardCode"
                    ORDER BY COUNT(T1."DiscPrcnt") DESC
                ) AS rn
            FROM "OINV" T0
            INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
            WHERE T1."DiscPrcnt" > 0
              AND T0."DocDate" >= '20220101'
            GROUP BY T0."CardCode", T1."DiscPrcnt"
        )
        WHERE rn = 1
    """
    t = time.time()
    filas = ejecutar_sql_sl(conn, sql)
    if filas is None:
        print(
            "→ La subconsulta NO funciona en este Service Layer. Vamos a la Opción 1 (por cliente)."
        )
    else:
        print(f"Total filas (1 por cliente): {len(filas)} en {time.time()-t:.1f}s")
        c0181 = [r for r in filas if str(r.get("CardCode")) == "C0181"]
        print(f"C0181: {c0181}")
        print(f"Muestra: {filas[:5]}")
    conn.logout()
