r"""
zonas_con_facturas.py - Quimicas Unidas / ADSX0019

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA. Unicamente GET contra SAP Service Layer (mas /Login y /Logout,
que es como autentica el Service Layer). No escribe, no edita, no elimina,
no envia correo, no genera PDF, no toca SharePoint ni Supabase.
No importa api.py. De agentes.py importa SOLO funciones de lectura.

A diferencia de los otros scripts de verificacion, este NO consulta los saldos
a favor: esa consulta pasa por obtener_saldos_favor_masivo(), que crea y borra
un query temporal en SAP via POST/DELETE a /SQLQueries. Dejarla fuera mantiene
al script en GET puro. La unica consecuencia es que no se cuentan las filas
"PR" (saldos a favor no aplicados), que de todos modos no sirven para elegir un
cliente con facturas: son montos en negativo.

PREGUNTA QUE RESPONDE
---------------------
Para armar una prueba MIXTA de la gira por zona hay que elegir clientes de
ZONAS DISTINTAS que de verdad traigan documentos al PDF de ese agente. El
27/09/2026 se probo con C0037 + C0080 + C0121 (agente 9) y los tres salieron
omitidos: eran sucursales sin ningun documento abierto.

Los reportes de septiembre no alcanzan para elegir bien:

  - Verificacion_Sucursales_Pendientes.txt cuenta documentos, pero solo de las
    102 sucursales con saldo cero, no de los clientes con saldo propio, y NO
    dice a que zona pertenece cada uno.
  - Verificacion_Zonas_Sucursales.txt dice cuantos clientes tiene cada zona,
    pero no cuales de ellos cargan documentos.
  - Y el numero que importa no es "documentos abiertos del cliente" sino
    "documentos ruteados a ESE agente" via BPAddresses.U_CODV: C0042 tiene 77
    facturas abiertas y solo 45 llegan al PDF del agente 7.

Este script cruza las tres cosas: zona del arbol, cliente, y documentos que
realmente entran al PDF de ese agente.

METODO
------
Replica exactamente las dos mitades del modulo:

  - El ARBOL que ve Tania: mismo filtro y misma agrupacion que
    obtenerArbolAgente() del frontend (sap.ts) -> clientes con
    'saldo != 0 or FatherCard != null', agrupados por U_ZGIRA normalizado
    contra la UDT U_GIRAS.
  - El RUTEO del backend: obtener_documentos_cliente() importada de agentes.py
    tal cual, que es la que asigna 'vendedor_final' a cada documento. Se cuenta
    solo lo que rutea al agente, igual que ejecutar_gira_selectiva().

Tambien replica la regla de procesar_datos_cliente() que descarta un perfil
cuyos totales en ambas monedas quedan en cero.

Genera: Verificacion_Zonas_Con_Facturas.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/zonas_con_facturas.py
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
    obtener_documentos_cliente,
    obtener_todos_paginado,
    obtener_vendedores,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Zonas_Con_Facturas.txt")

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


def resumen_cliente(conn, cliente, agente_id):
    """Documentos de un cliente que realmente entran al PDF de este agente."""
    docs = obtener_documentos_cliente(conn, cliente, saldos_favor_cache=None)
    mios = [d for d in docs if str(d.get("vendedor_final")) == str(agente_id)]

    # Misma regla que procesar_datos_cliente(): un perfil cuyos totales quedan
    # en cero en las dos monedas no llega al PDF.
    total_crc = sum(d["saldo"] for d in mios if d["moneda"] == "CRC")
    total_usd = sum(d["saldo"] for d in mios if d["moneda"] == "USD")
    if total_crc == 0 and total_usd == 0:
        mios = []

    return {
        "codigo": cliente.get("CardCode"),
        "nombre": (cliente.get("CardName") or "")[:34],
        "es_sucursal": bool(cliente.get("FatherCard")),
        "docs_mios": len(mios),
        "docs_totales": len(docs),
        # Por signo y no por tipo_codigo: ese campo es el U_TDOC crudo de SAP
        # y puede venir como NC, N/C, NCM... (ver TIPOS_QUE_RESTAN en agentes.py).
        "suman": len([d for d in mios if d["saldo"] > 0]),
        "restan": len([d for d in mios if d["saldo"] < 0]),
        "crc": total_crc if mios else 0.0,
        "usd": total_usd if mios else 0.0,
    }


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("ZONAS CON FACTURAS - que clientes traen documentos al PDF de cada agente")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("Script de SOLO LECTURA. Unicamente GET (mas Login/Logout).")
    log("No escribe, no edita, no elimina, no envia.")
    log("")
    log("Sirve para armar la prueba MIXTA: elegir clientes de zonas distintas")
    log("que de verdad aporten filas al PDF, no sucursales mudas.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION (solo lectura)...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return

    try:
        # ------------------------------------------------------------------
        # 1. Zonas y agentes
        # ------------------------------------------------------------------
        titulo("PASO 1 - Zonas (UDT U_GIRAS) y agentes con correo")

        # obtener_todos_paginado pone el $orderby por su cuenta con el 4o argumento.
        zonas_raw = obtener_todos_paginado(conn, "U_GIRAS", {}, "Code")
        mapa_zonas = {}
        for z in zonas_raw:
            mapa_zonas[normalizar_codigo_zona(z.get("Code"))] = (
                z.get("Name") or f"Zona {z.get('Code')}"
            )

        vendedores = obtener_vendedores(conn)
        con_correo = {
            vid: v for vid, v in vendedores.items() if (v.get("correo") or "").strip()
        }

        log("")
        log(f"   Zonas en U_GIRAS  : {len(mapa_zonas)}")
        log(f"   Agentes con correo: {len(con_correo)}")
        for vid in sorted(con_correo):
            log(f"      {vid:<4} | {con_correo[vid].get('nombre', '')}")

        # ------------------------------------------------------------------
        # 2. Universo de clientes, con el filtro del arbol
        # ------------------------------------------------------------------
        titulo("PASO 2 - Clientes del arbol (mismo filtro que obtenerArbolAgente)")

        todos = obtener_clientes_con_saldo(conn)
        del_agente = defaultdict(list)
        for c in todos:
            vid = c.get("SalesPersonCode")
            if vid in con_correo:
                del_agente[vid].append(c)

        log("")
        log(f"   Clientes que devuelve el filtro: {len(todos)}")
        for vid in sorted(del_agente):
            log(f"      Agente {vid}: {len(del_agente[vid])} clientes en el arbol")

        total_a_revisar = sum(len(v) for v in del_agente.values())
        log("")
        log(f"   A revisar uno por uno: {total_a_revisar} clientes")
        log("   (BPAddresses + Invoices + CreditNotes por cliente)")

        # ------------------------------------------------------------------
        # 3. Documentos que rutean a cada agente
        # ------------------------------------------------------------------
        titulo("PASO 3 - Documentos que rutean a cada agente (BPAddresses.U_CODV)")

        resultados = {}  # (agente, cardCode) -> resumen
        hechos = 0

        for vid in sorted(del_agente):
            clientes = del_agente[vid]
            with ThreadPoolExecutor(max_workers=GIRA_ZONA_MAX_WORKERS) as executor:
                futuros = {
                    executor.submit(resumen_cliente, conn, cli, vid): cli
                    for cli in clientes
                }
                for futuro in as_completed(futuros):
                    hechos += 1
                    print(
                        f"   Progreso: {hechos}/{total_a_revisar} clientes...",
                        end="\r",
                    )
                    cli = futuros[futuro]
                    try:
                        resultados[(vid, cli.get("CardCode"))] = futuro.result()
                    except Exception as e:
                        print(f"\n   Error en {cli.get('CardCode')}: {e}")

        print("")
        log("")
        log(f"   Clientes evaluados: {len(resultados)}")

        # ------------------------------------------------------------------
        # 4. El arbol, con el conteo real al lado
        # ------------------------------------------------------------------
        for vid in sorted(del_agente):
            nombre_agente = con_correo[vid].get("nombre", "")
            titulo(f"AGENTE {vid} - {nombre_agente}")

            por_zona = defaultdict(list)
            for cli in del_agente[vid]:
                zcode = normalizar_codigo_zona(cli.get("U_ZGIRA"))
                r = resultados.get((vid, cli.get("CardCode")))
                if r:
                    por_zona[zcode].append(r)

            # Mismo orden que el panel: zonas con mas clientes primero.
            orden = sorted(por_zona.items(), key=lambda kv: -len(kv[1]))

            for zcode, filas in orden:
                nombre_zona = (
                    mapa_zonas.get(zcode, f"Zona {zcode}")
                    if zcode
                    else "Sin zona asignada"
                )
                con_docs = [f for f in filas if f["docs_mios"] > 0]

                log("")
                log(
                    f"   Zona {zcode or '-':<4} {nombre_zona:<38} "
                    f"{len(con_docs)} de {len(filas)} clientes aportan al PDF"
                )

                if not con_docs:
                    log("      (ninguno: zona INUTIL para la prueba mixta)")
                    continue

                log(
                    "      CODIGO     | NOMBRE                             "
                    "| SUC | SUM  RES | TOTAL SAP |            CRC |          USD"
                )
                log("      " + "-" * 105)
                for f in sorted(con_docs, key=lambda f: -f["docs_mios"]):
                    log(
                        f"      {f['codigo']:<10} | {f['nombre']:<34} "
                        f"| {'si ' if f['es_sucursal'] else 'no '} "
                        f"| {f['suman']:>3}  {f['restan']:>3} "
                        f"| {f['docs_totales']:>9} "
                        f"| {f['crc']:>14,.2f} | {f['usd']:>12,.2f}"
                    )

                mudos = [f for f in filas if f["docs_mios"] == 0]
                if mudos:
                    log(
                        f"      Mudos en esta zona ({len(mudos)}): "
                        + ", ".join(f["codigo"] for f in mudos[:12])
                        + (" ..." if len(mudos) > 12 else "")
                    )

        # ------------------------------------------------------------------
        # 5. Selecciones mixtas listas para copiar
        # ------------------------------------------------------------------
        titulo("SELECCIONES MIXTAS SUGERIDAS - un cliente por zona, todos con carga")

        for vid in sorted(del_agente):
            nombre_agente = con_correo[vid].get("nombre", "")

            mejor_por_zona = {}
            for cli in del_agente[vid]:
                zcode = normalizar_codigo_zona(cli.get("U_ZGIRA"))
                r = resultados.get((vid, cli.get("CardCode")))
                if not r or r["docs_mios"] == 0:
                    continue
                actual = mejor_por_zona.get(zcode)
                if actual is None or r["docs_mios"] > actual["docs_mios"]:
                    mejor_por_zona[zcode] = r

            log("")
            log(f"   Agente {vid} - {nombre_agente}")
            if len(mejor_por_zona) < 2:
                log(
                    f"      Solo {len(mejor_por_zona)} zona(s) con carga: no alcanza"
                    " para una prueba mixta de varias zonas."
                )
                continue

            elegidos = sorted(
                mejor_por_zona.items(), key=lambda kv: -kv[1]["docs_mios"]
            )
            for zcode, r in elegidos:
                nombre_zona = mapa_zonas.get(zcode, f"Zona {zcode}")
                log(
                    f"      {r['codigo']:<10} {r['nombre']:<34} "
                    f"zona {zcode:<4} {nombre_zona:<38} {r['docs_mios']:>3} docs"
                )

            top3 = [r["codigo"] for _, r in elegidos[:3]]
            log(f"      -> Seleccion mixta de 3 zonas: {' '.join(top3)}")
            log(
                "         Esperado: solicitados 3, procesados 3, omitidos []. "
                "La zona del PDF debe decir 'Seleccion manual'."
            )

        # ------------------------------------------------------------------
        titulo("COMO LEER ESTA TABLA")
        log("")
        log("   SUM / RES  : documentos que rutean a ESE agente y son las filas")
        log("                que aparecen en su PDF. SUM suman al saldo (facturas),")
        log("                RES restan (notas de credito y equivalentes). Se")
        log("                separan por el signo del saldo, no por U_TDOC.")
        log("   TOTAL SAP  : documentos abiertos del cliente contando todos los")
        log("                vendedores. Siempre mayor o igual que FAC+NC. La")
        log("                diferencia va al PDF de otro agente, no se pierde.")
        log("   SUC        : 'si' = sucursal con FatherCard. Su saldo figura en")
        log("                cero porque se consolida en la cuenta padre, pero")
        log("                igual carga documentos.")
        log("   Mudos      : clientes de esa zona sin ningun documento ruteado a")
        log("                este agente. Si se seleccionan, salen en 'omitidos'")
        log("                y no aportan nada al PDF.")
        log("")
        log("   No se cuentan las filas PR (saldos a favor): ver el encabezado")
        log("   del script.")

        duracion = (datetime.now() - inicio).total_seconds()
        log("")
        log(f"   Duracion: {duracion:.1f} segundos")

    finally:
        try:
            conn.logout()
        except Exception:
            pass
        guardar()


if __name__ == "__main__":
    main()
