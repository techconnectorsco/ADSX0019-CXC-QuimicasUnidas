# -*- coding: utf-8 -*-
r"""
Verificacion OFFLINE del Paso 1. No se conecta a SAP: reemplaza
ejecutar_sql_sl por un doble que devuelve filas inventadas, para probar que
obtener_mapa_ruteo_masivo() aplica las mismas reglas que el PDF.

Tambien comprueba que extraer calcular_saldo_documento() no cambio el
resultado de procesar_documento(), comparandolo contra la logica vieja
reimplementada aqui tal como estaba antes del refactor.

Uso:  .\.venv\Scripts\python.exe tests/prueba_mapa_ruteo_offline.py
"""
import os
import sys

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
# 1. El refactor de procesar_documento no cambio el resultado
# ---------------------------------------------------------------------------
def procesar_documento_viejo(doc, tipo_origen):
    """La logica tal como estaba antes de extraer calcular_saldo_documento()."""
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
        return None

    tipo_doc = str(doc.get("U_TDOC", "") or "").strip().upper()
    if (
        tipo_origen == "creditnote"
        or tipo_doc in agentes.TIPOS_QUE_RESTAN
        or tipo_doc == "PR"
    ):
        saldo = -abs(saldo)
        total = -abs(total)
    return {"total": total, "saldo": saldo, "moneda": moneda}


print("")
print("1. procesar_documento() antes y despues del refactor")
print("")

monedas = [None, "", "CRC", "USD", "US$", "DOL", "EUR"]
tipos = [None, "", "FA", "NC", "PR", "n/c", " DEP ", "REM", "XX"]
montos = [
    (0, 0, 0, 0),
    (1000, 0, 0, 0),
    (1000.0, 1000.0, 0, 0),
    (1000.004, 1000.0, 0, 0),
    (0, 0, 500, 100),
    (250.5, 300.0, 1000, 0),
    (1479407.52, 0, 1479407.52, 0),
    (None, None, None, None),
    (0, 0, None, 7),
]

diferencias = 0
casos = 0
for moneda in monedas:
    for tipo in tipos:
        for (tfc, pfc, tl, pl) in montos:
            for origen in ("invoice", "creditnote"):
                doc = {
                    "DocCurrency": moneda,
                    "DocTotalFc": tfc,
                    "PaidToDateFC": pfc,
                    "DocTotal": tl,
                    "PaidToDate": pl,
                    "U_TDOC": tipo,
                    "DocNum": 1,
                    "ShipToCode": "X",
                    "DocDueDate": "2026-01-01",
                }
                casos += 1
                viejo = procesar_documento_viejo(doc, origen)
                nuevo = agentes.procesar_documento(doc, origen)

                if (viejo is None) != (nuevo is None):
                    diferencias += 1
                    print("      descarte distinto: %r %s" % (doc, origen))
                    continue
                if viejo is None:
                    continue
                for campo in ("total", "saldo", "moneda"):
                    if viejo[campo] != nuevo[campo]:
                        diferencias += 1
                        print(
                            "      %s: viejo=%r nuevo=%r en %r"
                            % (campo, viejo[campo], nuevo[campo], doc)
                        )

check(
    "%d combinaciones de documento dan el mismo saldo, total y moneda" % casos,
    diferencias == 0,
    "%d diferencias" % diferencias,
)


# ---------------------------------------------------------------------------
# 2. obtener_mapa_ruteo_masivo con filas inventadas
# ---------------------------------------------------------------------------
print("")
print("2. obtener_mapa_ruteo_masivo() sobre filas inventadas")
print("")

queries_vistos = []


def fila_doc(doc_entry, card, ship, moneda, total, pagado, tipo, u_codv, slp, zona="6"):
    """Una fila cruda como la que devuelve el SQL de OINV/ORIN."""
    es_usd = moneda in ("USD", "US$", "DOL")
    return {
        "DocEntry": doc_entry,
        "CardCode": card,
        "ShipToCode": ship,
        "DocCur": moneda,
        "DocTotal": 0 if es_usd else total,
        "PaidToDate": 0 if es_usd else pagado,
        "DocTotalFC": total if es_usd else 0,
        "PaidFC": pagado if es_usd else 0,
        "U_TDOC": tipo,
        "U_CODV": u_codv,
        "SlpCode": slp,
        "CardName": "CLIENTE " + card,
        "U_ZGIRA": zona,
        "FatherCard": None,
        "Phone1": "",
        "Phone2": "2222-0000",
        "Cellular": "8888-0000",
    }


