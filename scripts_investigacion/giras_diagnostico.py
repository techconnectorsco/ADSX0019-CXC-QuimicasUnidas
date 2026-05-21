"""
diagnostico_giras.py - Químicas Unidas
Script de DIAGNÓSTICO para investigar antes de ejecutar las giras.

Investiga:
  1. Si Colono y Gollo tienen CurrentAccountBalance en 0 (lo cual los excluiría
     del filtro actual) y si tienen facturas abiertas.
  2. Qué campos definidos por usuario (U_xxx) tienen las facturas, para
     identificar el campo de zona/destino por factura.
  3. Códigos de los agentes Berny, Siviany y José en SAP.

Uso:
    python diagnostico_giras.py

NO modifica nada en SAP. Solo lee.
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

# Códigos de cliente y patrones de nombre para investigar.
# Ajustar si los códigos exactos en SAP son distintos.
CLIENTES_INVESTIGAR_PATRONES = ["COLONO", "GOLLO", "GOLLOS"]
CLIENTES_INVESTIGAR_CODIGOS = []  # se llenan automáticamente al buscar por nombre

AGENTES_BUSCAR = ["berny", "siviany", "jose", "josé"]


def separador(titulo: str):
    print("\n" + "=" * 80)
    print(f"  {titulo}")
    print("=" * 80)


# =============================================================================
# 1. INVESTIGAR AGENTES (códigos)
# =============================================================================


def investigar_agentes(conn: ServiceLayerConnection):
    separador("1. AGENTES EN SAP - Berny, Siviany, José")

    params = {
        "$select": "SalesEmployeeCode,SalesEmployeeName,Email,Active",
        "$top": 200,
    }
    res = conn.get("SalesPersons", params)

    if not res or "value" not in res:
        print("   ❌ No se pudo obtener la lista de vendedores")
        return

    print(f"\n   {'Code':<6} {'Nombre':<40} {'Email':<35} {'Activo'}")
    print("   " + "-" * 90)

    encontrados = []
    for v in res["value"]:
        nombre_lower = (v.get("SalesEmployeeName") or "").lower()
        if any(b in nombre_lower for b in AGENTES_BUSCAR):
            code = v.get("SalesEmployeeCode", "")
            nombre = v.get("SalesEmployeeName", "")[:40]
            email = (v.get("Email") or "(sin correo)")[:35]
            activo = v.get("Active", "")
            print(f"   {code:<6} {nombre:<40} {email:<35} {activo}")
            encontrados.append(
                {
                    "code": code,
                    "nombre": v.get("SalesEmployeeName"),
                    "email": v.get("Email"),
                    "activo": activo,
                }
            )

    if not encontrados:
        print("   ⚠️ No se encontró ningún agente con esos nombres.")
        print("   Mostrando los primeros 20 vendedores activos para referencia:")
        for v in res["value"][:20]:
            if v.get("Active") == "tYES":
                print(
                    f"      [{v.get('SalesEmployeeCode')}] {v.get('SalesEmployeeName')}"
                )

    return encontrados


# =============================================================================
# 2. INVESTIGAR COLONO Y GOLLO
# =============================================================================


def investigar_colono_gollo(conn: ServiceLayerConnection):
    separador("2. COLONO Y GOLLO - ¿Por qué no aparecieron?")

    # Buscar por nombre
    filtro_nombres = " or ".join(
        [f"contains(CardName,'{p}')" for p in CLIENTES_INVESTIGAR_PATRONES]
    )
    params = {
        "$filter": f"CardType eq 'cCustomer' and ({filtro_nombres})",
        "$select": "CardCode,CardName,CurrentAccountBalance,Valid,SalesPersonCode,Frozen",
        "$top": 50,
    }

    res = conn.get("BusinessPartners", params)
    if not res or "value" not in res or not res["value"]:
        print(
            f"   ❌ No se encontró ningún cliente con nombres {CLIENTES_INVESTIGAR_PATRONES}"
        )
        return []

    print(f"\n   Encontrados {len(res['value'])} clientes:")
    print(
        f"   {'Código':<10} {'Nombre':<40} {'Balance':>15} {'Valid':<8} {'Frozen':<8} {'Vendedor'}"
    )
    print("   " + "-" * 100)

    codigos_encontrados = []
    for c in res["value"]:
        code = c.get("CardCode", "")
        nombre = (c.get("CardName") or "")[:40]
        balance = c.get("CurrentAccountBalance", 0) or 0
        valid = c.get("Valid", "")
        frozen = c.get("Frozen", "")
        vendedor = c.get("SalesPersonCode", "")
        print(
            f"   {code:<10} {nombre:<40} {balance:>15,.2f} {valid:<8} {frozen:<8} {vendedor}"
        )
        codigos_encontrados.append(code)

    # Verificar si tienen facturas abiertas (aunque el balance sea 0)
    print("\n   --- Verificando facturas abiertas por cliente ---")
    for code in codigos_encontrados:
        params_fac = {
            "$filter": f"CardCode eq '{code}' and DocumentStatus eq 'bost_Open'",
            "$select": "DocNum,DocTotal,PaidToDate,DocCurrency,DocDueDate",
            "$top": 100,
        }
        res_fac = conn.get("Invoices", params_fac)
        cantidad = len(res_fac.get("value", [])) if res_fac else 0

        saldo_total = 0
        for f in res_fac.get("value", []):
            saldo_total += (f.get("DocTotal", 0) or 0) - (f.get("PaidToDate", 0) or 0)

        if cantidad > 0:
            print(
                f"   ⚠️  {code}: {cantidad} facturas abiertas | Saldo aprox: {saldo_total:,.2f}"
            )
            print(
                f"       (Si el balance del cliente es 0 pero hay facturas, ESTE ES EL PROBLEMA)"
            )
        else:
            print(f"   ✓  {code}: 0 facturas abiertas (correcto que no aparezca)")

    return codigos_encontrados


# =============================================================================
# 3. INVESTIGAR CAMPOS DE FACTURA - ZONA POR FACTURA
# =============================================================================


def investigar_campos_factura(conn: ServiceLayerConnection, codigo_cliente: str):
    separador(
        f"3. CAMPOS DE FACTURA - Buscando campo de ZONA/DESTINO ({codigo_cliente})"
    )

    params = {
        "$filter": f"CardCode eq '{codigo_cliente}' and DocumentStatus eq 'bost_Open'",
        "$top": 1,  # Solo una para inspeccionar campos
    }
    res = conn.get("Invoices", params)

    if not res or "value" not in res or not res["value"]:
        print(f"   ❌ No hay facturas abiertas para {codigo_cliente}")
        return

    factura = res["value"][0]
    doc_num = factura.get("DocNum")

    # Listar TODOS los campos U_xxx (campos definidos por usuario)
    print(f"\n   Inspeccionando factura DocNum={doc_num}")
    print(f"\n   --- Campos U_xxx (definidos por usuario) a nivel CABECERA ---")

    campos_u = {
        k: v
        for k, v in factura.items()
        if k.startswith("U_") and v not in [None, "", 0]
    }
    if campos_u:
        for campo, valor in sorted(campos_u.items()):
            print(f"   {campo:<35} = {valor}")
    else:
        print("   (sin campos U_xxx con valor en cabecera)")

    # Campos estándar que podrían contener zona
    print(f"\n   --- Campos estándar de envío/zona ---")
    campos_estandar = [
        "ShipToCode",
        "ShipToDescription",
        "ShipToCity",
        "ShipToState",
        "Address",
        "City",
        "Country",
        "Indicator",
        "JournalMemo",
        "FederalTaxID",
        "Branch",
    ]
    for c in campos_estandar:
        valor = factura.get(c)
        if valor not in [None, ""]:
            print(f"   {c:<35} = {valor}")

    # Inspeccionar las líneas (DocumentLines) — la zona puede estar a nivel línea
    print(f"\n   --- Campos U_xxx a nivel LÍNEA (primer línea de la factura) ---")
    lineas = factura.get("DocumentLines", [])
    if lineas:
        primera_linea = lineas[0]
        campos_u_linea = {
            k: v
            for k, v in primera_linea.items()
            if k.startswith("U_") and v not in [None, "", 0]
        }
        if campos_u_linea:
            for campo, valor in sorted(campos_u_linea.items()):
                print(f"   {campo:<35} = {valor}")
        else:
            print("   (sin campos U_xxx con valor en líneas)")

        # Bodega de la línea, también podría servir
        print(f"\n   --- Posibles indicadores de destino a nivel línea ---")
        for c in [
            "WarehouseCode",
            "ShipDate",
            "ShippingMethod",
            "LocationCode",
            "CostingCode",
            "CostingCode2",
            "CostingCode3",
            "CostingCode4",
            "CostingCode5",
        ]:
            valor = primera_linea.get(c)
            if valor not in [None, "", -1]:
                print(f"   {c:<35} = {valor}")

    # Si hay varias líneas con valores distintos en algún U_, ese campo es candidato
    if len(lineas) > 1:
        print(
            f"\n   --- Variación de campos U_ entre líneas ({len(lineas)} líneas en total) ---"
        )
        campos_variables = {}
        for k in lineas[0].keys():
            if k.startswith("U_"):
                valores = set()
                for ln in lineas:
                    v = ln.get(k)
                    if v not in [None, ""]:
                        valores.add(str(v))
                if len(valores) > 1:
                    campos_variables[k] = valores

        if campos_variables:
            print(
                "   ⭐ CAMPOS QUE VARÍAN entre líneas (candidatos a ser ZONA/DESTINO):"
            )
            for campo, valores in campos_variables.items():
                print(f"   {campo:<35} = {list(valores)[:5]}")
        else:
            print("   (todos los campos U_ son iguales en todas las líneas)")


# =============================================================================
# 4. MUESTRA DE FACTURAS DEL CLIENTE C0504 (referencia que dio Tania)
# =============================================================================


def investigar_c0504(conn: ServiceLayerConnection):
    separador(
        "4. CLIENTE C0504 - Referencia mencionada por Tania (zonas Escazú, Belén...)"
    )

    # Verificar que el cliente exista
    bp = conn.get(
        "BusinessPartners('C0504')",
        {"$select": "CardCode,CardName,CurrentAccountBalance,Currency,SalesPersonCode"},
    )
    if not bp:
        print("   ❌ Cliente C0504 no encontrado en SAP")
        return

    print(f"   Cliente: {bp.get('CardName')}")
    print(f"   Moneda del cliente: {bp.get('Currency')}")
    print(f"   Balance: {bp.get('CurrentAccountBalance')}")

    investigar_campos_factura(conn, "C0504")


# =============================================================================
# 5. CAMPO MONEDA DEL LÍMITE DE CRÉDITO
# =============================================================================


def investigar_moneda_limite(conn: ServiceLayerConnection):
    separador("5. CAMPO MONEDA DEL LÍMITE DE CRÉDITO en BusinessPartners")

    # Traer un cliente con todos sus campos para ver cuál es la moneda del límite
    bp = conn.get("BusinessPartners('C0504')")
    if not bp:
        print("   ❌ No se pudo obtener cliente de referencia")
        return

    print(f"\n   Campos relacionados con moneda/crédito en BusinessPartners:")
    campos_buscar = [
        "Currency",
        "CreditCurrency",
        "CreditLimit",
        "MaxCommitment",
        "DebitorAccount",
        "DefaultBranch",
    ]
    for c in campos_buscar:
        valor = bp.get(c)
        if valor not in [None, ""]:
            print(f"   {c:<30} = {valor}")

    print(
        "\n   📌 La 'Currency' del cliente normalmente coincide con la moneda del límite."
    )
    print("      Si el cliente usa USD, su CreditLimit está en USD.")


# =============================================================================
# MAIN
# =============================================================================


def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO PRE-EJECUCIÓN GIRAS - Químicas Unidas")
    print(f"   Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        agentes = investigar_agentes(conn)
        codigos_clientes = investigar_colono_gollo(conn)
        investigar_c0504(conn)
        investigar_moneda_limite(conn)

        # Si encontramos Colono/Gollo, también inspeccionar sus facturas
        if codigos_clientes:
            for code in codigos_clientes[:2]:
                investigar_campos_factura(conn, code)

        separador("RESUMEN")
        print(f"\n   Agentes encontrados: {len(agentes) if agentes else 0}")
        print(f"   Clientes Colono/Gollo encontrados: {len(codigos_clientes)}")
        print(
            "\n   👉 Copia y comparte la salida de este script para terminar los ajustes."
        )
        print("=" * 80)

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
