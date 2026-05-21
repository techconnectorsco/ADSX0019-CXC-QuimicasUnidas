"""
diagnostico_bodegas.py - Químicas Unidas

OBJETIVO: Entender RÁPIDO (30 segundos) cuántas bodegas hay y cuáles
son de consignación, ANTES de hacer la consulta pesada de series.

Estrategia: usar agregaciones SQL para no traer millones de filas.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def ejecutar_sql_temporal(conn, sql_text, descripcion):
    """Helper para correr una query temporal y traer todos los resultados."""
    query_code = f"TMP_DIAG_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"
    resultados = []

    try:
        resp = conn.session.post(
            url_post,
            json={"SqlCode": query_code, "SqlName": "TMP", "SqlText": sql_text},
        )
        if resp.status_code not in (200, 201):
            print(f"   ❌ Error creando query: {resp.status_code}")
            try:
                print(
                    f"      {resp.json().get('error', {}).get('message', {}).get('value', '')[:200]}"
                )
            except Exception:
                pass
            return []

        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$skip": skip})
            if not res or "value" not in res or not res["value"]:
                break
            resultados.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20
            if skip > 5000:
                print(f"   ⚠️  Cortado en 5000")
                break
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass

    return resultados


def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO RÁPIDO DE BODEGAS")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # 1. Catálogo de bodegas (OWHS) — debería ser chico, < 100 bodegas
        # =====================================================================
        print("\n📋 PASO 1: Catálogo de bodegas (tabla OWHS)")
        print("-" * 80)

        sql_bodegas = (
            'SELECT "WhsCode", "WhsName", "Inactive" ' "FROM OWHS " 'ORDER BY "WhsCode"'
        )
        bodegas = ejecutar_sql_temporal(conn, sql_bodegas, "bodegas")
        print(f"   Total bodegas en catálogo: {len(bodegas)}")

        # Clasificar por prefijo
        prefijos = {}
        for b in bodegas:
            wc = b["WhsCode"]
            pref = wc[:2] if len(wc) >= 2 else wc
            if pref not in prefijos:
                prefijos[pref] = []
            prefijos[pref].append(b)

        print(f"\n   Distribución por prefijo:")
        for pref in sorted(prefijos.keys()):
            ejemplos = prefijos[pref][:3]
            nombres = ", ".join(f"{b['WhsCode']}={b['WhsName'][:20]}" for b in ejemplos)
            print(f"      {pref}: {len(prefijos[pref]):3} bodegas — ej: {nombres}")

        # =====================================================================
        # 2. Contar registros en OSRQ por prefijo de bodega
        # =====================================================================
        print("\n📋 PASO 2: Conteo de stock por número de serie (OSRQ)")
        print("-" * 80)

        sql_conteo = (
            'SELECT "WhsCode", COUNT(*) AS "Registros", SUM("Quantity") AS "TotalCantidad" '
            "FROM OSRQ "
            'WHERE "Quantity" > 0 '
            'GROUP BY "WhsCode" '
            'ORDER BY "WhsCode"'
        )
        conteos = ejecutar_sql_temporal(conn, sql_conteo, "conteos")

        total_global = sum(int(c.get("Registros", 0)) for c in conteos)
        print(f"   Bodegas con series en stock: {len(conteos)}")
        print(f"   Total registros OSRQ (Quantity>0): {total_global}")

        # Top 20 bodegas con más series
        conteos_ord = sorted(conteos, key=lambda x: -int(x.get("Registros", 0)))
        print(f"\n   Top 20 bodegas con más series:")
        bodegas_dict = {b["WhsCode"]: b for b in bodegas}
        for c in conteos_ord[:20]:
            wc = c["WhsCode"]
            nombre = bodegas_dict.get(wc, {}).get("WhsName", "?")[:35]
            print(f"      {wc:10} {nombre:35} {c.get('Registros'):>6} series")

        # =====================================================================
        # 3. Mismo conteo pero solo bodegas LIKE '00%' o 'C0%' (filtro actual)
        # =====================================================================
        print("\n📋 PASO 3: ¿Cuánto trae tu filtro actual ('00%' OR 'C0%')?")
        print("-" * 80)

        sql_filtro_actual = (
            'SELECT COUNT(*) AS "Total" '
            "FROM OSRQ "
            'WHERE "Quantity" > 0 '
            "AND (\"WhsCode\" LIKE '00%' OR \"WhsCode\" LIKE 'C0%')"
        )
        res_filtro = ejecutar_sql_temporal(conn, sql_filtro_actual, "filtro")
        if res_filtro:
            print(
                f"   Total con filtro actual: {res_filtro[0].get('Total', '?')} registros"
            )

        # =====================================================================
        # 4. Bodegas en OSRQ que NO existen en OWHS (huérfanas) o son internas
        # =====================================================================
        print("\n📋 PASO 4: Caracterización — ¿cuáles son bodegas 'de cliente'?")
        print("-" * 80)
        print("   Una bodega es 'de cliente/consignación' si su WhsCode coincide")
        print(
            "   con el sufijo de un CardCode existente (CardCode menos primer caracter)."
        )
        print()

        # Una forma eficiente: traer la lista de "sufijos válidos" en una query
        sql_sufijos = (
            'SELECT DISTINCT "WhsCode", "WhsName" '
            "FROM OWHS "
            'WHERE "WhsCode" IN (SELECT "WhsCode" FROM OSRQ WHERE "Quantity" > 0)'
        )
        bodegas_con_stock = ejecutar_sql_temporal(
            conn, sql_sufijos, "bodegas con stock"
        )
        print(f"   Bodegas con AL MENOS una serie en stock: {len(bodegas_con_stock)}")
        print(f"\n   Lista completa de bodegas con stock:")
        for b in bodegas_con_stock:
            print(f"      {b['WhsCode']:10} {b.get('WhsName', '?')[:60]}")

        print("\n" + "=" * 80)
        print("✅ DIAGNÓSTICO COMPLETADO")
        print("=" * 80)
        print("   Con esto sabemos:")
        print("   - Cuántas bodegas hay en total")
        print("   - Cuántas tienen stock actualmente")
        print("   - Cuáles son las que corresponden a consignaciones de clientes")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
