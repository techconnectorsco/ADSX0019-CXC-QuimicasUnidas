"""
==========================================================================
SCRIPT 5 — INVESTIGACIÓN: ASIGNACIÓN DE CLIENTES A AGENTES POR ZONA/GIRA
==========================================================================
Investiga puntos E1, E2, E3, E4 de los comentarios de Tania:

E1. El Lagar C0138-39-40: TODOS los destinos le salen a José, pero Jacó es
    de Berny y Belén es de Siviany. Cada zona/destino debería ir al agente
    correcto.
E2. Colono Agropecuario C0161-62-63-64: todos le salen a Berny.
E3. Almacenes Colono C0040-42-43: todos le salen a Berny.
E4. Carlos Ruiz C0314-15-16: le sale a Berny pero es gira 12 (José).
    Berny lleva giras 5-6-7.

OBJETIVO:
- Entender cómo se asigna un cliente a un agente
- Determinar si la asignación es por:
    a) SalesPersonCode del Business Partner (uno por cliente)
    b) U_ZGIRA (zona/gira numérica)
    c) Algún mapeo zona → agente
- Investigar si hay una tabla de asignación que estamos ignorando

USO:
    python 05_investigar_agentes_zonas.py
"""

import sys
from typing import List, Dict
from datetime import datetime

from modules.database.conexion import ServiceLayerConnection

# Casos reportados por Tania
CASOS_TANIA = [
    {
        "codes": ["C0138", "C0139", "C0140"],
        "esperado": "EL LAGAR - distribuir entre José/Berny/Siviany",
    },
    {
        "codes": ["C0161", "C0162", "C0163", "C0164"],
        "esperado": "COLONO AGROPECUARIO - distribuir, no todo Berny",
    },
    {"codes": ["C0040", "C0042", "C0043"], "esperado": "ALMACENES COLONO - distribuir"},
    {
        "codes": ["C0314", "C0315", "C0316"],
        "esperado": "CARLOS RUIZ - gira 12 (José), no Berny",
    },
]


def obtener_vendedores(conn):
    """Lista todos los vendedores configurados en SAP."""
    print("=" * 70)
    print("VENDEDORES CONFIGURADOS EN SAP")
    print("=" * 70)

    resp = conn.session.get(
        f"{conn.base_url}/SalesPersons",
        params={"$select": "SalesEmployeeCode,SalesEmployeeName,Active"},
        verify=False,
    )
    if not resp.ok:
        print(f"ERROR: {resp.status_code}")
        return {}

    vendedores = {}
    for v in resp.json().get("value", []):
        vendedores[v["SalesEmployeeCode"]] = v
        activo = "ACTIVO" if v.get("Active") == "tYES" else "INACTIVO"
        print(
            f"  Code {v['SalesEmployeeCode']:>4}: "
            f"{v.get('SalesEmployeeName', ''):<35} ({activo})"
        )

    return vendedores


def inspeccionar_clientes(conn, codes: List[str], vendedores: Dict):
    """Inspecciona un grupo de clientes mostrando agente y zona."""
    for code in codes:
        resp = conn.session.get(
            f"{conn.base_url}/BusinessPartners('{code}')",
            params={
                "$select": "CardCode,CardName,SalesPersonCode,U_ZGIRA,Address,ShipToDefault,MailAddress"
            },
            verify=False,
        )
        if not resp.ok:
            print(f"  {code}: ERROR {resp.status_code}")
            continue

        bp = resp.json()
        sp_code = bp.get("SalesPersonCode")
        nombre_vendedor = vendedores.get(sp_code, {}).get("SalesEmployeeName", "???")

        print(f"\n  {code} — {bp.get('CardName')}")
        print(f"    SalesPersonCode: {sp_code} → {nombre_vendedor}")
        print(f"    U_ZGIRA (zona/gira): {bp.get('U_ZGIRA')}")
        print(f"    Dirección: {(bp.get('Address') or '')[:70]}")


