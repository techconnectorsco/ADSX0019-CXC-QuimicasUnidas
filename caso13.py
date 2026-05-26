"""
investigar_v13.py - Químicas Unidas

OBJETIVO: replicar la pantalla 'Saldo de cuenta - C0489' de Tania exactamente.

En el screenshot vimos:
- Filtro por fechas (01/01/26 - 31/12/26)
- Checkbox "Visualizar sólo operaciones no reconciliadas"

Eso significa que el saldo a favor de ₡3,057.71 es el resultado de líneas
del libro mayor (JDT1) que NO han sido reconciliadas internamente.

La reconciliación se marca en la columna "MthDate" o en la tabla ITR1.
Las líneas no reconciliadas son las que importan para el estado de cuenta.

Probamos:
1. Listar líneas no reconciliadas de C0489 con TODOS los campos relevantes
2. Calcular saldo desde ahí
3. Validar contra los ₡3,057.71 que ve Tania
"""

import json
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def crear_y_ejecutar(conn, sql_code, sql_text, descripcion):
    print(f"\n{'=' * 100}")
    print(f"{descripcion}")
    print(f"{'=' * 100}")
    print(f"SQL:\n   {sql_text}\n")

    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url,
        json={
            "SqlCode": sql_code,
            "SqlName": descripcion[:50],
            "SqlText": sql_text,
        },
    )

    if resp.status_code not in (200, 201):
        print(f"   ❌ POST {resp.status_code}: {resp.text[:400]}")
        return None

    r = conn.get(f"SQLQueries('{sql_code}')/List", {})

    # Limpiar
    conn.session.delete(f"{conn.base_url}/SQLQueries('{sql_code}')")

    return r.get("value", []) if r else []


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # 1. Inspeccionar columnas de JDT1 relacionadas con reconciliación
        rows = crear_y_ejecutar(
            conn,
            "QU_INV1",
            'SELECT TOP 1 * FROM "JDT1" T0 WHERE T0."ShortName" = \'C0489\'',
            "1. Ver TODAS las columnas de una línea de JDT1 para C0489",
        )
        if rows:
            print(f"   Total columnas: {len(rows[0])}")
            # Columnas relevantes para reconciliación / antigüedad
            print("\n   Columnas relevantes (Recon, MatchSum, etc):")
            for k in sorted(rows[0].keys()):
                kl = k.lower()
                if any(
                    x in kl
                    for x in [
                        "recon",
                        "match",
                        "balsys",
                        "balfc",
                        "trans",
                        "bal",
                        "intr",
                        "mth",
                    ]
                ):
                    print(f"      {k}: {rows[0].get(k)}")

        # 2. Saldo del cliente C0489 considerando solo movimientos NO reconciliados
        # En SAP B1, las líneas reconciliadas tienen IntrnMatch != 0
        rows = crear_y_ejecutar(
            conn,
            "QU_INV2",
            "SELECT "
            'SUM(T0."Debit") AS "Cargos", '
            'SUM(T0."Credit") AS "Abonos" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND (T0."IntrnMatch" = 0 OR T0."IntrnMatch" IS NULL)',
            "2. Saldo de C0489 solo de líneas NO reconciliadas (IntrnMatch = 0)",
        )
        if rows:
            print(f"   RESULTADO: {rows}")
            if rows[0]:
                cargos = float(rows[0].get("Cargos", 0) or 0)
                abonos = float(rows[0].get("Abonos", 0) or 0)
                saldo = cargos - abonos
                print(f"\n   Cargos no reconciliados: {cargos:,.2f}")
                print(f"   Abonos no reconciliados: {abonos:,.2f}")
                print(f"   SALDO NETO:              {saldo:,.2f}")
                print(f"\n   ¿Coincide con ₡3,057.71 que ve Tania?")

        # 3. Detalle línea por línea de los NO reconciliados (esto debería ser
        # exactamente lo que ve Tania en su pantalla)
        rows = crear_y_ejecutar(
            conn,
            "QU_INV3",
            'SELECT T0."RefDate", T0."TransId", T0."BaseRef", T0."Debit", T0."Credit", T0."FCDebit", T0."FCCredit", T0."FCCurrency", T0."LineMemo" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND (T0."IntrnMatch" = 0 OR T0."IntrnMatch" IS NULL) '
            'ORDER BY T0."RefDate"',
            "3. Detalle de movimientos NO reconciliados de C0489",
        )
        if rows:
            print(f"   Total movimientos no reconciliados: {len(rows)}\n")
            print(
                f"   {'Fecha':<10} {'TransId':<10} {'BaseRef':<15} {'Debit':>12} {'Credit':>12} {'FCDeb':>10} {'FCCred':>10} {'Cur':<5}  Memo"
            )
            print(
                f"   {'-'*10} {'-'*10} {'-'*15} {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*5}  {'-'*60}"
            )
            for r in rows:
                print(
                    f"   {str(r.get('RefDate',''))[:10]:<10} "
                    f"{r.get('TransId',''):<10} "
                    f"{str(r.get('BaseRef',''))[:15]:<15} "
                    f"{float(r.get('Debit',0) or 0):>12,.2f} "
                    f"{float(r.get('Credit',0) or 0):>12,.2f} "
                    f"{float(r.get('FCDebit',0) or 0):>10,.2f} "
                    f"{float(r.get('FCCredit',0) or 0):>10,.2f} "
                    f"{(r.get('FCCurrency','') or ''):<5}  "
                    f"{(r.get('LineMemo','') or '')[:60]}"
                )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
