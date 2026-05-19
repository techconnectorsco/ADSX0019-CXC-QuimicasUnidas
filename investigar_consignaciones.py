"""
investigar_consignaciones.py - Químicas Unidas

OBJETIVO: Validar el modelo de datos de consignaciones ANTES de modificar
el módulo de generación de PDFs. NO genera PDFs, NO envía correos.

Solo imprime conteos y muestras para que entendamos:
  1. Qué devuelve la query 398 corregida (con SalesPersonCode y U_ZGIRA)
  2. Cuántos agentes / zonas / clientes / sucursales hay
  3. Cómo se agrupa la información jerárquicamente
  4. Validar contra el filtro "Giras Agentes = 3" del SAP

Uso:
    python investigar_consignaciones.py
"""

import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection

# ============================================================================
# SQL CORREGIDO: agrega SalesPersonCode y U_ZGIRA, sin filtros de parámetro
# ============================================================================
SQL_CONSIGNACIONES = (
    "SELECT DISTINCT "
    'T2."CardCode", T2."CardName", T2."ShipToCode", T2."DocDate", T2."DocNum", '
    'T1."ItemCode", T4."Dscription", T1."SysSerial", T1."SuppSerial", '
    'T3."SalesPersonCode", T3."U_ZGIRA" AS "Zona" '
    "FROM SRI1 T0 "
    'INNER JOIN OSRI T1 ON T0."SysSerial"=T1."SysSerial" AND T0."ItemCode"=T1."ItemCode" AND T0."WhsCode"=T1."WhsCode" '
    'INNER JOIN OWTR T2 ON T2."DocNum"=T0."BaseNum" '
    'INNER JOIN OCRD T3 ON T3."CardCode"=T2."CardCode" '
    'INNER JOIN WTR1 T4 ON T4."DocEntry"=T2."DocEntry" AND T4."ItemCode"=T1."ItemCode" AND T4."ItemCode"=T0."ItemCode" '
    'WHERE T1."Status"=0 '
    'AND (T0."WhsCode"=RIGHT(T2."CardCode",LENGTH(T2."CardCode")-1) '
    'OR T0."WhsCode" IN (SELECT RIGHT(T11."CardCode",LENGTH(T11."CardCode")-1) FROM OCRD T11 WHERE T11."FatherCard"=T2."CardCode")) '
    'ORDER BY T3."SalesPersonCode", T2."CardCode", T2."ShipToCode", T2."DocDate" ASC'
)


def extraer_consignaciones_ninja(conn):
    """Crea la query temporal, la ejecuta, la borra. Devuelve la lista."""
    query_name = "RPA_TMP_INVESTIG_CONSIG"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_name}')"

    # Limpieza preventiva
    try:
        conn.session.delete(url_del)
    except Exception:
        pass

    registros = []
    try:
        # Crear
        resp = conn.session.post(
            url_post,
            json={
                "SqlCode": query_name,
                "SqlName": "TMP_INVESTIG",
                "SqlText": SQL_CONSIGNACIONES,
            },
        )
        if resp.status_code not in (200, 201):
            print(
                f"   ❌ Error creando query temporal: {resp.status_code} - {resp.text[:200]}"
            )
            return []

        # Extraer paginado
        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_name}')/List", {"$skip": skip})
            if not res or "value" not in res or not res["value"]:
                break
            registros.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20
            if skip > 10000:
                print("   ⚠️  Límite de seguridad alcanzado (10000)")
                break
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass

    return registros


def obtener_cache_vendedores(conn):
    """Trae todos los vendedores con su nombre y correo."""
    vendedores = {}
    skip = 0
    while True:
        res = conn.get(
            "SalesPersons",
            {"$select": "SalesEmployeeCode,SalesEmployeeName,Email", "$skip": skip},
        )
        if not res or "value" not in res or not res["value"]:
            break
        for v in res["value"]:
            vendedores[v["SalesEmployeeCode"]] = {
                "nombre": v.get("SalesEmployeeName", "Sin nombre"),
                "correo": v.get("Email", "") or "",
            }
        if len(res["value"]) < 20:
            break
        skip += 20
    return vendedores


# ============================================================================
# REPORTES DE ANÁLISIS
# ============================================================================


def reporte_totales(registros):
    print("\n" + "=" * 80)
    print("📊 PARTE 1: TOTALES GENERALES")
    print("=" * 80)
    print(f"   Total de filas (equipos en consignación): {len(registros)}")

    if not registros:
        return

    print(f"\n   Campos devueltos: {list(registros[0].keys())}")
    print(f"\n   📋 Primera fila completa (muestra):")
    for k, v in registros[0].items():
        print(f"      {k}: {v}")


def reporte_por_agente(registros, vendedores_cache):
    print("\n" + "=" * 80)
    print("📊 PARTE 2: DESGLOSE POR AGENTE (SalesPersonCode)")
    print("=" * 80)

    por_agente = defaultdict(list)
    for r in registros:
        slp = r.get("SalesPersonCode", -1)
        por_agente[slp].append(r)

    print(f"   Agentes únicos con consignaciones: {len(por_agente)}")
    print(
        f"\n   {'SlpCode':<10} {'Nombre del agente':<35} {'Equipos':<10} {'Correo':<35}"
    )
    print("   " + "-" * 92)

    for slp in sorted(
        por_agente.keys(),
        key=lambda x: int(x) if str(x).lstrip("-").isdigit() else 9999,
    ):
        info = vendedores_cache.get(slp, {"nombre": "(no encontrado)", "correo": ""})
        print(
            f"   {str(slp):<10} {info['nombre'][:34]:<35} {len(por_agente[slp]):<10} {info['correo'][:34]:<35}"
        )

    return por_agente


