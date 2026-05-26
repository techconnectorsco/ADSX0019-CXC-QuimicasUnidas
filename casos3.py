"""
investigar_casos_v3.py - Químicas Unidas

OBJETIVO: Encontrar DÓNDE en SAP está el saldo a favor real de C0489 (₡3,057.71)
que ve Tania, pero que nosotros no podemos calcular bien.

HALLAZGOS PREVIOS:
- IncomingPayments NO tiene DocumentStatus, OpenSum, ni Applied.
- TransferSum - SumApplied de cada PR NO da el saldo a favor real del cliente.
- Tania ve ₡3,057.71 a favor, pero la matemática del PR 60623 da otra cosa.

ESTRATEGIA: probar 5 vías distintas y comparar resultados con lo que Tania ve.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def separador(titulo: str):
    print("\n" + "=" * 80)
    print(f"  {titulo}")
    print("=" * 80)


def imprimir_no_vacios(d: dict, indent: int = 6):
    """Imprime un dict solo con campos no nulos/vacíos."""
    pad = " " * indent
    for k in sorted(d.keys()):
        v = d[k]
        if v in (None, "", 0, 0.0, [], {}):
            continue
        if isinstance(v, list):
            print(f"{pad}{k}: (lista, {len(v)} items)")
        elif isinstance(v, dict):
            print(f"{pad}{k}: (dict con {len(v)} llaves)")
        else:
            print(f"{pad}{k}: {v}")


# =============================================================================
# VÍA 1 — CurrentAccountBalance crudo del BP
# =============================================================================


def via1_balance_bp(conn):
    separador("VÍA 1 — CurrentAccountBalance + campos de saldo del BP")
    print(
        "Si Tania ve ₡3,057.71 a favor, el balance del BP debe reflejar algo coherente.\n"
    )

    bp = conn.get("BusinessPartners('C0489')")
    if not bp:
        print("   (no se obtuvo)")
        return

    # Campos relacionados con saldos/balances/montos
    print(">> Campos del BP relacionados con saldos/balances:")
    candidatos = []
    for k in sorted(bp.keys()):
        kl = k.lower()
        if any(
            x in kl
            for x in [
                "balance",
                "amount",
                "credit",
                "debit",
                "open",
                "total",
                "current",
                "sum",
            ]
        ):
            candidatos.append((k, bp[k]))

    for k, v in candidatos:
        if v not in (None, "", 0, 0.0):
            print(f"   {k}: {v}")

    print(f"\n   Currency del BP: {bp.get('Currency')}")
    print(f"   CardName: {bp.get('CardName')}")


# =============================================================================
# VÍA 2 — InternalReconciliations
# =============================================================================


def via2_reconciliaciones(conn):
    separador("VÍA 2 — InternalReconciliations de C0489")
    print("Cuando SAP aplica un sobrante a una factura posterior, lo registra aquí.\n")

    # Primero ver si el endpoint existe y qué campos tiene
    print(">> Estructura del endpoint InternalReconciliations:")
    resp = conn.get("InternalReconciliations", {"$top": 1})
    if not resp:
        print("   ⚠️  Endpoint no respondió o no existe en esta versión")
    elif resp.get("value"):
        primera = resp["value"][0]
        print(f"   Llaves disponibles: {sorted(primera.keys())}\n")

        # Ahora filtrar por C0489
        print(">> Reconciliaciones de C0489:")
        recs = conn.get(
            "InternalReconciliations",
            {
                "$filter": "CardCode eq 'C0489'",
                "$top": 50,
                "$orderby": "ReconDate desc",
            },
        )
        if recs and recs.get("value"):
            print(f"   Total: {len(recs['value'])}\n")
            for r in recs["value"][:10]:
                print(f"   --- Reconciliación ---")
                imprimir_no_vacios(r)
                print()
        else:
            print("   (sin reconciliaciones)")
    else:
        print("   (sin datos en endpoint)")


# =============================================================================
# VÍA 3 — JournalEntries de la cuenta de cliente para C0489
# =============================================================================


def via3_journal_entries(conn):
    separador("VÍA 3 — JournalEntries (asientos contables) de C0489")
    print("Los asientos del BP en la cuenta de control deben dar el saldo neto real.\n")

    # JournalEntries tiene líneas, y cada línea tiene ShortName (CardCode) y Debit/Credit
    print(">> Probar endpoint JournalEntries con ShortName filtrado:")
    # Esto puede ser muy pesado, probemos con un top pequeño primero
    resp = conn.get(
        "JournalEntries",
        {
            "$top": 1,
        },
    )
    if not resp or not resp.get("value"):
        print("   (endpoint no devuelve datos sin filtro o no existe)")
        return

    primero = resp["value"][0]
    print(f"   Llaves del JournalEntry: {sorted(primero.keys())[:20]}...")

    if "JournalEntryLines" in primero:
        if primero["JournalEntryLines"]:
            print(
                f"\n   Llaves de una línea: {sorted(primero['JournalEntryLines'][0].keys())}"
            )


# =============================================================================
# VÍA 4 — SQLQueries (vistas/queries guardadas)
# =============================================================================


def via4_sql_queries(conn):
    separador("VÍA 4 — Endpoint SQLQueries (queries guardadas)")
    print("Si Novitec o el cliente tiene queries guardadas, podemos verlas.\n")

    resp = conn.get("SQLQueries", {"$top": 20, "$select": "SqlCode,SqlName,SqlText"})
    if not resp or not resp.get("value"):
        print("   (sin queries guardadas o endpoint no disponible)")
        return

    print(f"   Total queries disponibles: {len(resp['value'])}\n")
    for q in resp["value"]:
        nombre = q.get("SqlName", "")
        codigo = q.get("SqlCode", "")
        # Buscar las que mencionen saldo, sobrante, PR, a favor
        texto = (q.get("SqlText", "") or "").lower()
        if any(
            palabra in (nombre.lower() + " " + texto)
            for palabra in [
                "saldo",
                "favor",
                "sobrante",
                "estado",
                "cuenta",
                "cxc",
                "balance",
            ]
        ):
            print(f"   {codigo}: {nombre}")
            # Mostrar primeras líneas del SQL
            primeras_lineas = (q.get("SqlText", "") or "")[:300]
            print(f"      SQL (primeros 300 chars): {primeras_lineas}")
            print()


# =============================================================================
# VÍA 5 — Vista de antigüedad de saldos (CustomerRefundRequest, AgingReport)
# =============================================================================


def via5_endpoints_aging(conn):
    separador("VÍA 5 — Probar endpoints de antigüedad / reportes")
    print("SAP B1 a veces expone reportes como endpoints.\n")

    endpoints_probar = [
        "CustomerRefundRequests",
        "AgingReports",
        "AccountBalanceReport",
        "BusinessPartnerAgingReports",
        "CreditNoteRequests",
    ]

    for ep in endpoints_probar:
        print(f">> Probando /{ep}:")
        resp = conn.get(ep, {"$top": 1})
        if resp is None:
            print(f"   ❌ Endpoint no existe o sin permiso\n")
        elif "value" in resp and resp["value"]:
            print(f"   ✅ EXISTE - Llaves: {sorted(resp['value'][0].keys())}\n")
        else:
            print(f"   ⚠️  Existe pero sin datos\n")


# =============================================================================
# VÍA 6 — Examinar TODOS los documentos abiertos del C0489 con suma neta
# =============================================================================


def via6_neto_completo(conn):
    separador("VÍA 6 — Recalcular saldo neto de C0489 desde cero")
    print("Sumar facturas abiertas + restar NC abiertas + restar PR no aplicados.")
    print("Ver si la diferencia da los ₡3,057.71 o se acerca.\n")

    # 1. Facturas abiertas
    print(">> Facturas abiertas:")
    invs = conn.get(
        "Invoices",
        {
            "$filter": "CardCode eq 'C0489' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocDate,DocTotal,PaidToDate,DocCurrency",
            "$top": 100,
        },
    )
    total_facturas_abiertas = 0
    if invs and invs.get("value"):
        for f in invs["value"]:
            if f.get("DocCurrency") in ["COL", "CRC"]:
                pendiente = (f.get("DocTotal", 0) or 0) - (f.get("PaidToDate", 0) or 0)
                total_facturas_abiertas += pendiente
                print(
                    f"   FAC {f['DocNum']} | {str(f.get('DocDate',''))[:10]} | "
                    f"Total: {f.get('DocTotal')} | Pagado: {f.get('PaidToDate')} | "
                    f"Pendiente: {pendiente}"
                )
        print(
            f"   ── Total pendiente CRC en facturas abiertas: {total_facturas_abiertas}\n"
        )
    else:
        print("   (sin facturas abiertas)\n")

    # 2. CreditNotes abiertas
    print(">> CreditNotes abiertas:")
    ncs = conn.get(
        "CreditNotes",
        {
            "$filter": "CardCode eq 'C0489' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocDate,DocTotal,PaidToDate,DocCurrency",
            "$top": 100,
        },
    )
    total_nc_abiertas = 0
    if ncs and ncs.get("value"):
        for n in ncs["value"]:
            if n.get("DocCurrency") in ["COL", "CRC"]:
                pendiente = (n.get("DocTotal", 0) or 0) - (n.get("PaidToDate", 0) or 0)
                total_nc_abiertas += pendiente
                print(
                    f"   NC {n['DocNum']} | {str(n.get('DocDate',''))[:10]} | "
                    f"Pendiente: {pendiente}"
                )
        print(f"   ── Total pendiente CRC en NC abiertas: {total_nc_abiertas}\n")
    else:
        print("   (sin NC abiertas)\n")

    # 3. BP balance
    bp = conn.get(
        "BusinessPartners('C0489')", {"$select": "CardCode,CurrentAccountBalance"}
    )
    if bp:
        print(f">> CurrentAccountBalance del BP: {bp.get('CurrentAccountBalance')}")

    print(f"\n>> CÁLCULO MANUAL:")
    print(f"   Facturas abiertas:  {total_facturas_abiertas:,.2f}")
    print(f"   - NC abiertas:      {total_nc_abiertas:,.2f}")
    print(f"   = Saldo neto:       {total_facturas_abiertas - total_nc_abiertas:,.2f}")
    print(f"\n   ¿Tania ve ₡3,057.71 a favor? Entonces el balance debe dar negativo")
    print(f"   o las facturas abiertas + sobrante histórico = lo del estado")


# =============================================================================
# MAIN
# =============================================================================


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("Error de conexión")
        return
    try:
        via1_balance_bp(conn)
        via2_reconciliaciones(conn)
        via3_journal_entries(conn)
        via4_sql_queries(conn)
        via5_endpoints_aging(conn)
        via6_neto_completo(conn)
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
