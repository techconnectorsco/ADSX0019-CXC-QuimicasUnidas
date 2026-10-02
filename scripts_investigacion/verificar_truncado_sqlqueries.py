r"""
verificar_truncado_sqlqueries.py - Quimicas Unidas / ADSX0019

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA sobre los datos. GET mas los POST/DELETE a /SQLQueries que son el
mecanismo del Service Layer para correr SQL. No escribe datos de negocio, no
edita, no elimina, no envia correo, no genera PDF, no toca SharePoint ni
Supabase. No importa api.py.

PREGUNTA QUE RESPONDE
---------------------
Cuanto se estaba perdiendo por el truncado de /SQLQueries/List, y si el
arreglo lo resuelve.

EL BUG
------
/SQLQueries('CODE')/List devuelve SOLO las primeras 20 filas. Verificado
contra produccion el 30/09/2026:

    sin $top  -> 20 filas      $top=5   -> 20 filas
    $top=100  -> 20 filas      $top=500 -> 20 filas

y $skip se ignora: con $skip = 0, 20, 40, 60, 80, 100 sobre un cliente con 81
documentos abiertos, las seis paginas devolvieron LAS MISMAS 20 filas.

ejecutar_sql_sl() llamaba a /List una sola vez y devolvia res["value"] tal
cual, asi que nunca pudo ver mas de 20 filas. El unico consumidor en
produccion es obtener_saldos_favor_masivo(), que consulta JDT1 en lotes de 15
clientes: todo lote cuyos 15 clientes juntaran mas de 20 filas PR perdia el
resto, y esos saldos a favor no se restaban en el PDF del agente.

El comentario "<--- Bajamos a 15" en el parametro `lote` sugiere que el
sintoma ya se habia notado y se intento tapar bajando el tamano del lote. No
alcanza: un solo cliente puede tener mas de 20 filas.

EL ARREGLO
----------
La cabecera "Prefer: odata.maxpagesize=N". Con ella las 1.091 facturas
abiertas de toda la empresa llegan en una sola respuesta de 0,3s.

METODO
------
1. Confirma el sintoma: el mismo query con y sin la cabecera.
2. Trae los conteos de filas PR por cliente (una sola consulta agrupada).
3. Reconstruye los lotes de 15 tal como los arma obtener_saldos_favor_masivo
   y calcula, lote por lote, cuantas filas se caian.
4. Corre la funcion ya arreglada y compara el total real.

Genera: Verificacion_Truncado_SQLQueries.txt (raiz del proyecto)

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/verificar_truncado_sqlqueries.py
"""

import os
import sys
import uuid
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection
from agentes import (
    SQL_MAX_PAGE_SIZE,
    SQL_TIMEOUT_SEGS,
    ejecutar_sql_sl,
    obtener_saldos_favor_masivo,
)

REPORTE = os.path.join(BASE_DIR, "Verificacion_Truncado_SQLQueries.txt")

# El mismo lote que usa obtener_saldos_favor_masivo().
LOTE = 15

# Las mismas condiciones del query de produccion, para que los conteos sean
# los que de verdad se consultan.
WHERE_PR = (
    'T0."BalDueCred" > 0 '
    "AND T0.\"RefDate\" >= '20220101' "
    "AND T0.\"TransType\" NOT IN ('13', '14', '30')"
)

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


