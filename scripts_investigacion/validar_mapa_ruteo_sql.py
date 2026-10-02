r"""
validar_mapa_ruteo_sql.py - Quimicas Unidas / ADSX0019

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA sobre los datos. GET mas los POST/DELETE a /SQLQueries que son el
mecanismo del propio Service Layer para ejecutar SQL: crea un query temporal
con nombre unico, lo lee y lo borra. Es lo que ya hace ejecutar_sql_sl() en
cada corrida de produccion. No escribe datos de negocio, no edita, no elimina,
no envia correo, no genera PDF, no toca SharePoint ni Supabase. No importa
api.py.

PREGUNTA QUE RESPONDE
---------------------
Es el PASO 0 (bloqueante) del prefiltro de "Giras por Zona": el mapa que arme
el SQL tiene que coincidir, cliente por cliente, con lo que decide el Python
que genera el PDF. Si la pantalla dice "3 docs" y el PDF sale con 0, cambiamos
una confusion por otra peor.

El oraculo es obtener_documentos_cliente() importada de agentes.py tal cual,
que es la misma funcion que usa la gira real.

QUE YA SE VERIFICO (30/09/2026, primera corrida)
------------------------------------------------
  - Acceso por SQL a OCRD, CRD1, OINV, ORIN y JDT1: las cinco responden, con
    todas las columnas que el ruteo necesita. Los nombres son los de la BASE,
    no los de OData: DocCur, PaidFC, DocTotalFC, CRD1.AdresType.
  - El parser de /SQLQueries NO acepta funciones escalares (ABS, COALESCE,
    UPPER, TRIM), ni aritmetica en el SELECT, ni CASE, ni subqueries, ni
    SELECT *. Por eso el SQL trae filas CRUDAS y todo el calculo se hace en
    Python, reusando las reglas de procesar_documento().
  - /SQLQueries/List devuelve 20 filas si no se le manda
    "Prefer: odata.maxpagesize". Arreglado en ejecutar_sql_sl().

EL UNIVERSO, Y POR QUE ES MAS GRANDE DE LO QUE PARECE
-----------------------------------------------------
El arbol de hoy (sap.ts) filtra por SalesPersonCode de la FICHA del cliente.
El PDF rutea por U_CODV de la DIRECCION del documento. Son dos universos
distintos, y por eso se comparan las tres regiones:

  A \ B  el SQL los suma y el arbol viejo no los mostraba  (los faltantes)
  A & B  los que ambos reconocen
  B \ A  el arbol los ofrece y no aportan nada             (los inutiles)

Genera: Verificacion_Mapa_Ruteo_SQL.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/validar_mapa_ruteo_sql.py
"""

import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection, ejecutar_sql_sl
from agentes import (
    GIRA_ZONA_MAX_WORKERS,
    TIPOS_QUE_RESTAN,
    obtener_clientes_con_saldo,
    obtener_documentos_cliente,
    obtener_saldos_favor_masivo,
    obtener_todos_paginado,
    obtener_vendedores,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Mapa_Ruteo_SQL.txt")

# Cuantos clientes se verifican contra el oraculo por region y agente. Cada
# cliente cuesta ~3 llamadas a SAP: recorrer los ~413 completos seria la misma
# espera de 10 minutos de la gira entera.
MUESTRA_POR_REGION = 12

# Casos ya documentados. Si uno falla, el SQL esta mal aunque el resto coincida.
# C0042 tiene 77 documentos abiertos y 45 rutean al agente 7
# (scripts_investigacion/zonas_con_facturas.py y desglose_c0042.py).
CASOS_CONOCIDOS = {("C0042", 7): 45}

# Los tres que salieron omitidos el 27/09/2026 para el agente 9: eran
# sucursales sin ningun documento abierto. Deben seguir dando cero.
OMITIDOS_CONOCIDOS = [("C0037", 9), ("C0080", 9), ("C0121", 9)]

_lineas = []


def log(texto=""):
    print(texto)
    _lineas.append(texto)


def titulo(t):
    log("")
    log("=" * 78)
    log(t)
    log("=" * 78)


def guardar():
    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lineas))
    print("")
    print(f"Reporte guardado en: {REPORTE}")