FACTURAS = [
    # C0100: dos facturas CRC ruteadas al 7 por U_CODV, aunque su ficha dice 9
    fila_doc(1, "C0100", "JACO", "CRC", 100000, 0, "FA", 7, 9),
    fila_doc(2, "C0100", "JACO", "CRC", 50000, 20000, "FA", 7, 9),
    # C0100: una tercera factura que rutea al 6
    fila_doc(3, "C0100", "BELEN", "CRC", 7000, 0, "FA", 6, 9),
    # C0200: factura en dolares, direccion sin U_CODV -> cae al SlpCode 6
    fila_doc(4, "C0200", "SEDE", "USD", 1500.75, 500.75, "FA", None, 6),
    # C0200: U_CODV vacio (cadena en blanco) -> tambien cae al SlpCode
    fila_doc(5, "C0200", "SEDE", "USD", 10.0, 0, "FA", "   ", 6),
    # C0300: saldo despreciable, no entra
    fila_doc(6, "C0300", "SEDE", "CRC", 1000.002, 1000.0, "FA", 7, 7),
    # C0400: factura que un NC deja en cero exacto -> el par se descarta
    fila_doc(7, "C0400", "SEDE", "CRC", 80000, 0, "FA", 7, 7),
    # C0500: tipo que resta (DEP) aunque venga de una factura
    fila_doc(8, "C0500", "SEDE", "CRC", 30000, 0, "DEP", 9, 9),
    # duplicado del DocEntry 1: el join con CRD1 no debe contarlo dos veces
    fila_doc(1, "C0100", "JACO", "CRC", 100000, 0, "FA", 7, 9),
]

NOTAS = [
    # el NC que cancela exactamente la factura de C0400
    fila_doc(20, "C0400", "SEDE", "CRC", 80000, 0, "NC", 7, 7),
]

SALDOS_FAVOR = [
    # C0600 existe SOLO por un saldo a favor: queda negativo, SI sale en el PDF
    {"ShortName": "C0600", "FCCurrency": "CRC", "N": 3, "CRC": 45000.0, "USD": 0.0, "SlpCode": 7},
    # saldo a favor en dolares de un cliente que ya tiene facturas
    {"ShortName": "C0200", "FCCurrency": "USD", "N": 1, "CRC": 0.0, "USD": 25.0, "SlpCode": 6},
    # por debajo del umbral de 0.05: no entra
    {"ShortName": "C0700", "FCCurrency": "CRC", "N": 1, "CRC": 0.04, "USD": 0.0, "SlpCode": 7},
]

FICHAS_PR = [
    {
        "CardCode": "C0600",
        "CardName": "CLIENTE C0600",
        "SlpCode": 7,
        "U_ZGIRA": "06",
        "FatherCard": "C0059",
        "Phone1": "2100-1111",
        "Phone2": "",
        "Cellular": "",
    }
]


def ejecutar_sql_sl_doble(conn, sql, page_size=None, **kwargs):
    queries_vistos.append(sql)
    if '"OINV"' in sql:
        return list(FACTURAS)
    if '"ORIN"' in sql:
        return list(NOTAS)
    if '"JDT1"' in sql:
        return list(SALDOS_FAVOR)
    if '"OCRD" T0' in sql:
        return list(FICHAS_PR)
    raise AssertionError("query inesperado: %s" % sql)


agentes.ejecutar_sql_sl = ejecutar_sql_sl_doble

mapa = agentes.obtener_mapa_ruteo_masivo(None)
# Las consultas de ESTA llamada: mas abajo se invoca otra vez para probar
# el recorte por vendedor, y esa suma otras cuatro.
queries_primera = list(queries_vistos)
print("")

# --- ruteo por U_CODV, no por la ficha
check(
    "C0100 rutea al 7 por U_CODV aunque su ficha diga 9",
    ("C0100", 7) in mapa and ("C0100", 9) not in mapa,
)
check(
    "C0100 con el 7 suma 2 documentos y 130.000 CRC",
    mapa.get(("C0100", 7), {}).get("docs") == 2
    and abs(mapa[("C0100", 7)]["crc"] - 130000) < 0.001,
    repr(mapa.get(("C0100", 7))),
)
check(
    "el duplicado de DocEntry 1 no se conto dos veces",
    mapa.get(("C0100", 7), {}).get("docs") == 2,
)
check(
    "el mismo cliente aparece por separado para el 6",
    mapa.get(("C0100", 6), {}).get("docs") == 1
    and abs(mapa[("C0100", 6)]["crc"] - 7000) < 0.001,
)

