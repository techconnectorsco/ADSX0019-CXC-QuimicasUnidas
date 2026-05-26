"""
investigar_v8.py - Químicas Unidas

Necesitamos un filtro que el Service Layer entienda para traer SOLO
los Journal Entries que tocan a C0489, sin descargar miles de asientos.

Probamos campos del header del JournalEntry que apunten al BP.
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # 1. Primero: ver TODAS las llaves del header de un JournalEntry
        print("=" * 90)
        print("LLAVES DEL HEADER DE JournalEntry (no líneas)")
        print("=" * 90)
        resp = conn.get("JournalEntries", {"$top": 1})
        je = resp["value"][0]

        # Solo llaves del header (excluir listas)
        for k in sorted(je.keys()):
            v = je[k]
            if isinstance(v, list):
                continue
            print(f"  {k}: {v}")

        # 2. Probar filtros que apunten al BP
        print("\n\n" + "=" * 90)
        print("PROBAR FILTROS POR BP")
        print("=" * 90)

        filtros = [
            "BPCode eq 'C0489'",
            "CardCode eq 'C0489'",
            "ContraAccount eq 'C0489'",
            "BaseReference eq 'C0489'",
            "Reference1 eq 'C0489'",
        ]

        for f in filtros:
            print(f"\n>> $filter={f}")
            r = conn.get(
                "JournalEntries",
                {
                    "$filter": f,
                    "$top": 2,
                    "$select": "JdtNum,Number,ReferenceDate,Memo",
                },
            )
            if r is None:
                print("   ❌ Error")
            elif r.get("value"):
                print(f"   ✅ {len(r['value'])} resultados")
                for x in r["value"]:
                    print(
                        f"      JdtNum {x.get('JdtNum')} | {str(x.get('ReferenceDate',''))[:10]} | {x.get('Memo','')[:60]}"
                    )
            else:
                print(f"   ⚠️ Filtro válido pero 0 resultados")

        # 3. Si nada funciona en JournalEntries, probar el endpoint JournalEntryLines directamente
        print("\n\n" + "=" * 90)
        print("¿Existe endpoint JournalEntryLines como entidad navegable?")
        print("=" * 90)
        r = conn.get("JournalEntryLines", {"$top": 1})
        if r is None:
            print("❌ No existe ese endpoint")
        elif r.get("value"):
            print(f"✅ Existe, llaves: {sorted(r['value'][0].keys())}")
        else:
            print("⚠️ Existe pero vacío")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
