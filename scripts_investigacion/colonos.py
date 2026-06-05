import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar_saldos_viejos_colonos():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("=" * 80)
        print("🔍 INVESTIGANDO SALDOS A FAVOR (PR) EN GRUPO 'COLONO' (CON CHEQUES)")
        print("=" * 80)

        # 1. Buscar todos los clientes que contengan "COLONO" en su nombre
        params_bp = {
            "$filter": "contains(CardName, 'COLONO') and CardType eq 'cCustomer'",
            "$select": "CardCode,CardName",
        }
        res_bp = conn.get("BusinessPartners", params_bp)
        colonos = res_bp.get("value", []) if res_bp else []

        if not colonos:
            print("No se encontraron clientes con la palabra 'COLONO'.")
            return

        print(
            f"Se encontraron {len(colonos)} sucursales/clientes con la palabra 'COLONO'.\nBuscando sus sobrantes...\n"
        )

        pagos_viejos_encontrados = 0

        for cli in colonos:
            card_code = cli.get("CardCode")
            card_name = cli.get("CardName")

            # Traer los pagos no cancelados, INCLUYENDO PaymentChecks en el Select
            params_pr = {
                "$filter": f"CardCode eq '{card_code}' and Cancelled eq 'tNO'",
                "$select": "DocNum,DocDate,TransferSum,CashSum,DocCurrency,PaymentInvoices,PaymentChecks",
            }
            res_pr = conn.get("IncomingPayments", params_pr)
            pagos = res_pr.get("value", []) if res_pr else []

            sobrantes_cliente = []

            for p in pagos:
                # 1. Extraer los tres métodos de pago
                efectivo = float(p.get("CashSum", 0) or 0)
                transferencia = float(p.get("TransferSum", 0) or 0)
                cheques = sum(
                    float(chk.get("CheckSum", 0) or 0)
                    for chk in p.get("PaymentChecks", [])
                )

                # 2. Sumar el total real que entró
                total_pagado = efectivo + transferencia + cheques

                # 3. Sumar lo aplicado
                suma_aplicada = sum(
                    float(inv.get("SumApplied", 0) or 0)
                    for inv in p.get("PaymentInvoices", [])
                )

                # 4. Calcular diferencia
                sobrante = round(total_pagado - suma_aplicada, 2)

                # Si hay sobrante
                if sobrante > 0.05:
                    sobrantes_cliente.append(
                        {
                            "DocNum": p.get("DocNum"),
                            "Fecha": str(p.get("DocDate", ""))[:10],
                            "Monto": sobrante,
                            "Moneda": p.get("DocCurrency", "CRC"),
                        }
                    )

            # Imprimir si tiene sobrantes
            if sobrantes_cliente:
                # Ordenar del más antiguo al más reciente
                sobrantes_cliente.sort(key=lambda x: x["Fecha"])
                print(f"🏢 {card_code} - {card_name}")
                for s in sobrantes_cliente:
                    print(
                        f"   ⚠️ PR #{s['DocNum']} | Fecha: {s['Fecha']} | Sobrante: {s['Monto']} {s['Moneda']}"
                    )
                    pagos_viejos_encontrados += 1

        if pagos_viejos_encontrados == 0:
            print("✅ No se encontraron sobrantes sin aplicar en el grupo Colono.")
        else:
            print(
                f"\n📊 Total de pagos sobrantes encontrados: {pagos_viejos_encontrados}"
            )

    finally:
        conn.logout()


if __name__ == "__main__":
    investigar_saldos_viejos_colonos()
