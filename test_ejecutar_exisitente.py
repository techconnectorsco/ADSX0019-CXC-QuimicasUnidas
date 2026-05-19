"""
test_ejecutar_query_existente.py - Químicas Unidas

OBJETIVO: Probar si podemos EJECUTAR queries del Query Manager que ya están
guardados (como bodega_series, InternalKey=436), en lugar de crear nuevos.

La hipótesis es: Novitec bloquea SQL crudo a OSRI, pero los queries ya
autorizados en el Query Manager sí se pueden ejecutar vía Service Layer.

Probamos 4 endpoints distintos para ver cuál (si alguno) funciona.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def probar(conn, descripcion, metodo, url, params=None, json_body=None):
    """Hace una petición y reporta el resultado de forma compacta."""
    print(f"\n🧪 {descripcion}")
    print(f"   {metodo} {url[len(conn.base_url):]}")
    if params:
        print(f"   params: {params}")
    if json_body:
        print(f"   body:   {json.dumps(json_body)[:100]}")

    try:
        if metodo == "GET":
            resp = conn.session.get(url, params=params)
        else:
            resp = conn.session.post(url, json=json_body)

        if resp.status_code in (200, 201):
            try:
                data = resp.json()
                if "value" in data and data["value"]:
                    print(f"   ✅ OK — {len(data['value'])} fila(s)")
                    print(f"      Campos: {list(data['value'][0].keys())}")
                    print(f"      Primera fila: {data['value'][0]}")
                    return True, data
                elif "value" in data:
                    print(f"   ⚠️  OK pero lista vacía")
                    return True, data
                else:
                    print(f"   ⚠️  Respuesta sin 'value': {str(data)[:200]}")
                    return True, data
            except Exception:
                print(f"   ⚠️  Respuesta no es JSON: {resp.text[:200]}")
                return True, None
        else:
            try:
                err = (
                    resp.json()
                    .get("error", {})
                    .get("message", {})
                    .get("value", "")[:200]
                )
            except Exception:
                err = resp.text[:200]
            print(f"   ❌ {resp.status_code}: {err}")
            return False, None
    except Exception as e:
        print(f"   ❌ Excepción: {str(e)[:200]}")
        return False, None


def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return

    print("=" * 80)
    print("🔍 ¿Podemos EJECUTAR el query bodega_series (sin crearlo)?")
    print("=" * 80)
    print("InternalKey: 436 | SqlCode probable: 'bodega_series'")
    print("Parámetros del query: %0=WhsCode='0180', %1=Status=0")

    try:
        BASE = conn.base_url

        # =====================================================================
        # OPCIÓN A: Ejecutar como SQLQuery por SqlCode
        # =====================================================================
        # Si el query está guardado con SqlCode='bodega_series', así se invoca
        probar(
            conn,
            "A1: /SQLQueries('bodega_series')/List sin params",
            "GET",
            f"{BASE}/SQLQueries('bodega_series')/List",
        )

        probar(
            conn,
            "A2: /SQLQueries('bodega_series')/List con paramList",
            "GET",
            f"{BASE}/SQLQueries('bodega_series')/List",
            params={"ParamList": "WhsCode='0180'&Status=0"},
        )

        # =====================================================================
        # OPCIÓN B: Por InternalKey vía UserQueries
        # =====================================================================
        probar(
            conn,
            "B1: /UserQueries(436) — leer definición",
            "GET",
            f"{BASE}/UserQueries(436)",
        )

        # =====================================================================
        # OPCIÓN C: Servicio SQLQueriesService con Execute (sml.svc)
        # =====================================================================
        # Algunos SL exponen este endpoint para ejecución parametrizada
        probar(
            conn,
            "C1: POST /SQLQueries('bodega_series')/List",
            "POST",
            f"{BASE}/SQLQueries('bodega_series')/List",
            json_body={
                "ParamList": [
                    {"Name": "%0", "Value": "0180"},
                    {"Name": "%1", "Value": "0"},
                ]
            },
        )

        # =====================================================================
        # OPCIÓN D: Endpoint funcional UserQueriesService_Run (sml.svc)
        # =====================================================================
        probar(
            conn,
            "D1: POST /UserQueriesService_Run con InternalKey",
            "POST",
            f"{BASE}/UserQueriesService_Run",
            json_body={
                "InternalKey": 436,
                "ParamList": [
                    {"Name": "WhsCode", "Value": "0180"},
                    {"Name": "Status", "Value": "0"},
                ],
            },
        )

        # =====================================================================
        # OPCIÓN E: Buscar el SqlCode real
        # =====================================================================
        # SqlCode es distinto a QueryDescription. Vamos a leerlo del query 436.
        print("\n" + "=" * 80)
        print("🔍 Buscando el SqlCode real del query 436 en UserQueries")
        print("=" * 80)
        ok, data = probar(
            conn,
            "E1: GET /UserQueries(436) completo",
            "GET",
            f"{BASE}/UserQueries(436)",
        )

        if ok and data:
            print(f"\n   Todos los campos disponibles del query 436:")
            for k, v in data.items():
                valor_str = str(v)[:80] if v is not None else "null"
                print(f"      {k}: {valor_str}")

        # =====================================================================
        # OPCIÓN F: Listar SQLQueries
        # =====================================================================
        # Si en /SQLQueries listamos, vemos los SqlCode disponibles
        print("\n" + "=" * 80)
        print("🔍 Listando /SQLQueries para ver qué SqlCodes hay")
        print("=" * 80)
        probar(
            conn,
            "F1: GET /SQLQueries top 10",
            "GET",
            f"{BASE}/SQLQueries",
            params={"$top": 10},
        )

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
