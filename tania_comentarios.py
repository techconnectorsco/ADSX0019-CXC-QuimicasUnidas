import sys
import os
import json

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar_casos():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    # Clientes específicos mencionados por Tania
    clientes_a_investigar = [
        "C0326",  # Límite moneda
        "C0489",
        "C0250",
        "C0327",  # Faltan PR
        "C0179",
        "C0257",  # Plazo a 45 días (sale 30)
        "C0138",
        "C0139",
        "C0140",  # Lagar (Agentes y Padre/Hija)
        "C0161",
        "C0162",
        "C0163",
        "C0164",  # Colono Agrop (Padre/Hija)
        "C0040",
        "C0042",
        "C0043",  # Almacenes Colono (Padre/Hija)
        "C0314",
        "C0315",
        "C0316",  # Carlos Ruiz (Agente incorrecto)
        "C0470",  # Límite en USD sale en CRC
        "C0223",
        "C0224",
        "C0225",  # Jotocillo (Padre/Hija)
        "C0346",
        "C0347",  # Unicomer (Gollo)
    ]

    try:
        print("=" * 80)
        print("🔍 INVESTIGACIÓN DE CLIENTES - COMENTARIOS DE TANIA")
        print("=" * 80)

        for card_code in clientes_a_investigar:
            print(f"\nConsultando: {card_code}...")

            # 1. Datos Maestros del BP
            params_bp = {
                "$select": "CardCode,CardName,CardType,Valid,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,U_NTV_EnvioAutomatico,CreditLimit,Currency,FatherCard,PayTermsGrpCode"
            }
            bp_data = conn.get(f"BusinessPartners('{card_code}')", params_bp)

            if not bp_data:
                print(f"   ⚠️ Cliente no encontrado en SAP.")
                continue

            print(f"   👤 Nombre: {bp_data.get('CardName')}")
            print(f"   📍 Padre (FatherCard): {bp_data.get('FatherCard')}")
            print(f"   💰 Saldo Actual: {bp_data.get('CurrentAccountBalance')}")
            print(
                f"   💵 Límite Crédito: {bp_data.get('CreditLimit')} | Moneda BP: {bp_data.get('Currency')}"
            )
            print(
                f"   👨‍💼 Agente ID: {bp_data.get('SalesPersonCode')} | Zona: {bp_data.get('U_ZGIRA')}"
            )
            print(f"   📅 Condición Pago ID: {bp_data.get('PayTermsGrpCode')}")
            print(
                f"   📧 Envío Automático (U_NTV_EnvioAutomatico): '{bp_data.get('U_NTV_EnvioAutomatico')}'"
            )

            # 2. Búsqueda de Pagos Recibidos (PR) a Favor (OpenAmount > 0)
            params_pr = {
                "$filter": f"CardCode eq '{card_code}' and OpenAmount gt 0",
                "$select": "DocNum,DocDate,OpenAmount,DocCurrency",
            }
            pr_data = conn.get("IncomingPayments", params_pr)
            pagos_abiertos = pr_data.get("value", []) if pr_data else []

            if pagos_abiertos:
                print(
                    f"   ✅ Tiene {len(pagos_abiertos)} Pagos Recibidos (PR) con saldo abierto:"
                )
                for p in pagos_abiertos[:3]:  # Muestra max 3
                    print(
                        f"      - PR #{p.get('DocNum')} | Fecha: {p.get('DocDate')} | Saldo Abierto: {p.get('OpenAmount')} {p.get('DocCurrency')}"
                    )
            else:
                print("   ❌ No tiene Pagos Recibidos (PR) con saldo a favor.")

    finally:
        conn.logout()
        print("\n" + "=" * 80)
        print("FIN DE LA INVESTIGACIÓN")
        print("=" * 80)


if __name__ == "__main__":
    investigar_casos()