# --- fallback al SlpCode
check(
    "C0200 cae al SlpCode 6 cuando la direccion no trae U_CODV",
    ("C0200", 6) in mapa,
)
check(
    "C0200 suma los dolares de sus 2 facturas menos el saldo a favor",
    mapa.get(("C0200", 6), {}).get("docs") == 3
    and abs(mapa[("C0200", 6)]["usd"] - (1000.0 + 10.0 - 25.0)) < 0.001,
    repr(mapa.get(("C0200", 6))),
)

# --- descartes
check("C0300 no entra: su saldo es despreciable", ("C0300", 7) not in mapa)
check(
    "C0400 no entra: factura y NC lo dejan en cero en las dos monedas",
    ("C0400", 7) not in mapa,
)
check("C0700 no entra: su saldo a favor es menor al umbral", ("C0700", 7) not in mapa)

# --- signo
check(
    "C0500 queda negativo porque su U_TDOC esta en TIPOS_QUE_RESTAN",
    abs(mapa.get(("C0500", 9), {}).get("crc", 0) + 30000) < 0.001,
    repr(mapa.get(("C0500", 9))),
)
check(
    "el NC de C0400 entro negativo (por eso cancela la factura)",
    ("C0400", 7) not in mapa,
)

# --- el cliente que existe solo por saldo a favor
check(
    "C0600 SI aparece aunque solo tenga saldo a favor",
    ("C0600", 7) in mapa,
)
check(
    "C0600 queda negativo y con sus 3 filas PR contadas",
    mapa.get(("C0600", 7), {}).get("docs") == 3
    and abs(mapa[("C0600", 7)]["crc"] + 45000) < 0.001,
    repr(mapa.get(("C0600", 7))),
)
check(
    "C0600 recupero su ficha con la cuarta consulta",
    mapa.get(("C0600", 7), {}).get("nombre") == "CLIENTE C0600"
    and mapa[("C0600", 7)]["father_card"] == "C0059",
)
check(
    "la zona '06' de C0600 quedo normalizada a '6'",
    mapa.get(("C0600", 7), {}).get("zona") == "6",
)

# --- ficha
check(
    "el telefono respeta el orden Phone1 > Phone2 > Cellular",
    mapa.get(("C0100", 7), {}).get("telefono") == "2222-0000",
    repr(mapa.get(("C0100", 7), {}).get("telefono")),
)

# --- recorte por vendedor
solo7 = agentes.obtener_mapa_ruteo_masivo(None, solo_vendedores=[7])
check(
    "solo_vendedores=[7] deja unicamente pares del 7",
    solo7 and all(v == 7 for (_c, v) in solo7),
)
check(
    "el recorte no cambia los descartes: C0400 sigue fuera",
    ("C0400", 7) not in solo7,
)

# --- los queries
print("")
print("3. Los queries que se mandaron")
print("")
check(
    "se mandaron 4 consultas por llamada",
    len(queries_primera) == 4,
    str(len(queries_primera)),
)
prohibido = [" * ", "SELECT *", "CASE ", "COALESCE", "ABS(", "UPPER(", "TRIM("]
malos = [p for q in queries_primera for p in prohibido if p in q]
check(
    "ningun query usa algo que el parser de /SQLQueries rechaza",
    not malos,
    repr(malos),
)
check(
    "las facturas no llevan filtro de fecha y las NC si",
    "DocDate" not in queries_primera[0] and "20220101" in queries_primera[1],
)

for q in queries_primera:
    print("")
    print("   " + " ".join(q.split()))

# --- la red de seguridad
print("")
print("4. Que truene en vez de devolver un universo incompleto")
print("")

# Las tres vacias
agentes.ejecutar_sql_sl = lambda conn, sql, page_size=None, **kwargs: []
try:
    agentes.obtener_mapa_ruteo_masivo(None)
    check("lanza RuntimeError con las tres consultas vacias", False, "no lanzo nada")
except RuntimeError:
    check("lanza RuntimeError con las tres consultas vacias", True)


# SOLO las facturas vacias. Este es el caso que se escapo el 01/10/2026 contra
# produccion: la consulta de facturas se cayo por timeout, volvio [], y el mapa
# se armo con notas de credito y saldos a favor nada mas. Como arbol habria
# escondido a casi todos los clientes con carga.
def solo_facturas_vacias(conn, sql, page_size=None, **kwargs):
    if '"OINV"' in sql:
        return []
    if '"ORIN"' in sql:
        return list(NOTAS)
    if '"JDT1"' in sql:
        return list(SALDOS_FAVOR)
    return list(FICHAS_PR)


agentes.ejecutar_sql_sl = solo_facturas_vacias
try:
    agentes.obtener_mapa_ruteo_masivo(None)
    check(
        "lanza RuntimeError si SOLO las facturas vuelven vacias",
        False,
        "armo el mapa con un universo incompleto",
    )
