r"""
prueba_encabezado_zonas.py - Quimicas Unidas / ADSX0019

Nivel 1: NO toca SAP, NO envia nada, NO genera PDF. Solo ejercita la funcion
pura _encabezado_zonas_calculado() de agentes.py, la del hallazgo 11.

El caso 1 usa los datos REALES del PDF del 28/09/2026 22:20
(GIRA_7_Berny_Marin_Chavez_SELECCION_20260928_2220.pdf), que salio con 82
entradas y 833 caracteres en una sola linea.

Uso:  .\.venv\Scripts\python.exe tests\prueba_encabezado_zonas.py
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from agentes import GIRA_ZONA_MAX_CHARS_ZONAS, _encabezado_zonas_calculado

# Tal como los guarda datos_reporte["agente"]["zonas"]: un string por cliente,
# y cada string ya es la lista de destinos de ESE cliente unida por comas.
ZONAS_REALES_28_09 = {
    "5",
    "CARIARI, CARRILLO, CAÑAS",
    "MUELLE, JIMENEZ, SANTA ROSA",
    "TICABAN, GUAPILES",
    "CAÑAS, NICOYA, BATAAN",
    "JIMENEZ, MUELLE, LIMON, SIQUIRRES",
    "SANTA ROSA, PARRITA, GUACIMO",
    "TILARAN, CARIARI, GUAPILES",
    "PITAL, RIO FRIO, GUACIMO",
    "GUANACASTE, Guápiles, Jicaral, Puntarenas",
    "KG-SARDINAL, KG-SANTA CRUZ, KG-HUACAS, KG-NICOYA",
    "KG-COCO, KG-JICARAL, KG-SAN MARTIN, KG-PAQUERA",
    "LIBERIA, LIMON, NICARAGUA, PARRITA",
    "PUNTARENAS, RIO JIMENEZ, SIQUIRRES, RIOFRIO",
    "NICOYA CENTRO, BATAAN, LAVIRGEN, TICABAN",
    "CARIARI, LIMON, GUACIMO, LIBERIA",
    "HONECREEK, GUAPILES, BAGACES, GUAYABO",
    "JIMENEZ, SANTACRUZ, POCORA, SARAPIQUI",
    "RITA, SANTA CRUZ, SARAPIQUI, SIQUIRRES",
    "Santa Cruz, Guanacaste, TAMARINDO",
    "CAÑAS, NICOYA, BATAAN, FLAMINGO",
    "LIMON, SIQUIRRES, RIOFRIO, GUACIMO",
    "LIBERIA, TICABAN, POCORA, GUAPILES",
    "NICOYA CENTRO, GUAYABO",
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
r = _encabezado_zonas_calculado(ZONAS_REALES_28_09)
print(f"          -> {r!r}")
revisar("cabe en la banda", len(r) <= GIRA_ZONA_MAX_CHARS_ZONAS + 40, f"{len(r)} chars")
revisar("dice que es seleccion manual", r.startswith("Selección manual"))
revisar("dice cuantos destinos hay", "destinos" in r)
revisar("no repite GUAPILES", r.count("GUAPILES") <= 1)
revisar("no arrastra las 833 del PDF viejo", len(r) < 200)

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
r = _encabezado_zonas_calculado({"LIMON, GUAPILES", "GUAPILES, LIMON", "LIMON"})
print(f"          -> {r!r}")
revisar("GUAPILES una sola vez", r.count("GUAPILES") == 1)
revisar("LIMON una sola vez", r.count("LIMON") == 1)

# ── Caso 4: sin destinos ──────────────────────────────────────────────────
print("")
print("Caso 4 - ningun destino (documentos sin ShipToCode)")
for entrada in (set(), {""}, {" , "}, {"N/A"} - {"N/A"}):
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

print("")
print("=" * 78)
if fallos:
    print(f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    sys.exit(1)
print("Todos los chequeos pasaron.")
print("=" * 78)
