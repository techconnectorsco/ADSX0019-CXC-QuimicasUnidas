import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar_direcciones():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    # Clientes de prueba mencionados por Tania
    clientes_prueba = ["C0139", "C0161", "C0223"]

    try:
        for card_code in clientes_prueba:
            print(f"\n{'='*80}")
            print(f"🔍 INVESTIGANDO DIRECCIONES: {card_code}")
            print(f"{'='*80}")

            # Pedimos el encabezado y el arreglo de direcciones (BPAddresses)
            res = conn.get(
                f"BusinessPartners('{card_code}')",
                {"$select": "CardCode,CardName,SalesPersonCode,BPAddresses"},
            )

            if not res:
                print(f"❌ No se encontró el cliente {card_code}")
                continue

            nombre = res.get("CardName", "")
            vendedor_principal = res.get("SalesPersonCode")

            print(f"🏢 Cliente: {nombre}")
            print(f"👨‍💼 Vendedor General (Encabezado): {vendedor_principal}")
            print("-" * 80)

            direcciones = res.get("BPAddresses", [])
            if not direcciones:
                print("   No tiene direcciones registradas en SAP.")
                continue

            for dir in direcciones:
                # Traducir el tipo de dirección para mayor claridad
                tipo_crudo = dir.get("AddressType", "")
                if tipo_crudo == "bo_ShipTo":
                    tipo = "🚚 DESTINO (Envío)"
                elif tipo_crudo == "bo_BillTo":
                    tipo = "🏢 FACTURACIÓN (Cobro)"
                else:
                    tipo = tipo_crudo

                nombre_dir = dir.get("AddressName", "")

                print(f"📍 ID Dirección: {nombre_dir} | Tipo: {tipo}")

                # Buscar TODOS los campos personalizados (UDFs) que tengan datos
                udfs = {
                    k: v for k, v in dir.items() if k.startswith("U_") and v is not None
                }

                if "U_CODV" in dir:
                    print(f"   ➤ Campo U_CODV explícito: {dir.get('U_CODV')}")

                if udfs:
                    print(f"   ➤ Campos Personalizados encontrados: {udfs}")
                else:
                    print(f"   ➤ No se encontraron UDFs con datos en esta dirección.")
                print("")

    finally:
        conn.logout()


if __name__ == "__main__":
    investigar_direcciones()
