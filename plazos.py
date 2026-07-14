"""
investigar_plazo.py - Químicas Unidas
Caso Tania: clientes con plazo 45 días en SAP salen como 30 en las giras.
Muestra la condición de pago COMPLETA para ubicar dónde vive el "45".
NO toca producción.
"""

import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

# Los que Tania dice que tienen 45 días
CLIENTES = ["C0179", "C0180", "C0181", "C0048", "C0257", "C0258", "C0259"]


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # Cache de condiciones de pago ya vistas, para no repetir
        vistos = {}

        for code in CLIENTES:
            print("\n" + "=" * 60)
            print(f"CLIENTE: {code}")
            print("=" * 60)

            # 1. Traer el PayTermsGrpCode del cliente
            bp = conn.get(
                f"BusinessPartners('{code}')",
                {"$select": "CardCode,PayTermsGrpCode"},
            )
            if not bp:
                print("   ⚠️ No se pudo traer el BP")
                continue

            ptgc = bp.get("PayTermsGrpCode")
            print(f"   PayTermsGrpCode = {ptgc}")

            if ptgc is None:
                print("   ⚠️ Sin código de condición de pago")
                continue

            # 2. Traer la condición de pago COMPLETA (todos los campos)
            if ptgc not in vistos:
                pt = conn.get(f"PaymentTermsTypes({ptgc})", {})
                vistos[ptgc] = pt

            pt = vistos[ptgc]
            if pt:
                nombre = pt.get("PaymentTermsGroupName", "")
                print(f"   Nombre condición: {nombre}")
                # Mostrar TODOS los campos que suenen a días/plazo
                print("   Campos con 'day'/'days' en el nombre:")
                for k, v in pt.items():
                    if "day" in k.lower() or "date" in k.lower():
                        print(f"      {k} = {v}")
                # Lo que usa el código actual:
                print(
                    f"   >>> NumberOfAdditionalDays (lo que usa el código hoy) = {pt.get('NumberOfAdditionalDays')}"
                )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
