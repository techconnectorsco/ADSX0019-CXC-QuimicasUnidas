# -*- coding: utf-8 -*-
r"""
FIDELIDAD DEL PASO 1 - version acotada, para correr de dia.

Lo que valida es LO MISMO que importa del Paso 1: que el mapa nuevo diga,
cliente por cliente, lo mismo que hoy sale en el PDF. La diferencia con
validar_paso1_mapa_ruteo.py es que aca las consultas se acotan a un puñado de
clientes con CardCode IN (...), asi que son chicas y rapidas.

Por que existe: de dia cada llamada a /SQLQueries cuesta 25-30s y el barrido
de toda la empresa se cae por timeout (PLAN_GIRAS_POR_ZONA.md 17.14.12). Pero
la fidelidad de la REGLA no necesita el universo completo: necesita comparar
clientes concretos. Lo que si necesita la noche es el conteo por agente del
universo entero, que es otra cosa.

SOLO LECTURA. No genera documentos, no manda correos, no toca SharePoint.

Los clientes a probar salen de:
  - los casos conocidos (C0042 para el 7; C0037, C0080 y C0121 fuera del 9)
  - una muestra de los que el arbol viejo ofrece hoy para los agentes 6, 7 y 9,
    que se obtienen con UNA consulta liviana (obtener_fichas_sql por SlpCode)

Genera: Verificacion_Paso1_Fidelidad.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/validar_paso1_fidelidad.py
      .\.venv\Scripts\python.exe scripts_investigacion/validar_paso1_fidelidad.py C0042 C0040
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
    obtener_clientes_por_codigos,
    obtener_documentos_cliente,
    obtener_fichas_sql,
    obtener_mapa_ruteo_masivo,
    obtener_saldos_favor_masivo,
    obtener_vendedores,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Paso1_Fidelidad.txt")

AGENTES = [6, 7, 9]

# Cuantos clientes del arbol viejo se prueban por agente. Son pocos a
# proposito: cada uno cuesta ~3 llamadas a SAP y de dia eso se siente.
MUESTRA_POR_AGENTE = 12

# C0042 tiene documentos ruteados al agente 7 (77 abiertos en total, 45 al 7 el
# 27/09/2026, 49 el 30/09 - los datos cambian, asi que es referencia y no
# constante a cumplir).
DEBE_APARECER = [("C0042", 7)]

# Los tres que salieron omitidos el 27/09/2026 para el agente 9: sucursales sin
# ningun documento abierto propio.
DEBE_NO_APARECER = [("C0037", 9), ("C0080", 9), ("C0121", 9)]

# El redondeo a 6 cifras significativas sobre un millon da un error de
# unidades. Mas que esto ya no es redondeo.
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


def resumen_oraculo(cliente, agente_id, cache_pr, conn):
    """
    Lo que de verdad llega al PDF de ese agente, segun el Python de produccion.

    El cache de saldos a favor va PUESTO, porque el mapa del Paso 1 los
    incluye. Replica la regla de procesar_datos_cliente(): un perfil cuyos
    totales quedan en cero en las dos monedas no se genera.
    """
    docs = obtener_documentos_cliente(conn, cliente, saldos_favor_cache=cache_pr)
    mios = [d for d in docs if str(d.get("vendedor_final")) == str(agente_id)]

    total_crc = sum(d["saldo"] for d in mios if d["moneda"] == "CRC")
    total_usd = sum(d["saldo"] for d in mios if d["moneda"] == "USD")
    if total_crc == 0 and total_usd == 0:
        return {"docs": 0, "crc": 0.0, "usd": 0.0}

    return {"docs": len(mios), "crc": total_crc, "usd": total_usd}


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("FIDELIDAD DEL PASO 1 - MAPA DE RUTEO vs EL PDF DE HOY")
    log("Quimicas Unidas / ADSX0019 - rama giras_por_zona")
    log("Fecha: %s" % inicio.strftime("%d/%m/%Y %H:%M:%S"))
    log("")
    log("Version acotada: las consultas se limitan a los clientes probados,")
    log("para poder correr de dia. SOLO LECTURA.")
    log("=" * 78)

    pedidos = [a.strip().upper() for a in sys.argv[1:] if a.strip()]

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return 1

    try:
        vendedores = obtener_vendedores(conn)

        # ------------------------------------------------------------------
        titulo("PASO A - A quienes se les va a preguntar")

        if pedidos:
            log("")
            log("   Clientes pedidos por linea de comandos: %s"
                % ", ".join(pedidos))
            pares = [(cc, a) for cc in pedidos for a in AGENTES]
            codigos = list(pedidos)
        else:
            log("")
            log("   Una consulta liviana trae los clientes que el arbol viejo")
            log("   ofrece hoy (por SlpCode de la ficha)...")
            fichas = obtener_fichas_sql(conn, vendedores=AGENTES)
            log("   Fichas: %d" % len(fichas))

            por_agente = defaultdict(list)
            for cc, datos in fichas.items():
                por_agente[datos["slp_code"]].append(cc)

            pares = []
            for agente in AGENTES:
                muestra = sorted(por_agente.get(agente, []))[:MUESTRA_POR_AGENTE]
                log("   Agente %-3s | %4d en el arbol viejo | se prueban %d"
                    % (agente, len(por_agente.get(agente, [])), len(muestra)))
                pares.extend([(cc, agente) for cc in muestra])

            # Mas los casos conocidos, que son el valor real de esta prueba
            for par in DEBE_APARECER + DEBE_NO_APARECER:
                if par not in pares:
                    pares.append(par)

            codigos = sorted({cc for (cc, _a) in pares})

        log("")
        log("   Total: %d par(es) cliente-agente sobre %d cliente(s)"
            % (len(pares), len(codigos)))

        # ------------------------------------------------------------------
        titulo("PASO B - El mapa, acotado a esos clientes")
        log("")

        t0 = datetime.now()
        try:
            mapa = obtener_mapa_ruteo_masivo(conn, solo_clientes=codigos)
        except RuntimeError as e:
            log("")
            check("se pudo construir el mapa acotado", False, str(e))
            log("")
            log("   SAP no contesto ni acotando las consultas. Hay que")
            log("   reintentar mas tarde o de noche.")
            titulo("RESULTADO")
            log("")
            log("   FALLARON %d control(es):" % len(_fallos))
            for f in _fallos:
                log("      - %s" % f)
            guardar()
            return 1
        segundos = (datetime.now() - t0).total_seconds()

        log("")
        log("   %d par(es) en el mapa, en %.1fs" % (len(mapa), segundos))

        # ------------------------------------------------------------------
        titulo("PASO C - El oraculo: lo que hoy sale en el PDF")
        log("")
        log("   Trayendo fichas y saldos a favor de los %d clientes..."
            % len(codigos))

        fichas_od = {
            c.get("CardCode"): c
            for c in obtener_clientes_por_codigos(conn, codigos)
        }
        cache_pr = obtener_saldos_favor_masivo(conn, codigos)

        log("")
        log("   Consultando el oraculo cliente por cliente...")

        resultados = {}
        with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as pool:
            futuros = {}
            for (cc, agente) in pares:
                ficha = fichas_od.get(cc)
                if not ficha:
                    aviso("%s: no tiene ficha en SAP, se omite" % cc)
                    continue
                futuros[
                    pool.submit(resumen_oraculo, ficha, agente, cache_pr, conn)
                ] = (cc, agente)
            for fut in as_completed(futuros):
                clave = futuros[fut]
                try:
                    resultados[clave] = fut.result()
                except Exception as e:
                    resultados[clave] = {"error": str(e)}

        # ------------------------------------------------------------------
        titulo("PASO D - La comparacion")
        log("")
        log("   %-9s %-4s | %-8s %-8s | %-15s %-15s | %s"
            % ("CLIENTE", "AG", "DOCS SQL", "DOCS PDF", "CRC SQL", "CRC PDF",
               "DIF"))
        log("   " + "-" * 94)

        iguales = 0
        distintos = 0
        peor_monto = 0.0
        ambos_cero = 0

        for (cc, agente) in sorted(resultados):
            ora = resultados[(cc, agente)]
            if "error" in ora:
                aviso("%s/%s: el oraculo fallo (%s)" % (cc, agente, ora["error"]))
                continue

            sql = mapa.get((cc, agente), {"docs": 0, "crc": 0.0, "usd": 0.0})

            # Los dos de acuerdo en que no hay nada: cuenta, pero no se imprime
            # para no llenar el reporte de ceros.
            if sql["docs"] == 0 and ora["docs"] == 0:
                ambos_cero += 1
                iguales += 1
                continue

            dif_crc = abs(sql["crc"] - ora["crc"])
            dif_usd = abs(sql["usd"] - ora["usd"])
            peor_monto = max(peor_monto, dif_crc, dif_usd)

            marca = ""
            if sql["docs"] == ora["docs"]:
                iguales += 1
            else:
                distintos += 1
                marca = "  <-- DIFIEREN"

            log("   %-9s %-4s | %8d %8d | %15.2f %15.2f | %8.2f%s"
                % (cc, agente, sql["docs"], ora["docs"], sql["crc"], ora["crc"],
                   dif_crc, marca))

        log("")
        log("   %d par(es) coinciden (%d de ellos porque los dos dicen que no"
            % (iguales, ambos_cero))
        log("   hay nada, que tambien es coincidir), %d difieren." % distintos)
        log("   Peor diferencia de monto: %.2f" % peor_monto)

        log("")
        check(
            "el conteo de documentos coincide en todos los pares probados",
            distintos == 0,
            "%d par(es) difieren" % distintos,
        )
        check(
            "las diferencias de monto se quedan en el redondeo de /SQLQueries "
            "(peor: %.2f)" % peor_monto,
            peor_monto <= TOLERANCIA_MONTO,
            "peor %.2f, por encima de la tolerancia de %.2f"
            % (peor_monto, TOLERANCIA_MONTO),
        )

        # ------------------------------------------------------------------
        titulo("PASO E - Casos conocidos")
        log("")

        for (cc, agente) in DEBE_APARECER:
            entrada = mapa.get((cc, agente))
            check(
                "%s aparece en el mapa del agente %s" % (cc, agente),
                bool(entrada),
                "no aparecio",
            )
            if entrada:
                log("         %d documentos, %.2f CRC, %.2f USD"
                    % (entrada["docs"], entrada["crc"], entrada["usd"]))

        log("")
        for (cc, agente) in DEBE_NO_APARECER:
            check(
                "%s queda FUERA del mapa del agente %s" % (cc, agente),
                (cc, agente) not in mapa,
                "aparecio con %r" % (mapa.get((cc, agente)),),
            )

        # ------------------------------------------------------------------
        titulo("PASO F - Los no elegibles, que es el objetivo del cambio")
        log("")
        log("   De los clientes que el arbol viejo ofrece para estos agentes,")
        log("   cuantos NO aportan nada al PDF. Son los que hoy se pueden")
        log("   marcar y no salen, y los que el prefiltro va a ocultar.")
        log("")

        for agente in AGENTES:
            delagente = [(cc, a) for (cc, a) in resultados if a == agente]
            if not delagente:
                continue
            sin_carga = [
                cc for (cc, a) in delagente
                if resultados[(cc, a)].get("docs", 0) == 0
            ]
            log("   Agente %-3s | %3d probados | %3d sin carga (%.0f%%)"
                % (agente, len(delagente), len(sin_carga),
                   100.0 * len(sin_carga) / len(delagente)))
            for cc in sorted(sin_carga)[:12]:
                nombre = (fichas_od.get(cc, {}) or {}).get("CardName", "")
                log("                 %s  %s" % (cc, nombre[:45]))

        log("")
        log("   OJO: este porcentaje es de la MUESTRA, no del universo. El")
        log("   numero real por agente sale del barrido completo, que hay que")
        log("   correr de noche (validar_paso1_mapa_ruteo.py).")

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
        log("   La regla del mapa NO coincide con el PDF. Hay que arreglarlo")
        log("   antes de seguir al Paso 2.")
        guardar()
        return 1

    log("   TODOS LOS CONTROLES PASARON.")
    log("")
    log("   El mapa dice lo mismo que el PDF en los clientes probados. Lo que")
    log("   queda para la noche es el barrido del universo completo, que mide")
    log("   el conteo por agente, no la regla.")
    guardar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
