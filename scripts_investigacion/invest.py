import sys, os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def cazar_sobrante():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("🔍 Buscando PRs de C0250 (Willian Castro) para encontrar el sobrante...")
        # Traemos los pagos que no estén cancelados
        params = {"$filter": "CardCode eq 'C0250' and Cancelled eq 'tNO'"}
        res = conn.get("IncomingPayments", params)
        pagos = res.get("value", [])

        if not pagos:
            print("No se encontraron pagos para C0250.")
            return

        for pago in pagos:
            print(f"\n" + "-" * 50)
            print(f"💰 PR DocNum: {pago.get('DocNum')} | Fecha: {pago.get('DocDate')}")

            # Imprimir cualquier campo numérico en la cabecera que sea mayor a 0
            # (Aquí debería saltar el sobrante, ya sea como CashSum, TransferSum o NoDocSum)
            totales = {
                k: v for k, v in pago.items() if isinstance(v, (int, float)) and v > 0
            }
            print("Valores monetarios en la cabecera:")
            for k, v in totales.items():
                print(f"   - {k}: {v}")

            # Revisar las facturas a las que se les aplicó este pago
            invoices = pago.get("PaymentInvoices", [])
            print(f"Facturas a las que se aplicó este pago: {len(invoices)}")

            suma_aplicada = 0
            for inv in invoices:
                aplicado = inv.get("SumApplied", 0)
                suma_aplicada += aplicado
                print(f"   - Aplicado a DocEntry {inv.get('DocEntry')}: {aplicado}")

            total_pagado = pago.get("TransferSum", 0) + pago.get("CashSum", 0)
            if total_pagado > suma_aplicada:
                print(
                    f"   ⚠️ ¡SOBRANTE DETECTADO por diferencia! Pagó {total_pagado} pero se aplicó {suma_aplicada}"
                )

    finally:
        conn.logout()


if __name__ == "__main__":
    cazar_sobrante()
