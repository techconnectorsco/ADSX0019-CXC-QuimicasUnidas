"""
investigar_v10.py - Químicas Unidas

Tania encontró una SQLQuery existente en SAP:
"Pagos recibidos por rango de fechas" que apunta a tabla ORCT.

Probamos:
1. Listar TODAS las SQLQueries con todos sus campos (sin $select restrictivo).
2. Ejecutar la query de pagos para confirmar que el mecanismo funciona desde Service Layer.

Si funciona → pedimos a Novitec crear UNA query del saldo del cliente.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # 1. Listar TODAS las SQLQueries sin restricción
        print("=" * 90)
        print("1. TODAS LAS SQLQueries DISPONIBLES (sin $select para ver todo)")
        print("=" * 90)

        resp = conn.get("SQLQueries", {"$top": 100})
        if not resp or not resp.get("value"):
            print("Sin resultados o endpoint no devuelve nada")
            return

        queries = resp["value"]
        print(f"Total queries: {len(queries)}\n")

        for q in queries:
            print("--- Query ---")
            for k in sorted(q.keys()):
                v = q[k]
                if v in (None, "", 0):
                    continue
                # Truncar SQL muy largo
                if isinstance(v, str) and len(v) > 200:
                    v = v[:200] + "... (truncado)"
                print(f"   {k}: {v}")
            print()

        # 2. Si hay queries, intentar ejecutar la primera con un POST a SQLQueries('codigo')/List
        if queries:
            primera = queries[0]
            sql_code = primera.get("SqlCode")
            print("\n" + "=" * 90)
            print(f"2. INTENTAR EJECUTAR LA QUERY '{sql_code}'")
            print("=" * 90)

            if sql_code:
                # El endpoint estándar para ejecutar es SQLQueries('XXX')/List
                # Probamos como GET
                print(f"\n>> Intento A: GET SQLQueries('{sql_code}')/List")
                r = conn.get(f"SQLQueries('{sql_code}')/List", {})
                if r is not None:
                    print(f"   Respuesta: {str(r)[:500]}")
                else:
                    print("   ❌ No funcionó como GET")

                # Probamos otra variante
                print(f"\n>> Intento B: GET SQLQueries('{sql_code}')")
                r = conn.get(f"SQLQueries('{sql_code}')", {})
                if r is not None:
                    print(f"   ✅ Detalle de la query:")
                    for k in sorted(r.keys()):
                        v = r[k]
                        if v in (None, "", 0):
                            continue
                        if isinstance(v, str) and len(v) > 300:
                            v = v[:300] + "..."
                        print(f"      {k}: {v}")
                else:
                    print("   ❌")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