def normalizar_codigo_zona(valor) -> str:
    """Misma normalizacion que normalizarCodigoZona() de sap.ts: en SAP hay
    clientes con U_ZGIRA = '06' mientras U_GIRAS guarda '6'."""
    s = str(valor if valor is not None else "").strip()
    if not s:
        return ""
    return str(int(s)) if s.isdigit() else s


# ----------------------------------------------------------------------------
# Los queries: columnas planas y nada mas. El parser no acepta otra cosa.
# ----------------------------------------------------------------------------

COLUMNAS_DOC = (
    'T0."CardCode", T0."ShipToCode", T0."DocCur", T0."DocTotal", '
    'T0."PaidToDate", T0."DocTotalFC", T0."PaidFC", T0."U_TDOC", '
    'T2."U_CODV", T1."SlpCode", T1."CardName", T1."U_ZGIRA", '
    'T1."FatherCard", T1."Phone1", T1."Phone2", T1."Cellular"'
)

JOINS_DOC = (
    'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."CardCode" '
    'LEFT JOIN "CRD1" T2 ON T2."CardCode" = T0."CardCode" '
    'AND T2."Address" = T0."ShipToCode" AND T2."AdresType" = \'S\''
)


def sql_facturas():
    """Facturas abiertas, sin filtro de fecha: la deuda vieja sigue siendo deuda."""
    return (
        f'SELECT {COLUMNAS_DOC} FROM "OINV" T0 {JOINS_DOC} '
        f"WHERE T0.\"DocStatus\" = 'O' AND T1.\"CardType\" = 'C'"
    )


def sql_notas_credito():
    """Notas de credito abiertas desde 2022 (agentes.py evita la basura vieja)."""
    return (
        f'SELECT {COLUMNAS_DOC} FROM "ORIN" T0 {JOINS_DOC} '
        f"WHERE T0.\"DocStatus\" = 'O' AND T1.\"CardType\" = 'C' "
        f"AND T0.\"DocDate\" >= '20220101'"
    )


def sql_saldos_favor():
    """Filas PR colapsadas por cliente y moneda.

    Ruteo distinto al de los documentos: van por SlpCode del cliente, NO por
    direccion (agentes.py: doc_pr['vendedor_final'] = vendedor_general). Y
    siempre restan, asi que un SUM alcanza y no hace falta logica por fila.

    El INNER JOIN con OCRD no es decorativo: JDT1."ShortName" mezcla codigos
    de BP con cuentas de mayor, y las cuentas contables tienen decenas de miles
    de filas. Produccion solo consulta codigos de BP.
    """
    return (
        'SELECT T0."ShortName", T0."FCCurrency", COUNT(*) AS "N", '
        'SUM(T0."BalDueCred") AS "CRC", SUM(T0."BalFcCred") AS "USD", '
        'T1."SlpCode" '
        'FROM "JDT1" T0 '
        'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."ShortName" '
        "WHERE T0.\"BalDueCred\" > 0 AND T0.\"RefDate\" >= '20220101' "
        "AND T0.\"TransType\" NOT IN ('13', '14', '30') "
        "AND T1.\"CardType\" = 'C' "
        'GROUP BY T0."ShortName", T0."FCCurrency", T1."SlpCode"'
    )


