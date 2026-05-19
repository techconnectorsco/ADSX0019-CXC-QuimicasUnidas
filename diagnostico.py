"""
diagnostico_sql.py - Químicas Unidas

OBJETIVO: Aislar exactamente qué carácter/palabra rompe el parser del
Service Layer al crear una SQLQuery temporal.

Probamos 4 variantes incrementales:
  V1: SELECT trivial (SELECT 1 FROM OCRD)
  V2: SELECT con JOIN simple (sin SUBSTRING/RIGHT/LENGTH)
  V3: SELECT con SUBSTRING (workaround ANSI)
  V4: SELECT con RIGHT/LENGTH (formato exacto de la query 398)

Solo crea y borra queries temporales. NO genera PDFs ni envía correos.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection


def probar_sql(conn, nombre_test, sql_text):
    """Intenta crear y luego borrar una query temporal. Reporta resultado."""
    query_name = f"RPA_DIAG_{nombre_test}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_name}')"

    # Limpieza preventiva
    try:
        conn.session.delete(url_del)
    except Exception:
        pass

    print(f"\n{'='*80}")
    print(f"🧪 TEST: {nombre_test}")
    print(f"{'='*80}")
    print(f"SQL ({len(sql_text)} chars):")
    print(sql_text)
    print()

    try:
        resp = conn.session.post(
            url_post,
            json={
                "SqlCode": query_name,
                "SqlName": f"TMP_{nombre_test}",
                "SqlText": sql_text,
            },
        )

        if resp.status_code in (200, 201):
            print(f"   ✅ CREADO OK (status {resp.status_code})")

            # Intentar ejecutarlo
            try:
                res = conn.get(f"SQLQueries('{query_name}')/List", {"$top": 3})
                if res and "value" in res:
                    print(
                        f"   ✅ EJECUTADO OK — filas devueltas (top 3): {len(res['value'])}"
                    )
                    if res["value"]:
                        print(f"      Campos: {list(res['value'][0].keys())}")
                        print(f"      Primera fila: {res['value'][0]}")
                else:
                    print(f"   ⚠️  Ejecutado pero sin datos")
            except Exception as e:
                print(f"   ⚠️  Error al ejecutar: {e}")
        else:
            print(f"   ❌ ERROR (status {resp.status_code})")
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message", {}).get("value", str(err))
                print(f"      Mensaje: {msg}")
            except Exception:
                print(f"      Body: {resp.text[:500]}")
    finally:
        # Limpieza final
        try:
            conn.session.delete(url_del)
        except Exception:
            pass


def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO DE SQL — aislar qué rompe el parser")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        # ---------- V1: SELECT trivial ----------
        v1 = 'SELECT "CardCode" FROM OCRD'
        probar_sql(conn, "V1_trivial", v1)

        # ---------- V2: SELECT con JOIN, sin funciones de string ----------
        v2 = (
            'SELECT T2."CardCode", T2."CardName" '
            "FROM OWTR T2 "
            'INNER JOIN OCRD T3 ON T3."CardCode"=T2."CardCode"'
        )
        probar_sql(conn, "V2_join_simple", v2)

        # ---------- V3: con SUBSTRING ----------
        v3 = (
            'SELECT T2."CardCode" FROM OWTR T2 '
            'WHERE T2."CardCode"=SUBSTRING(T2."CardCode",2,999)'
        )
        probar_sql(conn, "V3_substring", v3)

        # ---------- V4: con RIGHT/LENGTH (formato EXACTO query 398) ----------
        # Ojo: copiamos el fragmento EXACTO que la query 398 usa.
        v4 = (
            'SELECT T2."CardCode" FROM OWTR T2 '
            'WHERE T2."CardCode"=RIGHT(T2."CardCode",LENGTH(T2."CardCode")-1)'
        )
        probar_sql(conn, "V4_right_length", v4)

        # ---------- V5: la query 398 ENTERA tal cual está en SAP ----------
        # Copia literal del Query Manager. Si falla, el endpoint /SQLQueries
        # no permite el mismo SQL que el Query Manager interno.
        v5 = (
            'SELECT DISTINCT  T2."CardCode", T1."ItemCode", T2."CardCode", T2."CardName", '
            'T2."ShipToCode", T2."DocDate", T2."DocNum",T4."ItemCode", T4."Dscription",'
            'T1."SysSerial", T1."SuppSerial" FROM SRI1 T0  '
            'INNER JOIN OSRI T1 ON T0."SysSerial" = T1."SysSerial" and T0."ItemCode" = T1."ItemCode" '
            'AND T0."WhsCode"=T1."WhsCode"  '
            'inner join OWTR T2 on T2."DocNum"= T0."BaseNum" '
            'inner join OCRD T3 ON T3."CardCode" = T2."CardCode" '
            'inner join WTR1 T4 on T4."DocEntry" = T2."DocEntry" and T1."ItemCode"=T4."ItemCode" '
            'and T0."ItemCode" = T4."ItemCode" and T0."WhsCode"=T4."WhsCode"  '
            'WHERE T1."Status" =0 and T3."U_ZGIRA"=\'3\' '
            'and (T0."WhsCode"=RIGHT(T2."CardCode",LENGTH(T2."CardCode")-1) '
            'or T0."WhsCode" in (Select RIGHT(T11."CardCode",LENGTH(T11."CardCode")-1) '
            'from OCRD T11 where T11."FatherCard"=T2."CardCode")) '
            'order by T2."CardCode", T2."CardName", T2."ShipToCode", T2."DocDate" ASC'
        )
        probar_sql(conn, "V5_query_398_literal", v5)

        print("\n" + "=" * 80)
        print("📋 INTERPRETACIÓN")
        print("=" * 80)
        print("   - Si V1 y V2 pasan: el endpoint /SQLQueries funciona en general")
        print("   - Si V3 pasa pero V4 falla: el problema es RIGHT/LENGTH/menos")
        print("   - Si V4 falla pero V5 pasa: hay algo en cómo armo MI SQL distinto")
        print(
            "   - Si V5 también falla: el endpoint NO acepta el SQL del Query Manager"
        )
        print("     (habría que usar otro método para ejecutar el reporte)")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