def reporte_por_zona(registros):
    print("\n" + "=" * 80)
    print("📊 PARTE 3: DESGLOSE POR ZONA (U_ZGIRA)")
    print("=" * 80)

    por_zona = defaultdict(int)
    for r in registros:
        zona = r.get("Zona") or "(sin zona)"
        por_zona[zona] += 1

    print(f"   Zonas únicas: {len(por_zona)}")
    print(f"\n   {'Zona (U_ZGIRA)':<20} {'Equipos':<10}")
    print("   " + "-" * 32)
    for zona, count in sorted(por_zona.items(), key=lambda x: -x[1]):
        print(f"   {str(zona):<20} {count:<10}")


def reporte_clientes_y_sucursales(por_agente, vendedores_cache):
    print("\n" + "=" * 80)
    print("📊 PARTE 4: JERARQUÍA AGENTE → CLIENTES → SUCURSALES")
    print("=" * 80)
    print("   (Muestra los 3 agentes con MÁS equipos)")

    top_agentes = sorted(por_agente.items(), key=lambda x: -len(x[1]))[:3]

    for slp, equipos in top_agentes:
        info = vendedores_cache.get(slp, {"nombre": "(no encontrado)"})
        print(f"\n   👨‍💼 AGENTE {slp} - {info['nombre']} ({len(equipos)} equipos)")

        # Agrupar por cliente
        por_cliente = defaultdict(lambda: defaultdict(list))
        for e in equipos:
            cc = e.get("CardCode", "?")
            sucursal = e.get("ShipToCode", "(sin sucursal)") or "(sin sucursal)"
            por_cliente[cc][sucursal].append(e)

        for cc in list(por_cliente.keys())[:5]:  # primeros 5 clientes
            sucursales = por_cliente[cc]
            total_eq_cliente = sum(len(v) for v in sucursales.values())
            nombre_cliente = sucursales[list(sucursales.keys())[0]][0].get(
                "CardName", "?"
            )
            print(
                f"      📌 {cc} - {nombre_cliente[:40]} ({total_eq_cliente} equipos, {len(sucursales)} sucursales)"
            )
            for suc, eqs in sucursales.items():
                print(f"         └─ Sucursal '{suc}': {len(eqs)} equipos")

        if len(por_cliente) > 5:
            print(f"      ... y {len(por_cliente) - 5} clientes más")


def reporte_validacion_agente_3(registros, vendedores_cache):
    """Valida contra el filtro del SAP: 'Giras Agentes = 3'."""
    print("\n" + "=" * 80)
    print("📊 PARTE 5: VALIDACIÓN — filtro 'Giras Agentes = 3' del SAP")
    print("=" * 80)
    print("   Probando dos interpretaciones del '3':")
    print()

    # Interpretación A: U_ZGIRA = '3'
    como_zona = [r for r in registros if str(r.get("Zona") or "") == "3"]
    print(f"   A) Si '3' es ZONA (U_ZGIRA = '3'):  {len(como_zona)} equipos")

    # Interpretación B: SlpCode = 3
    como_agente = [r for r in registros if str(r.get("SalesPersonCode") or "") == "3"]
    info_3 = vendedores_cache.get(
        3, vendedores_cache.get("3", {"nombre": "(no encontrado)"})
    )
    print(
        f"   B) Si '3' es AGENTE (SlpCode = 3 → {info_3['nombre']}):  {len(como_agente)} equipos"
    )

    print()
    print("   👉 La interpretación correcta es la que coincida con lo que la")
    print("      encargada ve en su pantalla cuando filtra '3'.")


def reporte_clientes_padre_hijo(registros):
    """Analiza el patrón cliente padre (FatherCard) → tiendas hijas."""
    print("\n" + "=" * 80)
    print("📊 PARTE 6: PATRÓN 'CLIENTE PADRE → TIENDAS HIJAS'")
    print("=" * 80)
    print("   En el SQL, la condición FatherCard sugiere que algunos CardCodes")
    print("   son tiendas hijas de un cliente padre (ej: El Colono → 5 tiendas).")
    print()

    # Contar cuántos clientes únicos vs cuántas combinaciones cliente+sucursal
    clientes_unicos = set(r.get("CardCode") for r in registros)
    combos = set((r.get("CardCode"), r.get("ShipToCode") or "") for r in registros)

    print(f"   Clientes únicos (CardCode):              {len(clientes_unicos)}")
    print(f"   Combinaciones cliente+sucursal únicas:   {len(combos)}")
    print(
        f"   Promedio sucursales por cliente:         {len(combos)/max(len(clientes_unicos),1):.1f}"
    )


# ============================================================================
# MAIN
# ============================================================================


def main():
    print("=" * 80)
    print("🔍 INVESTIGACIÓN DE CONSIGNACIONES — SOLO LECTURA")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        print("\n📋 Cargando caché de vendedores...")
        vendedores_cache = obtener_cache_vendedores(conn)
        print(f"   Vendedores cargados: {len(vendedores_cache)}")

        print("\n🥷 Ejecutando query de consignaciones (modo ninja)...")
        registros = extraer_consignaciones_ninja(conn)

        if not registros:
            print("❌ No se obtuvieron registros. Revisar la query.")
            return

        # Análisis
        reporte_totales(registros)
        por_agente = reporte_por_agente(registros, vendedores_cache)
        reporte_por_zona(registros)
        reporte_clientes_y_sucursales(por_agente, vendedores_cache)
        reporte_validacion_agente_3(registros, vendedores_cache)
        reporte_clientes_padre_hijo(registros)

        print("\n" + "=" * 80)
        print("✅ INVESTIGACIÓN COMPLETADA")
        print("=" * 80)
        print("   Próximo paso: con estos números decidimos cómo agrupar en el PDF.")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
