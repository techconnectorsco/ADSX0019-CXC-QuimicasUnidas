"""
investigar_v6.py - Químicas Unidas

Hallazgo previo: JdtNum eq 344885 SÍ funciona.
Pero el v5 no imprimió las líneas porque return prematuro o el formato no cuadró.

Aquí:
1. Imprimimos completo el JdtNum 344885 — todas sus líneas.
2. Probamos sintaxis correcta de filtro: ContraAccount, o por ShortName con CrossJoin.
"""

import json
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return
    try:
        # =====================================================================
        # 1. JdtNum 344885 — imprimir TODO sin filtrar
        # =====================================================================
        print("=" * 90)
        print("JOURNAL ENTRY 344885 (PR 60623 de Marlon)")
        print("=" * 90)

        resp = conn.get("JournalEntries", {"$filter": "JdtNum eq 344885"})
        if not resp or not resp.get("value"):
            print("No vino")
            return

        je = resp["value"][0]
        print(f"JdtNum:        {je.get('JdtNum')}")
        print(f"Number:        {je.get('Number')}")
        print(f"ReferenceDate: {je.get('ReferenceDate')}")
        print(f"TaxDate:       {je.get('TaxDate')}")
        print(f"DueDate:       {je.get('DueDate')}")
        print(f"Memo:          {je.get('Memo')}")
        print(f"TransactionCode: {je.get('TransactionCode')}")
        print(f"ProjectCode:   {je.get('ProjectCode')}")
        print(f"DocumentType:  {je.get('DocumentType')}")

        lineas = je.get("JournalEntryLines", []) or []
        print(f"\nTotal líneas en el asiento: {len(lineas)}\n")

        for i, l in enumerate(lineas):
            print(f"--- Línea {i} ---")
            # Imprimir todos los campos no vacíos
            for k in sorted(l.keys()):
                v = l[k]
                if v in (None, "", 0, 0.0, [], {}):
                    continue
                print(f"  {k}: {v}")
            print()

        # =====================================================================
        # 2. Probar sintaxis correcta del filtro por ShortName
        # =====================================================================
        print("\n" + "=" * 90)
        print("PROBANDO SINTAXIS DE FILTRO POR LÍNEA")
        print("=" * 90)

        # Variante 1: filtro directo sobre el header (a ver si ShortName se expone)
        print("\n>> Variante 1: $filter=ShortName eq 'C0489' (sobre header)")
        r1 = conn.get(
            "JournalEntries",
            {
                "$filter": "ShortName eq 'C0489'",
                "$top": 3,
            },
        )
        if r1 and "value" in r1:
            print(f"   ✅ Funcionó: {len(r1['value'])} resultados")

        # Variante 2: con TransId range (sin filtro de línea)
        print("\n>> Variante 2: rango de fechas SIN filtro de línea (ReferenceDate)")
        r2 = conn.get(
            "JournalEntries",
            {
                "$filter": "ReferenceDate ge '2026-05-01' and ReferenceDate le '2026-05-31'",
                "$top": 3,
                "$select": "JdtNum,Number,ReferenceDate,Memo",
            },
        )
        if r2 and "value" in r2:
            print(f"   ✅ Funcionó: {len(r2['value'])} resultados")
            for je2 in r2["value"]:
                print(
                    f"      JdtNum {je2.get('JdtNum')} | {str(je2.get('ReferenceDate',''))[:10]} | {je2.get('Memo','')[:50]}"
                )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
