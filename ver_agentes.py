import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def verificar_correos_agentes():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print("🔄 Obteniendo Vendedores desde SAP...")
        agentes = []
        skip = 0
        page_size = 20

        params = {
            "$select": "SalesEmployeeCode,SalesEmployeeName,Email",
            "$orderby": "SalesEmployeeCode",
        }

        # Paginación estricta de SAP (20 en 20)
        while True:
            params["$skip"] = skip
            params["$top"] = page_size
            res = conn.get("SalesPersons", params)

            if not res or "value" not in res:
                break
            cantidad = len(res["value"])
            if cantidad == 0:
                break

            agentes.extend(res["value"])
            print(f"   ⏳ Descargando... Llevamos {len(agentes)} agentes", end="\r")

            if cantidad < page_size:
                break
            skip += page_size

        print(f"\n✅ Total agentes descargados: {len(agentes)}")

        # Clasificamos a los agentes
        con_correo = []
        sin_correo = []

        for ag in agentes:
            # Ignoramos al agente -1 que es el sistema por defecto ("Ningún empleado")
            if ag.get("SalesEmployeeCode") == -1:
                continue

            email = ag.get("Email")
            if email and str(email).strip() != "":
                con_correo.append(ag)
            else:
                sin_correo.append(ag)

        # Generamos el reporte en TXT
        nombre_archivo = "Verificacion_Correos_Agentes.txt"
        with open(nombre_archivo, "w", encoding="utf-8") as f:
            f.write("REPORTE DE VERIFICACIÓN: CORREOS DE AGENTES EN SAP\n")
            f.write("=" * 85 + "\n\n")

            f.write(f"✅ AGENTES CON CORREO ASIGNADO ({len(con_correo)})\n")
            f.write("-" * 85 + "\n")
            f.write(f"{'ID':<5} | {'NOMBRE DEL AGENTE':<40} | {'CORREO'}\n")
            f.write("-" * 85 + "\n")
            for ag in con_correo:
                f.write(
                    f"{ag['SalesEmployeeCode']:<5} | {ag.get('SalesEmployeeName', '')[:38]:<40} | {ag.get('Email')}\n"
                )
            f.write("\n\n")

            f.write(f"🚫 AGENTES SIN CORREO ({len(sin_correo)})\n")
            f.write("-" * 85 + "\n")
            f.write(f"{'ID':<5} | {'NOMBRE DEL AGENTE':<40} | {'ESTADO'}\n")
            f.write("-" * 85 + "\n")
            for ag in sin_correo:
                f.write(
                    f"{ag['SalesEmployeeCode']:<5} | {ag.get('SalesEmployeeName', '')[:38]:<40} | VACÍO\n"
                )
            f.write("\n" + "=" * 85 + "\n")

        print(f"✅ ¡Listo! Archivo '{nombre_archivo}' generado con éxito.")

    finally:
        conn.logout()


if __name__ == "__main__":
    verificar_correos_agentes()
