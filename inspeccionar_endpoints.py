"""
inspeccionar_endpoints.py - Químicas Unidas

OBJETIVO: Inspeccionar el detalle completo de los endpoints OData clave para
saber qué campos pedir y cómo filtrar.

Tarda ~15 segundos. Trae 2 registros de cada endpoint con TODOS sus campos.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def imprimir_registro(reg, nivel=0, max_lineas_lista=3):
    """Imprime un registro JSON jerarquizado de forma legible."""
    prefix = "  " * nivel
    for k, v in reg.items():
        if isinstance(v, list):
            print(f"{prefix}{k}: [lista de {len(v)} items]")
            for i, item in enumerate(v[:max_lineas_lista]):
                print(f"{prefix}  [{i}]:")
                if isinstance(item, dict):
                    imprimir_registro(item, nivel + 2, max_lineas_lista=1)
                else:
                    print(f"{prefix}    {item}")
            if len(v) > max_lineas_lista:
                print(f"{prefix}  ... y {len(v) - max_lineas_lista} más")
        elif isinstance(v, dict):
            print(f"{prefix}{k}: {{...}}")
            imprimir_registro(v, nivel + 1, max_lineas_lista=1)
        else:
            valor = str(v)[:80] if v is not None else "null"
            print(f"{prefix}{k}: {valor}")


def main():
    print("=" * 80)
    print("🔍 INSPECCIÓN DE ENDPOINTS — campos y estructura")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # 1. /StockTransfers — 1 registro completo
        # =====================================================================
        print("\n" + "=" * 80)
        print("📦 /StockTransfers (1 registro completo)")
        print("=" * 80)
        try:
            res = conn.get("StockTransfers", {"$top": 1})
            if res and "value" in res and res["value"]:
                imprimir_registro(res["value"][0])
            else:
                print("   Sin datos")
        except Exception as e:
            print(f"   ❌ {e}")

        # =====================================================================
        # 2. /SerialNumberDetails — 3 registros completos
        # =====================================================================
        print("\n" + "=" * 80)
        print("🔢 /SerialNumberDetails (3 registros completos)")
        print("=" * 80)
        try:
            res = conn.get("SerialNumberDetails", {"$top": 3})
            if res and "value" in res and res["value"]:
                for i, r in enumerate(res["value"]):
                    print(f"\n--- Registro #{i+1} ---")
                    imprimir_registro(r)
            else:
                print("   Sin datos")
        except Exception as e:
            print(f"   ❌ {e}")

        # =====================================================================
        # 3. Probar filtros típicos en StockTransfers
        # =====================================================================
        print("\n" + "=" * 80)
        print("🧪 Probando filtros en /StockTransfers")
        print("=" * 80)

        # ¿Hay campo ToWarehouse para filtrar destino?
        print("\n   Test 1: Top 2 con $select de campos típicos")
        try:
            res = conn.get(
                "StockTransfers",
                {
                    "$top": 2,
                    "$select": "DocEntry,DocNum,DocDate,CardCode,CardName,FromWarehouse,ToWarehouse,Comments",
                },
            )
            if res and "value" in res:
                for r in res["value"]:
                    print(
                        f"      DocNum={r.get('DocNum')} Fecha={r.get('DocDate','')[:10]} "
                        f"De={r.get('FromWarehouse')} A={r.get('ToWarehouse')} "
                        f"Cli={r.get('CardCode')}"
                    )
        except Exception as e:
            print(f"      ❌ {e}")

        # =====================================================================
        # 4. Filtrar SerialNumberDetails por bodega
        # =====================================================================
        print("\n   Test 2: SerialNumberDetails — ¿se puede filtrar?")
        try:
            # Probar filtros típicos
            res = conn.get(
                "SerialNumberDetails", {"$top": 2, "$filter": "SystemSerialNumber gt 0"}
            )
            if res and "value" in res:
                print(
                    f"      ✅ Filtro por SystemSerialNumber funciona, devolvió {len(res['value'])}"
                )
        except Exception as e:
            print(f"      ❌ {e}")

        print("\n" + "=" * 80)
        print("✅ INSPECCIÓN COMPLETADA")
        print("=" * 80)
        print("\nCon esto vamos a saber EXACTAMENTE qué campos usar para")
        print("filtrar traslados hacia bodegas de consignación y obtener las series.")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
