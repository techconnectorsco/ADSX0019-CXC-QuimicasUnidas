import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar_todas_condiciones():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        print("=" * 80)
        print("🔍 TODAS LAS CONDICIONES DE PAGO EN SAP")
        print("=" * 80)

        # Traemos todas las condiciones de pago
        resultado = conn.get("PaymentTermsTypes")

        if resultado and "value" in resultado:
            condiciones = resultado["value"]
            for term in condiciones:
                id_term = term.get("GroupNumber")
                nombre = term.get("PaymentTermsGroupName")
                # Revisamos el campo que acabamos de descubrir
                dias = term.get("NumberOfAdditionalDays", "N/A")
                print(f"   - ID: {id_term:2} | Días: {dias:2} | Nombre: {nombre}")
        else:
            print("❌ No se encontraron condiciones.")

    finally:
        conn.logout()


if __name__ == "__main__":
    investigar_todas_condiciones()
