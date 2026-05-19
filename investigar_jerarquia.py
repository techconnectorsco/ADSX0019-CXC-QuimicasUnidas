"""
investigar_jerarquia.py - Químicas Unidas

OBJETIVO: Validar el modelo de jerarquía cliente padre → tiendas hijas
antes de modificar consignaciones.py.

Responde 3 preguntas con datos reales:
  1. ¿Cuántos clientes tienen FatherCard? (tiendas hijas)
  2. ¿Cómo lucen los códigos de bodega vs los CardCodes? (matcheo)
  3. ¿Cuántos equipos en total deberían aparecer en el reporte?

NO genera PDFs, NO envía correos. Solo lectura.
"""

import sys
import os
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def obtener_todos_paginado(conn, entidad, params):
    """
    Trae TODOS los registros paginando de 20 en 20.

    Nota importante: el Service Layer de SAP B1 ignora $top cuando es mayor
    al PageSize configurado en el servidor (típicamente 20). Por eso paginamos
    en bloques de 20 y cortamos solo cuando la respuesta venga vacía o con
    menos de 20 registros (señal de última página).
    """
    todos = []
    skip = 0
    while True:
        params["$skip"] = skip
        res = conn.get(entidad, params)
        if not res or "value" not in res or not res["value"]:
            break
        todos.extend(res["value"])
        # Si vino con menos de 20, es la última página
        if len(res["value"]) < 20:
            break
        skip += 20
        # Cinturón de seguridad para evitar loops infinitos
        if skip > 100000:
            print(f"   ⚠️  Cortado en {skip} registros (límite de seguridad)")
            break
    return todos


def extraer_series_bodega(conn):
    """Mismo SQL que tu consignaciones.py — sabemos que este funciona."""
    query_code = f"TMP_INVEST_{int(time.time())}"
    sql_text = (
        'SELECT T0."WhsCode", T0."ItemCode", T1."DistNumber" AS "SerialNumber" '
        "FROM OSRQ T0 "
        'INNER JOIN OSRN T1 ON T0."ItemCode"=T1."ItemCode" AND T0."SysNumber"=T1."SysNumber" '
        'WHERE T0."Quantity">0 AND (T0."WhsCode" LIKE \'00%\' OR T0."WhsCode" LIKE \'C0%\')'
    )

    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"
    series = []

    try:
        conn.session.post(
            url_post,
            json={"SqlCode": query_code, "SqlName": "TMP", "SqlText": sql_text},
        )
        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$skip": skip})
            if not res or "value" not in res or not res["value"]:
                break
            series.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass
    return series


