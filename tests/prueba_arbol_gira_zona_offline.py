# -*- coding: utf-8 -*-
r"""
Verificacion OFFLINE de los Pasos 2 y 3 del prefiltro. No se conecta a SAP:
reemplaza el mapa de ruteo, la UDT de zonas y la consulta del arbol viejo por
dobles, para probar que construir_arbol_gira_zona() arma bien el arbol y que
el cache hace lo que dice.

Lo que cubre:
  - que los ELEGIBLES salgan del mapa (criterio del PDF) y no de la ficha
  - que los NO ELEGIBLES sean los del arbol viejo que no aportan nada
  - los dos motivos: "otro_vendedor" (con el nombre de quien se lo lleva) y
    "sin_documentos"
  - la forma del JSON, que tiene que ser la que ya espera el frontend
  - el orden: clientes por nombre, zonas por cantidad de elegibles
  - la normalizacion de la zona y el grupo "sin zona"
  - el cache: que no vuelva a consultar, que ?refrescar lo tire, y que un
    fallo NO se cachee

Uso:  .\.venv\Scripts\python.exe tests/prueba_arbol_gira_zona_offline.py
"""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

import agentes

fallos = []
pruebas = 0


def check(nombre, condicion, detalle=""):
    global pruebas
    pruebas += 1
    if condicion:
        print("   OK   %s" % nombre)
    else:
        print("   FALLA %s   %s" % (nombre, detalle))
        fallos.append(nombre)


# ---------------------------------------------------------------------------
# Los dobles
# ---------------------------------------------------------------------------
# El agente que se prueba es el 7. El mapa dice quien aporta al PDF.
MAPA = {
    # Elegible y ademas estaba en el arbol viejo
    ("C0040", 7): {"docs": 10, "crc": 101005.0, "usd": 0.0,
                   "nombre": "ALMACEN LA ESPERANZA", "telefono": "2200-1111",
                   "zona": "6", "father_card": None},
    # Elegible pero el arbol viejo NO lo mostraba: su ficha es del 9.
    # Es el faltante que nadie habia reportado.
    ("C0042", 7): {"docs": 41, "crc": 286223.42, "usd": 10098.91,
                   "nombre": "EL COLONO AGROPECUARIO", "telefono": "2700-2222",
                   "zona": "06", "father_card": "C0041"},
    # Elegible en otra zona, para probar el orden de zonas
    ("C0050", 7): {"docs": 2, "crc": 5000.0, "usd": 0.0,
                   "nombre": "BAZAR EL SOL", "telefono": "", "zona": "2",
                   "father_card": None},
    # Elegible sin zona asignada
    ("C0090", 7): {"docs": 1, "crc": 900.0, "usd": 0.0,
                   "nombre": "ZZZ SIN ZONA S.A.", "telefono": "", "zona": "",
                   "father_card": None},
    # El mismo C0060 le pertenece al 9, no al 7: por eso el 7 lo vera en gris
    ("C0060", 9): {"docs": 3, "crc": 7000.0, "usd": 0.0,
                   "nombre": "FERRETERIA DEL VALLE", "telefono": "",
                   "zona": "6", "father_card": None},
}

# Lo que la pantalla ofrece HOY para el agente 7 (SalesPersonCode = 7)
ARBOL_VIEJO = [
    {"CardCode": "C0040", "CardName": "ALMACEN LA ESPERANZA", "U_ZGIRA": "6",
     "SalesPersonCode": 7, "Phone1": "2200-1111", "Phone2": "", "Cellular": "",
     "FatherCard": None},
    # Tiene documentos, pero rutean al 9: motivo "otro_vendedor"
    {"CardCode": "C0060", "CardName": "FERRETERIA DEL VALLE", "U_ZGIRA": "6",
     "SalesPersonCode": 7, "Phone1": "", "Phone2": "2500-3333",
     "Cellular": "", "FatherCard": None},
    # No tiene nada abierto: motivo "sin_documentos"
    {"CardCode": "C0037", "CardName": "ALMACEN COOPEVEGA", "U_ZGIRA": "06",
     "SalesPersonCode": 7, "Phone1": "", "Phone2": "", "Cellular": "8800-4444",
     "FatherCard": "C0036"},
]

ZONAS_UDT = [
    {"Code": "6", "Name": "SUR SHINDAIWA"},
    {"Code": "2", "Name": "COLONOS SUR"},
    {"Code": "15", "Name": "INACTIVAS"},
]

