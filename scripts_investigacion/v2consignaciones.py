"""
investigar_consignaciones_v2.py - Químicas Unidas

OBJETIVO: Armar el modelo de datos COMPLETO de consignaciones, rápido y
agrupado por cliente padre (opción A).

Estrategia para que sea rápido:
  1. Catálogo de bodegas vía /Warehouses (OData, rápido)
  2. Identificar bodegas "de consignación" (excluir internas)
  3. Descargar SOLO los clientes que matchean (no los 7750)
  4. Consultar series filtrando por la lista chica de bodegas
  5. Agrupar bajo cliente padre cuando exista FatherCard

NO genera PDFs, NO envía correos. Solo lectura + reporte en pantalla.

Genera caché en data/cache_consignaciones.json para desarrollo iterativo.
"""

import sys
import os
import time
import json
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

CACHE_FILE = "data/cache_consignaciones.json"
CACHE_MAX_AGE_MIN = 30  # minutos de validez del cache


# =============================================================================
# UTILIDADES
# =============================================================================


def odata_paginado(conn, entidad, params=None):
    """Trae todos los registros de un endpoint OData paginando de 20 en 20."""
    if params is None:
        params = {}
    todos = []
    skip = 0
    while True:
        params["$skip"] = skip
        res = conn.get(entidad, params)
        if not res or "value" not in res or not res["value"]:
            break
        todos.extend(res["value"])
        if len(res["value"]) < 20:
            break
        skip += 20
        if skip > 100000:
            print(f"   ⚠️  Cortado en {skip}")
            break
    return todos


def sql_temporal(conn, sql_text):
    """Ejecuta una query SQL temporal y devuelve todos los resultados."""
    query_code = f"TMP_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"
    resultados = []

    try:
        resp = conn.session.post(
            url_post,
            json={"SqlCode": query_code, "SqlName": "TMP", "SqlText": sql_text},
        )
        if resp.status_code not in (200, 201):
            print(f"   ❌ Error SQL ({resp.status_code}):")
            try:
                print(
                    f"      {resp.json().get('error', {}).get('message', {}).get('value', '')[:300]}"
                )
            except Exception:
                pass
            return []

        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$skip": skip})
            if not res or "value" not in res or not res["value"]:
                break
            resultados.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20
            if skip > 100000:
                break
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass

    return resultados


def cache_valido():
    """Verifica si existe cache y está fresco."""
    if not os.path.exists(CACHE_FILE):
        return False
    age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
    return age_min < CACHE_MAX_AGE_MIN


# =============================================================================
# EXTRACCIÓN DE DATOS BASE
# =============================================================================


def obtener_bodegas(conn):
    """Catálogo completo vía /Warehouses (rápido, < 1 min)."""
    print("📥 Bodegas vía OData...")
    bodegas = odata_paginado(
        conn, "Warehouses", {"$select": "WarehouseCode,WarehouseName,Inactive"}
    )
    print(f"   {len(bodegas)} bodegas")
    return bodegas


