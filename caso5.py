"""
investigar_v5_journal.py - Químicas Unidas

HALLAZGO CLAVE:
La pantalla "Saldo de cuenta" en SAP que Tania usa, se construye desde
JournalEntries filtrando por ShortName='C0489'. Esa pantalla muestra
columnas Cargo (Debit) / Abono (Credit) / Saldo acumulado.

El "saldo a favor" de ₡3,057.71 NO viene de IncomingPayments — viene
del balance acumulado del LIBRO MAYOR del cliente.

OBJETIVO: Reproducir esa pantalla exacta vía JournalEntries y validar
que llegamos a los mismos números que Tania ve.

NÚMERO DE TRANSACCIÓN del PR 60623 según el screenshot: 344885
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def separador(titulo: str):
    print("\n" + "=" * 100)
    print(f"  {titulo}")
    print("=" * 100)


# =============================================================================
# PASO 1: Confirmar que podemos traer el JournalEntry 344885 (el PR 60623)
# =============================================================================


def paso1_journal_344885(conn):
    separador("PASO 1 — Traer el JournalEntry 344885 (PR 60623 de Marlon)")
    print(
        "Si lo traemos completo, confirmamos que JournalEntries es la fuente correcta.\n"
    )

    # El TransactionNumber es el JdtNum / Number del Journal Entry
    # Probamos varias formas de filtrar
    print(">> Intento 1: Por Number eq 344885")
    resp = conn.get(
        "JournalEntries",
        {
            "$filter": "Number eq 344885",
            "$top": 1,
        },
    )
    if resp and resp.get("value"):
        je = resp["value"][0]
        print(f"   ✅ Encontrado")
        print(f"   JdtNum: {je.get('JdtNum')}")
        print(f"   Number: {je.get('Number')}")
        print(f"   ReferenceDate: {je.get('ReferenceDate')}")
        print(f"   Memo: {je.get('Memo')}")
        print(f"   TransactionCode: {je.get('TransactionCode')}")
        print(f"   Total líneas: {len(je.get('JournalEntryLines', []))}")

        # Mostrar todas las líneas
        print(f"\n   LÍNEAS DEL ASIENTO:")
        for i, l in enumerate(je.get("JournalEntryLines", [])):
            print(f"   Línea {i}:")
            print(f"      AccountCode: {l.get('AccountCode')}")
            print(f"      ShortName: {l.get('ShortName')}")
            print(f"      Debit: {l.get('Debit')}")
            print(f"      Credit: {l.get('Credit')}")
            print(f"      FCDebit: {l.get('FCDebit')}")
            print(f"      FCCredit: {l.get('FCCredit')}")
            print(f"      FCCurrency: {l.get('FCCurrency')}")
            print(f"      LineMemo: {l.get('LineMemo')}")
            print()
        return je
    else:
        print(f"   ❌ No encontrado por Number, probando otros campos...")

    # Si falla, probar JdtNum
    print("\n>> Intento 2: Por JdtNum eq 344885")
    resp = conn.get(
        "JournalEntries",
        {
            "$filter": "JdtNum eq 344885",
            "$top": 1,
        },
    )
    if resp and resp.get("value"):
        print(f"   ✅ Encontrado con JdtNum")
        return resp["value"][0]
    else:
        print(f"   ❌ Tampoco")

    return None


# =============================================================================
# PASO 2: Traer TODOS los asientos del cliente C0489 en el período del screenshot
# =============================================================================


def paso2_todos_los_asientos_c0489(conn):
    separador("PASO 2 — Todos los asientos de C0489 entre 01/01/26 y 31/12/26")
    print("Replicamos la pantalla 'Saldo de cuenta' que ve Tania.\n")

    # JournalEntryLines tiene ShortName con el CardCode
    # Pero el filtro debe ser sobre la línea, no sobre el header
    # Probamos primero un crossjoin o filtro directo

    # Opción A: filtrar JournalEntries cuyo Lines contengan ShortName = C0489
    print(">> Probando $filter con any() sobre JournalEntryLines:")
    resp = conn.get(
        "JournalEntries",
        {
            "$filter": "ReferenceDate ge '2026-01-01' and ReferenceDate le '2026-12-31' "
            "and JournalEntryLines/any(l: l/ShortName eq 'C0489')",
            "$orderby": "ReferenceDate",
            "$top": 20,
        },
    )

    if not resp or "value" not in resp:
        print("   ❌ Filtro any() no funcionó. Probando otra forma...")
        return

    if not resp.get("value"):
        print("   (sin resultados)")
        return

    asientos = resp["value"]
    print(f"   ✅ Asientos encontrados: {len(asientos)}\n")

    # Para cada asiento, mostrar solo las líneas que afectan a C0489
    saldo_acumulado_local = 0
    print(
        f"   {'Fecha':<12} {'Number':<10} {'TransCode':<8} {'Cuenta':<12} "
        f"{'Debit':>15} {'Credit':>15} {'Saldo':>15}  Memo"
    )
    print(f"   {'-'*12} {'-'*10} {'-'*8} {'-'*12} {'-'*15} {'-'*15} {'-'*15}  {'-'*40}")

    for je in asientos:
        fecha = str(je.get("ReferenceDate", ""))[:10]
        number = je.get("Number", "")
        trans_code = je.get("TransactionCode", "") or ""

        for l in je.get("JournalEntryLines", []):
            if l.get("ShortName") != "C0489":
                continue

            debit = float(l.get("Debit", 0) or 0)
            credit = float(l.get("Credit", 0) or 0)
            saldo_acumulado_local += debit - credit

            cuenta = l.get("AccountCode", "")
            memo = (l.get("LineMemo", "") or "")[:40]

            print(
                f"   {fecha:<12} {number:<10} {trans_code:<8} {cuenta:<12} "
                f"{debit:>15,.2f} {credit:>15,.2f} {saldo_acumulado_local:>15,.2f}  {memo}"
            )

    print(
        f"\n   ── SALDO ACUMULADO FINAL EN MONEDA LOCAL: {saldo_acumulado_local:,.2f}"
    )
    print(f"   ── Si es NEGATIVO, el cliente tiene saldo a favor")
    print(
        f"   ── Tania reporta saldo a favor de ₡3,057.71 → esperamos algo como -3,057.71"
    )


# =============================================================================
# PASO 3: ¿Hay un endpoint más directo? Probar BusinessPartner expand a Journals
# =============================================================================


def paso3_buscar_endpoint_directo(conn):
    separador("PASO 3 — ¿Existe endpoint más directo para 'Saldo de cuenta'?")

    candidatos = [
        "BusinessPartners('C0489')/JournalEntries",
        "BPAccountBalance",
        "ChartOfAccounts",
    ]

    for c in candidatos:
        print(f">> Probando: {c}")
        try:
            r = conn.get(c, {"$top": 1})
            if r is not None and "value" in r:
                print(f"   ✅ Existe")
            elif r is not None:
                print(f"   ⚠️ Respondió: {str(r)[:200]}")
            else:
                print(f"   ❌")
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")
        print()


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return
    try:
        paso1_journal_344885(conn)
        paso2_todos_los_asientos_c0489(conn)
        paso3_buscar_endpoint_directo(conn)
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
