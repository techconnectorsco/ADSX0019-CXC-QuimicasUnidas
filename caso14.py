"""
investigar_v14.py - Químicas Unidas

OBJETIVO: Conseguir EXACTAMENTE los ₡3,057.71 que ve Tania.

DESCUBRIMIENTO ANTERIOR:
- Los movimientos NO reconciliados del 2026 ya no aparecen porque SAP
  los aplicó internamente. Pero el saldo a favor REAL existe acumulado
  desde períodos anteriores + diferencias cambiarias.

ESTRATEGIA: replicar exactamente lo que SAP muestra en 'Saldo de cuenta'.

Probamos 3 cosas:
1. Sumar TODAS las líneas no reconciliadas (sin filtro de fecha) - debe dar el saldo real
2. Detalle con saldo acumulado fila por fila
3. La cuenta de control real del cliente (debitor account)
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def crear_ejecutar(conn, code, sql, titulo):
    print(f"\n{'=' * 100}")
    print(f"{titulo}")
    print(f"{'=' * 100}")

    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url,
        json={
            "SqlCode": code,
            "SqlName": titulo[:50],
            "SqlText": sql,
        },
    )
    if resp.status_code not in (200, 201):
        print(f"❌ POST {resp.status_code}: {resp.text[:400]}")
        return []

    r = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{conn.base_url}/SQLQueries('{code}')")
    return r.get("value", []) if r else []


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # 1. TODAS las líneas no reconciliadas de C0489 - SIN filtro de fecha
        # =====================================================================
        rows = crear_ejecutar(
            conn,
            "QU_X1",
            'SELECT SUM(T0."Debit") AS "Cargos", '
            'SUM(T0."Credit") AS "Abonos", '
            'SUM(T0."FCDebit") AS "CargosFC", '
            'SUM(T0."FCCredit") AS "AbonosFC" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND (T0."IntrnMatch" = 0 OR T0."IntrnMatch" IS NULL)',
            "1. SALDO REAL: todas las líneas no reconciliadas de C0489 (sin fecha)",
        )
        if rows:
            r = rows[0]
            cargos = float(r.get("Cargos", 0) or 0)
            abonos = float(r.get("Abonos", 0) or 0)
            cargos_fc = float(r.get("CargosFC", 0) or 0)
            abonos_fc = float(r.get("AbonosFC", 0) or 0)
            saldo_ml = cargos - abonos
            saldo_fc = cargos_fc - abonos_fc

            print(f"\n   En moneda local (CRC):")
            print(f"      Cargos:  {cargos:>15,.2f}")
            print(f"      Abonos:  {abonos:>15,.2f}")
            print(f"      ─────────────────────────")
            print(f"      Saldo:   {saldo_ml:>15,.2f}")

            print(f"\n   En moneda extranjera (USD):")
            print(f"      Cargos:  {cargos_fc:>15,.2f}")
            print(f"      Abonos:  {abonos_fc:>15,.2f}")
            print(f"      ─────────────────────────")
            print(f"      Saldo:   {saldo_fc:>15,.2f}")

        # =====================================================================
        # 2. Verificar: contar cuántas líneas hay no reconciliadas
        # =====================================================================
        rows = crear_ejecutar(
            conn,
            "QU_X2",
            'SELECT COUNT(*) AS "Total" FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND (T0."IntrnMatch" = 0 OR T0."IntrnMatch" IS NULL)',
            "2. Cantidad de líneas no reconciliadas (verificación)",
        )
        if rows:
            print(f"\n   Total: {rows[0].get('Total')} líneas no reconciliadas")

        # =====================================================================
        # 3. Probar las columnas Account / control. La cuenta del cliente es 11060102
        #    Quizás hay que filtrar por Account = '11060102' también
        # =====================================================================
        rows = crear_ejecutar(
            conn,
            "QU_X3",
            'SELECT T0."Account", '
            'SUM(T0."Debit") AS "Cargos", '
            'SUM(T0."Credit") AS "Abonos", '
            'COUNT(*) AS "Lineas" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND (T0."IntrnMatch" = 0 OR T0."IntrnMatch" IS NULL) '
            'GROUP BY T0."Account"',
            "3. Desglose por cuenta contable",
        )
        if rows:
            print(
                f"\n   {'Cuenta':<15} {'Cargos':>15} {'Abonos':>15} {'Saldo':>15} {'Líneas':>8}"
            )
            print(f"   {'-'*15} {'-'*15} {'-'*15} {'-'*15} {'-'*8}")
            for r in rows:
                cuenta = r.get("Account", "")
                c = float(r.get("Cargos", 0) or 0)
                a = float(r.get("Abonos", 0) or 0)
                s = c - a
                n = r.get("Lineas", 0)
                print(f"   {cuenta:<15} {c:>15,.2f} {a:>15,.2f} {s:>15,.2f} {n:>8}")

        # =====================================================================
        # 4. CurrentAccountBalance del BP — el saldo "consolidado" según SAP
        # =====================================================================
        rows = crear_ejecutar(
            conn,
            "QU_X4",
            'SELECT T0."CardCode", T0."CardName", T0."Balance", T0."BalanceSys", T0."BalanceFC" '
            'FROM "OCRD" T0 WHERE T0."CardCode" = \'C0489\'',
            "4. Balance del BP en OCRD (debe coincidir con CurrentAccountBalance)",
        )
        if rows:
            for r in rows:
                print(f"\n   CardCode: {r.get('CardCode')}")
                print(f"   CardName: {r.get('CardName')}")
                print(f"   Balance (ML):     {float(r.get('Balance', 0) or 0):>15,.2f}")
                print(
                    f"   BalanceSys:       {float(r.get('BalanceSys', 0) or 0):>15,.2f}"
                )
                print(
                    f"   BalanceFC:        {float(r.get('BalanceFC', 0) or 0):>15,.2f}"
                )

        # =====================================================================
        # 5. Resumen interpretativo
        # =====================================================================
        print(f"\n{'=' * 100}")
        print(f"INTERPRETACIÓN")
        print(f"{'=' * 100}")
        print(
            f"   Tania ve saldo a favor de ₡3,057.71 en la pantalla 'Saldo de cuenta'"
        )
        print(f"   Posibles interpretaciones de los datos arriba:")
        print(f"   - Si OCRD.Balance = 287,510.58 (positivo) → cliente DEBE ese monto")
        print(f"   - Pero Tania ve un PR vencido con (3,057.71) → eso es OTRO concepto")
        print(f"   - Probable: ₡3,057.71 = sobrante histórico no aplicado todavía")
        print(f"   - Y el debe es por las facturas USD ($636.75) convertidas a colones")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
