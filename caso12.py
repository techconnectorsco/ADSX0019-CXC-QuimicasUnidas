"""
investigar_v12.py - Químicas Unidas

El error anterior fue de SINTAXIS SQL (HANA), no de permisos.
SAP aceptó la petición de crear query, pero HANA rechazó la resta entre agregaciones.

CORRECCIÓN: usar subconsulta o calcular en el cliente.
"""

import json
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def crear_y_probar(conn, sql_code, sql_name, sql_text):
    print(f"\n{'=' * 90}")
    print(f"CREANDO: {sql_code}")
    print(f"{'=' * 90}")
    print(f"SQL:\n   {sql_text}\n")

    # Crear
    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url,
        json={
            "SqlCode": sql_code,
            "SqlName": sql_name,
            "SqlText": sql_text,
        },
    )
    print(f"POST status: {resp.status_code}")
    if resp.status_code not in (200, 201):
        print(f"   ❌ {resp.text[:600]}")
        return False
    print(f"   ✅ Query creada")

    # Ejecutar
    r = conn.get(f"SQLQueries('{sql_code}')/List", {})
    if r is not None:
        print(f"\n   RESULTADO:")
        print(
            f"   {json.dumps(r.get('value', r), indent=2, ensure_ascii=False, default=str)[:1000]}"
        )

    # Borrar
    conn.session.delete(f"{conn.base_url}/SQLQueries('{sql_code}')")
    return True


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # Variante 1: SIN la resta. Solo sumar Debit y Credit por separado.
        # Calculamos saldo en Python.
        crear_y_probar(
            conn,
            "QU_TEST1",
            "Saldo cliente sin resta",
            'SELECT SUM(T0."Debit") AS "Cargos", SUM(T0."Credit") AS "Abonos" '
            'FROM "JDT1" T0 WHERE T0."ShortName" = \'C0489\'',
        )

        # Variante 2: con subconsulta
        crear_y_probar(
            conn,
            "QU_TEST2",
            "Saldo cliente con subconsulta",
            'SELECT "Cargos", "Abonos", ("Cargos" - "Abonos") AS "Saldo" FROM ('
            'SELECT SUM(T0."Debit") AS "Cargos", SUM(T0."Credit") AS "Abonos" '
            'FROM "JDT1" T0 WHERE T0."ShortName" = \'C0489\''
            ") subq",
        )

        # Variante 3: trayendo detalle línea por línea (para que coincida con la pantalla de Tania)
        crear_y_probar(
            conn,
            "QU_TEST3",
            "Detalle libro mayor cliente",
            'SELECT TOP 20 T0."RefDate", T0."TransId", T0."Account", T0."Debit", T0."Credit", T0."LineMemo" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' AND T0.\"RefDate\" >= '2026-01-01' "
            'ORDER BY T0."RefDate"',
        )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
