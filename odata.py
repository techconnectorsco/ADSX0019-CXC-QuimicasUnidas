"""
diagnostico_odata.py - Químicas Unidas

OBJETIVO: Usar SOLO endpoints OData estándar (lo que sabemos que funciona)
para mapear bodegas. Sin SQL crudo pesado, sin OSRQ/OWHS directo.

Tiempo esperado: 30-60 segundos.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO VÍA ODATA (sin SQL crudo pesado)")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # 1. Endpoint Warehouses (equivalente OData de OWHS)
        # =====================================================================
        print("\n📋 PASO 1: Probando endpoint /Warehouses")
        print("-" * 80)

        bodegas = []
        skip = 0
        intento_ok = False

        while True:
            res = conn.get(
                "Warehouses",
                {"$select": "WarehouseCode,WarehouseName,Inactive", "$skip": skip},
            )
            if not res or "value" not in res:
                # ¿Falló? Reportar y romper
                print(f"   ❌ Respuesta inesperada en skip={skip}: {res}")
                break
            if not res["value"]:
                if skip == 0:
                    print("   ⚠️  /Warehouses devolvió lista vacía")
                break
            intento_ok = True
            bodegas.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20

        if intento_ok:
            print(f"   ✅ Total bodegas obtenidas: {len(bodegas)}")
            print(f"\n   Lista completa:")
            for b in bodegas:
                code = b.get("WarehouseCode", "?")
                name = b.get("WarehouseName", "?")
                inact = b.get("Inactive", "?")
                print(
                    f"      {code:10} {name[:50]:50} {'INACTIVA' if inact == 'tYES' else 'activa'}"
                )

        # =====================================================================
        # 2. Endpoint SerialNumberDetails (equivalente de OSRN)
        # =====================================================================
        print("\n📋 PASO 2: Probando endpoint /SerialNumberDetails (top 5)")
        print("-" * 80)

        try:
            sn = conn.get("SerialNumberDetails", {"$top": 5})
            if sn and "value" in sn and sn["value"]:
                print(f"   ✅ /SerialNumberDetails accesible")
                print(f"   Campos disponibles: {list(sn['value'][0].keys())[:15]}")
                print(f"   Ejemplo:")
                for k, v in list(sn["value"][0].items())[:10]:
                    print(f"      {k}: {v}")
            else:
                print(f"   ⚠️  Devuelve vacío")
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:200]}")

        # =====================================================================
        # 3. ItemWarehouseInfoCollection — stock por bodega vía Items
        # =====================================================================
        print("\n📋 PASO 3: Stock por bodega vía Items (un item de muestra)")
        print("-" * 80)

        try:
            # Traer un item con stock para inspeccionar su estructura
            items = conn.get(
                "Items",
                {
                    "$top": 1,
                    "$filter": "QuantityOnStock gt 0",
                    "$select": "ItemCode,ItemName,QuantityOnStock,ItemWarehouseInfoCollection",
                },
            )
            if items and "value" in items and items["value"]:
                item = items["value"][0]
                print(
                    f"   ✅ Item de muestra: {item.get('ItemCode')} - {item.get('ItemName', '')[:40]}"
                )
                print(f"   Stock total: {item.get('QuantityOnStock')}")
                whs_info = item.get("ItemWarehouseInfoCollection", [])
                con_stock = [w for w in whs_info if (w.get("InStock", 0) or 0) > 0]
                print(f"   Bodegas con stock para este item: {len(con_stock)}")
                for w in con_stock[:10]:
                    print(
                        f"      {w.get('WarehouseCode'):10} InStock={w.get('InStock')}"
                    )
            else:
                print(f"   ⚠️  No hay items con stock")
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:200]}")

        print("\n" + "=" * 80)
        print("✅ DIAGNÓSTICO COMPLETADO")
        print("=" * 80)
        print("\n   Si /Warehouses funcionó, ya tenemos el universo de bodegas.")
        print("   Vamos a poder filtrar mejor y evitar el cuelgue de OSRQ.")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
