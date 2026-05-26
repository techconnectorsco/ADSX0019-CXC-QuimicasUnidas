import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def exportar_verificacion_txt():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("🔄 Obteniendo datos de SAP...")
        clientes = []
        skip = 0
        page_size = 20

        # Filtro: Clientes a crédito con saldo
        params = {
            "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and PayTermsGrpCode ne -1 and CurrentAccountBalance ne 0",
            "$select": "CardCode,CardName,U_NTV_EnvioAutomatico",
            "$orderby": "CardCode",
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
            print(f"   ⏳ Descargando... Llevamos {len(clientes)} clientes", end="\r")

            if cantidad < page_size:
                break
            skip += page_size

        print(f"\n✅ Total descargados: {len(clientes)}")
        print("📝 Clasificando y generando archivo TXT...")

        clientes_si = []
        clientes_no = []

        # 1. Separar los clientes en dos listas
        for cli in clientes:
            valor_crudo = cli.get("U_NTV_EnvioAutomatico")
            codigo = cli.get("CardCode", "")
            nombre = cli.get("CardName", "")

            if not valor_crudo or str(valor_crudo).strip() == "":
                clientes_no.append(
                    {
                        "codigo": codigo,
                        "nombre": nombre,
                        "valor": "VACÍO",
                        "motivo": "Campo vacío en SAP",
                    }
                )
            else:
                valor_limpio = str(valor_crudo).strip().upper()
                if valor_limpio in ["Y", "S", "SI", "SÍ"]:
                    clientes_si.append(
                        {"codigo": codigo, "nombre": nombre, "valor": valor_limpio}
                    )
                else:
                    clientes_no.append(
                        {
                            "codigo": codigo,
                            "nombre": nombre,
                            "valor": valor_limpio,
                            "motivo": "No Envia explícito",
                        }
                    )

        # 2. Dibujar el archivo TXT
        nombre_archivo = "Verificacion_Envios_SAP.txt"
        with open(nombre_archivo, "w", encoding="utf-8") as f:
            f.write("REPORTE DE VERIFICACIÓN: ENVÍO AUTOMÁTICO DE ESTADOS DE CUENTA\n")
            f.write("=" * 110 + "\n\n")

            # --- TABLA 1: LOS QUE SÍ ---
            f.write(
                "✅ LISTA 1: CLIENTES QUE SÍ RECIBIRÁN EL ESTADO DE CUENTA (Tienen S, Y, SI)\n"
            )
            f.write("-" * 110 + "\n")
            f.write(f"{'CÓDIGO':<12} | {'NOMBRE DEL CLIENTE':<75} | {'VALOR SAP'}\n")
            f.write("-" * 110 + "\n")
            for c in clientes_si:
                f.write(f"{c['codigo']:<12} | {c['nombre'][:73]:<75} | {c['valor']}\n")
            f.write("-" * 110 + "\n")
            f.write(f"Total a enviar: {len(clientes_si)} clientes.\n\n\n")

            # --- TABLA 2: LOS QUE NO ---
            f.write(
                "🚫 LISTA 2: CLIENTES EXCLUIDOS DEL ENVÍO (Tienen N, NO, o campo Vacío)\n"
            )
            f.write("-" * 110 + "\n")
            f.write(
                f"{'CÓDIGO':<12} | {'NOMBRE DEL CLIENTE':<50} | {'VALOR SAP':<12} | {'MOTIVO'}\n"
            )
            f.write("-" * 110 + "\n")
            for c in clientes_no:
                f.write(
                    f"{c['codigo']:<12} | {c['nombre'][:48]:<50} | {c['valor']:<12} | {c['motivo']}\n"
                )
            f.write("-" * 110 + "\n")
            f.write(f"Total excluidos: {len(clientes_no)} clientes.\n\n\n")

            # --- RESUMEN FINAL ---
            f.write("=" * 110 + "\n")
            f.write("RESUMEN GENERAL:\n")
            f.write(f" - Clientes procesados para enviar:  {len(clientes_si)}\n")
            f.write(f" - Clientes restringidos/excluidos:  {len(clientes_no)}\n")
            f.write(f" - Total de cuentas con saldo:       {len(clientes)}\n")
            f.write("=" * 110 + "\n")

        print(
            f"✅ ¡Listo! Archivo '{nombre_archivo}' generado con las tablas separadas."
        )

    finally:
        conn.logout()


if __name__ == "__main__":
    exportar_verificacion_txt()
