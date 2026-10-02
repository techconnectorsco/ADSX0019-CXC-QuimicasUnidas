# -*- coding: utf-8 -*-
r"""
VALIDACION DE LOS PASOS 2 Y 3 contra SAP PRODUCCION.

SOLO LECTURA. No encola nada, no genera documentos, no manda correos.

Llama a construir_arbol_gira_zona() directo, sin levantar la API: lo que se
valida es el arbol y el cache, no el HTTP. Para probar el endpoint por HTTP hay
que levantar api.py y usar tests/prueba_gira_zona_endpoint.py arbol.

Lo que mide, que offline no se puede (tests/prueba_arbol_gira_zona_offline.py
ya cubre la forma y el cache con dobles):

  A. Que el arbol se arme con datos reales y en cuanto tiempo.
  B. El tamaño real del cambio por agente: cuantos clientes gana y cuantos
     pierde la pantalla. Esta es la tabla que hay que mostrarle a Tania.
  C. Que los casos conocidos caigan del lado correcto: C0042 elegible para el
     7; C0037, C0080 y C0121 en gris para el 9 con su motivo.
  D. El cache: que el segundo pedido no vuelva a barrer SAP.

OJO: necesita el mapa de ruteo COMPLETO, que de dia se cae por timeout
(PLAN_GIRAS_POR_ZONA.md 17.14.12). Si falla por eso, el mensaje lo dice y hay
que reintentar de noche.

Genera: Verificacion_Paso2_Arbol.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/validar_paso2_arbol.py
"""

