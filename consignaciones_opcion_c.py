"""
consignaciones_opcion_c.py - Químicas Unidas

ESTRATEGIA: Sin acceso a OSRI, intentamos reproducir la cifra correcta
cruzando dos fuentes que SÍ tenemos accesibles:

  1. /StockTransfers (DocumentStatus = bost_Open) → traslados a bodegas cliente
  2. OSRQ (Quantity > 0)                          → series físicamente presentes

Lógica: una serie está en consignación SOLO si cumple las DOS condiciones.

Cifras esperadas (Tania, febrero 2026):
  - José Chacón:     167
  - Berny Marín:      47
  - Siviany González: 102
  - Ashley Azofeifa: 100

Si nos acercamos a esos números, la estrategia funcionó.

Uso:
  python consignaciones_opcion_c.py            # usa cache si existe (30 min)
  python consignaciones_opcion_c.py --refresh  # fuerza consulta a SAP
  python consignaciones_opcion_c.py --debug    # más detalle por consola
"""

import sys
import os
import time
import json
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

CACHE_FILE = "data/cache_opcion_c.json"
CACHE_MAX_AGE_MIN = 30

BODEGAS_INTERNAS = {
    "-1",
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
}

# Referencia que nos dio Tania para validar (feb 2026)
CIFRAS_REFERENCIA = {
    9: ("José Chacón", 167),
    7: ("Berny Marín", 47),
    6: ("Siviany González", 102),
    5: ("Ashley Azofeifa", 100),
}


# =============================================================================
# UTILIDADES
# =============================================================================


def odata_paginado(conn, entidad, params=None, page_size=500):
    """Paginación OData con header Prefer maxpagesize."""
    if params is None:
        params = {}
    todos = []
    skip = 0
    headers = {"Prefer": f"odata.maxpagesize={page_size}"}
    while True:
        params["$skip"] = skip
        url = f"{conn.base_url}/{entidad}"
        r = conn.session.get(url, params=params, headers=headers)
        if r.status_code != 200:
            print(f"   ❌ {r.status_code} en {entidad} skip={skip}: {r.text[:200]}")
            break
        data = r.json()
        if not data or "value" not in data or not data["value"]:
            break
        todos.extend(data["value"])
        recibidos = len(data["value"])
        if recibidos < 20:
            break
        skip += recibidos
        if skip > 200000:
            print(f"   ⚠️  Corte de seguridad en skip={skip}")
            break
    return todos


def sql_temporal_grande(conn, sql, page_size=500, mostrar_progreso=True):
    """Crea SQLQuery temporal, ejecuta con páginas grandes, borra al final."""
    qc = f"OPC_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{qc}')"
    resultados = []
    try:
        r = conn.session.post(
            url_post, json={"SqlCode": qc, "SqlName": "OPC", "SqlText": sql}
        )
        if r.status_code not in (200, 201):
            try:
                err = (
                    r.json().get("error", {}).get("message", {}).get("value", "")[:300]
                )
            except Exception:
                err = r.text[:300]
            print(f"   ❌ Error creando query temporal: {r.status_code}")
            print(f"      {err}")
            return []

        skip = 0
        pagina = 0
        t_inicio = time.time()
        headers = {"Prefer": f"odata.maxpagesize={page_size}"}
        while True:
            rr = conn.session.get(
                f"{conn.base_url}/SQLQueries('{qc}')/List",
                params={"$skip": skip},
                headers=headers,
            )
            if rr.status_code != 200:
                break
            data = rr.json()
            if not data or "value" not in data or not data["value"]:
                break
            resultados.extend(data["value"])
            recibidos = len(data["value"])
            pagina += 1

            # Mostrar progreso cada 10 páginas
            if mostrar_progreso and pagina % 10 == 0:
                print(
                    f"      Página {pagina}: +{recibidos} | "
                    f"acumulado: {len(resultados):6} | {time.time()-t_inicio:.1f}s"
                )

            if recibidos < 20:
                break
            skip += recibidos
            if skip > 2000000:  # corte solo si algo se rompió de verdad
                print(f"   ⚠️  Corte real en skip={skip} (algo raro pasó)")
                break
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass
    return resultados


def cache_valido():
    if not os.path.exists(CACHE_FILE):
        return False
    age_min = (time.time() - os.path.getmtime(CACHE_FILE)) / 60
    return age_min < CACHE_MAX_AGE_MIN


# =============================================================================
# FUENTE A — OSRQ con Quantity > 0 (series físicamente presentes)
# =============================================================================


