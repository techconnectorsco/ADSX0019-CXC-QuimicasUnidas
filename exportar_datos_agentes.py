import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def exportar_datos_agentes():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión")
        return

    try:
        print(
            "🔄 Obteniendo datos completos de los Vendedores (SalesPersons) desde SAP..."
        )

        agentes = []
        skip = 0
        page_size = 20

        # Bucle de paginación respetando el límite de 20 de SAP
        while True:
            params = {"$top": page_size, "$skip": skip}
            resultado = conn.get("SalesPersons", params)

            if not resultado or "value" not in resultado:
                break

            cantidad_recibida = len(resultado["value"])
            if cantidad_recibida == 0:
                break

            agentes.extend(resultado["value"])
            print(f"   ⏳ Descargando... Llevamos {len(agentes)} agentes", end="\r")

            if cantidad_recibida < page_size:
                break

            skip += page_size

        print(
            f"\n✅ ¡Descarga completada! Total de agentes encontrados: {len(agentes)}"
        )

        print("📝 Escribiendo reporte en 'datos_completos_agentes.txt'...")
        with open("datos_completos_agentes.txt", "w", encoding="utf-8") as f:
            f.write("REPORTE COMPLETO DE AGENTES (SALES PERSONS)\n")
            f.write("=" * 80 + "\n\n")

            # Ordenamos por ID de agente para mayor claridad
            agentes_ordenados = sorted(
                agentes, key=lambda x: x.get("SalesEmployeeCode", 0)
            )

            for ag in agentes_ordenados:
                id_agente = ag.get("SalesEmployeeCode", "N/A")
                nombre = ag.get("SalesEmployeeName", "Sin Nombre")

                f.write(f"👨‍💼 AGENTE ID: {id_agente} - {nombre}\n")
                f.write("-" * 80 + "\n")

                # Recorrer e imprimir todos los campos (keys y values) que devuelve SAP
                for key, value in ag.items():
                    # Formatear un poco para que se vea ordenado
                    f.write(f"   {key:<30}: {value}\n")

                f.write("\n" + "=" * 80 + "\n\n")

        print("✅ ¡Listo! Reporte generado exitosamente.")
        print(
            "👉 Abre el archivo 'datos_completos_agentes.txt' y busca el campo 'Email' de cada agente."
        )

    finally:
        conn.logout()


if __name__ == "__main__":
    exportar_datos_agentes()