def identificar_bodegas_consignacion(bodegas):
    """
    Una bodega es 'de consignación' si su código es numérico (con o sin guion)
    pero NO es una bodega interna simple (01, 02, ..., 11).

    Bodegas internas conocidas: 01, 02, 03, ..., 11, -1
    Bodegas de consignación: 0017, 0180, 0161, CE9084, 01-RW, 431, etc.
    """
    INTERNAS = {"-1", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"}

    consignacion = []
    internas = []
    for b in bodegas:
        code = b.get("WarehouseCode", "")
        if code in INTERNAS:
            internas.append(b)
        else:
            consignacion.append(b)
    return consignacion, internas


def obtener_clientes_relevantes(conn, codigos_bodega):
    """
    Trae SOLO los clientes que podrían matchear con alguna bodega.

    Estrategia: para cada bodega 'NNNN' probamos buscar 'CNNNN' como CardCode.
    Hacemos lookups en lotes vía $filter para no descargar 7750 clientes.
    """
    print(f"📥 Clientes relevantes (matcheando {len(codigos_bodega)} bodegas)...")

    # Construimos lista de CardCodes candidatos
    candidatos = set()
    for code in codigos_bodega:
        candidatos.add(f"C{code}")  # regla principal: C + bodega
        candidatos.add(code)  # por si la bodega ya viene con prefijo

    candidatos = list(candidatos)
    todos_clientes = []

    # Procesamos en lotes de 50 (el filtro 'in (...)' tiene límites de URL)
    LOTE = 50
    for i in range(0, len(candidatos), LOTE):
        chunk = candidatos[i : i + LOTE]
        filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
        clientes_chunk = odata_paginado(
            conn,
            "BusinessPartners",
            {
                "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                "$filter": filtro,
            },
        )
        todos_clientes.extend(clientes_chunk)
        print(
            f"   Lote {i//LOTE + 1}/{(len(candidatos)-1)//LOTE + 1}: +{len(clientes_chunk)}"
        )

    # Ahora necesitamos también traer los PADRES de los clientes hijos encontrados
    padres_a_buscar = set()
    cards_ya_tenidos = {c["CardCode"] for c in todos_clientes}
    for c in todos_clientes:
        fc = c.get("FatherCard")
        if fc and fc not in cards_ya_tenidos:
            padres_a_buscar.add(fc)

    if padres_a_buscar:
        print(f"   Trayendo {len(padres_a_buscar)} clientes padre adicionales...")
        padres_lista = list(padres_a_buscar)
        for i in range(0, len(padres_lista), LOTE):
            chunk = padres_lista[i : i + LOTE]
            filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
            padres_chunk = odata_paginado(
                conn,
                "BusinessPartners",
                {
                    "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                    "$filter": filtro,
                },
            )
            todos_clientes.extend(padres_chunk)

    print(f"   Total clientes traídos: {len(todos_clientes)}")
    return todos_clientes


def obtener_series_de_bodegas(conn, codigos_bodega):
    """
    Trae las series en stock de las bodegas que nos interesan.

    ESTRATEGIA: una consulta por bodega (en vez de un solo IN con 112 valores).
    HANA usa el índice de WhsCode directamente y es MUCHÍSIMO más rápido,
    incluso aunque sean más requests HTTP.
    """
    print(f"📥 Series en {len(codigos_bodega)} bodegas (una consulta por bodega)...")

    total = len(codigos_bodega)
    series = []
    t_inicio = time.time()

    for i, code in enumerate(codigos_bodega, 1):
        # Escapar comillas simples por las dudas
        code_safe = code.replace("'", "''")
        sql = (
            'SELECT T0."WhsCode", T0."ItemCode", T1."DistNumber" AS "SerialNumber" '
            "FROM OSRQ T0 "
            'INNER JOIN OSRN T1 ON T0."ItemCode"=T1."ItemCode" AND T0."SysNumber"=T1."SysNumber" '
            f'WHERE T0."Quantity">0 AND T0."WhsCode"=\'{code_safe}\''
        )
        partial = sql_temporal_silencioso(conn, sql)
        series.extend(partial)

        # Progreso cada 10 bodegas
        if i % 10 == 0 or i == total:
            tasa = i / max(time.time() - t_inicio, 0.1)
            eta = (total - i) / max(tasa, 0.1)
            print(
                f"   [{i:3}/{total}] series acumuladas: {len(series):5} | ETA: {eta:.0f}s"
            )

    print(f"   ✅ {len(series)} series obtenidas en {time.time()-t_inicio:.1f}s")
    return series


def sql_temporal_silencioso(conn, sql_text):
    """Versión silenciosa de sql_temporal (sin prints) para llamadas en loop."""
    query_code = f"TMP_{int(time.time()*1000000) % 1000000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"
    resultados = []

    try:
        resp = conn.session.post(
            url_post,
            json={"SqlCode": query_code, "SqlName": "TMP", "SqlText": sql_text},
        )
        if resp.status_code not in (200, 201):
            return []

        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$skip": skip})
            if not res or "value" not in res or not res["value"]:
                break
            resultados.extend(res["value"])
            if len(res["value"]) < 20:
                break
            skip += 20
            if skip > 10000:
                break
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass

    return resultados


def obtener_items(conn, item_codes):
    """Trae descripción solo de los ItemCodes que aparecen en las series."""
    print(f"📥 Descripciones de {len(item_codes)} artículos...")
    items_dict = {}
    LOTE = 50
    item_list = list(item_codes)
    for i in range(0, len(item_list), LOTE):
        chunk = item_list[i : i + LOTE]
        filtro = " or ".join(f"ItemCode eq '{c}'" for c in chunk)
        items = odata_paginado(
            conn, "Items", {"$select": "ItemCode,ItemName", "$filter": filtro}
        )
        for it in items:
            items_dict[it["ItemCode"]] = it.get("ItemName", "?")
    print(f"   {len(items_dict)} items mapeados")
    return items_dict


def obtener_vendedores(conn):
    print("📥 Vendedores...")
    vends = odata_paginado(
        conn, "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"}
    )
    print(f"   {len(vends)} vendedores")
    return {v["SalesEmployeeCode"]: v for v in vends}


