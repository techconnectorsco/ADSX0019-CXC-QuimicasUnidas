import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def exportar_clientes_agente():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("🔄 Obteniendo Vendedores desde SAP...")
        res_slp = conn.get(
            "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName"}
        )
        vendedores = {}
        if res_slp and "value" in res_slp:
            vendedores = {
                v["SalesEmployeeCode"]: v.get("SalesEmployeeName", "Sin Nombre")
                for v in res_slp["value"]
            }

        print("🔄 Obteniendo clientes con SALDO ABIERTO...")

        clientes_brutos = []
        skip = 0
        page_size = 20

        # OData filter: Solo clientes activos y con saldo distinto a cero
        params_bp = {
            "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and CurrentAccountBalance ne 0",
            "$select": "CardCode,CardName,SalesPersonCode,CurrentAccountBalance,PayTermsGrpCode",
            "$orderby": "CardCode",
        }

        while True:
            params_bp["$top"] = page_size
            params_bp["$skip"] = skip
            resultado = conn.get("BusinessPartners", params_bp)

            if not resultado or "value" not in resultado:
                break

            cantidad_recibida = len(resultado["value"])
            if cantidad_recibida == 0:
                break

            clientes_brutos.extend(resultado["value"])
            print(
                f"   ⏳ Descargando... Llevamos {len(clientes_brutos)} clientes con saldo",
                end="\r",
            )

            if cantidad_recibida < page_size:
                break

            skip += page_size

        print(f"\n✅ ¡Descarga completada! Total encontrados: {len(clientes_brutos)}")

        # FILTRO DE CRÉDITO: Descartamos los de Contado (PayTermsGrpCode == -1)
        clientes_credito = [
            c for c in clientes_brutos if c.get("PayTermsGrpCode") not in [-1, None]
        ]
        print(
            f"📉 Después de filtrar los de 'Contado', quedan: {len(clientes_credito)} clientes a crédito."
        )

        print("📊 Agrupando datos...")
        agrupados = {}
        for cli in clientes_credito:
            slp_code = cli.get("SalesPersonCode", -1)
            if slp_code not in agrupados:
                agrupados[slp_code] = []
            agrupados[slp_code].append(cli)

        print("📝 Escribiendo reporte en 'agrupamiento_agentes.txt'...")
        with open("agrupamiento_agentes.txt", "w", encoding="utf-8") as f:
            f.write("REPORTE DE CLIENTES A CRÉDITO CON SALDO ABIERTO POR AGENTE\n")
            f.write("=" * 80 + "\n\n")

            for slp_code, lista_cli in sorted(agrupados.items()):
                nombre_vendedor = vendedores.get(slp_code, f"Agente ID {slp_code}")
                f.write(
                    f"👨‍💼 AGENTE ID: {slp_code} - {nombre_vendedor} (Total clientes: {len(lista_cli)})\n"
                )
                f.write("-" * 80 + "\n")

                lista_cli.sort(key=lambda x: x.get("CardCode", ""))
                for cli in lista_cli:
                    saldo = cli.get("CurrentAccountBalance", 0)
                    f.write(
                        f"   {cli.get('CardCode')} - {cli.get('CardName')} | Saldo: {saldo:,.2f}\n"
                    )
                f.write("\n" + "=" * 80 + "\n\n")

        print("✅ ¡Listo! Reporte generado exitosamente.")
        print("👉 Abre el archivo 'agrupamiento_agentes.txt' en esta misma carpeta.")

    finally:
        conn.logout()


if __name__ == "__main__":
    exportar_clientes_agente()
