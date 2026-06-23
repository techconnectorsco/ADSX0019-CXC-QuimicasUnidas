"""
generar_descuentos.py - Químicas Unidas
Precalcula el descuento más frecuente (moda) de cada cliente desde el historial
de facturas y lo guarda en descuentos.json (raíz del proyecto).

USO MANUAL: correr cuando se quiera refrescar la tabla de descuentos.
NO se ejecuta los martes con agentes.py.
"""

import sys, os, uuid, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

ARCHIVO_SALIDA = "descuentos.json"


def ejecutar_sql_sl(conn, sql):
    code = f"QU_DESC_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url, json={"SqlCode": code, "SqlName": "Descuentos", "SqlText": sql}
    )
    if resp.status_code not in (200, 201):
        return []
    res = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{url}('{code}')")
    return res.get("value", []) if res else []


def obtener_clientes(conn):
    """Lista de CardCode de clientes (mismo filtro que usa agentes.py)."""
    todos = []
    skip = 0
    filtro = (
        "CardType eq 'cCustomer' and (CurrentAccountBalance ne 0 or FatherCard ne null)"
    )
    while True:
        res = conn.get(
            "BusinessPartners",
            {
                "$filter": filtro,
                "$select": "CardCode",
                "$orderby": "CardCode",
                "$top": 20,
                "$skip": skip,
            },
        )
        page = res.get("value", []) if res else []
        if not page:
            break
        todos.extend([c["CardCode"] for c in page if c.get("CardCode")])
        if len(page) < 20:
            break
        skip += 20
    return todos


def moda_descuento(conn, card_code):
    """Descuento más frecuente de UN cliente. Consulta chica = rápida."""
    sql = f"""
        SELECT T1."DiscPrcnt" AS "Descuento", COUNT(T1."DiscPrcnt") AS "Freq"
        FROM "OINV" T0
        INNER JOIN "INV1" T1 ON T0."DocEntry" = T1."DocEntry"
        WHERE T0."CardCode" = '{card_code}'
          AND T1."DiscPrcnt" > 0
          AND T0."DocDate" >= '20220101'
        GROUP BY T1."DiscPrcnt"
    """
    filas = ejecutar_sql_sl(conn, sql)
    if not filas:
        return 0.0
    filas.sort(
        key=lambda x: (int(x.get("Freq", 0)), float(x.get("Descuento", 0))),
        reverse=True,
    )
    return float(filas[0].get("Descuento", 0) or 0)


def main():
    print("=" * 60)
    print("🧮 PRECÁLCULO DE DESCUENTOS POR CLIENTE")
    print("=" * 60)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    inicio = time.time()
    try:
        clientes = obtener_clientes(conn)
        total = len(clientes)
        print(f"   Clientes a procesar: {total}\n")

        descuentos = {}
        for i, code in enumerate(clientes, 1):
            descuentos[code] = moda_descuento(conn, code)
            print(f"   ⏳ {i}/{total}  {code} → {descuentos[code]}%", end="\r")

        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARCHIVO_SALIDA)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(descuentos, f, indent=2, ensure_ascii=False)

        con_desc = sum(1 for v in descuentos.values() if v > 0)
        print(f"\n\n✅ Guardado: {ruta}")
        print(f"   Total clientes: {total}")
        print(f"   Con descuento (>0): {con_desc}")
        print(f"   Tiempo: {time.time() - inicio:.1f}s")
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