# =============================================================================
# CRUCE Y AGRUPACIÓN — OPCIÓN A (por cliente padre)
# =============================================================================


def cruzar_y_agrupar(bodegas_cons, clientes, series, items_dict, vendedores):
    """
    Para cada serie:
      1. Encuentra el cliente dueño de la bodega (regla: bodega o C+bodega)
      2. Si el cliente tiene FatherCard, usa el padre como cliente "principal"
      3. La tienda hija queda como "ShipToCode" / "Enviado a"
      4. Agrupa todo bajo el agente del cliente principal
    """
    print("\n🔀 Cruzando datos...")

    clientes_dict = {c["CardCode"]: c for c in clientes}
    bodega_a_nombre = {
        b["WarehouseCode"]: b.get("WarehouseName", "?") for b in bodegas_cons
    }

    # Resolver bodega → cliente (CardCode)
    def cliente_de_bodega(whs_code):
        for cand in [whs_code, f"C{whs_code}"]:
            if cand in clientes_dict:
                return clientes_dict[cand]
        return None

    equipos = []
    bodegas_huerfanas = set()

    for s in series:
        b = s["WhsCode"]
        cli_directo = cliente_de_bodega(b)
        if not cli_directo:
            bodegas_huerfanas.add(b)
            continue

        # Determinar cliente PADRE (principal)
        father = cli_directo.get("FatherCard")
        if father and father in clientes_dict:
            cli_principal = clientes_dict[father]
            tienda_nombre = bodega_a_nombre.get(b, cli_directo.get("CardName", "?"))
            shipto_code = cli_directo["CardCode"]  # la "sucursal" es el hijo
        else:
            cli_principal = cli_directo
            tienda_nombre = bodega_a_nombre.get(b, cli_directo.get("CardName", "?"))
            shipto_code = ""  # sin sucursal, es directo

        equipos.append(
            {
                "WhsCode": b,
                "TiendaNombre": tienda_nombre,
                "ShipToCode": shipto_code,
                "ClienteCardCode": cli_principal["CardCode"],
                "ClienteNombre": cli_principal.get("CardName", "?"),
                "Zona": cli_principal.get("U_ZGIRA", ""),
                "SalesPersonCode": cli_principal.get("SalesPersonCode", -1),
                "ItemCode": s["ItemCode"],
                "ItemName": items_dict.get(s["ItemCode"], "?"),
                "SerialNumber": s.get("SerialNumber", ""),
            }
        )

    print(f"   Equipos cruzados: {len(equipos)}")
    if bodegas_huerfanas:
        print(
            f"   ⚠️  Bodegas sin cliente: {len(bodegas_huerfanas)} → {sorted(bodegas_huerfanas)[:10]}"
        )

    return equipos


# =============================================================================
# REPORTE EN PANTALLA
# =============================================================================


