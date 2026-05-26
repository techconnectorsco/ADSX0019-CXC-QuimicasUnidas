"""
investigar_v15.py - Químicas Unidas

PUNTO CLAVE: Un PR no puede estar "vencido" como tal. SAP marca "Vencido"
en un PR cuando hay un saldo a favor del cliente NO APLICADO todavía.

OBJETIVO: encontrar el campo que indica saldo pendiente de reconciliar
por línea, no por suma total.

En JDT1 / OJDT, los campos candidatos son:
- BalDueDeb / BalDueCred: saldo pendiente débito/crédito
- DueDate: fecha límite
- MthDate: fecha de cuadre
- ReconSum / ReconSumFC: monto ya reconciliado
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def crear_ejecutar(conn, code, sql, titulo):
    print(f"\n{'=' * 100}")
    print(f"{titulo}")
    print(f"{'=' * 100}")
    print(f"SQL:\n   {sql}\n")

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
        print(f"❌ POST {resp.status_code}: {resp.text[:500]}")
        return []
    r = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{conn.base_url}/SQLQueries('{code}')")
    return r.get("value", []) if r else []


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # 1. Ver columnas específicas de saldo pendiente
        rows = crear_ejecutar(
            conn,
            "QU_V15A",
            'SELECT TOP 3 T0."TransId", T0."Debit", T0."Credit", '
            'T0."BalDueDeb", T0."BalDueCred", T0."BalFcDeb", T0."BalFcCred", '
            'T0."DueDate", T0."MthDate", T0."IntrnMatch", T0."ReconSum" '
            'FROM "JDT1" T0 WHERE T0."ShortName" = \'C0489\' '
            'AND T0."Credit" > 0 '
            'ORDER BY T0."RefDate" DESC',
            "1. Ver campos BalDue* y ReconSum en líneas Credit de C0489",
        )
        if rows:
            for r in rows:
                print(f"   TransId {r.get('TransId')}: ")
                for k, v in r.items():
                    if k == "TransId":
                        continue
                    if v not in (None, 0, 0.0, ""):
                        print(f"      {k}: {v}")
                print()

        # 2. PRs (DocType IT) con saldo a favor pendiente
        # Filtrar por TransType para identificar pagos recibidos
        rows = crear_ejecutar(
            conn,
            "QU_V15B",
            'SELECT T0."RefDate", T0."TransId", T0."BaseRef", T0."TransType", '
            'T0."Debit", T0."Credit", '
            'T0."BalDueDeb", T0."BalDueCred", '
            'T0."LineMemo" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            'AND T0."Credit" > 0 '
            'AND (T0."BalDueCred" > 0 OR T0."BalDueDeb" > 0) '
            'ORDER BY T0."RefDate" DESC',
            "2. Líneas Credit con saldo pendiente real (BalDueCred > 0)",
        )
        if rows:
            print(f"   Total líneas con saldo pendiente: {len(rows)}\n")
            print(
                f"   {'Fecha':<10} {'TransId':<10} {'BaseRef':<12} {'Type':<6} "
                f"{'Debit':>14} {'Credit':>14} {'BalDeb':>14} {'BalCred':>14}  Memo"
            )
            print(
                f"   {'-'*10} {'-'*10} {'-'*12} {'-'*6} {'-'*14} {'-'*14} {'-'*14} {'-'*14}  {'-'*40}"
            )
            for r in rows:
                print(
                    f"   {str(r.get('RefDate',''))[:10]:<10} "
                    f"{r.get('TransId',''):<10} "
                    f"{str(r.get('BaseRef',''))[:12]:<12} "
                    f"{str(r.get('TransType','') or ''):<6} "
                    f"{float(r.get('Debit',0) or 0):>14,.2f} "
                    f"{float(r.get('Credit',0) or 0):>14,.2f} "
                    f"{float(r.get('BalDueDeb',0) or 0):>14,.2f} "
                    f"{float(r.get('BalDueCred',0) or 0):>14,.2f}  "
                    f"{(r.get('LineMemo','') or '')[:40]}"
                )

        # 3. Sumar saldos pendientes de C0489
        rows = crear_ejecutar(
            conn,
            "QU_V15C",
            "SELECT "
            'SUM(T0."BalDueDeb") AS "PendienteDebito", '
            'SUM(T0."BalDueCred") AS "PendienteCredito" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489'",
            "3. Suma de saldos PENDIENTES (BalDue) de C0489",
        )
        if rows:
            r = rows[0]
            d = float(r.get("PendienteDebito", 0) or 0)
            c = float(r.get("PendienteCredito", 0) or 0)
            print(f"\n   Pendiente DÉBITO  (facturas sin pagar):    {d:,.2f}")
            print(f"   Pendiente CRÉDITO (pagos sin aplicar):     {c:,.2f}")
            print(f"   ────────────────────────────────────────────────────")
            print(f"   Saldo neto (Debito - Credito):              {d-c:,.2f}")
            print(f"\n   Si el cliente tiene saldo a favor de ₡3,057.71:")
            print(f"   Esperamos: PendienteCredito >= 3,057.71 y se vea el PR origen")

        # 4. ¿Esa línea del PR 60623 tiene BalDueCred?
        rows = crear_ejecutar(
            conn,
            "QU_V15D",
            'SELECT T0."RefDate", T0."TransId", T0."BaseRef", '
            'T0."Debit", T0."Credit", T0."BalDueDeb", T0."BalDueCred", '
            'T0."IntrnMatch", T0."MthDate", T0."LineMemo" '
            'FROM "JDT1" T0 '
            "WHERE T0.\"ShortName\" = 'C0489' "
            "AND T0.\"BaseRef\" = '60623'",
            "4. Líneas del PR 60623 específicamente",
        )
        if rows:
            for r in rows:
                print(f"\n   Línea encontrada:")
                for k, v in r.items():
                    if v not in (None, 0, 0.0, ""):
                        print(f"      {k}: {v}")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