def traer_series_presentes_osrq(conn, codigos_bodega):
    """
    De OSRQ traemos las series que tienen Quantity > 0 en bodegas de consignación.

    IMPORTANTE: NO hacemos JOIN con OSRN. La razón es que OSRN puede tener
    múltiples filas por la misma (ItemCode, SysNumber), generando producto
    cartesiano que infla la consulta a millones de filas. OSRQ solo es lo
    que necesitamos para validar presencia física + cruzar con traslados.

    Si después necesitamos DistNumber (serie del fabricante), lo traemos
    por separado solo de las claves que sobreviven al cruce.
    """
    print(f"\n📥 FUENTE A — OSRQ solo (Quantity>0) en {len(codigos_bodega)} bodegas")
    print(f"   Sin JOIN con OSRN para evitar producto cartesiano")

    in_list = ",".join(f"'{c}'" for c in codigos_bodega)
    sql = (
        'SELECT T0."WhsCode", T0."ItemCode", T0."SysNumber" '
        "FROM OSRQ T0 "
        f'WHERE T0."Quantity">0 AND T0."WhsCode" IN ({in_list})'
    )
    t0 = time.time()
    filas = sql_temporal_grande(conn, sql, page_size=500)
    print(f"   ✅ {len(filas)} filas brutas en {time.time()-t0:.1f}s")

    # Deduplicar en Python
    indice = {}
    duplicados = 0
    for f in filas:
        clave = (str(f["WhsCode"]), str(f["ItemCode"]), str(f["SysNumber"]))
        if clave in indice:
            duplicados += 1
            continue
        indice[clave] = {
            "WhsCode": f["WhsCode"],
            "ItemCode": f["ItemCode"],
            "SysNumber": f["SysNumber"],
        }
    print(f"   {len(indice)} series únicas (descartamos {duplicados} duplicados)")
    return indice


# =============================================================================
# FUENTE B — /StockTransfers abiertos con sus líneas y series
# =============================================================================


def traer_traslados_abiertos(conn, codigos_bodega):
    print(f"\n📥 FUENTE B — /StockTransfers abiertos a {len(codigos_bodega)} bodegas")
    traslados = []
    LOTE = 30
    t0 = time.time()
    for i in range(0, len(codigos_bodega), LOTE):
        chunk = codigos_bodega[i : i + LOTE]
        cond = " or ".join(f"ToWarehouse eq '{c}'" for c in chunk)
        filtro = f"DocumentStatus eq 'bost_Open' and ({cond})"
        lote = odata_paginado(
            conn,
            "StockTransfers",
            {
                "$filter": filtro,
                "$select": "DocEntry,DocNum,DocDate,CardCode,CardName,ToWarehouse",
            },
        )
        traslados.extend(lote)
        print(
            f"   Lote {i//LOTE+1}/{(len(codigos_bodega)-1)//LOTE+1}: "
            f"+{len(lote)} | total: {len(traslados)} | {time.time()-t0:.1f}s"
        )
    print(f"   ✅ {len(traslados)} traslados abiertos")
    return traslados


def traer_series_de_traslados(conn, traslados, debug=False):
    """
    Para cada traslado, descarga el detalle completo y extrae las series
    a nivel (WhsCode, ItemCode, SystemSerialNumber).
    """
    print(f"\n📥 Extrayendo series de {len(traslados)} traslados...")
    series_traslados = set()
    detalle_por_serie = {}  # clave → fecha, docnum, cardcode
    t0 = time.time()

    for i, t in enumerate(traslados, 1):
        de = t["DocEntry"]
        r = conn.session.get(f"{conn.base_url}/StockTransfers({de})")
        if r.status_code != 200:
            continue
        doc = r.json()
        for ln in doc.get("StockTransferLines", []):
            whs = ln.get("WarehouseCode")
            item = ln.get("ItemCode")
            for s in ln.get("SerialNumbers", []):
                # SystemSerialNumber es el SysNumber en OSRQ
                sysn = s.get("SystemSerialNumber")
                if sysn is None:
                    continue
                clave = (str(whs), str(item), str(sysn))
                series_traslados.add(clave)
                if clave not in detalle_por_serie:
                    detalle_por_serie[clave] = {
                        "DocNum": t.get("DocNum"),
                        "DocDate": (t.get("DocDate") or "")[:10],
                        "CardCodeTraslado": t.get("CardCode"),
                        "ManufacturerSerialNumber": s.get("ManufacturerSerialNumber"),
                        "InternalSerialNumber": s.get("InternalSerialNumber"),
                    }
        if i % 50 == 0 or i == len(traslados):
            tasa = i / max(time.time() - t0, 0.1)
            eta = (len(traslados) - i) / max(tasa, 0.1)
            print(
                f"   [{i:4}/{len(traslados)}] series únicas: {len(series_traslados):5} | "
                f"ETA: {eta:.0f}s"
            )

    print(f"   ✅ {len(series_traslados)} series únicas en traslados")
    return series_traslados, detalle_por_serie