except RuntimeError:
    check("lanza RuntimeError si SOLO las facturas vuelven vacias", True)


# Y que el modo estricto llegue de verdad a ejecutar_sql_sl
estrictos = []
topes = []


def espia_estricto(conn, sql, page_size=None, **kwargs):
    estrictos.append(kwargs.get("estricto", False))
    topes.append(kwargs.get("timeout_segs"))
    return ejecutar_sql_sl_doble(conn, sql, page_size)


agentes.ejecutar_sql_sl = espia_estricto
agentes.obtener_mapa_ruteo_masivo(None)
check(
    "las tres consultas del universo van con estricto=True",
    estrictos[:3] == [True, True, True],
    repr(estrictos),
)
check(
    "y con el techo de espera largo, no con los 120s por defecto",
    topes[:3] == [agentes.GIRA_ZONA_SQL_TIMEOUT] * 3,
    repr(topes[:3]),
)

# ---------------------------------------------------------------------------
# 5. La regla de cuando reintentar
#
# Es la parte mas facil de romper "mejorandola". Un timeout NO se reintenta
# porque el query sigue corriendo del lado del Service Layer, y mandarle otro
# le apila una segunda consulta pesada encima. Se puso 300s y tres intentos el
# 01/10/2026 y fue peor: hay que dejarlo asi.
# ---------------------------------------------------------------------------
print("")
print("5. Cuando se reintenta y cuando no")
print("")

from modules.database.conexion import ErrorSqlSl


def contador_que_falla(tipo, veces=99):
    """Devuelve (funcion, lista_de_intentos) que falla con ese tipo."""
    intentos = []

    def fn(conn, sql, page_size=None, **kwargs):
        if '"OINV"' not in sql:
            return ejecutar_sql_sl_doble(conn, sql, page_size)
        intentos.append(1)
        if len(intentos) <= veces:
            raise ErrorSqlSl("simulado: %s" % tipo, tipo)
        return list(FACTURAS)

    return fn, intentos


# Un timeout: un solo intento, sin reintentar
fn, intentos = contador_que_falla("timeout")
agentes.ejecutar_sql_sl = fn
try:
    agentes.obtener_mapa_ruteo_masivo(None)
    check("un timeout no se reintenta", False, "no lanzo")
except ErrorSqlSl:
    check(
        "un timeout NO se reintenta (el query sigue corriendo en SAP)",
        len(intentos) == 1,
        "lo intento %d veces" % len(intentos),
    )

# Sesion muerta: se reintenta una vez
relogins = []


class ConnFalsa:
    def login(self):
        relogins.append(1)
        return True


fn, intentos = contador_que_falla("auth")
agentes.ejecutar_sql_sl = fn
try:
    agentes.obtener_mapa_ruteo_masivo(ConnFalsa())
    check("una sesion muerta se reintenta", False, "no lanzo")
except ErrorSqlSl:
    check(
        "una sesion muerta SI se reintenta, una vez",
        len(intentos) == 2,
        "lo intento %d veces" % len(intentos),
    )
    check("y reloguea antes de reintentar", len(relogins) == 1, repr(relogins))

# Rechazo del servidor: se reintenta, pero sin reloguear
relogins.clear()
fn, intentos = contador_que_falla("rechazo")
agentes.ejecutar_sql_sl = fn
try:
    agentes.obtener_mapa_ruteo_masivo(ConnFalsa())
    check("un rechazo se reintenta", False, "no lanzo")
except ErrorSqlSl:
    check(
        "un rechazo del servidor se reintenta una vez",
        len(intentos) == 2,
        "lo intento %d veces" % len(intentos),
    )
    check("y no reloguea, porque la sesion esta viva", not relogins, repr(relogins))

# Si el reintento funciona, el mapa sale bien
fn, intentos = contador_que_falla("auth", veces=1)
agentes.ejecutar_sql_sl = fn
mapa_reintento = agentes.obtener_mapa_ruteo_masivo(ConnFalsa())
check(
    "si el reintento funciona, el mapa sale completo igual",
    ("C0100", 7) in mapa_reintento,
    repr(sorted(mapa_reintento)[:3]),
)

check(
    "el techo de espera quedo bajo, no en los 300s que empeoraban todo",
    agentes.GIRA_ZONA_SQL_TIMEOUT <= 60,
    repr(agentes.GIRA_ZONA_SQL_TIMEOUT),
)

print("")
print("=" * 70)
if fallos:
    print("FALLARON %d de %d" % (len(fallos), pruebas))
    for f in fallos:
        print("   - %s" % f)
    sys.exit(1)
print("PASARON LAS %d PRUEBAS" % pruebas)
