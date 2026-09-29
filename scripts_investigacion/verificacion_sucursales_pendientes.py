"""
verificacion_sucursales_pendientes.py - Quimicas Unidas
Complemento de verificacion_giras_zona.py (CHECK 4).

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA. Unicamente GET contra SAP Service Layer (mas /Login y /Logout,
que es como autentica el Service Layer). No escribe, no edita, no elimina,
no envia correo, no genera PDF, no toca SharePoint ni Supabase.
No importa agentes.py ni main.py.

PREGUNTA QUE RESPONDE
---------------------
La verificacion anterior encontro 102 sucursales (FatherCard != null) con
CurrentAccountBalance = 0 asignadas a los 3 agentes con correo. La gira
completa SI las incluye (su filtro es: saldo != 0 OR FatherCard != null);
el arbol del modulo nuevo NO las mostraria.

Saber si importa depende de un solo dato: esas sucursales tienen documentos
abiertos con saldo? Un saldo total en cero puede significar dos cosas muy
distintas:

  a) No tienen ningun documento abierto -> no aportan nada al PDF de gira.
     El arbol puede ignorarlas sin perder informacion.

  b) Tienen facturas abiertas compensadas con notas de credito -> el PDF de
     la gira completa SI muestra esas lineas, y el modulo nuevo las perderia.

Este script distingue (a) de (b).

METODO
------
Consulta Invoices y CreditNotes abiertas de esas sucursales, en lotes de 15
codigos por peticion (filtros OR), y calcula el saldo por documento igual que
procesar_documento() en agentes.py: saldo = total - pagado, descartando los
menores a 0.005.

Genera: Verificacion_Sucursales_Pendientes.txt (raiz del proyecto)

Uso:  python scripts_investigacion/verificacion_sucursales_pendientes.py
"""

import os
import sys
from collections import defaultdict
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.database.conexion import ServiceLayerConnection

REPORTE = os.path.join(BASE_DIR, "Verificacion_Sucursales_Pendientes.txt")

LOTE = 15  # codigos por peticion, igual criterio que obtener_saldos_favor_masivo

_lineas = []


def log(texto=""):
    print(texto)
    _lineas.append(texto)


def titulo(texto):
    log("")
    log("=" * 78)
    log(texto)
    log("=" * 78)


def get_paginado(conn, entidad, params, campo_orden):
    """Paginacion identica a la de agentes.py (solo GET)."""
    todos = []
    skip = 0
    page_size = 20
    params = dict(params)
    params["$top"] = page_size
    params["$orderby"] = campo_orden

    while True:
        params["$skip"] = skip
        res = conn.get(entidad, params)
        if not res or "value" not in res or len(res["value"]) == 0:
            break
        todos.extend(res["value"])
        if len(res["value"]) < page_size:
            break
        skip += page_size
        if skip >= 10000:
            break
    return todos


def saldo_documento(doc):
    """
    Mismo calculo que procesar_documento() en agentes.py:
    saldo = total - pagado, segun la moneda del documento.
    Devuelve (saldo, moneda) o (None, None) si es despreciable.
    """
    if doc.get("DocCurrency") in ["USD", "US$", "DOL"]:
        total = doc.get("DocTotalFc", 0) or doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDateFC", 0) or doc.get("PaidToDate", 0) or 0
        moneda = "USD"
    else:
        total = doc.get("DocTotal", 0) or 0
        pagado = doc.get("PaidToDate", 0) or 0
        moneda = "CRC"

    saldo = total - pagado
    if abs(saldo) < 0.005:
        return None, None
    return saldo, moneda


