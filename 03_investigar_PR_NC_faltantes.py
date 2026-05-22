"""
==========================================================================
SCRIPT 3 — INVESTIGACIÓN: DOCUMENTOS PR (PAGOS A CUENTA) Y NC FALTANTES
==========================================================================
Investiga puntos C1, C2 de los comentarios de Tania:

C1. C0489, C0250, C0327 tienen un sobrante de pago PR que no salió en el
    estado de cuenta. PR y NC deben reflejarse.
C2. En varios clientes de muestra se repite la misma situación.

OBJETIVO:
- Identificar QUÉ tipos de documentos están en la cuenta de cobro de estos
  clientes en SAP (facturas, notas de crédito, pagos a cuenta, anticipos)
- Comparar contra lo que main.py/agentes.py están extrayendo actualmente
- Determinar si nuestro filtro está excluyendo PR/NC indebidamente

USO:
    python 03_investigar_PR_NC_faltantes.py
"""

import sys
from typing import List, Dict
from datetime import datetime

from modules.database.conexion import ServiceLayerConnection

# Clientes reportados por Tania con sobrantes PR no visibles
CLIENTES_INVESTIGAR = ["C0489", "C0250", "C0327"]


def obtener_partidas_abiertas(conn, card_code: str) -> List[Dict]:
    """
    Trae TODAS las partidas abiertas del cliente desde SAP, sin filtrar por tipo.
    Esto incluye facturas (IN), notas de crédito (CN), pagos a cuenta (PR),
    anticipos (DT), notas de débito (ND), etc.
    """
    print(f"\n>>> Consultando partidas abiertas de {card_code}...")

    # Endpoint del Service Layer para partidas abiertas
    # Probamos primero con InternalReconciliationOpenTrans
    todas_partidas = []

    # Estrategia 1: Journal Entries que afecten al cliente
    # Estrategia 2: Usar el endpoint específico de partidas
    # En SAP B1 Service Layer, lo más confiable es consultar JournalEntries
    # filtrando por ShortName (CardCode)

    # Pero también podemos consultar directamente cada tipo de documento:
    tipos_documento = [
        ("Invoices", "Facturas (FA)"),
        ("CreditNotes", "Notas de Crédito (NC)"),
        ("IncomingPayments", "Pagos Recibidos (PR)"),
        ("JournalEntries", "Asientos Contables (incluye sobrantes/ajustes)"),
    ]

    for endpoint, descripcion in tipos_documento:
        print(f"  [{descripcion}]")
        try:
            if endpoint == "JournalEntries":
                # JournalEntries no se filtra por CardCode directo, sino por línea
                filter_q = f"JournalEntryLines/any(d: d/ShortName eq '{card_code}')"
            else:
                filter_q = f"CardCode eq '{card_code}'"

            params = {
                "$select": (
                    "DocEntry,DocNum,DocDate,DocDueDate,DocTotal,DocCurrency,DocumentStatus"
                    if endpoint != "JournalEntries"
                    else "JdtNum,ReferenceDate,DueDate,Memo,TransactionCode"
                ),
                "$filter": filter_q,
                "$top": 50,
                "$orderby": (
                    "DocDate desc"
                    if endpoint != "JournalEntries"
                    else "ReferenceDate desc"
                ),
            }

            resp = conn.session.get(
                f"{conn.base_url}/{endpoint}",
                params=params,
                verify=False,
            )

            if not resp.ok:
                print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            docs = data.get("value", [])
            print(f"    Encontrados: {len(docs)} documentos")

            # Mostrar los últimos 5
            for doc in docs[:5]:
                if endpoint == "JournalEntries":
                    print(
                        f"      JDT {doc.get('JdtNum')} | "
                        f"{doc.get('ReferenceDate', '')[:10]} | "
                        f"Trans: {doc.get('TransactionCode', '')} | "
                        f"{(doc.get('Memo') or '')[:50]}"
                    )
                else:
                    estatus = doc.get("DocumentStatus", "")
                    print(
                        f"      Doc {doc.get('DocNum')} | "
                        f"{doc.get('DocDate', '')[:10]} | "
                        f"Total: {doc.get('DocCurrency', '')} {doc.get('DocTotal', 0):>12,.2f} | "
                        f"Status: {estatus}"
                    )
                todas_partidas.append(
                    {**doc, "_tipo": descripcion, "_endpoint": endpoint}
                )

        except Exception as e:
            print(f"    EXCEPCIÓN: {e}")

    return todas_partidas


