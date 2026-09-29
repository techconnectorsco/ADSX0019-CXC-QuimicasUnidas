"""
verificacion_giras_zona.py - Quimicas Unidas
Verificacion previa a la implementacion del modulo "Giras por Zona".

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA. Unicamente ejecuta GET contra SAP Service Layer.
Las unicas peticiones que no son GET son /Login y /Logout, que es como
el Service Layer autentica: crean y cierran una sesion, no tocan datos.

NO hace: POST/PUT/DELETE sobre entidades, SQLQueries (ni el temporal que
si usa el codigo de produccion), generacion de PDF, subida a SharePoint,
envio de correo, escritura en Supabase.
NO importa agentes.py ni main.py, por lo que no toca ninguna variable
global de esos modulos (MODO_PRUEBA, EMAIL_PRUEBA, status_global_giras).

POR QUE EXISTE
--------------
Antes de escribir el modulo hay cuatro decisiones de codigo que no se
pueden tomar sin datos reales. Este script las responde:

  1. Existe y responde la UDT @GIRAS (U_GIRAS) por Service Layer?
     -> Define si obtenerZonas() se consulta o si los nombres de zona
        se hardcodean como constantes en el frontend.

  2. Cuantos clientes tienen facturas ruteadas a un vendedor distinto
     al SalesPersonCode del cliente (via BPAddresses.U_CODV)?
     -> El arbol de la web agrupa por vendedor DEL CLIENTE, pero el motor
        (agentes.py) asigna cada documento al vendedor DE LA DIRECCION.
        Si el desajuste es 0, el riesgo de "PDF vacio" no existe.
        Si es alto, hay que devolver el conteo real a la interfaz.

  3. Cuantos clientes con FatherCard y saldo 0 quedarian fuera del arbol?
     -> La gira completa los incluye (filtro: saldo != 0 OR FatherCard != null),
        el arbol propuesto no. Mide el tamano real de esa diferencia.

  4. Sigue viva la BD de pruebas ZSBO_CR_QUIMICAS_TEST?
     -> Define si hay entorno seguro para probar el resto del desarrollo.

Genera: Verificacion_Giras_Por_Zona.txt (raiz del proyecto)

Uso:  python scripts_investigacion/verificacion_giras_zona.py
"""

import os
import sys
from collections import defaultdict
from datetime import datetime

# Consola Windows: inmunizar prints contra acentos y caracteres de SAP
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection

REPORTE = os.path.join(BASE_DIR, "Verificacion_Giras_Por_Zona.txt")

# Acumulador del reporte: todo lo que se imprime tambien se guarda
_lineas = []


def log(texto=""):
    print(texto)
    _lineas.append(texto)


def titulo(texto):
    log("")
    log("=" * 78)
    log(texto)
    log("=" * 78)


def get_paginado(conn, entidad, params, campo_orden):
    """Paginacion identica a la de agentes.py (solo GET)."""
    todos = []
    skip = 0
    page_size = 20
    params = dict(params)
    params["$top"] = page_size
    params["$orderby"] = campo_orden

    while True:
        params["$skip"] = skip
        res = conn.get(entidad, params)
        if not res or "value" not in res or len(res["value"]) == 0:
            break
        todos.extend(res["value"])
        if len(res["value"]) < page_size:
            break
        skip += page_size
        if skip >= 10000:
            break
    return todos