def sql_sin_arreglo(conn, sql):
    """ejecutar_sql_sl() como estaba ANTES: un /List sin la cabecera."""
    code = f"QU_OLD_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"
    resp = conn.session.post(
        url,
        json={"SqlCode": code, "SqlName": "Comparacion", "SqlText": sql},
        timeout=SQL_TIMEOUT_SEGS,
    )
    if resp.status_code not in (200, 201):
        return []
    try:
        res = conn.session.get(f"{url}('{code}')/List", timeout=SQL_TIMEOUT_SEGS)
        return (res.json() or {}).get("value") or [] if res.status_code == 200 else []
    finally:
        try:
            conn.session.delete(f"{url}('{code}')", timeout=SQL_TIMEOUT_SEGS)
        except Exception:
            pass


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("TRUNCADO DE /SQLQueries/List - impacto y verificacion del arreglo")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("SOLO LECTURA de datos. No envia nada, no genera PDF.")
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
        titulo("PASO 1 - El sintoma: el mismo query, con y sin la cabecera")

        sql_prueba = (
            'SELECT T0."DocEntry", T0."CardCode", T0."DocTotal" '
            'FROM "OINV" T0 WHERE T0."DocStatus" = \'O\''
        )

        viejo = sql_sin_arreglo(conn, sql_prueba)
        nuevo = ejecutar_sql_sl(conn, sql_prueba)

        log("")
        log("   Facturas abiertas de toda la empresa:")
        log(f"      sin la cabecera (como estaba): {len(viejo):>8,} filas")
        log(f"      con Prefer: odata.maxpagesize: {len(nuevo):>8,} filas")
        if len(nuevo) > len(viejo):
            log(f"      El arreglo recupera {len(nuevo) - len(viejo):,} filas "
                f"({len(nuevo) / max(len(viejo), 1):.0f}x).")
        else:
            log("      ATENCION: no hay diferencia. Revisar el arreglo.")

        # ------------------------------------------------------------------
        titulo("PASO 2 - Filas PR por cliente (una sola consulta agrupada)")

        # JDT1."ShortName" mezcla codigos de BP con cuentas de mayor: los que
        # mas filas PR tienen (71030208, 71090102...) son cuentas contables, no
        # clientes. obtener_saldos_favor_masivo() filtra por ShortName IN
        # (card_codes), asi que solo ve codigos de BP. El INNER JOIN con OCRD
        # deja el conteo en lo que de verdad se consulta.
        filas_conteo = ejecutar_sql_sl(
            conn,
            f'SELECT T0."ShortName", COUNT(*) AS "N" FROM "JDT1" T0 '
            f'INNER JOIN "OCRD" T1 ON T1."CardCode" = T0."ShortName" '
            f"WHERE {WHERE_PR} AND T1.\"CardType\" = 'C' "
            f'GROUP BY T0."ShortName"',
        )

        if not filas_conteo:
            log("")
            log("   El query agrupado no devolvio nada. Sin esto no se puede medir")
            log("   el impacto; se corta aca.")
            return

        por_cliente = {}
        for r in filas_conteo:
            sn = str(r.get("ShortName") or "").strip()
            if sn:
                por_cliente[sn] = int(r.get("N") or 0)

        total_filas_pr = sum(por_cliente.values())
        log("")
        log(f"   Clientes con filas PR : {len(por_cliente):,}")
        log(f"   Filas PR en total     : {total_filas_pr:,}")
        log(f"   Clientes con mas de 20: "
            f"{sum(1 for n in por_cliente.values() if n > 20):,}")
        peor = sorted(por_cliente.items(), key=lambda kv: -kv[1])[:8]
        log("")
        log("   Los que mas filas tienen:")
        for cc, n in peor:
            log(f"      {cc:<12} {n:>6,} filas")

        # ------------------------------------------------------------------
        titulo("PASO 3 - Cuanto perdia cada lote de 15 clientes")
        log("")
        log("   obtener_saldos_favor_masivo() consulta JDT1 en lotes de 15 clientes.")
        log("   El truncado es POR LOTE: si los 15 juntos pasaban de 20 filas, el")
        log("   resto se caia. Se reconstruyen los lotes en el mismo orden.")

        # El filtro de produccion es, en OData:
        #     CardType eq 'cCustomer' and (CurrentAccountBalance ne 0
        #                                  or FatherCard ne null)
        # y ese "FatherCard ne null" matchea a casi TODOS: en SAP el campo es
        # cadena vacia, no NULL, cuando el cliente no es sucursal. O sea que el
        # universo real es practicamente todo CardType='C', no solo los que
        # tienen saldo. Por eso aca no se filtra por Balance: filtrarlo daria un
        # universo de ~300 clientes y mediria otra cosa.
        filas_univ = ejecutar_sql_sl(
            conn,
            'SELECT T0."CardCode" FROM "OCRD" T0 WHERE T0."CardType" = \'C\'',
        )

        universo = {str(r.get("CardCode") or "").strip() for r in filas_univ}
        universo.discard("")
        # Mismo orden que obtener_clientes_con_saldo(), que pagina con
        # $orderby=CardCode: el orden decide como caen los lotes de 15.
        codigos = sorted(universo)

        log("")
        log(f"   Clientes en el universo de la gira: {len(codigos):,}")

        if not codigos:
            log("   No se pudo reconstruir el universo; se corta aca.")
            return

        lotes_truncados = 0
        filas_perdidas = 0
        clientes_afectados = set()

        for i in range(0, len(codigos), LOTE):
            bloque = codigos[i : i + LOTE]
            n_lote = sum(por_cliente.get(c, 0) for c in bloque)
            if n_lote > 20:
                lotes_truncados += 1
                filas_perdidas += n_lote - 20
                clientes_afectados.update(
                    c for c in bloque if por_cliente.get(c, 0) > 0
                )

        total_lotes = (len(codigos) + LOTE - 1) // LOTE
        log("")
        log(f"   Lotes en total            : {total_lotes:,}")
        log(f"   Lotes que se truncaban    : {lotes_truncados:,} "
            f"({100 * lotes_truncados / max(total_lotes, 1):.1f}%)")
        log(f"   Filas PR que se perdian   : {filas_perdidas:,} de {total_filas_pr:,} "
            f"({100 * filas_perdidas / max(total_filas_pr, 1):.1f}%)")
        log(f"   Clientes en lotes afectados: {len(clientes_afectados):,}")

        # ------------------------------------------------------------------
        titulo("PASO 4 - La funcion de produccion, ya arreglada")
        log("")
        log("   obtener_saldos_favor_masivo() sobre los clientes que mas filas PR")
        log("   tienen: antes devolvia como maximo 20 por lote.")

        muestra = [cc for cc, _ in peor]
        cache = obtener_saldos_favor_masivo(conn, muestra)
        log("")
        log(f"   {'CLIENTE':<12} {'ESPERADO':>10} {'DEVUELTO':>10}   ESTADO")
        log("   " + "-" * 52)
        for cc, esperado in peor:
            devuelto = len(cache.get(cc, []))
            # El query de produccion filtra igual que el conteo, asi que deberian
            # coincidir.
            estado = "OK" if devuelto == esperado else "REVISAR"
            log(f"   {cc:<12} {esperado:>10,} {devuelto:>10,}   {estado}")

        # ------------------------------------------------------------------
        titulo("CONCLUSION")
        log("")
        if filas_perdidas > 0:
            log(f"   El bug era real y medible: {filas_perdidas:,} filas PR "
                f"({100 * filas_perdidas / max(total_filas_pr, 1):.1f}% del total)")
            log(f"   no llegaban al PDF, repartidas en {lotes_truncados:,} lotes.")
            log("   Son saldos a favor que NO se le restaban al cliente, asi que el")
            log("   agente cobraba de mas.")
        else:
            log("   Con los datos de hoy ningun lote pasaba de 20 filas, asi que el")
            log("   bug no estaba produciendo perdida todavia. El arreglo igual")
            log("   corresponde: era cuestion de tiempo.")
        log("")
        log(f"   SQL_MAX_PAGE_SIZE actual: {SQL_MAX_PAGE_SIZE:,}")
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
