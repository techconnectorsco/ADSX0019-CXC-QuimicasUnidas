"""
investigar_v4_simple.py - Químicas Unidas

OBJETIVO ÚNICO:
Tania ve UN PR (60623) con sobrante de ₡3,057.71 en el estado de cuenta de C0489.
Los otros 12 pagos NO aparecen.

PREGUNTA: ¿Qué tiene DIFERENTE el PR 60623 vs los otros 12?

ESTRATEGIA: Traer el JSON COMPLETO crudo de los 13 pagos sin filtros,
sin $select, sin nada, y compararlos campo por campo.

NO ASUMIMOS NADA. Solo miramos los datos.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # Traer TODOS los pagos de C0489, sin filtros de campos
        print("=" * 80)
        print("TODOS LOS PAGOS DE C0489 — JSON CRUDO COMPLETO")
        print("=" * 80)

        resp = conn.get(
            "IncomingPayments",
            {
                "$filter": "CardCode eq 'C0489'",
                "$orderby": "DocDate desc",
            },
        )

        if not resp or not resp.get("value"):
            print("Sin pagos")
            return

        pagos = resp["value"]
        print(f"\nTotal pagos: {len(pagos)}\n")

        # Calcular para cada pago: cuánto entró vs cuánto se aplicó
        print(
            f"{'DocNum':<10} {'Fecha':<12} {'Cancelled':<10} "
            f"{'TransferSum':<15} {'CashSum':<12} {'SumApplied':<15} {'Diferencia':<15}"
        )
        print("-" * 95)

        for p in pagos:
            doc_num = p.get("DocNum")
            fecha = str(p.get("DocDate", ""))[:10]
            cancelled = p.get("Cancelled", "")
            transfer = float(p.get("TransferSum", 0) or 0)
            cash = float(p.get("CashSum", 0) or 0)
            entrada = transfer + cash

            # Sumar lo aplicado
            aplicado = 0
            for inv in p.get("PaymentInvoices", []) or []:
                aplicado += float(inv.get("SumApplied", 0) or 0)

            diferencia = round(entrada - aplicado, 2)

            marca = "  <-- 60623" if doc_num == 60623 else ""
            print(
                f"{doc_num:<10} {fecha:<12} {cancelled:<10} "
                f"{transfer:<15,.2f} {cash:<12,.2f} {aplicado:<15,.2f} {diferencia:<15,.2f}{marca}"
            )

        # Ahora el zoom: comparar el PR 60623 contra un pago "ordinario" (digamos el 60394)
        print("\n\n" + "=" * 80)
        print("COMPARACIÓN CAMPO POR CAMPO: PR 60623 vs PR 60394")
        print("=" * 80)
        print("Si hay diferencia en algún campo, ahí está la pista.\n")

        pr_target = next((p for p in pagos if p.get("DocNum") == 60623), None)
        pr_otro = next((p for p in pagos if p.get("DocNum") == 60394), None)

        if not pr_target or not pr_otro:
            print("No encontré uno de los dos pagos")
            return

        todas_llaves = sorted(set(list(pr_target.keys()) + list(pr_otro.keys())))

        print(
            f"{'CAMPO':<40} {'PR 60623 (Tania ve)':<30} {'PR 60394 (no aparece)':<30}"
        )
        print("-" * 100)

        for k in todas_llaves:
            v_target = pr_target.get(k)
            v_otro = pr_otro.get(k)

            # Saltar campos donde ambos están vacíos
            if v_target in (None, "", 0, 0.0, [], {}) and v_otro in (
                None,
                "",
                0,
                0.0,
                [],
                {},
            ):
                continue

            # Convertir a string corto
            def cortar(v):
                if isinstance(v, list):
                    return f"[lista {len(v)}]"
                if isinstance(v, dict):
                    return f"{{dict {len(v)}}}"
                s = str(v)
                return s if len(s) <= 28 else s[:25] + "..."

            s_target = cortar(v_target)
            s_otro = cortar(v_otro)

            # Marcar si son distintos
            marca = " <-- DIFIERE" if s_target != s_otro else ""
            print(f"{k:<40} {s_target:<30} {s_otro:<30}{marca}")

        # PaymentInvoices detalle de 60623
        print("\n\n" + "=" * 80)
        print("PaymentInvoices del PR 60623 — qué facturas aplicó")
        print("=" * 80)
        for inv in pr_target.get("PaymentInvoices") or []:
            print(
                f"  DocEntry factura aplicada: {inv.get('DocEntry')} | "
                f"SumApplied: {inv.get('SumApplied')} | "
                f"AppliedFC: {inv.get('AppliedFC')} | "
                f"InvoiceType: {inv.get('InvoiceType')}"
            )

        # ¿Y si el PR 60623 tiene una "factura" especial tipo "saldo a favor"?
        # Veamos los DocEntry de las facturas aplicadas y qué son realmente
        doc_entries_aplicados = [
            inv.get("DocEntry") for inv in (pr_target.get("PaymentInvoices") or [])
        ]
        if doc_entries_aplicados:
            print(f"\n>> Buscando qué son los DocEntry {doc_entries_aplicados}:")
            for de in doc_entries_aplicados:
                # Probar primero como Invoice
                inv_real = conn.get(
                    f"Invoices({de})",
                    {
                        "$select": "DocNum,DocEntry,DocTotal,DocTotalFc,DocCurrency,CardCode,DocDate"
                    },
                )
                if inv_real:
                    print(
                        f"   DocEntry {de} -> Invoice DocNum {inv_real.get('DocNum')} | "
                        f"Moneda: {inv_real.get('DocCurrency')} | "
                        f"Total: {inv_real.get('DocTotal')} | TotalFC: {inv_real.get('DocTotalFc')}"
                    )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