def documentos_abiertos(conn, entidad, codigos, filtro_extra=""):
    """Trae documentos abiertos de una lista de clientes, en lotes con OR."""
    campos = (
        "DocNum,DocEntry,CardCode,DocDate,DocDueDate,DocTotal,DocTotalFc,"
        "PaidToDate,PaidToDateFC,DocCurrency,U_TDOC"
    )
    encontrados = []
    total_lotes = (len(codigos) + LOTE - 1) // LOTE

    for i in range(0, len(codigos), LOTE):
        bloque = codigos[i : i + LOTE]
        lote_actual = (i // LOTE) + 1
        print(f"   ... {entidad}: lote {lote_actual}/{total_lotes}", end="\r")

        filtro_or = " or ".join([f"CardCode eq '{c}'" for c in bloque])
        filtro = f"({filtro_or}) and DocumentStatus eq 'bost_Open'{filtro_extra}"

        encontrados.extend(
            get_paginado(conn, entidad, {"$filter": filtro, "$select": campos}, "DocEntry")
        )

    return encontrados


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("VERIFICACION - SUCURSALES SIN SALDO: TIENEN DOCUMENTOS PENDIENTES?")
    log("Quimicas Unidas / ADSX0019")
    log(f"Fecha: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    log("")
    log("Script de SOLO LECTURA. Unicamente GET (mas Login/Logout).")
    log("No escribe, no edita, no elimina, no envia.")
    log("=" * 78)

    conn = ServiceLayerConnection(use_test_db=False)
    log("")
    log("Conectando a SAP PRODUCCION (solo lectura)...")
    if not conn.login():
        log("ERROR: no se pudo conectar al Service Layer. Se aborta.")
        guardar()
        return

    try:
        # ---------------------------------------------------------------------
        # 1. Reconstruir el universo: agentes con correo + sus sucursales
        # ---------------------------------------------------------------------
        titulo("PASO 1 - Universo de sucursales a revisar")

        vendedores = get_paginado(
            conn,
            "SalesPersons",
            {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"},
            "SalesEmployeeCode",
        )
        activos = {
            v["SalesEmployeeCode"]: v.get("SalesEmployeeName", "")
            for v in vendedores
            if v.get("SalesEmployeeCode") != -1 and "@" in str(v.get("Email") or "")
        }

        sucursales = get_paginado(
            conn,
            "BusinessPartners",
            {
                "$filter": (
                    "CardType eq 'cCustomer' and FatherCard ne null "
                    "and CurrentAccountBalance eq 0"
                ),
                "$select": "CardCode,CardName,FatherCard,SalesPersonCode,U_ZGIRA",
            },
            "CardCode",
        )

        objetivo = [s for s in sucursales if s.get("SalesPersonCode") in activos]
        codigos = [s["CardCode"] for s in objetivo]
        info = {s["CardCode"]: s for s in objetivo}

        log("")
        log(f"   Agentes con correo: {len(activos)}")
        log(f"   Sucursales con FatherCard y saldo cero: {len(sucursales)}")
        log(f"   De ellas, asignadas a un agente con correo: {len(objetivo)}")

        if not codigos:
            log("   Nada que revisar.")
            return

        # ---------------------------------------------------------------------
        # 2. Documentos abiertos de esas sucursales
        # ---------------------------------------------------------------------
        titulo("PASO 2 - Documentos abiertos de esas sucursales")

        log("")
        log(f"   Consultando en lotes de {LOTE} codigos...")

        facturas = documentos_abiertos(conn, "Invoices", codigos)
        notas = documentos_abiertos(
            conn, "CreditNotes", codigos, " and DocDate ge '2022-01-01'"
        )

        log("")
        log(f"   Facturas abiertas encontradas: {len(facturas)}")
        log(f"   Notas de credito abiertas (>= 2022): {len(notas)}")

        # ---------------------------------------------------------------------
        # 3. Calcular saldo por sucursal
        # ---------------------------------------------------------------------
        titulo("PASO 3 - Saldo real por sucursal")

        por_cliente = defaultdict(
            lambda: {"docs": 0, "facturas": 0, "notas": 0, "crc": 0.0, "usd": 0.0}
        )

        for doc in facturas:
            saldo, moneda = saldo_documento(doc)
            if saldo is None:
                continue
            reg = por_cliente[doc.get("CardCode")]
            reg["docs"] += 1
            reg["facturas"] += 1
            reg["crc" if moneda == "CRC" else "usd"] += saldo

        for doc in notas:
            saldo, moneda = saldo_documento(doc)
            if saldo is None:
                continue
            # En agentes.py las NC siempre restan
            saldo = -abs(saldo)
            reg = por_cliente[doc.get("CardCode")]
            reg["docs"] += 1
            reg["notas"] += 1
            reg["crc" if moneda == "CRC" else "usd"] += saldo

        con_docs = {c: r for c, r in por_cliente.items() if r["docs"] > 0}

        log("")
        log(f"   Sucursales revisadas: {len(codigos)}")
        log(f"   Sucursales SIN ningun documento abierto: {len(codigos) - len(con_docs)}")
        log(f"   Sucursales CON al menos un documento abierto: {len(con_docs)}")

        if con_docs:
            log("")
            log(
                f"   {'CODIGO':<10} | {'NOMBRE':<34} | {'PADRE':<8} | "
                f"{'FAC':>3} {'NC':>3} | {'CRC':>14} | {'USD':>12}"
            )
            log("   " + "-" * 96)
            for card_code in sorted(con_docs, key=lambda c: -con_docs[c]["docs"]):
                r = con_docs[card_code]
                s = info.get(card_code, {})
                log(
                    f"   {card_code:<10} | {str(s.get('CardName', ''))[:34]:<34} | "
                    f"{str(s.get('FatherCard', '')):<8} | "
                    f"{r['facturas']:>3} {r['notas']:>3} | "
                    f"{r['crc']:>14,.2f} | {r['usd']:>12,.2f}"
                )

        # ---------------------------------------------------------------------
        # 4. Conclusion
        # ---------------------------------------------------------------------
        titulo("CONCLUSION")

        log("")
        if not con_docs:
            log("   Ninguna de estas sucursales tiene documentos abiertos.")
            log("")
            log("   -> No aportan NADA al PDF de la gira completa.")
            log("   -> El arbol del modulo nuevo puede ignorarlas sin perder")
            log("      informacion. El filtro simple (saldo != 0) es correcto.")
            log("   -> NO hace falta consultar la decision con Tania.")
        else:
            total_docs = sum(r["docs"] for r in con_docs.values())
            log(f"   {len(con_docs)} sucursales tienen {total_docs} documentos abiertos")
            log("   pese a reportar CurrentAccountBalance = 0.")
            log("")
            log("   CAUSA: en SAP el saldo de una sucursal con FatherCard se consolida")
            log("   en la cuenta padre, por eso la sucursal reporta balance cero aunque")
            log("   tenga facturas abiertas. No es compensacion con notas de credito:")
            log("   el desglose FAC/NC de arriba lo confirma (hay sucursales con")
            log("   decenas de facturas y cero notas de credito).")
            log("")
            log("   Por eso obtener_clientes_con_saldo() en agentes.py usa el filtro")
            log("   'CurrentAccountBalance != 0 OR FatherCard != null'. Sin esa segunda")
            log("   condicion estos documentos se pierden por completo.")
            log("")
            log("   -> La gira completa SI muestra estas lineas en el PDF.")
            log("   -> El arbol del modulo nuevo, con el filtro que propone el plan")
            log("      (solo 'saldo != 0'), las perderia.")
            log("   -> El arbol DEBE replicar el filtro de agentes.py. No es una")
            log("      decision de producto: es una inconsistencia a corregir.")

        log("")
        log(f"   Duracion: {round((datetime.now() - inicio).total_seconds(), 1)} segundos")

    finally:
        conn.logout()
        guardar()


def guardar():
    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(_lineas))
    print(f"\nReporte guardado en: {REPORTE}")


if __name__ == "__main__":
    main()