import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection
from agentes import (
    construir_arbol_gira_zona,
    obtener_clientes_del_arbol_viejo,
    invalidar_cache_gira_zona,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Paso2_Arbol.txt")

AGENTES = [6, 7, 9]

DEBE_SER_ELEGIBLE = [("C0042", 7)]
DEBE_ESTAR_EN_GRIS = [("C0037", 9), ("C0080", 9), ("C0121", 9)]

_lineas = []
_fallos = []


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


def indexar(arbol):
    """{card_code: cliente} de todas las zonas mas sinZona."""
    salida = {}
    for z in arbol.get("zonas", []):
        for c in z["clientes"]:
            salida[c["cardCode"]] = c
    for c in arbol.get("sinZona", []):
        salida[c["cardCode"]] = c
    return salida


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("VALIDACION DE LOS PASOS 2 Y 3 - EL ARBOL Y EL CACHE")
    log("Quimicas Unidas / ADSX0019 - rama giras_por_zona")
    log("Fecha: %s" % inicio.strftime("%d/%m/%Y %H:%M:%S"))
    log("")
    log("SOLO LECTURA. No encola, no genera, no envia.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return 1

    arboles = {}

    try:
        invalidar_cache_gira_zona()

        # ------------------------------------------------------------------
        titulo("PASO A - Armar el arbol de cada agente")

        for agente in AGENTES:
            log("")
            log("   --- Agente %s" % agente)
            t0 = datetime.now()
            try:
                arbol = construir_arbol_gira_zona(conn, agente)
            except RuntimeError as e:
                log("")
                check("se pudo armar el arbol del agente %s" % agente, False,
                      str(e))
                log("")
                log("   SAP no devolvio el mapa completo. Esto NO invalida los")
                log("   Pasos 2 y 3: es el timeout de horario de oficina")
                log("   (17.14.12). Reintentar de noche.")
                titulo("RESULTADO")
                log("")
                log("   FALLARON %d control(es):" % len(_fallos))
                for f in _fallos:
                    log("      - %s" % f)
                guardar()
                return 1

            segs = (datetime.now() - t0).total_seconds()
            arboles[agente] = arbol
            log("       %s | %d zona(s) | %d elegibles, %d en gris | %.1fs"
                % (arbol["agente"]["nombre"], len(arbol["zonas"]),
                   arbol["totalElegibles"], arbol["totalNoElegibles"], segs))

        check("se armo el arbol de los tres agentes", len(arboles) == 3)

        # ------------------------------------------------------------------
        titulo("PASO B - El tamaño del cambio, por agente")
        log("")
        log("   Esto es lo que hay que contarle a Tania antes de que lo vea:")
        log("   la pantalla va a mostrar MENOS clientes marcables, y algunos")
        log("   que antes no aparecian.")
        log("")
        log("   %-4s %-22s | %7s %7s | %7s %7s"
            % ("AG", "NOMBRE", "ANTES", "AHORA", "NUEVOS", "OCULTOS"))
        log("   " + "-" * 70)

        for agente in AGENTES:
            arbol = arboles[agente]
            indice = indexar(arbol)
            viejos = {
                c["CardCode"]
                for c in obtener_clientes_del_arbol_viejo(conn, agente)
            }
            elegibles = {cc for cc, c in indice.items() if c["elegible"]}
            nuevos = elegibles - viejos
            ocultos = viejos - elegibles

            log("   %-4s %-22s | %7d %7d | %7d %7d"
                % (agente, arbol["agente"]["nombre"][:22], len(viejos),
                   len(elegibles), len(nuevos), len(ocultos)))

            if viejos:
                log("        -> %.0f%% de lo que se ofrecia hoy no aportaba nada"
                    % (100.0 * len(ocultos) / len(viejos)))

        log("")
        log("   ANTES = lo que la pantalla ofrece hoy (SalesPersonCode de la")
        log("   ficha). AHORA = los que de verdad aportan al PDF. NUEVOS = los")
        log("   que faltaban. OCULTOS = los que se podian marcar y no salian.")

        # ------------------------------------------------------------------
        titulo("PASO C - Casos conocidos")
        log("")

        for (cc, agente) in DEBE_SER_ELEGIBLE:
            cliente = indexar(arboles[agente]).get(cc)
            check(
                "%s es elegible para el agente %s" % (cc, agente),
                bool(cliente) and cliente.get("elegible") is True,
                repr(cliente),
            )
            if cliente and cliente.get("elegible"):
                log("         %d docs | %.2f CRC | %.2f USD | zona %s (%s)"
                    % (cliente["docs"], cliente["crc"], cliente["usd"],
                       cliente["zonaCode"], cliente["zonaNombre"]))

        log("")
        for (cc, agente) in DEBE_ESTAR_EN_GRIS:
            cliente = indexar(arboles[agente]).get(cc)
            check(
                "%s esta en gris para el agente %s" % (cc, agente),
                bool(cliente) and cliente.get("elegible") is False,
                "no aparece" if not cliente else repr(cliente.get("elegible")),
            )
            if cliente and not cliente.get("elegible"):
                log("         motivo: %s%s"
                    % (cliente.get("motivo"),
                       " (%s)" % cliente["vendedorNombre"]
                       if cliente.get("vendedorNombre") else ""))

        # ------------------------------------------------------------------
        titulo("PASO D - Coherencia del arbol")
        log("")

        for agente in AGENTES:
            arbol = arboles[agente]
            indice = indexar(arbol)

            sin_motivo = [
                cc for cc, c in indice.items()
                if not c["elegible"] and not c.get("motivo")
            ]
            check(
                "agente %s: todo no elegible trae motivo" % agente,
                not sin_motivo,
                "%d sin motivo: %s" % (len(sin_motivo), sin_motivo[:5]),
            )

            elegibles_sin_docs = [
                cc for cc, c in indice.items()
                if c["elegible"] and c["docs"] == 0
            ]
            check(
                "agente %s: todo elegible tiene al menos un documento" % agente,
                not elegibles_sin_docs,
                "%d con cero docs: %s"
                % (len(elegibles_sin_docs), elegibles_sin_docs[:5]),
            )

            otro_sin_nombre = [
                cc for cc, c in indice.items()
                if c.get("motivo") == "otro_vendedor"
                and not c.get("vendedorNombre")
            ]
            check(
                "agente %s: los de otro_vendedor dicen de quien" % agente,
                not otro_sin_nombre,
                repr(otro_sin_nombre[:5]),
            )

            zonas_vacias = [
                z["zona"]["codigo"] for z in arbol["zonas"]
                if not z["clientes"]
            ]
            check(
                "agente %s: no hay zonas vacias" % agente,
                not zonas_vacias,
                repr(zonas_vacias),
            )

            ordenadas = [z["totalElegibles"] for z in arbol["zonas"]]
            check(
                "agente %s: las zonas vienen ordenadas por elegibles" % agente,
                ordenadas == sorted(ordenadas, reverse=True),
                repr(ordenadas),
            )

        # ------------------------------------------------------------------
        titulo("PASO E - El cache")
        log("")

        t0 = datetime.now()
        construir_arbol_gira_zona(conn, 7)
        caliente = (datetime.now() - t0).total_seconds()
        log("   Segundo pedido del agente 7, con cache caliente: %.1fs"
            % caliente)
        check(
            "con cache caliente responde en segundos (%.1fs)" % caliente,
            caliente < 30,
            "%.1fs" % caliente,
        )

        t0 = datetime.now()
        construir_arbol_gira_zona(conn, 7, refrescar=True)
        frio = (datetime.now() - t0).total_seconds()
        log("   Con refrescar=True (tira el cache): %.1fs" % frio)
        check(
            "refrescar=True vuelve a barrer, o sea tarda mas",
            frio > caliente,
            "caliente %.1fs, refrescado %.1fs" % (caliente, frio),
        )

    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # ----------------------------------------------------------------------
    titulo("RESULTADO")
    log("")
    log("   Duracion: %.1f minutos"
        % ((datetime.now() - inicio).total_seconds() / 60.0))
    log("")
    if _fallos:
        log("   FALLARON %d control(es):" % len(_fallos))
        for f in _fallos:
            log("      - %s" % f)
        guardar()
        return 1

    log("   TODOS LOS CONTROLES PASARON.")
    log("   Los Pasos 2 y 3 estan validados. Sigue el Paso 4, la pantalla.")
    guardar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