VENDEDORES = {
    6: {"nombre": "Siviany Gonzalez", "correo": "siviany@qu.cr"},
    7: {"nombre": "Berny Marin Chavez", "correo": "berny@qu.cr"},
    9: {"nombre": "Jose Chacon", "correo": "jose@qu.cr"},
}

llamadas = {"mapa": 0, "zonas": 0, "arbol_viejo": 0}
fallar_mapa = {"si": False}


def doble_mapa(conn, solo_vendedores=None, solo_clientes=None):
    llamadas["mapa"] += 1
    if fallar_mapa["si"]:
        raise RuntimeError("SAP no contesto (simulado)")
    return dict(MAPA)


def doble_paginado(conn, entidad, params, campo_orden="DocNum"):
    if entidad == "U_GIRAS":
        llamadas["zonas"] += 1
        return list(ZONAS_UDT)
    if entidad == "BusinessPartners":
        llamadas["arbol_viejo"] += 1
        return list(ARBOL_VIEJO)
    raise AssertionError("entidad inesperada: %s" % entidad)


agentes.obtener_mapa_ruteo_masivo = doble_mapa
agentes.obtener_todos_paginado = doble_paginado
agentes.obtener_vendedores = lambda conn: dict(VENDEDORES)


def limpiar():
    agentes.invalidar_cache_gira_zona()
    llamadas.update({"mapa": 0, "zonas": 0, "arbol_viejo": 0})


# ---------------------------------------------------------------------------
print("")
print("1. El arbol del agente 7")
print("")

limpiar()
arbol = agentes.construir_arbol_gira_zona(None, 7)

por_codigo = {}
for z in arbol["zonas"]:
    for c in z["clientes"]:
        por_codigo[c["cardCode"]] = c
for c in arbol["sinZona"]:
    por_codigo[c["cardCode"]] = c

check(
    "el agente viene con nombre y correo",
    arbol["agente"] == {"codigo": 7, "nombre": "Berny Marin Chavez",
                        "correo": "berny@qu.cr"},
    repr(arbol["agente"]),
)

# --- elegibles: salen del mapa, no de la ficha
check(
    "C0042 es elegible aunque el arbol viejo no lo mostraba",
    por_codigo.get("C0042", {}).get("elegible") is True,
    repr(por_codigo.get("C0042")),
)
check(
    "C0042 trae sus contadores del mapa",
    por_codigo["C0042"]["docs"] == 41
    and abs(por_codigo["C0042"]["crc"] - 286223.42) < 0.01
    and abs(por_codigo["C0042"]["usd"] - 10098.91) < 0.01,
    repr(por_codigo["C0042"]),
)
check(
    "C0040 es elegible y estaba en los dos",
    por_codigo.get("C0040", {}).get("elegible") is True,
)

# --- no elegibles y sus motivos
check(
    "C0060 es NO elegible para el 7",
    por_codigo.get("C0060", {}).get("elegible") is False,
    repr(por_codigo.get("C0060")),
)
check(
    "C0060 dice que sus documentos los tiene otro vendedor, con nombre",
    por_codigo["C0060"]["motivo"] == "otro_vendedor"
    and por_codigo["C0060"]["vendedorNombre"] == "Jose Chacon",
    repr(por_codigo["C0060"]),
)
check(
    "C0037 es NO elegible con motivo sin_documentos",
    por_codigo.get("C0037", {}).get("elegible") is False
    and por_codigo["C0037"]["motivo"] == "sin_documentos",
    repr(por_codigo.get("C0037")),
)
check(
    "un no elegible no inventa vendedorNombre",
    por_codigo["C0037"]["vendedorNombre"] is None,
)
check(
    "los no elegibles van en cero, no en None",
    por_codigo["C0037"]["docs"] == 0
    and por_codigo["C0037"]["crc"] == 0.0
    and por_codigo["C0037"]["usd"] == 0.0,
)

# --- la forma que el frontend ya espera
campos_frontend = {
    "cardCode", "cardName", "telefono", "zonaCode", "zonaNombre",
    "vendedorCode", "fatherCard",
}
faltantes = campos_frontend - set(por_codigo["C0040"].keys())
check(
    "cada cliente trae los campos que el frontend ya usaba",
    not faltantes,
    "faltan %s" % faltantes,
)
check(
    "y los campos nuevos del prefiltro",
    {"elegible", "docs", "crc", "usd"} <= set(por_codigo["C0040"].keys()),
)
check(
    "el arbol avisa que los montos son aproximados",
    arbol.get("montosAproximados") is True,
)
check(
    "trae los totales de elegibles y no elegibles",
    arbol["totalElegibles"] == 4 and arbol["totalNoElegibles"] == 2,
    "%r / %r" % (arbol["totalElegibles"], arbol["totalNoElegibles"]),
)

