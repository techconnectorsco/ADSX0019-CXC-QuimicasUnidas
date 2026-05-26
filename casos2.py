"""
investigar_casos_v2.py - Químicas Unidas

CORRECCIÓN: 'DocTotal' no es un campo válido en IncomingPayments.
Primero descubrimos la estructura real, luego repetimos casos A y B.
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


# =============================================================================
# PASO 0: Descubrir estructura de IncomingPayments
# =============================================================================


def descubrir_estructura_pagos(conn):
    separador("PASO 0 — Estructura real de IncomingPayments")
    print("Sin $select para que devuelva TODAS las llaves disponibles.\n")

    # Tomar UN solo pago de cualquier cliente para ver todas las llaves
    resp = conn.get("IncomingPayments", {"$top": 1})
    if not resp or not resp.get("value"):
        print("   (no se obtuvo nada)")
        return None

    pago = resp["value"][0]
    llaves = sorted(pago.keys())
    print(f"   Total llaves: {len(llaves)}\n")

    # Mostrar todas
    print("   TODAS LAS LLAVES:")
    for k in llaves:
        v = pago[k]
        # Mostrar valor solo si es escalar y útil
        if isinstance(v, (str, int, float, bool)) or v is None:
            print(f"      {k}: {v}")
        elif isinstance(v, list):
            print(f"      {k}: [lista con {len(v)} items]")
        else:
            print(f"      {k}: {type(v).__name__}")

    # Llaves candidatas para el "monto" del pago
    print("\n   CANDIDATAS para monto/saldo/aplicado/abierto:")
    for k in llaves:
        kl = k.lower()
        if any(
            x in kl
            for x in ["sum", "total", "amount", "applied", "open", "balance", "paid"]
        ):
            print(f"      {k}: {pago[k]}")

    return llaves


# =============================================================================
# CASO A (reintento): PR de C0489
# =============================================================================


def investigar_pr_marlon_v2(conn, llaves_validas):
    separador("CASO A v2 — PR/Sobrantes de C0489 (Marlon Guadamuz)")
    print("Tania ve UN solo saldo a favor: PR 60623 del 07/05/26 por COL 3,057.71\n")

    # Construir $select solo con las llaves que existen
    deseadas = [
        "DocNum",
        "DocEntry",
        "DocDate",
        "DocCurrency",
        "TransferSum",
        "CashSum",
        "CheckAccount",
        "Cancelled",
        "DocumentStatus",
        "Remarks",
        "Reference1",
        "Reference2",
    ]
    # Agregar cualquier campo de monto/saldo que exista
    for k in llaves_validas or []:
        kl = k.lower()
        if any(x in kl for x in ["sum", "total", "amount", "open", "applied"]):
            if k not in deseadas:
                deseadas.append(k)

    select_validos = [k for k in deseadas if k in (llaves_validas or [])]
    select_str = ",".join(select_validos)

    print(f">> Pagos de C0489 (Cancelled=tNO), select dinámico:")
    print(f"   Campos: {select_str}\n")

    pagos = conn.get(
        "IncomingPayments",
        {
            "$filter": "CardCode eq 'C0489' and Cancelled eq 'tNO'",
            "$select": select_str,
            "$orderby": "DocDate desc",
            "$top": 50,
        },
    )
    if not pagos or not pagos.get("value"):
        print("   (sin resultados)")
        return

    print(f"   Total pagos encontrados: {len(pagos['value'])}\n")

    for p in pagos["value"]:
        print(
            f"   PR {p.get('DocNum')} | Fecha: {str(p.get('DocDate',''))[:10]} | "
            f"Moneda: {p.get('DocCurrency')} | Status: {p.get('DocumentStatus')}"
        )
        # Imprimir cualquier campo de monto que tenga valor
        for k, v in p.items():
            if k in ("DocNum", "DocDate", "DocCurrency", "DocumentStatus", "Cancelled"):
                continue
            if v not in (None, "", 0, 0.0):
                print(f"      {k}: {v}")
        print()

    # Traer el detalle COMPLETO del PR 60623 (sin $select) para ver todos los campos
    print("\n>> Detalle COMPLETO del PR 60623 (sin $select):")
    detalle = conn.get(
        "IncomingPayments",
        {
            "$filter": "DocNum eq 60623 and CardCode eq 'C0489'",
        },
    )
    if detalle and detalle.get("value"):
        pr = detalle["value"][0]
        # Imprimir solo campos no nulos / no vacíos para que sea legible
        print("   {")
        for k in sorted(pr.keys()):
            v = pr[k]
            if v in (None, "", 0, 0.0, []):
                continue
            if isinstance(v, list):
                print(f"     {k}: (lista, {len(v)} items)")
                for i, item in enumerate(v):
                    print(
                        f"        [{i}] {json.dumps(item, ensure_ascii=False, default=str)}"
                    )
            else:
                print(f"     {k}: {v}")
        print("   }")
    else:
        print("   (no encontrado)")


# =============================================================================
# CASO B (reintento): PR de C0161
# =============================================================================


def investigar_colono_c0161_v2(conn, llaves_validas):
    separador("CASO B v2 — PR históricos de C0161 (Colono Agropecuario)")

    deseadas = [
        "DocNum",
        "DocDate",
        "DocCurrency",
        "TransferSum",
        "CashSum",
        "DocumentStatus",
        "Cancelled",
        "Remarks",
    ]
    for k in llaves_validas or []:
        kl = k.lower()
        if any(x in kl for x in ["sum", "total", "open", "applied"]):
            if k not in deseadas:
                deseadas.append(k)
    select_validos = [k for k in deseadas if k in (llaves_validas or [])]
    select_str = ",".join(select_validos)

    print(f">> Pagos de C0161 (Cancelled=tNO):\n   Campos: {select_str}\n")

    pagos = conn.get(
        "IncomingPayments",
        {
            "$filter": "CardCode eq 'C0161' and Cancelled eq 'tNO'",
            "$select": select_str,
            "$orderby": "DocDate asc",
            "$top": 50,
        },
    )
    if not pagos or not pagos.get("value"):
        print("   (sin resultados)")
        return

    print(f"   Total: {len(pagos['value'])}\n")
    for p in pagos["value"]:
        anio = str(p.get("DocDate", ""))[:4]
        print(
            f"   PR {p.get('DocNum')} | {str(p.get('DocDate',''))[:10]} ({anio}) | "
            f"{p.get('DocCurrency')} | Status: {p.get('DocumentStatus')}"
        )
        for k, v in p.items():
            if k in ("DocNum", "DocDate", "DocCurrency", "DocumentStatus", "Cancelled"):
                continue
            if v not in (None, "", 0, 0.0):
                print(f"      {k}: {v}")
        print()


# =============================================================================
# MAIN
# =============================================================================


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("Error de conexión")
        return
    try:
        llaves = descubrir_estructura_pagos(conn)
        investigar_pr_marlon_v2(conn, llaves)
        investigar_colono_c0161_v2(conn, llaves)
    finally:
        conn.logout()


if __name__ == "__main__":
    main()
