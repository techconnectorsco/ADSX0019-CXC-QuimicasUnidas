import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def verificar_campo_envio():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("=" * 80)
        print("🔍 VERIFICANDO VALORES DEL CAMPO DE ENVÍO AUTOMÁTICO EN SAP")
        print("=" * 80)

        # Buscar clientes activos, de crédito (no contado) y con saldo distinto de 0
        clientes = []
        skip = 0
        page_size = 20

        params = {
            "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and PayTermsGrpCode ne -1 and CurrentAccountBalance ne 0",
            "$select": "CardCode,CardName,U_NTV_EnvioAutomatico",
        }

        while True:
            params["$skip"] = skip
            params["$top"] = page_size
            res = conn.get("BusinessPartners", params)

            if not res or "value" not in res:
                break
            cantidad = len(res["value"])
            if cantidad == 0:
                break

            clientes.extend(res["value"])
            print(
                f"   ⏳ Descargando... Llevamos {len(clientes)} clientes con saldo",
                end="\r",
            )

            if cantidad < page_size:
                break
            skip += page_size

        print(f"\n\n📊 Total clientes a crédito con saldo abierto: {len(clientes)}")

        valores_encontrados = {}
        for cli in clientes:
            valor_crudo = cli.get("U_NTV_EnvioAutomatico")
            # Si viene None o vacío, lo catalogamos claramente
            if not valor_crudo or str(valor_crudo).strip() == "":
                valor = "VACÍO/NULO"
            else:
                valor = str(valor_crudo).strip().upper()

            if valor not in valores_encontrados:
                valores_encontrados[valor] = []
            valores_encontrados[valor].append(cli)

        print("\n📈 RESUMEN DE LO QUE HAY ESCRITO EN SAP:")
        print("-" * 40)

        total_si = 0
        total_no = 0

        for valor, lista in valores_encontrados.items():
            print(f"   ➤ '{valor}': {len(lista)} clientes")

            # Contabilizar para comparar con Tania
            if valor in ["Y", "S", "SI", "SÍ"]:
                total_si += len(lista)
            elif valor in ["N", "NO"]:
                total_no += len(lista)

        print("-" * 40)
        print(f"✅ Total que el script procesará como SÍ: {total_si} (Tania dice 85)")
        print(f"🚫 Total que el script procesará como NO: {total_no} (Tania dice 8)")

        # Opcional: mostrar si alguien escribió algo muy raro
        print("\n⚠️ Clientes con valores atípicos (no son Y, S, SI, N, NO, VACÍO):")
        raros_encontrados = False
        for valor, lista in valores_encontrados.items():
            if valor not in ["Y", "S", "SI", "SÍ", "N", "NO", "VACÍO/NULO"]:
                raros_encontrados = True
                for cli in lista:
                    print(
                        f"   - {cli['CardCode']} - {cli['CardName']} (Tiene escrito: '{valor}')"
                    )

        if not raros_encontrados:
            print("   (Ninguno, la base de datos está limpia en este aspecto)")

        # Listar los que dicen que NO para validar con Tania
        print("\n🚫 Detalle de los clientes marcados para NO enviar:")
        for valor, lista in valores_encontrados.items():
            if valor in ["N", "NO"]:
                for cli in lista:
                    print(f"   - {cli['CardCode']} - {cli['CardName']}")

    finally:
        conn.logout()


if __name__ == "__main__":
    verificar_campo_envio()