# --- zonas
check(
    "la zona '06' de C0042 se normalizo a '6' y cayo con los demas",
    por_codigo["C0042"]["zonaCode"] == "6",
)
check(
    "el nombre de la zona sale de la UDT",
    por_codigo["C0042"]["zonaNombre"] == "SUR SHINDAIWA",
    por_codigo["C0042"]["zonaNombre"],
)
zona6 = [z for z in arbol["zonas"] if z["zona"]["codigo"] == "6"]
check(
    "la zona 6 junta a los cuatro de esa zona",
    zona6 and len(zona6[0]["clientes"]) == 4,
    repr([len(z["clientes"]) for z in arbol["zonas"]]),
)
check(
    "y separa el conteo de elegibles del de no elegibles",
    zona6 and zona6[0]["totalElegibles"] == 2
    and zona6[0]["totalNoElegibles"] == 2,
    repr(zona6[0]) if zona6 else "",
)
check(
    "las zonas se ordenan por cantidad de elegibles",
    [z["zona"]["codigo"] for z in arbol["zonas"]] == ["6", "2"],
    repr([z["zona"]["codigo"] for z in arbol["zonas"]]),
)
check(
    "los clientes de una zona van ordenados por nombre",
    zona6 and [c["cardName"] for c in zona6[0]["clientes"]]
    == sorted(c["cardName"] for c in zona6[0]["clientes"]),
    repr([c["cardName"] for c in zona6[0]["clientes"]]) if zona6 else "",
)
check(
    "una zona de la UDT sin clientes no aparece",
    all(z["zona"]["codigo"] != "15" for z in arbol["zonas"]),
)

# --- sin zona
check(
    "el cliente sin U_ZGIRA cae en sinZona",
    [c["cardCode"] for c in arbol["sinZona"]] == ["C0090"],
    repr(arbol["sinZona"]),
)
check(
    "y se le pone una etiqueta legible",
    arbol["sinZona"][0]["zonaNombre"] == "Sin zona asignada",
)

# --- agente inexistente
try:
    agentes.construir_arbol_gira_zona(None, 99)
    check("un agente que no existe lanza ValueError", False, "no lanzo")
except ValueError:
    check("un agente que no existe lanza ValueError", True)


# ---------------------------------------------------------------------------
print("")
print("2. El cache")
print("")

limpiar()
agentes.construir_arbol_gira_zona(None, 7)
check(
    "la primera vez construye el mapa y lee las zonas",
    llamadas["mapa"] == 1 and llamadas["zonas"] == 1,
    repr(llamadas),
)

agentes.construir_arbol_gira_zona(None, 7)
check(
    "la segunda vez NO vuelve a consultar el mapa ni las zonas",
    llamadas["mapa"] == 1 and llamadas["zonas"] == 1,
    repr(llamadas),
)
check(
    "pero si vuelve a pedir el arbol viejo, que es por agente y es barato",
    llamadas["arbol_viejo"] == 2,
    repr(llamadas),
)

agentes.construir_arbol_gira_zona(None, 7, refrescar=True)
check(
    "refrescar=True fuerza el recalculo",
    llamadas["mapa"] == 2 and llamadas["zonas"] == 2,
    repr(llamadas),
)

# El TTL
limpiar()
agentes.construir_arbol_gira_zona(None, 7)
agentes._cache_mapa["cuando"] = time.time() - agentes.GIRA_ZONA_CACHE_TTL_SEGS - 1
agentes.construir_arbol_gira_zona(None, 7)
check(
    "cuando vence el TTL vuelve a construir",
    llamadas["mapa"] == 2,
    repr(llamadas),
)

# Un fallo NO se cachea: seria sostener el error 12 minutos
limpiar()
fallar_mapa["si"] = True
try:
    agentes.construir_arbol_gira_zona(None, 7)
    check("un fallo del mapa se propaga", False, "no lanzo")
except RuntimeError:
    check("un fallo del mapa se propaga", True)

fallar_mapa["si"] = False
agentes.construir_arbol_gira_zona(None, 7)
check(
    "y no quedo cacheado: el pedido siguiente lo vuelve a intentar",
    llamadas["mapa"] == 2,
    repr(llamadas),
)

print("")
print("=" * 70)
if fallos:
    print("FALLARON %d de %d" % (len(fallos), pruebas))
    for f in fallos:
        print("   - %s" % f)
    sys.exit(1)
print("PASARON LAS %d PRUEBAS" % pruebas)
