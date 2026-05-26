"""
investigar_v7_saldo_real.py - Químicas Unidas

Reproducir la pantalla 'Saldo de cuenta - C0489' que ve Tania,
usando JournalEntries y filtrando en código las líneas con ShortName='C0489'.

VALIDACIÓN: el saldo acumulado final debe coincidir con lo que Tania ve.
"""

import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        print("=" * 100)
        print("REPRODUCIENDO 'SALDO DE CUENTA - C0489' (Marlon Guadamuz)")
        print("Período: 01/01/2026 - 31/12/2026  (mismo que el screenshot de Tania)")
        print("=" * 100)

        # Paginar todos los JournalEntries del rango
        fecha_desde = "2026-01-01"
        fecha_hasta = "2026-12-31"

        todos_asientos = []
        skip = 0
        page_size = 20

        while True:
            resp = conn.get(
                "JournalEntries",
                {
                    "$filter": f"ReferenceDate ge '{fecha_desde}' and ReferenceDate le '{fecha_hasta}'",
                    "$orderby": "ReferenceDate,JdtNum",
                    "$top": page_size,
                    "$skip": skip,
                },
            )

            if not resp or not resp.get("value"):
                break

            todos_asientos.extend(resp["value"])

            if len(resp["value"]) < page_size:
                break

            skip += page_size

            # Tope de seguridad
            if skip >= 100000:
                print(f"⚠️ Llegamos a {skip} sin terminar, abortando.")
                break

            # Progreso cada 500
            if skip % 500 == 0:
                print(f"   ... {skip} asientos descargados")

        print(f"\nTotal asientos descargados: {len(todos_asientos)}\n")

        # Filtrar y mostrar solo líneas que tocan a C0489
        print(
            f"{'Fecha':<12} {'JdtNum':<10} {'Cuenta':<12} {'Debit':>15} {'Credit':>15} {'Saldo':>15}  Memo"
        )
        print("-" * 130)

        saldo = 0.0
        movimientos_c0489 = 0

        for je in todos_asientos:
            fecha = str(je.get("ReferenceDate", ""))[:10]
            jdt = je.get("JdtNum", "")

            for linea in je.get("JournalEntryLines", []) or []:
                if linea.get("ShortName") != "C0489":
                    continue

                debit = float(linea.get("Debit", 0) or 0)
                credit = float(linea.get("Credit", 0) or 0)
                saldo += debit - credit

                cuenta = linea.get("AccountCode", "")
                memo = (linea.get("LineMemo", "") or "")[:55]

                movimientos_c0489 += 1
                print(
                    f"{fecha:<12} {jdt:<10} {cuenta:<12} "
                    f"{debit:>15,.2f} {credit:>15,.2f} {saldo:>15,.2f}  {memo}"
                )

        print("-" * 130)
        print(f"\nTotal movimientos de C0489 en el período: {movimientos_c0489}")
        print(f"SALDO ACUMULADO FINAL: {saldo:,.2f}")

        if saldo < 0:
            print(f"   → Cliente tiene SALDO A FAVOR de {abs(saldo):,.2f}")
        elif saldo > 0:
            print(f"   → Cliente DEBE {saldo:,.2f}")
        else:
            print(f"   → Cuenta en cero")

        print(
            f"\nTania en su pantalla 'Saldo de cuenta' ve: COL (3,057.71) saldo a favor"
        )
        print(f"¿Cuadra con nuestro cálculo?")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