def saldo_y_moneda(fila, es_nota_credito):
    """Replica procesar_documento() de agentes.py sobre una fila cruda de SQL.

    Ojo con el patron `DocTotalFc or DocTotal`: si el total en moneda
    extranjera viene en 0, el original cae al total en colones. Se replica tal
    cual, incluido ese detalle, porque es lo que decide el monto del PDF.

    Devuelve (saldo, moneda) o (None, None) si el documento no entra.
    """
    def num(v):
        return float(v or 0)

    if str(fila.get("DocCur") or "") in ["USD", "US$", "DOL"]:
        total = num(fila.get("DocTotalFC")) or num(fila.get("DocTotal"))
        pagado = num(fila.get("PaidFC")) or num(fila.get("PaidToDate"))
        moneda = "USD"
    else:
        total = num(fila.get("DocTotal"))
        pagado = num(fila.get("PaidToDate"))
        moneda = "CRC"

    saldo = total - pagado
    if abs(saldo) < 0.005:
        return None, None

    tipo_doc = str(fila.get("U_TDOC") or "").strip().upper()
    if es_nota_credito or tipo_doc in TIPOS_QUE_RESTAN or tipo_doc == "PR":
        saldo = -abs(saldo)

    return saldo, moneda


def vendedor_de(fila):
    """U_CODV de la direccion del documento; si no hay, el SalesPersonCode.

    obtener_mapeo_direcciones() solo mapea las direcciones cuyo U_CODV no es
    None ni cadena vacia, y despues hace mapeo.get(destino, vendedor_general).
    Una direccion sin U_CODV cae al vendedor del cliente igual que una
    inexistente.
    """
    u_codv = fila.get("U_CODV")
    if u_codv is not None and str(u_codv).strip() != "":
        try:
            return int(u_codv)
        except (TypeError, ValueError):
            pass
    try:
        return int(fila.get("SlpCode") or -1)
    except (TypeError, ValueError):
        return -1