def reporte(equipos, vendedores):
    print("\n" + "=" * 80)
    print("📊 RESULTADO: equipos agrupados por agente → cliente → tienda")
    print("=" * 80)

    # Agrupar por agente
    por_agente = defaultdict(list)
    for e in equipos:
        por_agente[e["SalesPersonCode"]].append(e)

    print(f"\nTotal equipos: {len(equipos)}")
    print(f"Total agentes con consignaciones: {len(por_agente)}")
    print()

    # Resumen por agente
    print(
        f"{'SlpCode':<10} {'Agente':<40} {'Clientes':<10} {'Tiendas':<10} {'Equipos':<10}"
    )
    print("-" * 82)
    for slp, eqs in sorted(por_agente.items(), key=lambda x: -len(x[1])):
        info = vendedores.get(slp, {})
        nombre = info.get("SalesEmployeeName", f"(?{slp})")
        clientes_unicos = len(set(e["ClienteCardCode"] for e in eqs))
        tiendas_unicas = len(set((e["ClienteCardCode"], e["WhsCode"]) for e in eqs))
        print(
            f"{str(slp):<10} {nombre[:39]:<40} {clientes_unicos:<10} {tiendas_unicas:<10} {len(eqs):<10}"
        )

    # Detalle del agente con más equipos
    if por_agente:
        top_slp, top_eqs = max(por_agente.items(), key=lambda x: len(x[1]))
        info = vendedores.get(top_slp, {})
        print(
            f"\n📋 DETALLE — Agente con más equipos: {info.get('SalesEmployeeName', '?')} ({len(top_eqs)} equipos)"
        )
        print("-" * 82)

        # Agrupar por cliente
        por_cliente = defaultdict(list)
        for e in top_eqs:
            por_cliente[(e["ClienteCardCode"], e["ClienteNombre"])].append(e)

        for (cc, cn), eqs in sorted(por_cliente.items(), key=lambda x: -len(x[1]))[:5]:
            print(f"\n   🏢 {cc} — {cn} ({len(eqs)} equipos)")
            por_tienda = defaultdict(list)
            for e in eqs:
                por_tienda[(e["WhsCode"], e["TiendaNombre"])].append(e)
            for (wc, wn), tn_eqs in por_tienda.items():
                print(f"      └─ Bodega {wc} ({wn}): {len(tn_eqs)} equipos")


# =============================================================================
# MAIN
# =============================================================================


def main():
    print("=" * 80)
    print("🔍 INVESTIGACIÓN DE CONSIGNACIONES — VERSIÓN OPTIMIZADA")
    print("=" * 80)

    # Intentar usar cache
    if cache_valido() and "--refresh" not in sys.argv:
        print(f"\n💾 Usando cache fresco ({CACHE_FILE})")
        print("   Usá --refresh para forzar refresco")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        equipos = data["equipos"]
        vendedores = {
            int(k) if k.lstrip("-").isdigit() else k: v
            for k, v in data["vendedores"].items()
        }
        reporte(equipos, vendedores)
        return

    # Sin cache → consultar SAP
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        t0 = time.time()

        # 1. Bodegas
        bodegas = obtener_bodegas(conn)
        bodegas_cons, bodegas_internas = identificar_bodegas_consignacion(bodegas)
        print(
            f"   → {len(bodegas_cons)} consignación / {len(bodegas_internas)} internas"
        )
        codigos_bodega = [b["WarehouseCode"] for b in bodegas_cons]

        # 2. Clientes relevantes
        clientes = obtener_clientes_relevantes(conn, codigos_bodega)

        # 3. Series de esas bodegas
        series = obtener_series_de_bodegas(conn, codigos_bodega)

        if not series:
            print("⚠️  No hay series en consignación")
            return

        # 4. Items
        item_codes = set(s["ItemCode"] for s in series)
        items_dict = obtener_items(conn, item_codes)

        # 5. Vendedores
        vendedores = obtener_vendedores(conn)

        # 6. Cruce
        equipos = cruzar_y_agrupar(
            bodegas_cons, clientes, series, items_dict, vendedores
        )

        # 7. Guardar cache
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "equipos": equipos,
                    "vendedores": {str(k): v for k, v in vendedores.items()},
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\n💾 Cache guardado en {CACHE_FILE}")

        # 8. Reporte
        reporte(equipos, vendedores)

        print(f"\n⏱️  Tiempo total: {time.time()-t0:.1f} segundos")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