def main():
    print("=" * 80)
    print("🔍 INVESTIGACIÓN DE JERARQUÍA CLIENTE PADRE / TIENDA HIJA")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # PASO 1: Descargar maestro de clientes CON FatherCard
        # =====================================================================
        print("\n📥 Descargando maestro de clientes (con FatherCard)...")
        clientes = obtener_todos_paginado(
            conn,
            "BusinessPartners",
            {
                "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA,CardType",
                "$filter": "CardType eq 'cCustomer'",
            },
        )
        print(f"   Total clientes: {len(clientes)}")

        clientes_dict = {c["CardCode"]: c for c in clientes}

        # Análisis de jerarquía
        con_padre = [c for c in clientes if c.get("FatherCard")]
        padres = set(c["FatherCard"] for c in con_padre)

        print(f"\n   📊 JERARQUÍA:")
        print(f"      Clientes con FatherCard (tiendas hijas): {len(con_padre)}")
        print(f"      Clientes padre únicos:                   {len(padres)}")
        print(
            f"      Clientes sin jerarquía:                  {len(clientes) - len(con_padre)}"
        )

        if con_padre:
            print(f"\n   📋 EJEMPLOS DE JERARQUÍA (primeros 3 padres con más hijos):")
            por_padre = defaultdict(list)
            for c in con_padre:
                por_padre[c["FatherCard"]].append(c)
            top_padres = sorted(por_padre.items(), key=lambda x: -len(x[1]))[:3]

            for padre_code, hijos in top_padres:
                padre = clientes_dict.get(padre_code, {})
                print(f"\n      🏢 {padre_code} — {padre.get('CardName', '?')}")
                print(f"         Tiendas: {len(hijos)}")
                for h in hijos[:5]:
                    print(f"            └─ {h['CardCode']} — {h['CardName']}")
                if len(hijos) > 5:
                    print(f"            ... y {len(hijos)-5} más")

        # =====================================================================
        # PASO 2: Series en bodegas
        # =====================================================================
        print("\n📥 Descargando series en bodegas...")
        series = extraer_series_bodega(conn)
        print(f"   Total series en bodegas: {len(series)}")

        bodegas_unicas = set(s["WhsCode"] for s in series)
        print(f"   Bodegas únicas con stock: {len(bodegas_unicas)}")

        # =====================================================================
        # PASO 3: Probar 3 estrategias de matcheo y comparar
        # =====================================================================
        print("\n" + "=" * 80)
        print("🧪 PROBANDO 3 ESTRATEGIAS DE MATCHEO BODEGA → CLIENTE")
        print("=" * 80)

        # Construir índices auxiliares
        # Mapeo: "sufijo del CardCode" → CardCode completo
        # Ej: si CardCode = "C0180", sufijo = "0180"
        sufijo_a_card = {}
        for c in clientes:
            cc = c["CardCode"]
            if len(cc) > 1:
                sufijo = cc[1:]  # quitar el primer carácter
                sufijo_a_card[sufijo] = cc

        # ESTRATEGIA 1 (tu código actual): bodega == CardCode, o C+bodega == CardCode
        match_actual = 0
        for s in series:
            b = s["WhsCode"]
            if b in clientes_dict or f"C{b}" in clientes_dict:
                match_actual += 1

        # ESTRATEGIA 2 (la del SQL): bodega == CardCode[1:] (sufijo)
        match_sufijo = 0
        bodegas_matcheadas_sufijo = set()
        for s in series:
            b = s["WhsCode"]
            if b in sufijo_a_card:
                match_sufijo += 1
                bodegas_matcheadas_sufijo.add(b)

        # ESTRATEGIA 3 (sufijo + padre): bodega matchea con sufijo de cliente
        #                                  O sufijo de algún hijo de cliente
        match_completo = 0
        for s in series:
            b = s["WhsCode"]
            if b in sufijo_a_card:
                match_completo += 1

        print(f"\n   Series totales en bodegas: {len(series)}")
        print(
            f"\n   Estrategia 1 (tu código actual):           {match_actual} series matcheadas"
        )
        print(
            f"   Estrategia 2 (sufijo, sin jerarquía):      {match_sufijo} series matcheadas"
        )
        print(
            f"   Estrategia 3 (sufijo CON jerarquía padre): {match_completo} series matcheadas"
        )

        # =====================================================================
        # PASO 4: Mostrar bodegas que NO matchean — para entender por qué
        # =====================================================================
        print("\n" + "=" * 80)
        print("🔎 BODEGAS QUE NO MATCHEAN CON NINGÚN CLIENTE")
        print("=" * 80)

        bodegas_no_matcheadas = bodegas_unicas - bodegas_matcheadas_sufijo
        print(
            f"\n   Bodegas con stock pero sin cliente asociado: {len(bodegas_no_matcheadas)}"
        )
        if bodegas_no_matcheadas:
            print(f"\n   Muestra (primeras 20):")
            for b in sorted(bodegas_no_matcheadas)[:20]:
                # Contar cuántas series tiene esta bodega
                count = sum(1 for s in series if s["WhsCode"] == b)
                print(f"      {b}  ({count} series)")

        # =====================================================================
        # PASO 5: Proyección — agrupando por agente con estrategia correcta
        # =====================================================================
        print("\n" + "=" * 80)
        print("📊 PROYECCIÓN: equipos por agente con estrategia correcta")
        print("=" * 80)

        # Cache de vendedores
        vends = obtener_todos_paginado(
            conn, "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName"}
        )
        vend_dict = {
            v["SalesEmployeeCode"]: v.get("SalesEmployeeName", "?") for v in vends
        }

        # Aplicar estrategia 3 (la correcta)
        equipos_por_agente = defaultdict(int)
        for s in series:
            b = s["WhsCode"]
            if b in sufijo_a_card:
                card_code = sufijo_a_card[b]
                cli = clientes_dict.get(card_code, {})
                # Si el cliente tiene padre, usar el agente del PADRE
                if cli.get("FatherCard"):
                    padre = clientes_dict.get(cli["FatherCard"], {})
                    slp = padre.get("SalesPersonCode", cli.get("SalesPersonCode", -1))
                else:
                    slp = cli.get("SalesPersonCode", -1)
                equipos_por_agente[slp] += 1

        print(f"\n   Agentes con equipos en consignación: {len(equipos_por_agente)}")
        print(f"\n   {'SlpCode':<10} {'Agente':<40} {'Equipos':<10}")
        print("   " + "-" * 62)
        for slp, count in sorted(equipos_por_agente.items(), key=lambda x: -x[1]):
            nombre = vend_dict.get(slp, "(?)")
            print(f"   {str(slp):<10} {nombre[:39]:<40} {count:<10}")

        total = sum(equipos_por_agente.values())
        print(f"\n   TOTAL equipos: {total}")
        print(f"   (Compará con los 13 que estás generando hoy)")

        print("\n" + "=" * 80)
        print("✅ INVESTIGACIÓN COMPLETADA")
        print("=" * 80)

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
