"""
investigar_v9.py - Químicas Unidas

ÚLTIMO INTENTO antes de pedir acceso HANA o SQLQuery a Novitec.

Probamos sintaxis avanzadas de OData que el Service Layer A VECES soporta
para filtrar JournalEntries por una propiedad de sus líneas (ShortName).
"""

import sys, os
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def probar(conn, descripcion: str, endpoint: str, params: dict):
    print(f"\n>> {descripcion}")
    print(f"   GET {endpoint}?{urllib.parse.urlencode(params)}")
    r = conn.get(endpoint, params)
    if r is None:
        print("   ❌ Error o no devolvió nada")
        return None
    if "value" in r:
        n = len(r["value"])
        print(f"   ✅ {n} resultados")
        if n > 0 and n <= 5:
            for x in r["value"][:5]:
                if isinstance(x, dict):
                    # imprimir solo 3-4 campos clave
                    keys = [
                        k
                        for k in (
                            "JdtNum",
                            "ReferenceDate",
                            "Memo",
                            "DocNum",
                            "DocDate",
                        )
                        if k in x
                    ]
                    print(f"      {' | '.join(f'{k}={x.get(k)}' for k in keys)}")
        return r
    else:
        print(f"   ⚠️ Respuesta sin 'value': {str(r)[:200]}")
        return r


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        print("=" * 90)
        print("INTENTOS DE FILTRO AVANZADO")
        print("=" * 90)

        # 1. $crossjoin
        probar(
            conn,
            "1. $crossjoin entre JournalEntries y JournalEntryLines",
            "$crossjoin(JournalEntries,JournalEntryLines)",
            {"$top": 1},
        )

        # 2. expand con filter dentro (OData v4)
        probar(
            conn,
            "2. $expand con filtro dentro de las líneas",
            "JournalEntries",
            {"$expand": "JournalEntryLines($filter=ShortName eq 'C0489')", "$top": 1},
        )

        # 3. Otra sintaxis any
        probar(
            conn,
            "3. any con paréntesis explícitos",
            "JournalEntries",
            {"$filter": "JournalEntryLines/any(d:d/ShortName eq 'C0489')", "$top": 1},
        )

        # 4. Probar IncomingPayments filtrando por CardCode + endpoints relacionados
        probar(
            conn,
            "4. ¿Existe BusinessPartners('C0489')?$expand=JournalEntryLines?",
            "BusinessPartners('C0489')",
            {"$expand": "JournalEntryLines"},
        )

        # 5. Probar el endpoint TaxInvoiceReport / específicos
        for ep in [
            "AccountSegmentationCategories",
            "Accounts",
            "BusinessPlaces",
            "FinancialReports",
            "FinancialPeriods",
        ]:
            probar(conn, f"5.x Endpoint {ep}", ep, {"$top": 1})

        # 6. Probar acción/función especial: B1Sessions, SqlQueries con name
        probar(
            conn,
            "6. SQLQueries listar todas con nombre",
            "SQLQueries",
            {"$select": "SqlCode,SqlName"},
        )

        # 7. Probar acción $count en JournalEntries con filtro de fecha como prueba
        probar(
            conn,
            "7. JournalEntries con $count y filtro fecha pequeña",
            "JournalEntries",
            {
                "$filter": "ReferenceDate eq '2026-05-07'",
                "$select": "JdtNum,Memo",
                "$top": 5,
            },
        )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
