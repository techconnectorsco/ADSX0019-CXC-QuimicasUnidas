# -*- coding: utf-8 -*-
r"""
SONDA - por que la consulta de facturas abiertas se cayo por timeout.

El 01/10/2026, corriendo el Paso 1 contra produccion a las 09:26 (horario de
oficina), la consulta de OINV abiertas se cayo con "Read timed out
(read timeout=120)". El Paso 0, el 30/09, la habia corrido en 0,3 s y devolvio
1.091 filas.

Entre una y otra hay un solo cambio en el query: se agrego la columna
T0."DocEntry" al SELECT, para poder deduplicar las filas del LEFT JOIN con
CRD1. Esta sonda mide si esa columna es la culpable o si fue carga del
servidor.

Corre cuatro variantes, de la mas simple a la del Paso 1, y cronometra cada
una. SOLO LECTURA.

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/sonda_timeout_facturas.py
"""

import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection, ejecutar_sql_sl
from agentes import _SQL_COLUMNAS_DOC, _SQL_FILTRO_CLIENTE, _SQL_JOINS_DOC

# Las columnas del Paso 0, es decir las del Paso 1 SIN DocEntry
COLUMNAS_SIN_DOCENTRY = _SQL_COLUMNAS_DOC.replace('T0."DocEntry", ', "")


def correr(conn, etiqueta, sql):
    print("")
    print("-" * 70)
    print(etiqueta)
    t0 = datetime.now()
    try:
        filas = ejecutar_sql_sl(conn, sql, estricto=True)
        segs = (datetime.now() - t0).total_seconds()
        print("   %d filas en %.1fs" % (len(filas), segs))
        return len(filas), segs
    except RuntimeError as e:
        segs = (datetime.now() - t0).total_seconds()
        print("   FALLO a los %.1fs: %s" % (segs, e))
        return None, segs


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    print("Conectando a SAP PRODUCCION (solo lectura)...")
    if not conn.login():
        print("ERROR: no se pudo conectar.")
        return 1

    try:
        correr(
            conn,
            "1. Conteo pelado de OINV abiertas (sin joins, sin columnas)",
            'SELECT COUNT(*) AS "N" FROM "OINV" T0 WHERE T0."DocStatus" = \'O\'',
        )

        correr(
            conn,
            "2. Las columnas del Paso 1, SIN el LEFT JOIN de CRD1",
            'SELECT T0."DocEntry", T0."CardCode", T0."DocCur", T0."DocTotal" '
            'FROM "OINV" T0 WHERE T0."DocStatus" = \'O\'',
        )

        correr(
            conn,
            "3. El query del PASO 0 (sin DocEntry) - 0,3s el 30/09",
            'SELECT %s FROM "OINV" T0 %s WHERE T0."DocStatus" = \'O\' AND %s'
            % (COLUMNAS_SIN_DOCENTRY, _SQL_JOINS_DOC, _SQL_FILTRO_CLIENTE),
        )

        correr(
            conn,
            "4. El query del PASO 1 (con DocEntry) - el que se cayo",
            'SELECT %s FROM "OINV" T0 %s WHERE T0."DocStatus" = \'O\' AND %s'
            % (_SQL_COLUMNAS_DOC, _SQL_JOINS_DOC, _SQL_FILTRO_CLIENTE),
        )

        print("")
        print("-" * 70)
        print("Repitiendo la 4 para ver si el primer intento paga un costo")
        print("de cache que los siguientes no pagan:")
        for intento in (1, 2):
            correr(
                conn,
                "4.%d El query del Paso 1, otra vez" % intento,
                'SELECT %s FROM "OINV" T0 %s WHERE T0."DocStatus" = \'O\' AND %s'
                % (_SQL_COLUMNAS_DOC, _SQL_JOINS_DOC, _SQL_FILTRO_CLIENTE),
            )
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
