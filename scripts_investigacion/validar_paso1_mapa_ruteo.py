# -*- coding: utf-8 -*-
r"""
VALIDACION DEL PASO 1 - obtener_mapa_ruteo_masivo() contra SAP PRODUCCION.

SOLO LECTURA. Hace GET y los POST/DELETE a /SQLQueries que son el mecanismo
del Service Layer para correr un SELECT. No genera documentos, no manda
correos, no sube nada a SharePoint.

Lo que mide, que no se puede medir offline (tests/prueba_mapa_ruteo_offline.py
ya cubrio las reglas con filas inventadas):

  A. Que el parser de /SQLQueries acepte los cuatro queries tal como quedaron.
     Lo unico que el Paso 0 no habia probado es la columna T0."DocEntry" que se
     agrego al SELECT de documentos para poder deduplicar.

  B. Fidelidad contra el oraculo: que el mapa coincida, cliente por cliente,
     con lo que obtener_documentos_cliente() le entrega hoy al PDF. Se compara
     con el cache de saldos a favor PUESTO, porque el mapa si los incluye.

  C. Las tres regiones contra el arbol viejo (SalesPersonCode de la ficha):
     cuantos clientes aporta el mapa que el arbol no mostraba, cuantos ofrece
     el arbol que no aportan nada, y cuantos reconocen los dos.

  D. Los casos conocidos: C0042 para el agente 7, y C0037 / C0080 / C0121 que
     deben quedar FUERA del mapa del agente 9.

  E. La medicion que el Paso 0 dejo pendiente: de los clientes nuevos, cuantos
     tienen U_ZGIRA vacio. Ese numero decide si el grupo "sin zona" de la
     pantalla necesita interfaz de verdad o sigue siendo un contador muerto.

OJO CON LOS MONTOS: la precision de /SQLQueries depende de la sesion y redondea
a 6 cifras significativas (PLAN_GIRAS_POR_ZONA.md 17.14.4). Por eso los montos
se comparan con tolerancia y las diferencias de centimos se reportan como
esperadas. Lo que tiene que cuadrar EXACTO es el ruteo y el conteo de
documentos, que es lo que decide la elegibilidad.

Genera: Verificacion_Paso1_Mapa_Ruteo.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/validar_paso1_mapa_ruteo.py
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

from modules.database.conexion import ServiceLayerConnection
from agentes import (
    GIRA_ZONA_MAX_WORKERS,
    obtener_clientes_con_saldo,
    obtener_clientes_por_codigos,
    obtener_documentos_cliente,
    obtener_mapa_ruteo_masivo,
    obtener_saldos_favor_masivo,
    obtener_vendedores,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Paso1_Mapa_Ruteo.txt")

# Agentes del modulo: Siviany (6), Berny (7), Jose (9)
AGENTES = [6, 7, 9]

# Cuantos clientes se verifican contra el oraculo por region y agente. Cada
# cliente cuesta ~3 llamadas a SAP, asi que recorrer los cientos completos
# seria la misma espera de 10 minutos de la gira entera.
MUESTRA_POR_REGION = 10

# C0042 tenia 77 documentos abiertos y 45 ruteados al agente 7 el 27/09/2026.
# El Paso 0 lo volvio a medir el 30/09 y dieron 49: los datos cambian. Asi que
# NO se trata como una constante a cumplir, solo se reporta para comparar.
REFERENCIA_HISTORICA = {("C0042", 7): 45}

# Los tres que salieron omitidos el 27/09/2026 para el agente 9: eran
# sucursales sin ningun documento abierto propio. Deben quedar fuera del mapa.
OMITIDOS_CONOCIDOS = [("C0037", 9), ("C0080", 9), ("C0121", 9)]

# Tolerancia de monto. El redondeo a 6 cifras significativas sobre un millon
# da un error de unidades, no de miles.
TOLERANCIA_MONTO = 10.0

_lineas = []
_fallos = []
_avisos = []


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
    print("Reporte guardado en: %s" % REPORTE)


def check(nombre, condicion, detalle=""):
    if condicion:
        log("   OK    %s" % nombre)
    else:
        log("   FALLA %s   %s" % (nombre, detalle))
        _fallos.append(nombre)


def aviso(texto):
    log("   AVISO %s" % texto)
    _avisos.append(texto)


def resumen_oraculo(conn, cliente, agente_id, cache_pr):
    """
    Lo que de verdad llega al PDF de ese agente, segun el Python de produccion.

    A diferencia del oraculo del Paso 0, aca el cache de saldos a favor va
    PUESTO: el mapa del Paso 1 incluye las filas PR, asi que para comparar
    manzanas con manzanas el oraculo tambien tiene que incluirlas.

    Replica la regla de procesar_datos_cliente(): un perfil cuyos totales
    quedan en cero en las dos monedas no se genera.
    """
    docs = obtener_documentos_cliente(conn, cliente, saldos_favor_cache=cache_pr)
    mios = [d for d in docs if str(d.get("vendedor_final")) == str(agente_id)]

    total_crc = sum(d["saldo"] for d in mios if d["moneda"] == "CRC")
    total_usd = sum(d["saldo"] for d in mios if d["moneda"] == "USD")
    if total_crc == 0 and total_usd == 0:
        return {"docs": 0, "crc": 0.0, "usd": 0.0}

    return {"docs": len(mios), "crc": total_crc, "usd": total_usd}


def comparar_muestra(conn, conn_pool, pares, etiqueta):
    """
    Compara una lista de (card_code, agente) contra el oraculo y lo reporta.

    Devuelve (coinciden_docs, difieren_docs, peor_diferencia_de_monto).
    """
    if not pares:
        log("   (sin clientes en esta region)")
        return 0, 0, 0.0

    codigos = sorted({cc for (cc, _a) in pares})

    # Las fichas, con el mismo $select que usa la gira
    fichas = {
        c.get("CardCode"): c for c in obtener_clientes_por_codigos(conn, codigos)
    }

    # El cache de saldos a favor, en una sola tanda
    cache_pr = obtener_saldos_favor_masivo(conn, codigos)

    resultados = {}
    with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as pool:
        futuros = {}
        for (cc, agente) in pares:
            ficha = fichas.get(cc)
            if not ficha:
                continue
            futuros[pool.submit(resumen_oraculo, conn, ficha, agente, cache_pr)] = (
                cc,
                agente,
            )
        for fut in as_completed(futuros):
            clave = futuros[fut]
            try:
                resultados[clave] = fut.result()
            except Exception as e:
                resultados[clave] = {"error": str(e)}

    log("")
    log("   %-9s %-5s | %-9s %-9s | %-14s %-14s | %s"
        % ("CLIENTE", "AG", "DOCS SQL", "DOCS ORA", "CRC SQL", "CRC ORACULO", "DIF"))
    log("   " + "-" * 92)

    iguales = 0
    distintos = 0
    peor_monto = 0.0

    for (cc, agente) in sorted(pares):
        ora = resultados.get((cc, agente))
        if ora is None:
            aviso("%s/%s: no se pudo traer la ficha del cliente" % (cc, agente))
            continue
        if "error" in ora:
            aviso("%s/%s: el oraculo fallo (%s)" % (cc, agente, ora["error"]))
            continue

        sql = MAPA.get((cc, agente), {"docs": 0, "crc": 0.0, "usd": 0.0})
        dif_crc = abs(sql["crc"] - ora["crc"])
        dif_usd = abs(sql["usd"] - ora["usd"])
        peor_monto = max(peor_monto, dif_crc, dif_usd)

        marca = ""
        if sql["docs"] == ora["docs"]:
            iguales += 1
        else:
            distintos += 1
            marca = "  <-- DOCS"

        log("   %-9s %-5s | %9d %9d | %14.2f %14.2f | %8.2f%s"
            % (cc, agente, sql["docs"], ora["docs"], sql["crc"], ora["crc"],
               dif_crc, marca))

    log("")
    log("   %s: %d coinciden en documentos, %d difieren. "
        "Peor diferencia de monto: %.2f"
        % (etiqueta, iguales, distintos, peor_monto))

    return iguales, distintos, peor_monto


MAPA = {}


def main():
    global MAPA
    inicio = datetime.now()

    log("=" * 78)
    log("VALIDACION DEL PASO 1 - MAPA DE RUTEO MASIVO")
    log("Quimicas Unidas / ADSX0019 - rama giras_por_zona")
    log("Fecha: %s" % inicio.strftime("%d/%m/%Y %H:%M:%S"))
    log("")
    log("SOLO LECTURA. GET + los POST/DELETE a /SQLQueries que son el")
    log("mecanismo del Service Layer para correr un SELECT. No envia nada,")
    log("no genera documentos en SAP y no toca SharePoint ni correo.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return 1

    try:
        # ------------------------------------------------------------------
        titulo("PASO A - Los cuatro queries y el tiempo")
        log("")
        log("   Si el parser rechaza alguno, ejecutar_sql_sl lo avisa en la")
        log("   linea de arriba y el mapa sale incompleto o vacio.")
        log("")

        t0 = datetime.now()
        try:
            MAPA = obtener_mapa_ruteo_masivo(conn)
        except RuntimeError as e:
            # Pasa con el servidor cargado: /SQLQueries se cae por timeout.
            # No es un fallo del Paso 1 y no tiene sentido seguir con los
            # pasos siguientes, que comparan contra un mapa que no existe.
            # Mejor un mensaje claro y el reporte guardado que un traceback.
            segundos = (datetime.now() - t0).total_seconds()
            log("")
            check("se pudo construir el mapa", False, str(e))
            log("")
            log("   Esto NO invalida el Paso 1: significa que SAP no contesto.")
            log("   Medido el 01/10/2026, cada viaje a /SQLQueries cuesta 25-30s")
            log("   en horario de oficina contra 0,3s de noche. Volver a correr")
            log("   esta validacion de noche, cuando nadie este usando SAP.")
            log("   Se corto a los %.1fs." % segundos)
            titulo("RESULTADO")
            log("")
            log("   FALLARON %d control(es):" % len(_fallos))
            for f in _fallos:
                log("      - %s" % f)
            guardar()
            return 1
        segundos = (datetime.now() - t0).total_seconds()

        log("")
        check("el mapa no volvio vacio", bool(MAPA), "%d pares" % len(MAPA))

        # El tiempo NO es un control de aprobacion del Paso 1. Medido el
        # 01/10/2026 en horario de oficina, CADA viaje a /SQLQueries cuesta
        # 25-30s, hasta un COUNT(*) sin joins (sonda_timeout_facturas.py); de
        # noche el mismo query corre en 0,3s. Asi que esto mide carga del
        # servidor, no calidad del query. Lo que tiene que responder rapido es
        # el endpoint CON cache, y eso es el Paso 3.
        log("")
        log("   Construir el mapa tomo %.1fs (%d consultas)." % (segundos, 4))
        if segundos > 180:
            aviso(
                "el mapa tardo %.1fs. No invalida el Paso 1 (el costo esta en "
                "el viaje al Service Layer, no en el query), pero confirma que "
                "el endpoint NECESITA el cache del Paso 3 y que conviene "
                "precalentarlo" % segundos
            )

        clientes_totales = {cc for (cc, _v) in MAPA}
        vendedores_mapa = {v for (_c, v) in MAPA}
        log("")
        log("   Pares cliente-vendedor : %d" % len(MAPA))
        log("   Clientes distintos     : %d" % len(clientes_totales))
        log("   Vendedores distintos   : %d" % len(vendedores_mapa))
        log("   Tiempo                 : %.1fs" % segundos)

        # ------------------------------------------------------------------
        titulo("PASO B - El mapa por agente, contra el arbol viejo")

        vendedores = obtener_vendedores(conn)
        log("")
        log("   Trayendo el universo de obtener_clientes_con_saldo() por OData")
        log("   (lento, ~350 llamadas) para reconstruir el arbol de hoy...")
        universo = obtener_clientes_con_saldo(conn)
        log("   Universo de OData: %d clientes" % len(universo))

        arbol_viejo = defaultdict(set)
        zona_de_ficha = {}
        for c in universo:
            zona_de_ficha[c.get("CardCode")] = c.get("U_ZGIRA")
            arbol_viejo[c.get("SalesPersonCode")].add(c.get("CardCode"))

        mapa_por_agente = defaultdict(set)
        for (cc, vend) in MAPA:
            mapa_por_agente[vend].add(cc)

        log("")
        log("   %-4s %-22s | %8s %8s | %8s %8s %8s"
            % ("AG", "NOMBRE", "ARBOL", "MAPA", "AMBOS", "NUEVOS", "INUTILES"))
        log("   " + "-" * 82)

        regiones = {}
        for agente in AGENTES:
            viejos = arbol_viejo.get(agente, set())
            nuevos = mapa_por_agente.get(agente, set())
            ambos = viejos & nuevos
            solo_mapa = nuevos - viejos
            solo_arbol = viejos - nuevos
            regiones[agente] = {
                "ambos": ambos,
                "nuevos": solo_mapa,
                "inutiles": solo_arbol,
            }
            log("   %-4s %-22s | %8d %8d | %8d %8d %8d"
                % (agente,
                   (vendedores.get(agente, {}).get("nombre", "?"))[:22],
                   len(viejos), len(nuevos), len(ambos),
                   len(solo_mapa), len(solo_arbol)))

        log("")
        log("   INUTILES es el reclamo original: clientes que la pantalla deja")
        log("   marcar y que nunca salen en el PDF. NUEVOS es el otro lado, el")
        log("   que no estaba reportado: clientes con carga que el arbol no")
        log("   mostraba porque filtraba por la ficha y no por el ruteo.")

        # ------------------------------------------------------------------
        titulo("PASO C - Fidelidad contra el oraculo")
        log("")
        log("   El oraculo es obtener_documentos_cliente(), el Python que hoy")
        log("   alimenta el PDF, con el cache de saldos a favor puesto.")
        log("   Muestra de %d clientes por region y agente." % MUESTRA_POR_REGION)

        total_iguales = 0
        total_distintos = 0
        peor_global = 0.0

        for agente in AGENTES:
            for nombre_region in ("ambos", "nuevos", "inutiles"):
                conjunto = sorted(regiones[agente][nombre_region])
                muestra = [(cc, agente) for cc in conjunto[:MUESTRA_POR_REGION]]
                log("")
                log("   --- Agente %s, region %s (%d clientes, se prueban %d)"
                    % (agente, nombre_region.upper(), len(conjunto), len(muestra)))
                ig, di, peor = comparar_muestra(
                    conn, None, muestra, "Agente %s / %s" % (agente, nombre_region)
                )
                total_iguales += ig
                total_distintos += di
                peor_global = max(peor_global, peor)

        log("")
        check(
            "el conteo de documentos coincide en toda la muestra "
            "(%d iguales, %d distintos)" % (total_iguales, total_distintos),
            total_distintos == 0,
            "%d pares difieren en documentos" % total_distintos,
        )
        check(
            "las diferencias de monto se quedan en el redondeo esperado "
            "(peor: %.2f)" % peor_global,
            peor_global <= TOLERANCIA_MONTO,
            "peor diferencia %.2f, por encima de la tolerancia de %.2f"
            % (peor_global, TOLERANCIA_MONTO),
        )

        # ------------------------------------------------------------------
        titulo("PASO D - Casos conocidos")
        log("")

        for (cc, agente), docs_historicos in REFERENCIA_HISTORICA.items():
            entrada = MAPA.get((cc, agente))
            if entrada:
                log("   %s para el agente %s: %d documentos en el mapa "
                    "(el 27/09/2026 eran %d; los datos cambian)"
                    % (cc, agente, entrada["docs"], docs_historicos))
                check("%s aparece en el mapa del agente %s" % (cc, agente), True)
            else:
                check(
                    "%s aparece en el mapa del agente %s" % (cc, agente),
                    False,
                    "no esta en el mapa, y el 27/09 tenia %d documentos"
                    % docs_historicos,
                )

        log("")
        for (cc, agente) in OMITIDOS_CONOCIDOS:
            check(
                "%s queda FUERA del mapa del agente %s" % (cc, agente),
                (cc, agente) not in MAPA,
                "aparecio con %r" % (MAPA.get((cc, agente)),),
            )

        # ------------------------------------------------------------------
        titulo("PASO E - Los clientes nuevos y su zona")
        log("")
        log("   Medicion que el Paso 0 dejo pendiente: de los clientes que el")
        log("   mapa agrega, cuantos tienen U_ZGIRA vacio. Si son cero, el")
        log("   grupo 'sin zona' de la pantalla sigue sin necesitar interfaz.")
        log("")

        sin_zona_total = set()
        for agente in AGENTES:
            nuevos = regiones[agente]["nuevos"]
            sin_zona = set()
            for cc in nuevos:
                # La zona del mapa ya viene normalizada; vacia es vacia
                entrada = MAPA.get((cc, agente), {})
                if not (entrada.get("zona") or "").strip():
                    sin_zona.add(cc)
            sin_zona_total |= sin_zona
            log("   Agente %-3s | %4d nuevos | %4d sin U_ZGIRA"
                % (agente, len(nuevos), len(sin_zona)))
            if sin_zona:
                for cc in sorted(sin_zona)[:15]:
                    log("                 sin zona: %s  %s"
                        % (cc, MAPA.get((cc, agente), {}).get("nombre", "")))

        log("")
        if sin_zona_total:
            aviso(
                "hay %d cliente(s) nuevos sin U_ZGIRA: el grupo 'sin zona' de "
                "la pantalla SI necesita interfaz real (Paso 4)"
                % len(sin_zona_total)
            )
        else:
            log("   Ningun cliente nuevo sin U_ZGIRA: 'sin zona' sigue vacio y")
            log("   no hace falta construirle interfaz.")

        # ------------------------------------------------------------------
        titulo("PASO F - La cuarta consulta: fichas por vendedor")
        log("")
        log("   Es la que el Paso 2 usa para mostrar en gris a los no")
        log("   elegibles. Se prueba aca que el query corra y traiga a los")
        log("   clientes que el arbol viejo ofrece.")
        log("")

        from agentes import obtener_fichas_sql

        fichas = obtener_fichas_sql(conn, vendedores=AGENTES)
        log("   Fichas traidas por SlpCode IN (%s): %d"
            % (", ".join(str(a) for a in AGENTES), len(fichas)))

        esperados = set()
        for agente in AGENTES:
            esperados |= arbol_viejo.get(agente, set())
        faltan = esperados - set(fichas)
        check(
            "la consulta de fichas trae a todos los del arbol viejo",
            not faltan,
            "faltan %d: %s" % (len(faltan), sorted(faltan)[:10]),
        )

        inutiles_con_ficha = 0
        for agente in AGENTES:
            for cc in regiones[agente]["inutiles"]:
                if cc in fichas:
                    inutiles_con_ficha += 1
        log("   No elegibles con ficha disponible para pintarlos: %d"
            % inutiles_con_ficha)

    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # ----------------------------------------------------------------------
    titulo("RESULTADO")
    log("")
    log("   Duracion total: %.1f minutos"
        % ((datetime.now() - inicio).total_seconds() / 60.0))
    log("")
    if _avisos:
        log("   Avisos (%d):" % len(_avisos))
        for a in _avisos:
            log("      - %s" % a)
        log("")
    if _fallos:
        log("   FALLARON %d control(es):" % len(_fallos))
        for f in _fallos:
            log("      - %s" % f)
        log("")
        log("   El Paso 1 NO esta validado. No seguir al Paso 2.")
        guardar()
        return 1

    log("   TODOS LOS CONTROLES PASARON.")
    log("   El mapa dice lo mismo que el PDF. Se puede seguir al Paso 2.")
    guardar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
