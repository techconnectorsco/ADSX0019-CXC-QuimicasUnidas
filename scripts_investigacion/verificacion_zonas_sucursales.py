"""
verificacion_zonas_sucursales.py - Quimicas Unidas
Cierra la ultima incognita previa al modulo "Giras por Zona".

NATURALEZA DEL SCRIPT
---------------------
SOLO LECTURA. Unicamente GET contra SAP Service Layer (mas /Login y /Logout,
que es como autentica el Service Layer). No escribe, no edita, no elimina,
no envia correo, no genera PDF, no toca SharePoint ni Supabase.
No importa agentes.py ni main.py.

PREGUNTA QUE RESPONDE
---------------------
Las verificaciones anteriores concluyeron que el arbol del modulo nuevo debe
incluir las sucursales (FatherCard != null), porque 50 de ellas cargan 599
documentos abiertos que la gira completa si reporta.

Queda una incognita: esas sucursales tienen U_ZGIRA asignada?

  - Si la tienen: caen dentro de una zona existente y el bucket
    "Sin zona asignada" de la interfaz sigue sobrando.
  - Si NO la tienen: el bucket vuelve a ser necesario, y hay que decidir
    si la sucursal hereda la zona de su cuenta padre.

Por eso el script tambien compara la zona de cada sucursal contra la de su
padre: si la herencia es viable, la interfaz puede resolver el nombre de zona
sin inventar una categoria aparte.

Genera: Verificacion_Zonas_Sucursales.txt (raiz del proyecto)

Uso:  python scripts_investigacion/verificacion_zonas_sucursales.py
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

REPORTE = os.path.join(BASE_DIR, "Verificacion_Zonas_Sucursales.txt")

LOTE = 15

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


def por_lotes_or(conn, entidad, codigos, campos, filtro_extra="", campo_orden="CardCode"):
    """Consulta una entidad filtrando por lista de CardCode, en lotes con OR."""
    encontrados = []
    total_lotes = (len(codigos) + LOTE - 1) // LOTE

    for i in range(0, len(codigos), LOTE):
        bloque = codigos[i : i + LOTE]
        print(f"   ... {entidad}: lote {(i // LOTE) + 1}/{total_lotes}", end="\r")
        filtro_or = " or ".join([f"CardCode eq '{c}'" for c in bloque])
        filtro = f"({filtro_or}){filtro_extra}"
        encontrados.extend(
            get_paginado(conn, entidad, {"$filter": filtro, "$select": campos}, campo_orden)
        )

    return encontrados


def zona_de(bp):
    return str(bp.get("U_ZGIRA") or "").strip()


def main():
    inicio = datetime.now()

    log("=" * 78)
    log("VERIFICACION - LAS SUCURSALES TIENEN ZONA (U_ZGIRA)?")
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
        # 1. Zonas, agentes y sucursales
        # ---------------------------------------------------------------------
        titulo("PASO 1 - Universo")

        zonas_raw = get_paginado(conn, "U_GIRAS", {}, "Code")
        mapa_zonas = {
            str(z.get("Code")): (z.get("Name") or f"Zona {z.get('Code')}") for z in zonas_raw
        }

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

        log("")
        log(f"   Zonas en U_GIRAS: {len(mapa_zonas)}")
        log(f"   Agentes con correo: {len(activos)}")
        log(f"   Sucursales de esos agentes (saldo cero): {len(objetivo)}")

        if not codigos:
            log("   Nada que revisar.")
            return

        # ---------------------------------------------------------------------
        # 2. Cuales cargan documentos abiertos (las que realmente importan)
        # ---------------------------------------------------------------------
        titulo("PASO 2 - Cuales sucursales cargan documentos abiertos")

        campos_doc = "DocEntry,CardCode,DocTotal,DocTotalFc,PaidToDate,PaidToDateFC,DocCurrency"
        log("")
        facturas = por_lotes_or(
            conn, "Invoices", codigos, campos_doc,
            " and DocumentStatus eq 'bost_Open'", "DocEntry",
        )
        notas = por_lotes_or(
            conn, "CreditNotes", codigos, campos_doc,
            " and DocumentStatus eq 'bost_Open' and DocDate ge '2022-01-01'", "DocEntry",
        )

        con_docs = set()
        for doc in facturas + notas:
            if doc.get("DocCurrency") in ["USD", "US$", "DOL"]:
                total = doc.get("DocTotalFc", 0) or doc.get("DocTotal", 0) or 0
                pagado = doc.get("PaidToDateFC", 0) or doc.get("PaidToDate", 0) or 0
            else:
                total = doc.get("DocTotal", 0) or 0
                pagado = doc.get("PaidToDate", 0) or 0
            if abs(total - pagado) >= 0.005:
                con_docs.add(doc.get("CardCode"))

        log("")
        log(f"   Sucursales con al menos un documento abierto: {len(con_docs)}")
        log(f"   Sucursales sin documentos (no aportan al PDF): {len(codigos) - len(con_docs)}")

        # ---------------------------------------------------------------------
        # 3. Cobertura de U_ZGIRA
        # ---------------------------------------------------------------------
        titulo("PASO 3 - Tienen zona asignada?")

        con_zona = [s for s in objetivo if zona_de(s)]
        sin_zona = [s for s in objetivo if not zona_de(s)]

        rel_con_zona = [s for s in objetivo if s["CardCode"] in con_docs and zona_de(s)]
        rel_sin_zona = [s for s in objetivo if s["CardCode"] in con_docs and not zona_de(s)]

        log("")
        log(f"   De las {len(objetivo)} sucursales:")
        log(f"      Con U_ZGIRA asignada : {len(con_zona)}")
        log(f"      Sin U_ZGIRA          : {len(sin_zona)}")
        log("")
        log(f"   De las {len(con_docs)} que SI cargan documentos (las que importan):")
        log(f"      Con U_ZGIRA asignada : {len(rel_con_zona)}")
        log(f"      Sin U_ZGIRA          : {len(rel_sin_zona)}")

        # ---------------------------------------------------------------------
        # 4. Herencia: el padre tiene zona?
        # ---------------------------------------------------------------------
        titulo("PASO 4 - Las sucursales sin zona pueden heredarla del padre?")

        if not sin_zona:
            log("")
            log("   No hay sucursales sin zona. La herencia no hace falta.")
            padres_zona = {}
        else:
            padres = sorted({s.get("FatherCard") for s in sin_zona if s.get("FatherCard")})
            log("")
            log(f"   Sucursales sin zona: {len(sin_zona)} (de {len(padres)} padres distintos)")
            log("   Consultando la zona de cada padre...")

            padres_raw = por_lotes_or(
                conn, "BusinessPartners", padres, "CardCode,CardName,U_ZGIRA"
            )
            padres_zona = {p["CardCode"]: p for p in padres_raw}

            heredan = 0
            huerfanas = 0
            log("")
            log(
                f"   {'SUCURSAL':<10} | {'NOMBRE':<32} | {'PADRE':<8} | "
                f"{'ZONA PADRE':<8} | DOCS"
            )
            log("   " + "-" * 82)
            for s in sorted(sin_zona, key=lambda x: x["CardCode"]):
                padre = s.get("FatherCard")
                zp = zona_de(padres_zona.get(padre, {}))
                if zp:
                    heredan += 1
                else:
                    huerfanas += 1
                marca = "SI" if s["CardCode"] in con_docs else "no"
                log(
                    f"   {s['CardCode']:<10} | {str(s.get('CardName', ''))[:32]:<32} | "
                    f"{str(padre):<8} | {(zp or '-'):<8} | {marca}"
                )

            log("")
            log(f"   Pueden heredar zona del padre : {heredan}")
            log(f"   El padre tampoco tiene zona   : {huerfanas}")

        # ---------------------------------------------------------------------
        # 5. Forma final del arbol
        # ---------------------------------------------------------------------
        titulo("PASO 5 - Forma final del arbol (con sucursales incluidas)")

        principales = get_paginado(
            conn,
            "BusinessPartners",
            {
                "$filter": "CardType eq 'cCustomer' and CurrentAccountBalance ne 0",
                "$select": "CardCode,CardName,U_ZGIRA,SalesPersonCode,FatherCard",
            },
            "CardCode",
        )

        arbol = defaultdict(lambda: defaultdict(int))
        for c in principales:
            v = c.get("SalesPersonCode")
            if v in activos:
                arbol[v][zona_de(c) or "(sin zona)"] += 1
        for s in objetivo:
            z = zona_de(s)
            if not z:
                z = zona_de(padres_zona.get(s.get("FatherCard"), {}))
            arbol[s["SalesPersonCode"]][z or "(sin zona)"] += 1

        log("")
        log("   Contando clientes con saldo + sucursales, con herencia de zona:")
        for code in sorted(arbol):
            total = sum(arbol[code].values())
            log("")
            log(f"   {activos[code]} (ID {code}): {total} clientes, {len(arbol[code])} zonas")
            for z in sorted(arbol[code], key=lambda x: -arbol[code][x]):
                nombre = "SIN ZONA ASIGNADA" if z == "(sin zona)" else mapa_zonas.get(z, "(no resuelto)")
                log(f"      Zona {z:<12} {nombre[:42]:<42} {arbol[code][z]} clientes")

        # ---------------------------------------------------------------------
        # 6. Conclusion
        # ---------------------------------------------------------------------
        titulo("CONCLUSION")

        hay_sin_zona = any("(sin zona)" in arbol[c] for c in arbol)

        log("")
        if not hay_sin_zona:
            log("   Todos los clientes del arbol quedan dentro de una zona.")
            log("   -> El bucket 'Sin zona asignada' de la interfaz NO hace falta.")
            log("   -> Mantener el campo sinZona en el tipo por seguridad, pero sin")
            log("      disenar interfaz alrededor de el.")
        else:
            log("   Quedan clientes sin zona incluso aplicando herencia del padre.")
            log("   -> El bucket 'Sin zona asignada' SI hace falta en la interfaz.")
            log("   -> Ver el detalle del PASO 5 para el conteo por agente.")

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
