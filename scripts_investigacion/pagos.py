import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar_pagos():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        print("Buscando estructura de Pagos para C0250...")
        # Traemos solo 1 pago de ese cliente para ver los campos que existen
        params = {"$filter": "CardCode eq 'C0250'", "$top": 1}
        resultado = conn.get("IncomingPayments", params)

        if resultado and "value" in resultado and len(resultado["value"]) > 0:
            pago = resultado["value"][0]
            print("\n✅ Campos encontrados en el Pago:")
            # Imprimir solo las llaves principales y valores que parecen saldos
            for k, v in pago.items():
                if (
                    "amoun" in k.lower()
                    or "balan" in k.lower()
                    or "total" in k.lower()
                    or k in ["DocNum", "DocCurrency"]
                ):
                    print(f"   - {k}: {v}")
        else:
            print(
                "❌ No se encontraron pagos para C0250, intentando sin filtro de cliente..."
            )
            # Si no tiene pagos, traemos cualquiera para ver la estructura
            res2 = conn.get("IncomingPayments", {"$top": 1})
            if res2 and "value" in res2 and len(res2["value"]) > 0:
                pago = res2["value"][0]
                for k, v in pago.items():
                    if (
                        "amoun" in k.lower()
                        or "balan" in k.lower()
                        or "total" in k.lower()
                        or k in ["DocNum", "DocCurrency"]
                    ):
                        print(f"   - {k}: {v}")

    finally:
        conn.logout()


if __name__ == "__main__":
    investigar_pagos()