# =============================================================================
# CHECK 1 - La UDT @GIRAS responde por Service Layer?
# =============================================================================
def check_udt_giras(conn):
    titulo("CHECK 1 - Tabla de zonas (UDT @GIRAS)")

    mapa_zonas = {}
    nombre_entidad_ok = None

    # El Service Layer expone las UDT como U_<NOMBRE>. Se prueban variantes
    # por si la tabla esta registrada con otro nombre.
    for entidad in ["U_GIRAS", "U_ZGIRAS", "U_MGIRAS"]:
        log("")
        log(f"   Probando entidad '{entidad}'...")
        res = conn.get(entidad, {"$top": 50, "$orderby": "Code"})

        if res and "value" in res:
            filas = res["value"]
            log(f"   [OK] Responde. Registros en la primera pagina: {len(filas)}")
            if filas:
                log(f"   Campos disponibles: {list(filas[0].keys())}")
                nombre_entidad_ok = entidad
                todas = get_paginado(conn, entidad, {}, "Code")
                for z in todas:
                    code = str(z.get("Code"))
                    mapa_zonas[code] = z.get("Name") or f"Zona {code}"
                log(f"   Total de zonas leidas: {len(mapa_zonas)}")
                break
            else:
                log("   [--] Responde pero sin registros.")
        else:
            log("   [--] No accesible (sin permiso o no existe).")

    log("")
    if mapa_zonas:
        log(f"   RESULTADO: la UDT responde como '{nombre_entidad_ok}'.")
        log("   -> obtenerZonas() del plan es viable tal cual.")
        log("")
        log(f"   {'CODE':<8} | NOMBRE")
        log("   " + "-" * 60)
        for code in sorted(mapa_zonas, key=lambda x: (len(x), x)):
            log(f"   {code:<8} | {mapa_zonas[code]}")
    else:
        log("   RESULTADO: la UDT NO respondio por Service Layer.")
        log("   -> Plan B: hardcodear el mapa codigo->nombre en types.ts.")

    return mapa_zonas


