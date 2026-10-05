import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import (
    ServiceLayerConnection,
    ejecutar_sql_sl,
)


conn = ServiceLayerConnection(use_test_db=False)
if conn.login():
    sql = """
        SELECT T0."CardCode", T1."DiscPrcnt" AS "Descuento", COUNT(T1."DiscPrcnt") AS "Freq"
        FROM "OINV" T0 INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
        WHERE T1."DiscPrcnt" > 0 AND T0."DocDate" >= '20220101'
        GROUP BY T0."CardCode", T1."DiscPrcnt"
    """
    t = time.time()
    filas = ejecutar_sql_sl(conn, sql)
    print(f"Total filas: {len(filas)} en {time.time()-t:.1f}s")
    c0181 = [r for r in filas if str(r.get("CardCode")) == "C0181"]
    print(f"C0181: {c0181}")
    conn.logout()
