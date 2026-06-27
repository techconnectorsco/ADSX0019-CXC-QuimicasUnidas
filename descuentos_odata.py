"""
investigar_descuento_odata.py - Químicas Unidas
Intenta leer los grupos de descuento de C0224 por OData (Service Layer),
sin tocar las tablas crudas OEDG/EDG1 (bloqueadas por Novitec).
NO toca producción. Solo lee.
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

CLIENTE = "C0224"


def probar_get(conn, etiqueta, endpoint, params=None):
    print("\n" + "=" * 60)
    print(f"PRUEBA: {etiqueta}")
    print(f"   GET {endpoint}  params={params}")
    print("=" * 60)
    try:
        r = conn.get(endpoint, params or {})
        if not r:
            print("   ⚠️ Respuesta vacía/None")
            return
        if isinstance(r, dict) and "value" not in r:
            print("   ✅ Respuesta OK. Llaves disponibles en el objeto:")
            print("   " + ", ".join(sorted(r.keys())))
            for k in r.keys():
                if "disc" in k.lower() or "Discount" in k:
                    print(f"\n   >>> {k}:")
                    print(json.dumps(r[k], indent=2, ensure_ascii=False)[:1500])
        else:
            print(f"   ✅ {len(r.get('value', []))} filas:")
            print(json.dumps(r.get("value", [])[:10], indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:300]}")


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ No se pudo conectar")
        return

    try:
        # 1. BP completo: ver TODAS las llaves que expone
        probar_get(
            conn,
            "BusinessPartner C0224 completo (ver llaves de descuento)",
            f"BusinessPartners('{CLIENTE}')",
        )

        # 2. Expandir grupos de descuento
        probar_get(
            conn,
            "BP con $expand BPDiscountGroups",
            f"BusinessPartners('{CLIENTE}')",
            {"$expand": "BPDiscountGroups"},
        )

        # 3. Otro nombre posible
        probar_get(
            conn,
            "BP con $expand DiscountGroups",
            f"BusinessPartners('{CLIENTE}')",
            {"$select": "CardCode,CardName", "$expand": "DiscountGroups"},
        )

    finally:
        conn.logout()
        print("\n✅ Investigación terminada.")


if __name__ == "__main__":
    main()