def resumen_oraculo(conn, cliente, agente_id):
    """Lo que de verdad llega al PDF de ese agente, segun el Python de produccion.

    Misma logica que resumen_cliente() de zonas_con_facturas.py: documentos
    ruteados al agente, y la regla de procesar_datos_cliente() de descartar un
    perfil cuyos totales quedan en cero en las dos monedas.

    saldos_favor_cache=None deja fuera las filas PR, igual que el oraculo
    existente: se compara contra el SQL de documentos, y las PR se validan
    aparte en el Paso D.
    """
    docs = obtener_documentos_cliente(conn, cliente, saldos_favor_cache=None)
    mios = [d for d in docs if str(d.get("vendedor_final")) == str(agente_id)]

    total_crc = sum(d["saldo"] for d in mios if d["moneda"] == "CRC")
    total_usd = sum(d["saldo"] for d in mios if d["moneda"] == "USD")
    if total_crc == 0 and total_usd == 0:
        return {"docs": 0, "crc": 0.0, "usd": 0.0}

    return {"docs": len(mios), "crc": total_crc, "usd": total_usd}


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("VALIDACION DEL MAPA DE RUTEO POR SQL - Paso 0 del prefiltro")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("SOLO LECTURA de datos. GET + los POST/DELETE a /SQLQueries que son el")
    log("mecanismo del Service Layer para correr SQL. No envia nada.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return

    try:
        # ------------------------------------------------------------------
        titulo("PASO A - Los queries crudos")

        vendedores = obtener_vendedores(conn)
        con_correo = {
            vid: v for vid, v in vendedores.items() if (v.get("correo") or "").strip()
        }
        log("")
        log(f"   Agentes con correo en SAP: {len(con_correo)}")
        for vid in sorted(con_correo):
            log(f"      {vid:<4} | {con_correo[vid].get('nombre', '')}")

        log("")
        t0 = datetime.now()
        facturas = ejecutar_sql_sl(conn, sql_facturas())
        log(f"   OINV abiertas            : {len(facturas):>6,} filas "
            f"({(datetime.now() - t0).total_seconds():.1f}s)")

        t0 = datetime.now()
        notas = ejecutar_sql_sl(conn, sql_notas_credito())
        log(f"   ORIN abiertas desde 2022 : {len(notas):>6,} filas "
            f"({(datetime.now() - t0).total_seconds():.1f}s)")

        t0 = datetime.now()
        filas_pr = ejecutar_sql_sl(conn, sql_saldos_favor())
        log(f"   JDT1 PR agrupadas        : {len(filas_pr):>6,} filas "
            f"({(datetime.now() - t0).total_seconds():.1f}s)")

        if not facturas:
            log("")
            log("   Sin facturas no hay nada que validar. Se corta.")
            return

        # El LEFT JOIN con CRD1 puede duplicar filas si un cliente tiene dos
        # direcciones ShipTo con el MISMO nombre: ahi el documento se contaria
        # dos veces. Se compara contra el conteo pelado de OINV.
        base = ejecutar_sql_sl(
            conn,
            'SELECT COUNT(*) AS "N" FROM "OINV" T0 '
            'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."CardCode" '
            "WHERE T0.\"DocStatus\" = 'O' AND T1.\"CardType\" = 'C'",
        )
        n_base = int(base[0]["N"]) if base else 0
        log("")
        log(f"   Control de duplicados por el JOIN con CRD1:")
        log(f"      OINV sin el join : {n_base:>6,}")
        log(f"      OINV con el join : {len(facturas):>6,}")
        if len(facturas) != n_base:
            log("")
            log("   ATENCION: el join duplica filas. Hay clientes con dos")
            log("   direcciones ShipTo del mismo nombre, y cada documento se")
            log("   estaria contando mas de una vez. Hay que deduplicar por")
            log("   DocEntry antes de seguir.")
        else:
            log("      Sin duplicados.")

        # ------------------------------------------------------------------
        titulo("PASO B - El mapa, calculado en Python")
        log("")
        log("   El parser de /SQLQueries no acepta funciones ni aritmetica, asi")
        log("   que el saldo, el signo y el ruteo se calculan aca, con las")
        log("   mismas reglas de procesar_documento().")

        # mapa_docs: solo documentos, es lo comparable contra el oraculo.
        mapa_docs = defaultdict(lambda: {"docs": 0, "crc": 0.0, "usd": 0.0})
        descartados = 0

        for filas, es_nc in ((facturas, False), (notas, True)):
            for f in filas:
                saldo, moneda = saldo_y_moneda(f, es_nc)
                if saldo is None:
                    descartados += 1
                    continue
                clave = (str(f.get("CardCode") or "").strip(), vendedor_de(f))
                mapa_docs[clave]["docs"] += 1
                mapa_docs[clave][moneda.lower()] += saldo

        log("")
        log(f"   Documentos descartados por saldo < 0.005: {descartados:,}")
        log(f"   Pares (cliente, vendedor) antes de la regla del cero: "
            f"{len(mapa_docs):,}")

        # Regla de procesar_datos_cliente(): totales en cero en las dos monedas
        # no llegan al PDF.
        mapa_docs = {
            k: v
            for k, v in mapa_docs.items()
            if round(v["crc"], 2) != 0 or round(v["usd"], 2) != 0
        }
        log(f"   Pares elegibles por documentos: {len(mapa_docs):,}")

        # Las fichas, de las mismas filas: el endpoint no necesitara OData.
        fichas = {}
        for filas in (facturas, notas):
            for f in filas:
                cc = str(f.get("CardCode") or "").strip()
                if cc and cc not in fichas:
                    fichas[cc] = f

        # El mapa completo suma las filas PR, que rutean por SlpCode.
        mapa_total = defaultdict(lambda: {"docs": 0, "crc": 0.0, "usd": 0.0})
        for k, v in mapa_docs.items():
            mapa_total[k] = dict(v)
        for r in filas_pr:
            cc = str(r.get("ShortName") or "").strip()
            try:
                vend = int(r.get("SlpCode") or -1)
            except (TypeError, ValueError):
                vend = -1
            if not cc:
                continue
            es_usd = str(r.get("FCCurrency") or "") in ["USD", "US$", "DOL"]
            monto = float(r.get("USD") or 0) if es_usd else float(r.get("CRC") or 0)
            if abs(monto) < 0.005:
                continue
            mapa_total[(cc, vend)]["docs"] += int(r.get("N") or 0)
            mapa_total[(cc, vend)]["usd" if es_usd else "crc"] += -abs(monto)

        mapa_total = {
            k: v
            for k, v in mapa_total.items()
            if round(v["crc"], 2) != 0 or round(v["usd"], 2) != 0
        }
        log(f"   Pares elegibles con las filas PR incluidas: {len(mapa_total):,}")

        # ------------------------------------------------------------------
        titulo("PASO C - Fidelidad contra el oraculo (agentes.py)")
        log("")
        log("   El oraculo es obtener_documentos_cliente() importada tal cual: la")
        log("   misma funcion que usa la gira real.")
        log("")
        log("   Trayendo el universo de clientes por OData (lento, ~350 llamadas)...")

        todos = obtener_clientes_con_saldo(conn)
        por_codigo = {c.get("CardCode"): c for c in todos}
        log(f"   Universo de obtener_clientes_con_saldo(): {len(todos):,} clientes")

        # El filtro de produccion es
        #   CardType eq 'cCustomer' and (CurrentAccountBalance ne 0
        #                                or FatherCard ne null)
        # y en OData ese "ne null" matchea tambien la cadena vacia, asi que en
        # la practica el universo es todo cCustomer. Se verifica en vez de
        # asumirlo, porque de eso depende a quien se le consultan documentos.
        solo_c = ejecutar_sql_sl(
            conn,
            'SELECT COUNT(*) AS "N" FROM "OCRD" T0 WHERE T0."CardType" = \'C\'',
        )
        n_solo_c = int(solo_c[0]["N"]) if solo_c else 0
        log(f"   OCRD con CardType = 'C'                 : {n_solo_c:,}")
        if abs(len(todos) - n_solo_c) <= max(5, n_solo_c * 0.01):
            log("   -> Coinciden: el 'or FatherCard ne null' hace que el filtro")
            log("      equivalga a todo cCustomer, como se suponia.")
        else:
            log("   -> NO coinciden. El filtro de OData recorta mas de lo que")
            log("      replica el SQL; hay que mirarlo antes del Paso 1.")

        arbol_viejo = defaultdict(set)
        for c in todos:
            vid = c.get("SalesPersonCode")
            if vid in con_correo:
                arbol_viejo[vid].add(c.get("CardCode"))

        sql_por_agente = defaultdict(set)
        for (cc, vend) in mapa_docs:
            if vend in con_correo:
                sql_por_agente[vend].add(cc)

        a_verificar = []
        for vid in sorted(con_correo):
            nuevos = sorted(sql_por_agente[vid] - arbol_viejo[vid])
            comunes = sorted(sql_por_agente[vid] & arbol_viejo[vid])
            inutiles = sorted(arbol_viejo[vid] - sql_por_agente[vid])
            for cc in nuevos[:MUESTRA_POR_REGION]:
                a_verificar.append((cc, vid, "nuevo"))
            for cc in comunes[:MUESTRA_POR_REGION]:
                a_verificar.append((cc, vid, "comun"))
            for cc in inutiles[:MUESTRA_POR_REGION]:
                a_verificar.append((cc, vid, "inutil"))

        ya = {(cc, vid) for cc, vid, _ in a_verificar}
        for (cc, vid) in list(CASOS_CONOCIDOS) + OMITIDOS_CONOCIDOS:
            if (cc, vid) not in ya:
                a_verificar.append((cc, vid, "conocido"))

        sin_ficha = [t for t in a_verificar if t[0] not in por_codigo]
        a_verificar = [t for t in a_verificar if t[0] in por_codigo]

        log("")
        log(f"   Clientes a verificar: {len(a_verificar)} "
            f"(hasta {MUESTRA_POR_REGION} por region y agente, mas los conocidos)")
        if sin_ficha:
            log(f"   Sin ficha en el universo, no verificables: "
                f"{[t[0] for t in sin_ficha]}")
        log("")

        discrepancias = []
        verificados = 0

        with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as executor:
            futuros = {
                executor.submit(resumen_oraculo, conn, por_codigo[cc], vid):
                    (cc, vid, reg)
                for (cc, vid, reg) in a_verificar
            }
            for futuro in as_completed(futuros):
                cc, vid, reg = futuros[futuro]
                verificados += 1
                print(f"   Progreso: {verificados}/{len(a_verificar)}...", end="\r")
                try:
                    real = futuro.result()
                except Exception as e:
                    discrepancias.append((cc, vid, reg, "error", str(e)[:60]))
                    continue

                dicho = mapa_docs.get((cc, vid), {"docs": 0, "crc": 0.0, "usd": 0.0})
                if real["docs"] != dicho["docs"]:
                    discrepancias.append(
                        (cc, vid, reg, "docs",
                         f"SQL {dicho['docs']} vs Python {real['docs']}"))
                elif abs(real["crc"] - dicho["crc"]) > 0.05:
                    discrepancias.append(
                        (cc, vid, reg, "CRC",
                         f"SQL {dicho['crc']:,.2f} vs Python {real['crc']:,.2f}"))
                elif abs(real["usd"] - dicho["usd"]) > 0.05:
                    discrepancias.append(
                        (cc, vid, reg, "USD",
                         f"SQL {dicho['usd']:,.2f} vs Python {real['usd']:,.2f}"))

        print(" " * 60, end="\r")

        if discrepancias:
            log(f"   DISCREPANCIAS: {len(discrepancias)} de {len(a_verificar)}")
            log("")
            log(f"   {'CLIENTE':<11} {'AG':<4} {'REGION':<9} {'CAMPO':<6} DETALLE")
            log("   " + "-" * 70)
            for cc, vid, reg, campo, detalle in sorted(discrepancias):
                log(f"   {cc:<11} {vid:<4} {reg:<9} {campo:<6} {detalle}")
        else:
            log(f"   SIN DISCREPANCIAS en los {len(a_verificar)} clientes "
                f"verificados, en las tres regiones.")

        log("")
        log("   Casos documentados:")
        for (cc, vid), esperado in CASOS_CONOCIDOS.items():
            dicho = mapa_docs.get((cc, vid), {"docs": 0})
            marca = "OK" if dicho["docs"] == esperado else "FALLA"
            log(f"      {marca:<6} {cc} / agente {vid}: SQL dice {dicho['docs']} "
                f"docs, esperado {esperado}")
        for (cc, vid) in OMITIDOS_CONOCIDOS:
            dicho = mapa_docs.get((cc, vid), {"docs": 0})
            marca = "OK" if dicho["docs"] == 0 else "FALLA"
            log(f"      {marca:<6} {cc} / agente {vid}: SQL dice {dicho['docs']} "
                f"docs, esperado 0 (omitido el 27/09/2026)")

        # ------------------------------------------------------------------
        titulo("PASO D - Forma del arbol nuevo")

        zonas_raw = obtener_todos_paginado(conn, "U_GIRAS", {}, "Code")
        mapa_zonas = {
            normalizar_codigo_zona(z.get("Code")): z.get("Name") or ""
            for z in zonas_raw
        }

        log("")
        log(f"   {'AG':<4} {'AGENTE':<20} {'VIEJO':>7} {'NUEVO':>7} "
            f"{'FALTAN':>7} {'INUTIL':>7} {'S/ZONA':>7}")
        log("   " + "-" * 70)

        detalle_sin_zona = {}
        for vid in sorted(con_correo):
            del_agente = {cc for (cc, v) in mapa_total if v == vid}
            viejo = arbol_viejo[vid]
            nuevos = del_agente - viejo
            inutiles = viejo - del_agente

            sin_zona = set()
            for cc in del_agente:
                ficha = fichas.get(cc) or por_codigo.get(cc) or {}
                if not normalizar_codigo_zona(ficha.get("U_ZGIRA")):
                    sin_zona.add(cc)
            detalle_sin_zona[vid] = (sin_zona, nuevos)

            log(f"   {vid:<4} {con_correo[vid].get('nombre', '')[:20]:<20} "
                f"{len(viejo):>7} {len(del_agente):>7} {len(nuevos):>7} "
                f"{len(inutiles):>7} {len(sin_zona):>7}")

        log("")
        log("   VIEJO  : lo que el arbol muestra hoy (SalesPersonCode de la ficha).")
        log("   NUEVO  : clientes con carga real ruteada a ese agente.")
        log("   FALTAN : estaban ausentes del arbol y si aportan al PDF.")
        log("   INUTIL : el arbol los ofrece y no aportan nada.")
        log("   S/ZONA : de los NUEVO, cuantos tienen U_ZGIRA vacio.")

        titulo("PASO D-bis - Cuanta interfaz necesita el grupo 'sin zona'")
        log("")
        log("   Hoy sinZona esta siempre vacio y en la UI es un contador muerto")
        log("   (girazonapanel.svelte:609-617). Si con el universo corregido deja")
        log("   de estarlo, necesita lista propia y seleccionable.")
        log("")
        for vid in sorted(con_correo):
            sin_zona, nuevos = detalle_sin_zona[vid]
            nombre = con_correo[vid].get("nombre", "")
            log(f"   Agente {vid} - {nombre}")
            if not sin_zona:
                log("      Ninguno sin zona: el grupo sigue vacio.")
            else:
                de_los_nuevos = sin_zona & nuevos
                log(f"      {len(sin_zona)} sin U_ZGIRA, de los cuales "
                    f"{len(de_los_nuevos)} son clientes nuevos.")
                log(f"      Ejemplos: {sorted(sin_zona)[:10]}")

        log("")
        log(f"   Zonas en la UDT U_GIRAS: {len(mapa_zonas)}")

        # ------------------------------------------------------------------
        titulo("PASO E - Las filas PR, contra obtener_saldos_favor_masivo()")
        log("")
        log("   El oraculo del Paso C corre con saldos_favor_cache=None, asi que")
        log("   las PR se validan aparte contra la funcion de produccion.")

        pr_por_cliente = defaultdict(int)
        for r in filas_pr:
            cc = str(r.get("ShortName") or "").strip()
            if cc:
                pr_por_cliente[cc] += int(r.get("N") or 0)

        muestra_pr = sorted(pr_por_cliente.items(), key=lambda kv: -kv[1])[:8]
        if muestra_pr:
            cache = obtener_saldos_favor_masivo(conn, [cc for cc, _ in muestra_pr])
            log("")
            log(f"   {'CLIENTE':<12} {'SQL':>8} {'PRODUCCION':>12}   ESTADO")
            log("   " + "-" * 48)
            for cc, n in muestra_pr:
                devuelto = len(cache.get(cc, []))
                estado = "OK" if devuelto == n else "REVISAR"
                log(f"   {cc:<12} {n:>8,} {devuelto:>12,}   {estado}")
        else:
            log("")
            log("   No hay filas PR de clientes reales.")

        # ------------------------------------------------------------------
        titulo("VEREDICTO")
        log("")
        if discrepancias:
            log("   NO PASA. El SQL no coincide con el Python; ver Paso C.")
            log("   No seguir al Paso 1 hasta cerrar esas diferencias.")
        else:
            log("   PASA. Los queries de columnas planas mas el calculo en Python")
            log("   reproducen al Python de produccion. Se puede construir")
            log("   obtener_mapa_ruteo_masivo() con esto.")
        log("")
        log(f"   Duracion: {(datetime.now() - inicio).total_seconds():.1f} segundos")

    finally:
        try:
            conn.logout()
        except Exception:
            pass
        guardar()


if __name__ == "__main__":
    main()
