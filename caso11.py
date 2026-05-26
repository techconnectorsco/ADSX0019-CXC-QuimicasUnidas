"""
investigar_v11.py - Químicas Unidas

CONFIRMADO: SQLQueries('X')/List ejecuta SQL guardado y devuelve resultados.

AHORA: ¿podemos CREAR queries con nuestro usuario? Si sí, somos autónomos.
Si no, hay que pedirle a Novitec que las cree.

PRUEBA: crear una query mínima que solo lea la cuenta del cliente C0489.
"""

import json
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # POST a SQLQueries para crear una nueva
        # El SQL: saldo neto del cliente C0489 desde JDT1
        sql_test = (
            "SELECT "
            'SUM(T0."Debit") AS "TotalCargos", '
            'SUM(T0."Credit") AS "TotalAbonos", '
            'SUM(T0."Debit") - SUM(T0."Credit") AS "SaldoNeto" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489'"
        )

        payload = {
            "SqlCode": "QU_SALDO_TEST",
            "SqlName": "Prueba saldo cliente C0489",
            "SqlText": sql_test,
        }

        print("=" * 90)
        print("INTENTANDO CREAR SQLQuery 'QU_SALDO_TEST'")
        print("=" * 90)
        print(f"SQL a guardar:\n   {sql_test}\n")

        # POST manual usando la sesión interna
        url = f"{conn.base_url}/SQLQueries"
        try:
            response = conn.session.post(url, json=payload)
            print(f"Status code: {response.status_code}")
            print(f"Respuesta:\n{response.text[:1500]}")
        except Exception as e:
            print(f"❌ Excepción: {e}")

        # Si se creó, intentar ejecutarla
        print("\n" + "=" * 90)
        print("INTENTAR EJECUTAR QU_SALDO_TEST")
        print("=" * 90)
        r = conn.get("SQLQueries('QU_SALDO_TEST')/List", {})
        if r is not None:
            print(
                f"Respuesta:\n{json.dumps(r, indent=2, ensure_ascii=False, default=str)[:2000]}"
            )

        # Limpieza: borrar la query de prueba
        print("\n" + "=" * 90)
        print("LIMPIEZA - eliminar query de prueba")
        print("=" * 90)
        try:
            r_del = conn.session.delete(f"{conn.base_url}/SQLQueries('QU_SALDO_TEST')")
            print(f"DELETE status: {r_del.status_code}")
            if r_del.status_code not in (204, 200):
                print(f"   {r_del.text[:500]}")
        except Exception as e:
            print(f"Excepción al borrar: {e}")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