# =============================================================================
# CRUCE Y ENRIQUECIMIENTO
# =============================================================================


def traer_clientes(conn, card_codes_necesarios):
    print(f"\n📥 Clientes ({len(card_codes_necesarios)} necesarios)...")
    todos = []
    LOTE = 50
    lista = list(card_codes_necesarios)
    for i in range(0, len(lista), LOTE):
        chunk = lista[i : i + LOTE]
        filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
        todos.extend(
            odata_paginado(
                conn,
                "BusinessPartners",
                {
                    "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                    "$filter": filtro,
                },
            )
        )
    # Traer padres faltantes
    cards_ya = {c["CardCode"] for c in todos}
    padres = {
        c["FatherCard"]
        for c in todos
        if c.get("FatherCard") and c["FatherCard"] not in cards_ya
    }
    if padres:
        plista = list(padres)
        for i in range(0, len(plista), LOTE):
            chunk = plista[i : i + LOTE]
            filtro = " or ".join(f"CardCode eq '{c}'" for c in chunk)
            todos.extend(
                odata_paginado(
                    conn,
                    "BusinessPartners",
                    {
                        "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
                        "$filter": filtro,
                    },
                )
            )
    print(f"   ✅ {len(todos)} clientes (incl. padres)")
    return todos


def traer_items(conn, item_codes):
    print(f"\n📥 Items ({len(item_codes)} necesarios)...")
    items_dict = {}
    LOTE = 50
    lista = list(item_codes)
    for i in range(0, len(lista), LOTE):
        chunk = lista[i : i + LOTE]
        filtro = " or ".join(f"ItemCode eq '{c}'" for c in chunk)
        for it in odata_paginado(
            conn, "Items", {"$select": "ItemCode,ItemName", "$filter": filtro}
        ):
            items_dict[it["ItemCode"]] = it.get("ItemName", "?")
    return items_dict


def traer_vendedores(conn):
    print("\n📥 Vendedores...")
    vs = odata_paginado(
        conn, "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"}
    )
    return {v["SalesEmployeeCode"]: v for v in vs}


# =============================================================================
# MAIN
# =============================================================================


