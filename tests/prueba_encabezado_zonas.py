r"""
prueba_encabezado_zonas.py - Quimicas Unidas / ADSX0019

Nivel 1: NO toca SAP, NO envia nada, NO genera PDF. Solo ejercita las funciones
puras _encabezado_zonas_calculado() y _normalizar_destino() de agentes.py, las
del hallazgo 11.

El caso 1 usa los datos REALES del PDF del 28/09/2026 22:20
(GIRA_7_Berny_Marin_Chavez_SELECCION_20260928_2220.pdf), que salio con 82
entradas y 833 caracteres en una sola linea.

OJO con el contrato: _encabezado_zonas_calculado() recibe los destinos YA
SEPARADOS, uno por elemento. Antes recibia el `zona_gira` de cada cliente (la
lista de destinos de ese cliente unida por ", ") y los partia por coma adentro,
lo que rompia todo destino con coma propia. Ver el caso 6.

Uso:  .\.venv\Scripts\python.exe tests\prueba_encabezado_zonas.py
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from agentes import (
    GIRA_ZONA_MAX_CHARS_ZONAS,
    _encabezado_zonas_calculado,
    _normalizar_destino,
)

# Los destinos del 28/09, uno por elemento, tal como los junta ahora el
# llamador desde los documentos. "Jicaral, Puntarenas" entra ENTERO: es un solo
# destino que lleva coma adentro.
DESTINOS_REALES_28_09 = {
    "5",
    "BAGACES",
    "BATAAN",
    "CARIARI",
    "CARRILLO",
    "CAÑAS",
    "FLAMINGO",
    "GUACIMO",
    "GUANACASTE",
    "GUAPILES",
    "GUAYABO",
    "Guanacaste",
    "Guápiles",
    "HONECREEK",
    "JIMENEZ",
    "Jicaral, Puntarenas",
    "KG-COCO",
    "KG-HUACAS",
    "KG-JICARAL",
    "KG-NICOYA",
    "KG-PAQUERA",
    "KG-SAN MARTIN",
    "KG-SANTA CRUZ",
    "KG-SARDINAL",
    "LAVIRGEN",
    "LIBERIA",
    "LIMON",
    "MUELLE",
    "NICARAGUA",
    "NICOYA",
    "NICOYA CENTRO",
    "PARRITA",
    "PITAL",
    "POCORA",
    "PUNTARENAS",
    "RIO FRIO",
    "RIO JIMENEZ",
    "RIOFRIO",
    "RITA",
    "SANTA CRUZ",
    "SANTA ROSA",
    "SANTACRUZ",
    "SARAPIQUI",
    "SIQUIRRES",
    "Santa Cruz",
    "TAMARINDO",
    "TICABAN",
    "TILARAN",
}

fallos = []


def revisar(nombre, condicion, detalle=""):
    print(f"   {'[OK]' if condicion else '[FALLA]'} {nombre}")
    if detalle:
        print(f"          {detalle}")
    if not condicion:
        fallos.append(nombre)


print("=" * 78)
print("HALLAZGO 11 - encabezado de ZONAS con seleccion mixta")
print("=" * 78)

# ── Caso 1: la seleccion grande del 28/09 ─────────────────────────────────
print("")
print("Caso 1 - los 43 clientes del 28/09 (el que salio de 833 caracteres)")
r = _encabezado_zonas_calculado(DESTINOS_REALES_28_09)
print(f"          -> {r!r}")
revisar("cabe en la banda", len(r) <= GIRA_ZONA_MAX_CHARS_ZONAS + 40, f"{len(r)} chars")
revisar("dice que es seleccion manual", r.startswith("Selección manual"))
revisar("dice cuantos destinos hay", "destinos" in r)
revisar("no repite GUAPILES", r.count("GUAPILES") <= 1)
revisar("no arrastra las 833 del PDF viejo", len(r) < 200)
# 48 entradas menos las 3 que son la misma escritas distinto: GUAPILES/Guápiles,
# GUANACASTE/Guanacaste y SANTA CRUZ/Santa Cruz.
revisar("cuenta 45 destinos, no 48", "45 destinos" in r, r)

# ── Caso 2: pocas zonas, se listan ────────────────────────────────────────
print("")
print("Caso 2 - tres clientes de tres destinos: la lista si cabe")
r = _encabezado_zonas_calculado({"LIMON", "GUAPILES", "CARIARI"})
print(f"          -> {r!r}")
revisar("lista los tres", all(z in r for z in ("LIMON", "GUAPILES", "CARIARI")))
revisar("en orden alfabetico", r.index("CARIARI") < r.index("GUAPILES") < r.index("LIMON"))
revisar("no habla de conteo", "destinos" not in r)

# ── Caso 3: duplicados entre clientes ─────────────────────────────────────
print("")
print("Caso 3 - dos clientes que comparten destinos: se deduplica")
r = _encabezado_zonas_calculado({"LIMON", "GUAPILES"})
print(f"          -> {r!r}")
revisar("GUAPILES una sola vez", r.count("GUAPILES") == 1)
revisar("LIMON una sola vez", r.count("LIMON") == 1)

# ── Caso 4: sin destinos ──────────────────────────────────────────────────
print("")
print("Caso 4 - ningun destino (documentos sin ShipToCode)")
for entrada in (set(), {""}, {"  "}, {"N/A"} - {"N/A"}, None):
    r = _encabezado_zonas_calculado(entrada)
    print(f"          {entrada!r} -> {r!r}")
    revisar(f"cae en 'Selección manual' con {entrada!r}", r == "Selección manual")

# ── Caso 5: acentos y eñes sobreviven ─────────────────────────────────────
print("")
print("Caso 5 - acentos y eñes")
r = _encabezado_zonas_calculado({"CAÑAS", "Guápiles"})
print(f"          -> {r!r}")
revisar("mantiene CAÑAS", "CAÑAS" in r)
revisar("mantiene Guápiles", "Guápiles" in r)

# ── Caso 6: un destino con coma propia NO se parte ────────────────────────
# El bug del 02/10/2026: "Jicaral, Puntarenas" es UN destino. Partido por coma
# contaba dos, y el encabezado anunciaba 15 destinos donde habia 14.
print("")
print("Caso 6 - un destino con coma adentro cuenta como uno")
r = _encabezado_zonas_calculado({"Jicaral, Puntarenas"})
print(f"          -> {r!r}")
revisar("queda entero", "Jicaral, Puntarenas" in r)
revisar("no habla de conteo con un solo destino", "destinos" not in r)

print("")
print("Caso 6b - los 14 destinos reales de la corrida del 02/10/2026")
DESTINOS_REALES_02_10 = {
    "LIMON",
    "Guápiles",
    "GUANACASTE",
    "Jicaral, Puntarenas",
    "JACO COSTANERA",
    "JACO",
    "GUAPILES",
    "SANTA ROSA",
    "CAÑAS",
    "JIMENEZ",
    "MUELLE",
    "TICABAN",
    "NICARAGUA",
    "GUACIMO",
}
r = _encabezado_zonas_calculado(DESTINOS_REALES_02_10)
print(f"          -> {r!r}")
# 14 entradas, y GUAPILES/Guápiles son el mismo lugar -> 13 destinos reales.
revisar("cuenta 13 destinos, no 15", "13 destinos" in r, r)

# ── Caso 7: la llave de normalizacion ─────────────────────────────────────
print("")
print("Caso 7 - _normalizar_destino()")
revisar("tildes fuera", _normalizar_destino("Guápiles") == "GUAPILES")
revisar(
    "GUAPILES y Guápiles dan la misma llave",
    _normalizar_destino("GUAPILES") == _normalizar_destino("Guápiles"),
)
revisar("espacios colapsados", _normalizar_destino("  SANTA   ROSA ") == "SANTA ROSA")
revisar(
    "la coma interna se respeta",
    _normalizar_destino("Jicaral, Puntarenas") == "JICARAL, PUNTARENAS",
)
revisar(
    "SANTA CRUZ y SANTACRUZ NO son el mismo destino",
    _normalizar_destino("SANTA CRUZ") != _normalizar_destino("SANTACRUZ"),
)

print("")
print("=" * 78)
if fallos:
    print(f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    sys.exit(1)
print("Todos los chequeos pasaron.")
print("=" * 78)
