# -*- coding: utf-8 -*-
r"""
¿ESTA SAP EN CONDICIONES DE CORRER LAS PRUEBAS?

Corre esto ANTES de probar la gira. Si SAP no esta, las pruebas van a fallar
por eso y no por el codigo, y uno pierde media hora buscando un bug que no
existe.

Tres controles, de lo mas barato a lo mas caro, y corta en el primero que
falle:

  1. Login. Es lo primero que se cae cuando el Service Layer no alcanza al SLD,
     y no toca ningun dato.
  2. Una consulta OData chica (un cliente por codigo). Es el camino que usa la
     gira para traer facturas y direcciones.
  3. Una consulta SQL chica (un COUNT). Es el camino que usa el arbol nuevo
     para el mapa de ruteo.

A PROPOSITO es liviano: pide un cliente y un conteo, nada mas. Antes esta
sonda corria la consulta de 1.067 facturas, lo cual era contradictorio — le
agregaba carga al servidor justo cuando se quiere averiguar si esta sufriendo.
El TIEMPO de estas dos consultas chicas ya dice todo: si un COUNT tarda 25
segundos, SAP esta ahogado aunque conteste.

SOLO LECTURA. No genera nada, no envia nada.

Uso:  .\.venv\Scripts\python.exe scripts_investigacion/sonda_sap_vivo.py

Codigo de salida 0 si se puede probar, 1 si no. Sirve para encadenar:
  .\.venv\Scripts\python.exe scripts_investigacion/sonda_sap_vivo.py; if ($?) { ... }
"""

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection, ejecutar_sql_sl

# Un cliente cualquiera que existe desde siempre. Solo se usa para ver si el
# Service Layer contesta: no importa que devuelva.
CLIENTE_SONDA = "C0040"

# Arriba de esto, SAP contesta pero esta ahogado. Medido el 01/10/2026: una
# consulta chica sana tarda menos de 1s; con el servidor cargado, 25-30s.
SEGUNDOS_LENTO = 8.0


def main():
    print("")
    print("=" * 66)
    print("¿ESTA SAP EN CONDICIONES DE PROBAR?")
    print("=" * 66)

    # ---------------------------------------------------------------- 1. login
    print("")
    print("1. Login...")
    t0 = time.time()
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("")
        print("   >>> SAP NO ESTA. No pruebes nada todavia.")
        print("")
        print("   Si el error dice 'Fail to connect to SLD' o 'OIDC', es el")
        print("   servidor: el Service Layer no alcanza al directorio que")
        print("   valida la autenticacion. No es el codigo ni los datos, y no")
        print("   hay nada que hacer de este lado: hay que escalarlo.")
        return 1
    print("   ok, en %.1fs" % (time.time() - t0))

    try:
        # ------------------------------------------------------------- 2. OData
        print("")
        print("2. Una consulta OData chica (el camino de las facturas)...")
        t0 = time.time()
        res = conn.get(
            f"BusinessPartners('{CLIENTE_SONDA}')", {"$select": "CardCode,CardName"}
        )
        segs_odata = time.time() - t0

        if res is None:
            print("")
            print("   >>> SAP DEJA ENTRAR PERO NO CONTESTA LAS CONSULTAS.")
            print("")
            print("   Es el caso traicionero: el login pasa y uno cree que")
            print("   esta todo bien. NO pruebes: la gira va a reportar")
            print("   clientes como 'no evaluables' y no vas a saber si es")
            print("   SAP o el codigo.")
            return 1
        print("   ok, en %.1fs" % segs_odata)

        # --------------------------------------------------------------- 3. SQL
        print("")
        print("3. Una consulta SQL chica (el camino del arbol nuevo)...")
        t0 = time.time()
        try:
            filas = ejecutar_sql_sl(
                conn,
                'SELECT COUNT(*) AS "N" FROM "OINV" T0 '
                "WHERE T0.\"DocStatus\" = 'O'",
                estricto=True,
                timeout_segs=60,
            )
        except RuntimeError as e:
            print("")
            print("   >>> EL CAMINO SQL NO RESPONDE: %s" % e)
            print("")
            print("   El arbol de la pantalla no va a poder construirse.")
            return 1
        segs_sql = time.time() - t0
        abiertas = int(filas[0]["N"]) if filas else 0
        print("   ok, en %.1fs (%d facturas abiertas en la empresa)"
              % (segs_sql, abiertas))

        # ----------------------------------------------------------- veredicto
        peor = max(segs_odata, segs_sql)
        print("")
        print("=" * 66)
        if peor < SEGUNDOS_LENTO:
            print(">>> SAP ESTA SANO. Adelante con las pruebas.")
            print("")
            print("    Siguiente paso: el GUION DE PRUEBAS DEL PREFILTRO,")
            print("    arriba de PLAN_GIRAS_POR_ZONA.md.")
        else:
            print(">>> SAP CONTESTA PERO ESTA LENTO (%.0fs una consulta chica)."
                  % peor)
            print("")
            print("    Se puede probar, con paciencia: el arbol en frio son")
            print("    cuatro consultas y la primera carga va a tardar. Si")
            print("    algo falla, sospecha del servidor antes que del codigo,")
            print("    y volve a correr esta sonda para confirmar.")
        print("=" * 66)
        return 0

    finally:
        try:
            conn.logout()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
