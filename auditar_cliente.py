"""
auditar_cliente.py - Químicas Unidas
Script forense para investigar un cliente específico directamente en SAP Service Layer.
"""

import sys
import os

# Agregar path del proyecto para importar la conexión
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection
import uuid


def ejecutar_sql_sl(conn: ServiceLayerConnection, sql: str):
    code = f"QU_AUDIT_{uuid.uuid4().hex[:8]}"
    url = f"{conn.base_url}/SQLQueries"

    resp = conn.session.post(
        url,
        json={"SqlCode": code, "SqlName": "Query Auditoria Temporal", "SqlText": sql},
    )
    if resp.status_code not in (200, 201):
        return []

    res = conn.get(f"SQLQueries('{code}')/List", {})
    conn.session.delete(f"{url}('{code}')")
    return res.get("value", []) if res else []


def investigar_cliente(card_code: str):
    card_code = card_code.strip().upper()
    print("=" * 80)
    print(f"🕵️‍♂️ INVESTIGACIÓN FORENSE DE CLIENTE EN SAP: {card_code}")
    print("=" * 80)

    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    try:
        # 1. DATOS MAESTROS DEL SOCIO DE NEGOCIOS
        print("\n[1] 📋 Revisando Datos Maestros en BusinessPartners...")
        bp = conn.get(
            f"BusinessPartners('{card_code}')",
            {
                "$select": "CardCode,CardName,CurrentAccountBalance,U_NTV_EnvioAutomatico,EmailAddress,U_NVT_CorreoEstadoCuenta"
            },
        )

        if not bp:
            print(f"❌ El cliente '{card_code}' NO existe en la base de datos de SAP.")
            return

        balance = bp.get("CurrentAccountBalance", 0)
        envio_auto = bp.get("U_NTV_EnvioAutomatico", "VACÍO")
        correo_std = bp.get("EmailAddress", "VACÍO")
        correo_cxc = bp.get("U_NVT_CorreoEstadoCuenta", "VACÍO")

        print(f"   🔹 Nombre: {bp.get('CardName')}")
        print(
            f"   🔹 Saldo en Cuenta Corriente (SAP): ₡{balance:,.2f}"
            if balance >= 0
            else f"   🔹 Saldo en Cuenta Corriente (SAP): (₡{abs(balance):,.2f})"
        )
        print(f"   🔹 Campo Envío Automático (U_NTV_EnvioAutomatico): '{envio_auto}'")
        print(f"   🔹 Correo Principal (EmailAddress): '{correo_std}'")
        print(f"   🔹 Correo CXC (U_NVT_CorreoEstadoCuenta): '{correo_cxc}'")

        # 2. FACTURAS ABIERTAS
        print("\n[2] 📄 Buscando Facturas Abiertas (Invoices)...")
        filtro_fac = f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'"
        facturas = conn.get(
            "Invoices",
            {"$filter": filtro_fac, "$select": "DocNum,DocDate,DocTotal,PaidToDate"},
        )
        lista_fac = facturas.get("value", []) if facturas else []
        print(f"   🔹 Total Facturas abiertas encontradas: {len(lista_fac)}")
        for f in lista_fac:
            saldo = f.get("DocTotal", 0) - f.get("PaidToDate", 0)
            print(
                f"      - Factura № {f.get('DocNum')} | Fecha: {f.get('DocDate')[:10]} | Saldo Pendiente: ₡{saldo:,.2f}"
            )

        # 3. NOTAS DE CRÉDITO ABIERTAS (Filtro desde 2022)
        print(
            "\n[3] 💸 Buscando Notas de Crédito Abiertas (CreditNotes - Desde 2022)..."
        )
        filtro_nc = f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open' and DocDate ge '2022-01-01'"
        ncs = conn.get(
            "CreditNotes",
            {"$filter": filtro_nc, "$select": "DocNum,DocDate,DocTotal,PaidToDate"},
        )
        lista_nc = ncs.get("value", []) if ncs else []
        print(f"   🔹 Total Notas de Crédito abiertas encontradas: {len(lista_nc)}")
        for nc in lista_nc:
            saldo = nc.get("DocTotal", 0) - nc.get("PaidToDate", 0)
            print(
                f"      - NC № {nc.get('DocNum')} | Fecha: {nc.get('DocDate')[:10]} | Saldo a Favor: (₡{abs(saldo):,.2f})"
            )

        # 4. ASIENTOS / PAGOS NO APLICADOS (PR en JDT1 desde 2022)
        print(
            "\n[4] 💰 Buscando Asientos o Pagos Recibidos a favor (PR en JDT1 - Desde 2022)..."
        )
        sql_pr = f"""
            SELECT T0."RefDate", T0."BaseRef" AS "DocNum", T0."TransType", T0."BalDueCred", T0."LineMemo"
            FROM "JDT1" T0
            WHERE T0."ShortName" = '{card_code}'
              AND T0."BalDueCred" > 0
              AND T0."RefDate" >= '20220101'
              AND T0."TransType" NOT IN ('13', '14', '30')
        """
        filas_pr = ejecutar_sql_sl(conn, sql_pr)
        print(f"   🔹 Total Líneas de asiento a favor encontradas: {len(filas_pr)}")
        for r in filas_pr:
            print(
                f"      - Asiento/Origen № {r.get('DocNum')} | Tipo Trans: {r.get('TransType')} | Monto: (₡{float(r.get('BalDueCred', 0)):,.2f}) | Detalle: {r.get('LineMemo')}"
            )

        print("\n" + "=" * 80)
        print("🏁 FIN DE LA AUDITORÍA")
        print("=" * 80)

    finally:
        conn.logout()


if __name__ == "__main__":
    # Si pasas un cliente por consola lo usa, si no, audita a C1061 por defecto
    cliente_a_revisar = sys.argv[1] if len(sys.argv) > 1 else "C1061"
    investigar_cliente(cliente_a_revisar)
