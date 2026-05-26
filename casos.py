"""
investigar_casos.py - Químicas Unidas
Script de SOLO LECTURA para investigar 3 casos puntuales:

CASO A: PR/sobrantes de Marlon Guadamuz (C0489) — Tania ve ₡3,057.71, nosotros vemos varios
CASO B: PR históricos de Colono Agropecuario (C0161) — no deben salir los viejos
CASO C: Vendedor por dirección en Lagar (C0139) — Desamparados=9, Jacó=7

NO MODIFICA NADA. Solo imprime JSON crudo para que veamos qué nos devuelve SAP.

Uso:
    python investigar_casos.py
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def separador(titulo: str):
    print("\n" + "=" * 80)
    print(f"  {titulo}")
    print("=" * 80)


# =============================================================================
# CASO A: Sobrantes PR de Marlon Guadamuz C0489
# =============================================================================


def investigar_pr_marlon(conn: ServiceLayerConnection):
    separador("CASO A — PR/Sobrantes de C0489 (Marlon Guadamuz)")
    print("Tania ve UN solo saldo a favor: PR 60623 del 07/05/26 por COL 3,057.71")
    print("Nuestro código actual trae varios. Veamos qué dice SAP crudo.\n")

    # 1. Todos los IncomingPayments del cliente (sin filtrar por Cancelled)
    print(
        ">> Todos los IncomingPayments de C0489 (incluyendo cancelados, para ver todo):"
    )
    pagos = conn.get(
        "IncomingPayments",
        {
            "$filter": "CardCode eq 'C0489'",
            "$select": "DocNum,DocEntry,DocDate,DocCurrency,TransferSum,CashSum,DocTotal,"
            "Cancelled,DocumentStatus,Remarks,Reference1",
            "$orderby": "DocDate desc",
            "$top": 50,
        },
    )

    if not pagos or "value" not in pagos:
        print("   (sin resultados)")
        return

    print(f"   Total pagos encontrados: {len(pagos['value'])}\n")

    for p in pagos["value"]:
        print(
            f"   PR {p.get('DocNum')} | Fecha: {str(p.get('DocDate',''))[:10]} | "
            f"Moneda: {p.get('DocCurrency')} | Cancelled: {p.get('Cancelled')} | "
            f"Status: {p.get('DocumentStatus')}"
        )
        print(
            f"      TransferSum: {p.get('TransferSum')} | CashSum: {p.get('CashSum')} | "
            f"DocTotal: {p.get('DocTotal')}"
        )
        print(
            f"      Reference1: {p.get('Reference1','')} | Remarks: {p.get('Remarks','')[:60]}"
        )

    # 2. Detalle del PR 60623 específicamente (el que Tania dice que es el correcto)
    print("\n>> Detalle completo del PR 60623 (el que Tania confirma como correcto):")
    pr_target = conn.get(
        "IncomingPayments",
        {
            "$filter": "DocNum eq 60623 and CardCode eq 'C0489'",
        },
    )
    if pr_target and pr_target.get("value"):
        print(
            json.dumps(pr_target["value"][0], indent=2, ensure_ascii=False, default=str)
        )
    else:
        print("   (no encontrado por DocNum 60623 — quizá el DocEntry sea otro)")

    # 3. Probar si existe campo OpenSum / OpenAmount en IncomingPayments
    print("\n>> Probar campos de saldo abierto (OpenSum, OpenSumFC):")
    prueba = conn.get(
        "IncomingPayments",
        {
            "$filter": "CardCode eq 'C0489' and Cancelled eq 'tNO'",
            "$top": 3,
        },
    )
    if prueba and prueba.get("value"):
        primer_pago = prueba["value"][0]
        print(f"   Llaves disponibles en IncomingPayments:")
        for k in sorted(primer_pago.keys()):
            if "open" in k.lower() or "balance" in k.lower() or "applied" in k.lower():
                print(f"      {k}: {primer_pago[k]}")
        # Mostrar todas las llaves por si hay algo no obvio
        print(f"\n   TODAS las llaves (para identificar campo de sobrante real):")
        print(f"   {sorted(primer_pago.keys())}")


# =============================================================================
# CASO B: PR/NC históricos de Colono Agropecuario C0161
# =============================================================================


def investigar_colono_c0161(conn: ServiceLayerConnection):
    separador("CASO B — PR/NC históricos de C0161 (Colono Agropecuario)")
    print("Tania quiere que NO salgan los saldos a favor viejos (2018-2022).")
    print("Veamos qué tiene SAP.\n")

    # PR antiguos
    print(">> IncomingPayments de C0161 (todos, ordenados por fecha):")
    pagos = conn.get(
        "IncomingPayments",
        {
            "$filter": "CardCode eq 'C0161' and Cancelled eq 'tNO'",
            "$select": "DocNum,DocDate,DocCurrency,TransferSum,CashSum,DocTotal,"
            "DocumentStatus,Remarks",
            "$orderby": "DocDate asc",
            "$top": 50,
        },
    )
    if pagos and pagos.get("value"):
        print(f"   Total: {len(pagos['value'])}")
        for p in pagos["value"]:
            print(
                f"   PR {p.get('DocNum')} | {str(p.get('DocDate',''))[:10]} | "
                f"{p.get('DocCurrency')} | Total: {p.get('DocTotal')} | "
                f"Status: {p.get('DocumentStatus')}"
            )

    # NC antiguos
    print("\n>> CreditNotes abiertas de C0161:")
    nc = conn.get(
        "CreditNotes",
        {
            "$filter": "CardCode eq 'C0161' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocDate,DocDueDate,DocTotal,DocTotalFc,PaidToDate,DocCurrency",
            "$orderby": "DocDate asc",
            "$top": 50,
        },
    )
    if nc and nc.get("value"):
        print(f"   Total NC abiertas: {len(nc['value'])}")
        for n in nc["value"]:
            print(
                f"   NC {n.get('DocNum')} | {str(n.get('DocDate',''))[:10]} | "
                f"{n.get('DocCurrency')} | Total: {n.get('DocTotal')} | "
                f"Pagado: {n.get('PaidToDate')}"
            )


# =============================================================================
# CASO C: Vendedor por dirección en Lagar C0139
# =============================================================================


def investigar_lagar_c0139(conn: ServiceLayerConnection):
    separador("CASO C — Vendedor por dirección en C0139 (Lagar / Shindaiwa)")
    print("Tania dice: Desamparados=9 (José Chacón), Jacó=7 (Berny Marín)")
    print("Veamos la estructura de BPAddresses.\n")

    bp = conn.get(
        "BusinessPartners('C0139')",
        {
            "$select": "CardCode,CardName,SalesPersonCode,BPAddresses",
        },
    )
    if not bp:
        print("   (no se obtuvo el BP)")
        return

    print(f"   SalesPersonCode del encabezado: {bp.get('SalesPersonCode')}")
    print(f"   Total direcciones: {len(bp.get('BPAddresses', []))}\n")

    print(">> Estructura completa de la PRIMERA dirección (para ver TODAS las llaves):")
    direcciones = bp.get("BPAddresses", [])
    if direcciones:
        print(json.dumps(direcciones[0], indent=2, ensure_ascii=False, default=str))

    print(
        "\n>> Resumen de todas las direcciones (buscando código de vendedor por dirección):"
    )
    for d in direcciones:
        # Buscamos cualquier campo que parezca código de vendedor por dirección
        candidatos = {}
        for k, v in d.items():
            if v in (None, "", 0, -1):
                continue
            kl = k.lower()
            if (
                "sales" in kl
                or "vendedor" in kl
                or "agent" in kl
                or "zona" in kl
                or "u_" in kl
            ):
                candidatos[k] = v
        print(
            f"\n   AddressName: {d.get('AddressName')} | Type: {d.get('AddressType')}"
        )
        for k, v in candidatos.items():
            print(f"      {k}: {v}")


# =============================================================================
# MAIN
# =============================================================================


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("Error de conexión a SAP")
        return
    try:
        investigar_pr_marlon(conn)
        investigar_colono_c0161(conn)
        investigar_lagar_c0139(conn)
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