def replicar_query_main(conn, card_code: str):
    """
    Replica EXACTAMENTE la query que usa main.py para extraer documentos
    y compara con lo que vimos arriba. Si nuestra query está filtrando algo
    que no debería, aquí lo veremos.
    """
    print(f"\n--- Replicando query actual de main.py para {card_code} ---")

    # Esta es la query que usa main.py / agentes.py basada en lo visto en
    # los archivos. AJUSTAR si difiere de tu implementación real.
    # Si tu código usa un endpoint custom o una vista, dímelo y lo cambio.

    filter_q = f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'"
    select = ",".join(
        [
            "DocEntry",
            "DocNum",
            "DocDate",
            "DocDueDate",
            "DocTotal",
            "DocTotalSys",
            "DocCurrency",
            "PaidToDate",
            "PaidToDateFC",
            "U_NumConsecutivo",
            "NumAtCard",
            "DocType",
        ]
    )

    resp = conn.session.get(
        f"{conn.base_url}/Invoices",
        params={
            "$select": select,
            "$filter": filter_q,
            "$top": 100,
        },
        verify=False,
    )

    if not resp.ok:
        print(f"  ERROR: {resp.status_code}")
        return

    data = resp.json()
    docs = data.get("value", [])
    print(f"  Facturas abiertas según main.py: {len(docs)}")
    print(f"  ¡ATENCIÓN! Solo trae Invoices. NC, PR y otros NO están aquí.")

    total_facturas = sum(d.get("DocTotal", 0) - d.get("PaidToDate", 0) for d in docs)
    print(f"  Saldo de solo facturas: {total_facturas:,.2f}")


def comparar_con_balance_total(conn, card_code: str):
    """
    Compara el saldo total que SAP reporta para el cliente vs la suma de
    documentos abiertos que estamos extrayendo. Si hay diferencia, faltan documentos.
    """
    print(f"\n--- Comparando con saldo total reportado por SAP para {card_code} ---")

    resp = conn.session.get(
        f"{conn.base_url}/BusinessPartners('{card_code}')",
        params={
            "$select": "CardCode,CardName,CurrentAccountBalance,CurrentAccountBalanceFC,CurrentAccountBalanceSys"
        },
        verify=False,
    )
    if not resp.ok:
        print(f"  ERROR: {resp.status_code}")
        return

    bp = resp.json()
    print(f"  Cliente: {bp.get('CardName')}")
    print(
        f"  CurrentAccountBalance (CRC): {bp.get('CurrentAccountBalance', 0):>15,.2f}"
    )
    print(
        f"  CurrentAccountBalanceFC (USD): {bp.get('CurrentAccountBalanceFC', 0):>15,.2f}"
    )
    print(
        f"  CurrentAccountBalanceSys:       {bp.get('CurrentAccountBalanceSys', 0):>15,.2f}"
    )
    print(f"\n  >>> Si este saldo NO coincide con la suma de facturas abiertas,")
    print(
        f"      entonces hay documentos (NC, PR, anticipos, etc) que NO estamos extrayendo."
    )


def main():
    print("=" * 70)
    print("SCRIPT 3 - INVESTIGACIÓN DE PR Y NC FALTANTES")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("ERROR: No se pudo conectar a SAP")
        sys.exit(1)

    for code in CLIENTES_INVESTIGAR:
        print("\n" + "█" * 70)
        print(f"  ANÁLISIS DE CLIENTE {code}")
        print("█" * 70)

        # 1. Ver TODAS las partidas (facturas, NC, PR, asientos)
        obtener_partidas_abiertas(conn, code)

        # 2. Replicar la query que usa main.py
        replicar_query_main(conn, code)

        # 3. Comparar contra saldo total que reporta SAP
        comparar_con_balance_total(conn, code)

    print("\n" + "=" * 70)
    print("INVESTIGACIÓN COMPLETADA")
    print("=" * 70)
    print("Comparte conmigo la salida de consola completa.")
    print("Especialmente para cada cliente:")
    print("  - Cuántas Facturas, NC, PR y Asientos tiene")
    print("  - El saldo total reportado por SAP vs la suma de solo facturas")


if __name__ == "__main__":
    main()