# =============================================================================
# CHECK 2 - Agentes activos (regla de negocio: tienen correo)
# =============================================================================
def check_agentes(conn):
    titulo("CHECK 2 - Agentes con correo en SAP")

    vendedores = get_paginado(
        conn,
        "SalesPersons",
        {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"},
        "SalesEmployeeCode",
    )

    activos = {}
    for v in vendedores:
        code = v.get("SalesEmployeeCode")
        email = v.get("Email") or ""
        if code != -1 and "@" in str(email):
            activos[code] = {"nombre": v.get("SalesEmployeeName", ""), "correo": email}

    log("")
    log(f"   Vendedores en SAP: {len(vendedores)}")
    log(f"   Con correo valido (los que el sistema considera activos): {len(activos)}")
    log("")
    log(f"   {'ID':<5} | {'NOMBRE':<32} | CORREO")
    log("   " + "-" * 70)
    for code, info in sorted(activos.items()):
        log(f"   {code:<5} | {info['nombre'][:32]:<32} | {info['correo']}")

    return activos


# =============================================================================
# CHECK 3 - Arbol Agente -> Zona -> Clientes (la consulta del plan)
# =============================================================================
def check_arbol(conn, agentes_activos, mapa_zonas):
    titulo("CHECK 3 - Arbol Agente -> Zona -> Clientes")

    log("")
    log("   Ejecutando la consulta exacta que propone el plan:")
    log("   BusinessPartners?$filter=CardType eq 'cCustomer' and CurrentAccountBalance ne 0")
    log("")

    clientes = get_paginado(
        conn,
        "BusinessPartners",
        {
            "$filter": "CardType eq 'cCustomer' and CurrentAccountBalance ne 0",
            "$select": "CardCode,CardName,U_ZGIRA,SalesPersonCode,Phone1,Phone2,Cellular",
        },
        "CardCode",
    )

    log(f"   Clientes con saldo distinto de cero: {len(clientes)}")

    por_agente = defaultdict(lambda: defaultdict(list))
    sin_zona_total = 0
    huerfanos = 0

    for c in clientes:
        vendedor = c.get("SalesPersonCode")
        zona = str(c.get("U_ZGIRA") or "").strip()
        if not zona:
            sin_zona_total += 1
        if vendedor not in agentes_activos:
            huerfanos += 1
            continue
        por_agente[vendedor][zona or "(sin zona)"].append(c)

    log(f"   Clientes sin U_ZGIRA asignada: {sin_zona_total}")
    log(f"   Clientes cuyo vendedor NO tiene correo (no visibles en el arbol): {huerfanos}")

    for code in sorted(por_agente):
        info = agentes_activos[code]
        zonas = por_agente[code]
        total = sum(len(v) for v in zonas.values())
        log("")
        log(f"   {info['nombre']} (ID {code}): {total} clientes, {len(zonas)} zonas")
        for z in sorted(zonas, key=lambda x: -len(zonas[x])):
            if z == "(sin zona)":
                nombre_zona = "SIN ZONA ASIGNADA"
            else:
                nombre_zona = mapa_zonas.get(z, "(nombre no resuelto)")
            log(f"      Zona {z:<12} {nombre_zona[:42]:<42} {len(zonas[z])} clientes")

    return por_agente


# =============================================================================
# CHECK 4 - Hueco de FatherCard (sucursales sin saldo)
# =============================================================================
def check_father_card(conn, agentes_activos):
    titulo("CHECK 4 - Clientes con FatherCard que el arbol dejaria fuera")

    log("")
    log("   La gira completa usa: saldo != 0  OR  FatherCard != null")
    log("   El arbol del plan usa: saldo != 0")
    log("   Diferencia = sucursales con saldo en cero.")

    sucursales = get_paginado(
        conn,
        "BusinessPartners",
        {
            "$filter": "CardType eq 'cCustomer' and FatherCard ne null and CurrentAccountBalance eq 0",
            "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
        },
        "CardCode",
    )

    log("")
    log(f"   Sucursales con saldo cero: {len(sucursales)}")

    de_agentes = [s for s in sucursales if s.get("SalesPersonCode") in agentes_activos]
    log(f"   De ellas, asignadas a un agente con correo: {len(de_agentes)}")

    if de_agentes:
        log("")
        log(f"   {'CODIGO':<12} | {'NOMBRE':<38} | {'PADRE':<10} | VEND")
        log("   " + "-" * 74)
        for s in de_agentes[:40]:
            log(
                f"   {s.get('CardCode', ''):<12} | {str(s.get('CardName', ''))[:38]:<38} | "
                f"{str(s.get('FatherCard', '')):<10} | {s.get('SalesPersonCode')}"
            )
        if len(de_agentes) > 40:
            log(f"   ... y {len(de_agentes) - 40} mas.")

    log("")
    if len(de_agentes) == 0:
        log("   RESULTADO: sin diferencia. El filtro simple del plan es suficiente.")
    elif len(de_agentes) <= 5:
        log("   RESULTADO: diferencia minima. Se puede ignorar sin consecuencias.")
    else:
        log("   RESULTADO: diferencia relevante. Decidir con Tania si el arbol")
        log("   debe incluir sucursales sin saldo propio.")

    return de_agentes


# =============================================================================
# CHECK 5 - Desajuste vendedor: cliente vs documento (BPAddresses.U_CODV)
# =============================================================================
def check_desajuste_vendedor(conn, por_agente):
    titulo("CHECK 5 - Vendedor del cliente vs vendedor de la direccion (U_CODV)")

    log("")
    log("   El arbol agrupa por SalesPersonCode del CLIENTE.")
    log("   agentes.py rutea cada documento por BPAddresses.U_CODV de su ShipTo.")
    log("   Si difieren, Tania puede seleccionar un cliente y recibir un PDF vacio.")
    log("")

    total = 0
    con_mapeo = 0
    con_desajuste = 0
    detalle = []

    lista = [
        (code, c)
        for code in por_agente
        for zona in por_agente[code]
        for c in por_agente[code][zona]
    ]
    log(f"   Revisando direcciones de {len(lista)} clientes (un GET por cliente)...")

    for idx, (code_agente, cli) in enumerate(lista, 1):
        card_code = cli.get("CardCode")
        print(f"   ... {idx}/{len(lista)}", end="\r")
        total += 1

        res = conn.get(f"BusinessPartners('{card_code}')", {"$select": "BPAddresses"})
        if not res or "BPAddresses" not in res:
            continue

        vendedores_dir = set()
        for d in res["BPAddresses"]:
            if d.get("AddressType") != "bo_ShipTo":
                continue
            v = d.get("U_CODV")
            if v is not None and str(v).strip() != "":
                try:
                    vendedores_dir.add(int(v))
                except ValueError:
                    pass

        if not vendedores_dir:
            continue
        con_mapeo += 1

        ajenos = vendedores_dir - {code_agente}
        if ajenos:
            con_desajuste += 1
            detalle.append(
                (card_code, str(cli.get("CardName", ""))[:34], code_agente, sorted(ajenos))
            )

    log("")
    log(f"   Clientes revisados: {total}")
    log(f"   Con al menos una direccion que define vendedor (U_CODV): {con_mapeo}")
    log(f"   Con direcciones apuntando a OTRO vendedor: {con_desajuste}")

    if detalle:
        log("")
        log(f"   {'CODIGO':<12} | {'NOMBRE':<34} | {'AGENTE':<7} | OTROS VENDEDORES")
        log("   " + "-" * 76)
        for card_code, nombre, agente, ajenos in detalle[:40]:
            log(f"   {card_code:<12} | {nombre:<34} | {agente:<7} | {ajenos}")
        if len(detalle) > 40:
            log(f"   ... y {len(detalle) - 40} mas.")

    log("")
    if con_desajuste == 0:
        log("   RESULTADO: no hay desajuste. El riesgo de 'PDF vacio' NO aplica.")
        log("   -> No hace falta construir el conteo de retorno en la interfaz.")
    else:
        pct = round(con_desajuste * 100 / total, 1) if total else 0
        log(f"   RESULTADO: {con_desajuste} clientes ({pct}%) pueden generar un PDF")
        log("   con menos clientes de los seleccionados, o vacio.")
        log("   -> ejecutar_gira_selectiva DEBE devolver el conteo real procesado")
        log("      y la interfaz mostrarlo.")

    return con_desajuste, total


# =============================================================================
# CHECK 6 - Sigue viva la BD de pruebas?
# =============================================================================
def check_bd_pruebas():
    titulo("CHECK 6 - Base de datos de pruebas")

    log("")
    log("   Intentando Login contra SAP_COMPANY_DB_TEST...")
    conn_test = ServiceLayerConnection(use_test_db=True)
    log(f"   BD configurada: {conn_test.company_db or '(vacia en .env)'}")

    if not conn_test.company_db:
        log("   [--] No hay BD de pruebas configurada.")
        return False

    if conn_test.login():
        log("   [OK] La BD de pruebas responde.")
        log("   -> Hay entorno seguro: ServiceLayerConnection(use_test_db=True)")
        conn_test.logout()
        return True

    log("   [--] No se pudo entrar. Toda prueba sera contra PRODUCCION.")
    return False


# =============================================================================
# MAIN
# =============================================================================
def main():
    inicio = datetime.now()

    log("=" * 78)
    log("VERIFICACION PREVIA - MODULO GIRAS POR ZONA")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("Script de SOLO LECTURA. Unicamente GET (mas Login/Logout, que es como")
    log("autentica el Service Layer). No escribe, no edita, no elimina, no envia.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION (solo lectura)...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return

    try:
        mapa_zonas = check_udt_giras(conn)
        agentes_activos = check_agentes(conn)
        por_agente = check_arbol(conn, agentes_activos, mapa_zonas)
        sucursales = check_father_card(conn, agentes_activos)
        desajuste, revisados = check_desajuste_vendedor(conn, por_agente)
    finally:
        conn.logout()

    bd_test = check_bd_pruebas()

    # -------------------------------------------------------------------------
    titulo("CONCLUSIONES PARA LA IMPLEMENTACION")

    if mapa_zonas:
        estado_udt = f"ACCESIBLE ({len(mapa_zonas)} zonas)"
    else:
        estado_udt = "NO ACCESIBLE -> hardcodear nombres"

    log("")
    log(f"   1. UDT de zonas: {estado_udt}")
    log(f"   2. Desajuste de vendedor: {desajuste} de {revisados} clientes")
    log(f"   3. Sucursales fuera del arbol: {len(sucursales)}")
    log(f"   4. BD de pruebas: {'DISPONIBLE' if bd_test else 'NO DISPONIBLE'}")
    log("")
    log(f"   Duracion: {round((datetime.now() - inicio).total_seconds(), 1)} segundos")

    guardar()


def guardar():
    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lineas))
    print(f"\nReporte guardado en: {REPORTE}")


if __name__ == "__main__":
    main()