def descargar_y_cruzar(debug=False):
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return None

    try:
        t_total = time.time()

        # --- Bodegas ---
        print("📥 Bodegas...")
        bodegas = odata_paginado(
            conn, "Warehouses", {"$select": "WarehouseCode,WarehouseName"}
        )
        bodegas_cons = [
            b["WarehouseCode"]
            for b in bodegas
            if b["WarehouseCode"] not in BODEGAS_INTERNAS
        ]
        print(
            f"   {len(bodegas_cons)} de consignación / {len(bodegas)-len(bodegas_cons)} internas"
        )
        bodegas_dict = {
            b["WarehouseCode"]: b.get("WarehouseName", "?") for b in bodegas
        }

        # --- FUENTE A: OSRQ ---
        indice_osrq = traer_series_presentes_osrq(conn, bodegas_cons)

        # --- FUENTE B: StockTransfers ---
        traslados = traer_traslados_abiertos(conn, bodegas_cons)
        series_traslados, detalle = traer_series_de_traslados(
            conn, traslados, debug=debug
        )

        # --- CRUCE: solo las que están en AMBOS ---
        print("\n🔀 Cruzando OSRQ ∩ StockTransfers...")
        intersecion = set(indice_osrq.keys()) & series_traslados
        solo_osrq = set(indice_osrq.keys()) - series_traslados
        solo_trasl = series_traslados - set(indice_osrq.keys())

        print(f"   En OSRQ (Quantity>0):              {len(indice_osrq):6}")
        print(f"   En traslados abiertos:             {len(series_traslados):6}")
        print(f"   ✅ EN AMBOS (consignación real):   {len(intersecion):6}")
        print(f"   Solo OSRQ (sin traslado abierto):  {len(solo_osrq):6}")
        print(f"   Solo traslado (no presente OSRQ):  {len(solo_trasl):6}")

        # --- Construir lista final con todos los datos ---
        equipos = []
        for clave in intersecion:
            whs, item, sysn = clave
            det = detalle.get(clave, {})
            equipos.append(
                {
                    "WhsCode": whs,
                    "ItemCode": item,
                    "SysNumber": sysn,
                    # Serie del fabricante viene de StockTransfers
                    "ManufacturerSerialNumber": det.get("ManufacturerSerialNumber"),
                    "InternalSerialNumber": det.get("InternalSerialNumber"),
                    "DocNum": det.get("DocNum"),
                    "DocDate": det.get("DocDate"),
                    "CardCodeTraslado": det.get("CardCodeTraslado"),
                    "BodegaNombre": bodegas_dict.get(whs, "?"),
                }
            )

        # --- Enriquecer con clientes / items / vendedores ---
        card_codes = {
            e["CardCodeTraslado"] for e in equipos if e.get("CardCodeTraslado")
        }
        clientes = traer_clientes(conn, card_codes)
        clientes_dict = {c["CardCode"]: c for c in clientes}

        item_codes = {e["ItemCode"] for e in equipos}
        items_dict = traer_items(conn, item_codes)

        vendedores = traer_vendedores(conn)

        # --- Aplicar jerarquía padre/hijo y armar resultado final ---
        print("\n🔀 Aplicando jerarquía padre/hijo...")
        for e in equipos:
            cc = e["CardCodeTraslado"]
            if not cc or cc not in clientes_dict:
                e["SalesPersonCode"] = -99  # huérfano
                continue
            cli = clientes_dict[cc]
            father = cli.get("FatherCard")
            if father and father in clientes_dict:
                cli_principal = clientes_dict[father]
                e["TiendaCardCode"] = cli["CardCode"]
            else:
                cli_principal = cli
                e["TiendaCardCode"] = ""
            e["ClienteCardCode"] = cli_principal["CardCode"]
            e["ClienteNombre"] = cli_principal.get("CardName", "?")
            e["Zona"] = cli_principal.get("U_ZGIRA", "")
            e["SalesPersonCode"] = cli_principal.get("SalesPersonCode", -1)
            e["ItemName"] = items_dict.get(e["ItemCode"], "?")

        print(f"   ✅ {len(equipos)} equipos finales")
        print(f"\n⏱️  Tiempo total: {time.time()-t_total:.1f}s")

        return {
            "timestamp": datetime.now().isoformat(),
            "equipos": equipos,
            "vendedores": {str(k): v for k, v in vendedores.items()},
            "diagnostico": {
                "osrq_total": len(indice_osrq),
                "traslados_series": len(series_traslados),
                "interseccion": len(intersecion),
                "solo_osrq": len(solo_osrq),
                "solo_traslados": len(solo_trasl),
            },
        }
    finally:
        conn.logout()


def reportar(data):
    equipos = data["equipos"]
    vendedores = {
        int(k) if str(k).lstrip("-").isdigit() else k: v
        for k, v in data["vendedores"].items()
    }

    por_agente = defaultdict(list)
    for e in equipos:
        por_agente[e.get("SalesPersonCode", -99)].append(e)

    print("\n" + "=" * 80)
    print(
        f"📊 RESULTADO OPCIÓN C — {len(equipos)} equipos en {len(por_agente)} agentes"
    )
    print("=" * 80)
    print(
        f"\n{'SlpCode':<10} {'Agente':<35} {'Equipos':<10} {'Referencia Tania':<20} {'Diff'}"
    )
    print("-" * 100)
    for slp, eqs in sorted(por_agente.items(), key=lambda x: -len(x[1])):
        info = vendedores.get(slp, {})
        nombre = info.get("SalesEmployeeName", f"({slp})")[:34]
        ref = CIFRAS_REFERENCIA.get(slp)
        ref_str = f"{ref[1]} (feb 2026)" if ref else "—"
        diff = ""
        if ref:
            d = len(eqs) - ref[1]
            diff = f"{'+' if d > 0 else ''}{d}"
        print(f"{str(slp):<10} {nombre:<35} {len(eqs):<10} {ref_str:<20} {diff}")

    diag = data.get("diagnostico", {})
    if diag:
        print("\n🔬 Diagnóstico del cruce:")
        print(f"   OSRQ con Quantity>0 (presentes):   {diag.get('osrq_total')}")
        print(f"   Series en traslados abiertos:      {diag.get('traslados_series')}")
        print(f"   ✅ Intersección (lo correcto):     {diag.get('interseccion')}")
        print(f"   Solo OSRQ (descartadas):           {diag.get('solo_osrq')}")
        print(f"   Solo traslados (descartadas):      {diag.get('solo_traslados')}")


def main():
    debug = "--debug" in sys.argv

    if cache_valido() and "--refresh" not in sys.argv:
        print(f"💾 Usando cache ({CACHE_FILE})")
        print("   Usá --refresh para forzar consulta a SAP")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = descargar_y_cruzar(debug=debug)
        if data is None:
            return
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    reportar(data)


if __name__ == "__main__":
    main()
