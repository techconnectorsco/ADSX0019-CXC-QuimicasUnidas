"""
diagnostico_tablas_series.py - Químicas Unidas

OBJETIVO: Mapear qué tablas y endpoints relacionados con series y traslados
están realmente accesibles. Esto define las opciones reales que tenemos.

Tablas SAP relacionadas con números de serie e inventario:
  OSRI  - Serial Numbers (instancias) -> ya sabemos: NO accesible
  OSRQ  - Serial Numbers Quantity -> SÍ accesible (la estamos usando)
  OSRN  - Serial Numbers Master -> SÍ accesible
  OSRT  - Serial Numbers Transactions -> ?
  SRI1  - Serial Numbers in Documents -> ?
  OWTR  - Stock Transfers (cabecera) -> ya sabemos: NO accesible
  WTR1  - Stock Transfers (líneas) -> ?
  OINV/INV1 - Facturas -> ?
  OITM  - Items -> SÍ accesible
  OCRD  - BP -> SÍ accesible
  OWHS  - Warehouses -> NO accesible (pero /Warehouses OData SÍ)

Endpoints OData a probar:
  /StockTransfers - equivalente OData de OWTR
  /SerialNumberDetails - series detalladas
  /Items con expand de stock
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def probar_tabla_sql(conn, tabla, descripcion):
    """Prueba si una tabla es accesible vía SQL temporal."""
    import time

    query_code = f"DIAG_{int(time.time()*1000) % 100000}"
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"

    sql = f"SELECT * FROM {tabla}"

    try:
        resp = conn.session.post(
            url_post, json={"SqlCode": query_code, "SqlName": "DIAG", "SqlText": sql}
        )
        if resp.status_code in (200, 201):
            # Probar ejecutar
            res = conn.get(f"SQLQueries('{query_code}')/List", {"$top": 1})
            try:
                conn.session.delete(url_del)
            except Exception:
                pass
            if res and "value" in res and res["value"]:
                campos = list(res["value"][0].keys())
                print(
                    f"   ✅ {tabla:<15} ACCESIBLE — campos: {campos[:8]}{'...' if len(campos)>8 else ''}"
                )
                return True, campos
            elif res and "value" in res:
                print(f"   ✅ {tabla:<15} ACCESIBLE (tabla vacía)")
                return True, []
            else:
                print(f"   ⚠️  {tabla:<15} accesible pero sin respuesta")
                return True, []
        else:
            try:
                err = (
                    resp.json()
                    .get("error", {})
                    .get("message", {})
                    .get("value", "")[:80]
                )
            except Exception:
                err = resp.text[:80]
            print(f"   ❌ {tabla:<15} BLOQUEADA — {err}")
            return False, []
    except Exception as e:
        print(f"   ❌ {tabla:<15} error: {str(e)[:80]}")
        return False, []
    finally:
        try:
            conn.session.delete(url_del)
        except Exception:
            pass


def probar_endpoint_odata(conn, endpoint, descripcion):
    """Prueba si un endpoint OData responde."""
    try:
        res = conn.get(endpoint, {"$top": 1})
        if res is None:
            print(f"   ❌ /{endpoint:<25} sin respuesta")
            return False
        if "value" in res:
            if res["value"]:
                campos = list(res["value"][0].keys())
                muestra = campos[:6]
                print(
                    f"   ✅ /{endpoint:<25} OK — campos: {muestra}{'...' if len(campos)>6 else ''}"
                )
                return True
            else:
                print(f"   ✅ /{endpoint:<25} OK (vacío)")
                return True
        elif "error" in res:
            err = res.get("error", {}).get("message", {}).get("value", "?")[:80]
            print(f"   ❌ /{endpoint:<25} {err}")
            return False
        else:
            print(f"   ⚠️  /{endpoint:<25} respuesta inesperada")
            return False
    except Exception as e:
        print(f"   ❌ /{endpoint:<25} {str(e)[:80]}")
        return False


def main():
    print("=" * 80)
    print("🔍 MAPEO DE TABLAS Y ENDPOINTS ACCESIBLES")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    try:
        # =====================================================================
        # SECCIÓN 1: Tablas SAP vía SQL temporal
        # =====================================================================
        print("\n📋 PARTE 1: Tablas SAP vía SQL crudo")
        print("-" * 80)

        tablas_serie = [
            ("OSRI", "Serial Numbers - instancias"),
            ("OSRQ", "Serial Numbers - cantidad por bodega"),
            ("OSRN", "Serial Numbers - maestro"),
            ("OSRT", "Serial Numbers - transacciones"),
            ("SRI1", "Series ligadas a documentos"),
        ]

        tablas_traslados = [
            ("OWTR", "Stock Transfers - cabecera"),
            ("WTR1", "Stock Transfers - líneas"),
            ("OWHS", "Warehouses"),
            ("OITW", "Items por bodega"),
        ]

        tablas_facturas = [
            ("OINV", "Facturas de venta - cabecera"),
            ("INV1", "Facturas de venta - líneas"),
            ("ODLN", "Entregas - cabecera"),
            ("DLN1", "Entregas - líneas"),
        ]

        print("\n   📦 Series:")
        accesibles_serie = {}
        for t, d in tablas_serie:
            ok, campos = probar_tabla_sql(conn, t, d)
            if ok:
                accesibles_serie[t] = campos

        print("\n   🚚 Traslados / Bodegas:")
        accesibles_traslado = {}
        for t, d in tablas_traslados:
            ok, campos = probar_tabla_sql(conn, t, d)
            if ok:
                accesibles_traslado[t] = campos

        print("\n   📄 Facturas / Entregas:")
        accesibles_fact = {}
        for t, d in tablas_facturas:
            ok, campos = probar_tabla_sql(conn, t, d)
            if ok:
                accesibles_fact[t] = campos

        # =====================================================================
        # SECCIÓN 2: Endpoints OData
        # =====================================================================
        print("\n📋 PARTE 2: Endpoints OData")
        print("-" * 80)

        endpoints = [
            "StockTransfers",
            "SerialNumberDetails",
            "SerialNumbers",
            "InventoryGenEntries",
            "InventoryGenExits",
            "Deliveries",
            "Invoices",
            "Warehouses",
        ]

        print("\n   Endpoints estándar:")
        for ep in endpoints:
            probar_endpoint_odata(conn, ep, "")

        # =====================================================================
        # SECCIÓN 3: Para las tablas accesibles, mostrar campos completos
        # =====================================================================
        print("\n📋 PARTE 3: Campos completos de tablas clave accesibles")
        print("-" * 80)

        for t, campos in {
            **accesibles_serie,
            **accesibles_traslado,
            **accesibles_fact,
        }.items():
            if campos:
                print(f"\n   🔹 {t}: {len(campos)} columnas")
                # Mostrar de a 5 por línea
                for i in range(0, len(campos), 5):
                    print(f"      {', '.join(campos[i:i+5])}")

        print("\n" + "=" * 80)
        print("✅ MAPEO COMPLETADO")
        print("=" * 80)
        print("\nCon esto sabemos QUÉ podemos usar para construir el reporte correcto.")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