def obtener_direcciones_envio(conn, card_code: str):
    """
    Lista TODAS las direcciones de envío (ShipTo) de un cliente.
    Aquí podría estar la clave: cada destino puede tener una zona/agente diferente.
    """
    resp = conn.session.get(
        f"{conn.base_url}/BusinessPartners('{card_code}')",
        params={"$select": "CardCode,CardName,BPAddresses"},
        verify=False,
    )
    if not resp.ok:
        return

    bp = resp.json()
    direcciones = bp.get("BPAddresses", [])
    print(f"\n  {card_code} - Direcciones registradas: {len(direcciones)}")
    for addr in direcciones:
        tipo = addr.get("AddressType", "")
        # bo_BillTo = facturación, bo_ShipTo = envío
        nombre_addr = addr.get("AddressName", "")
        ciudad = addr.get("City", "")
        zona = addr.get("U_ZGIRA", "")  # ¿Existe U_ZGIRA a nivel de dirección?
        print(f"    [{tipo}] '{nombre_addr}' | Ciudad: {ciudad} | U_ZGIRA: {zona}")


def investigar_zonas_en_facturas(conn, card_code: str):
    """
    Mira las facturas abiertas del cliente y sus ShipToCode.
    Si cada factura va a un ShipTo diferente, y cada ShipTo es de una zona
    diferente, ahí está el quid del asunto.
    """
    print(f"\n  Facturas abiertas de {card_code} con sus destinos (ShipTo):")
    resp = conn.session.get(
        f"{conn.base_url}/Invoices",
        params={
            "$select": "DocEntry,DocNum,DocDate,DocTotal,ShipToCode,Address2",
            "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
            "$top": 20,
            "$orderby": "DocDate desc",
        },
        verify=False,
    )
    if not resp.ok:
        return

    docs = resp.json().get("value", [])
    print(f"    Total facturas abiertas: {len(docs)}")

    # Agrupar por ShipToCode
    por_destino = {}
    for d in docs:
        st = d.get("ShipToCode", "(sin destino)")
        por_destino.setdefault(st, []).append(d)

    for destino, facts in por_destino.items():
        print(f"    Destino '{destino}': {len(facts)} facturas")


def main():
    print("=" * 70)
    print("SCRIPT 5 - INVESTIGACIÓN DE AGENTES Y ZONAS")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("ERROR: No se pudo conectar a SAP")
        sys.exit(1)

    # 1. Listar vendedores
    vendedores = obtener_vendedores(conn)

    # 2. Investigar cada caso reportado
    print("\n" + "=" * 70)
    print("CASOS REPORTADOS POR TANIA")
    print("=" * 70)

    for caso in CASOS_TANIA:
        print(f"\n--- {caso['esperado']} ---")
        inspeccionar_clientes(conn, caso["codes"], vendedores)

        # Para el primer cliente del grupo, mirar direcciones y facturas
        primer_code = caso["codes"][0]
        obtener_direcciones_envio(conn, primer_code)
        investigar_zonas_en_facturas(conn, primer_code)

    # 3. Pregunta abierta a confirmar con Tania
    print("\n" + "=" * 70)
    print("PREGUNTAS PARA TANIA (a confirmar)")
    print("=" * 70)
    print("""
    1. ¿La asignación de un cliente a un agente debe basarse en:
       (a) El SalesPersonCode del Business Partner (un solo agente por cliente)
       (b) El U_ZGIRA (gira/zona) que tiene cada cliente
       (c) Cada ShipTo (destino) tiene su propia zona, y según la FACTURA
           se asigna al agente de esa zona

    2. ¿Existe en algún lado una tabla de mapeo "zona → agente"?
       Por ejemplo:
       - Gira 5, 6, 7 → Berny Marín Chavez
       - Gira 12 → José Chacón
       - Gira 26 → Siviany González

    3. Para el caso de El Lagar/Colono/Almacenes Colono: ¿el cliente
       padre tiene UN solo SalesPersonCode pero los ShipTo deben ir
       a DIFERENTES agentes según la zona física?
    """)


if __name__ == "__main__":
    main()
