"""
verificar_permisos_sap.py - Químicas Unidas

OBJETIVO: Generar evidencia técnica de las tablas SAP a las que el usuario
de Service Layer (habilitado por Novitec) NO tiene acceso.

Este reporte se puede compartir con Novitec para solicitar la habilitación
de permisos sobre las tablas necesarias para el reporte de consignaciones.

Tablas críticas que necesitamos:
  - OSRI : Serial Numbers (instancias) — fuente de verdad de Tania
  - OWTR : Stock Transfers (cabecera)
  - WTR1 : Stock Transfers (líneas)
  - SRI1 : Series en documentos
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

# Tablas que SÍ deberían estar accesibles (control positivo)
TABLAS_CONTROL = [
    ("OCRD", "Maestro de Socios de Negocio"),
    ("OITM", "Maestro de Artículos"),
    ("OSRQ", "Serial Numbers Quantity"),
]

# Tablas críticas que NO se pueden acceder y necesitamos
TABLAS_BLOQUEADAS = [
    ("OSRI", "Serial Numbers Instances — query bodega_series de Tania la usa"),
    ("OWTR", "Stock Transfers cabecera — query inventario_entre_bodegas"),
    ("WTR1", "Stock Transfers líneas"),
    ("SRI1", "Series en Documentos — JOIN principal del reporte"),
    ("OSRN", "Serial Numbers Master"),
    ("OWHS", "Warehouses"),
    ("OINV", "Facturas de Venta"),
    ("INV1", "Líneas de Factura"),
]


def probar_tabla(conn, tabla, descripcion):
    """Intenta una query mínima sobre la tabla y reporta el resultado."""
    query_code = f"PERM_TEST_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"

    # SQL mínimo: solo contar registros, no traer datos
    sql = f'SELECT COUNT(*) AS "Total" FROM {tabla}'

    print(f"\n   Tabla: {tabla:<8} ({descripcion})")
    print(f"   SQL  : {sql}")

    try:
        resp = conn.session.post(
            url_post,
            json={"SqlCode": query_code, "SqlName": "PERM_TEST", "SqlText": sql},
        )

        if resp.status_code in (200, 201):
            # Crear funcionó, ahora ejecutar
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$top": 1})
            if res and "value" in res and res["value"]:
                total = res["value"][0].get("Total", "?")
                print(f"   ✅ ACCESIBLE — registros en la tabla: {total}")
                return "ACCESIBLE", None
            else:
                print(f"   ⚠️  CREADA pero ejecución vacía")
                return "PARCIAL", None
        else:
            try:
                err_msg = (
                    resp.json().get("error", {}).get("message", {}).get("value", "")
                )
            except Exception:
                err_msg = resp.text[:200]
            print(f"   ❌ BLOQUEADA — HTTP {resp.status_code}")
            print(f"      Mensaje SAP: {err_msg[:200]}")
            return "BLOQUEADA", err_msg
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass


def main():
    print("=" * 80)
    print("VERIFICACIÓN DE PERMISOS DE TABLAS SAP B1 — Service Layer")
    print("Cliente: Químicas Unidas (BD: SBO_CR_QUIMICAS_PROD)")
    print("Fecha: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ ERROR: no se pudo iniciar sesión en SAP Service Layer")
        return

    print(f"\n✅ Sesión iniciada en SAP Service Layer")
    print(f"   Base URL: {conn.base_url}")

    resumen = {"ACCESIBLE": [], "BLOQUEADA": [], "PARCIAL": []}

    try:
        # =====================================================================
        # SECCIÓN 1: Tablas que SÍ funcionan (control positivo)
        # =====================================================================
        print("\n" + "=" * 80)
        print("SECCIÓN 1: Tablas con acceso confirmado (control)")
        print("=" * 80)
        for tabla, desc in TABLAS_CONTROL:
            estado, _ = probar_tabla(conn, tabla, desc)
            resumen[estado].append(tabla)

        # =====================================================================
        # SECCIÓN 2: Tablas que NO funcionan (el problema)
        # =====================================================================
        print("\n" + "=" * 80)
        print("SECCIÓN 2: Tablas sin acceso — NECESARIAS PARA EL REPORTE")
        print("=" * 80)
        errores_bloqueados = {}
        for tabla, desc in TABLAS_BLOQUEADAS:
            estado, err = probar_tabla(conn, tabla, desc)
            resumen[estado].append(tabla)
            if estado == "BLOQUEADA":
                errores_bloqueados[tabla] = err

        # =====================================================================
        # RESUMEN FINAL
        # =====================================================================
        print("\n" + "=" * 80)
        print("RESUMEN DE PERMISOS")
        print("=" * 80)
        print(f"\n✅ Tablas ACCESIBLES ({len(resumen['ACCESIBLE'])}):")
        for t in resumen["ACCESIBLE"]:
            print(f"   - {t}")

        print(f"\n❌ Tablas BLOQUEADAS ({len(resumen['BLOQUEADA'])}):")
        for t in resumen["BLOQUEADA"]:
            print(f"   - {t}")

        if resumen["PARCIAL"]:
            print(f"\n⚠️  Tablas con acceso PARCIAL ({len(resumen['PARCIAL'])}):")
            for t in resumen["PARCIAL"]:
                print(f"   - {t}")

        # =====================================================================
        # IMPACTO TÉCNICO
        # =====================================================================
        print("\n" + "=" * 80)
        print("IMPACTO TÉCNICO")
        print("=" * 80)
        print("""
La automatización del reporte de Toma Física de Consignaciones requiere
acceso de LECTURA a las siguientes tablas, las cuales son las mismas que
usan los queries internos del Query Manager que la encargada ejecuta
manualmente cada martes:

  - OSRI : usado por 'bodega_series' (InternalKey 436) — fuente de verdad
  - OWTR : usado por 'inventario_entre_bodegas' (InternalKey 398)
  - WTR1 : líneas del traslado
  - SRI1 : relación entre series y documentos

Sin acceso a estas tablas, no es posible replicar exactamente los reportes
internos del Query Manager vía Service Layer. Esto deriva en discrepancias
de cifras entre los reportes automáticos y los manuales (ej: el reporte
automático muestra 326 equipos para un agente cuando el manual muestra 167).

Se solicita a Novitec habilitar acceso de LECTURA (SELECT) sobre estas
tablas para el usuario de Service Layer asignado a esta integración.
""")

    finally:
        conn.logout()
        print("✅ Sesión cerrada")


if __name__ == "__main__":
    main()
