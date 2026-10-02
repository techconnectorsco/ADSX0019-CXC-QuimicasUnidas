# -*- coding: utf-8 -*-
r"""
Verificacion OFFLINE de los arreglos 2 y 3: que un fallo de SAP NO se reporte
como "no hay nada que cobrar", y que no se genere un PDF sobre SAP caido.

Reproduce el caso real del 01/10/2026. El usuario selecciono 8 clientes del
arbol nuevo (agente 7) y la pantalla dijo "3 de 8 entraron, 5 sin ningun
documento abierto en SAP: no hay nada que cobrar", nombrando a C0042 (41
documentos del agente 7), C0347 (22) y tres mas. Los logs mostraron que TODAS
las peticiones habian fallado con "500 Fail to connect to SLD".

Lo importante del caso, y por lo que un balde para excepciones no alcanzaba:
esos clientes **no tiraron excepcion**. conn.get() devuelve None ante un error
y obtener_todos_paginado lo trata igual que "no hay mas paginas", asi que
procesar_datos_cliente devolvio [] sin que nadie se enterara.

No toca SAP: reemplaza la conexion por un doble que falla a pedido.

Uso:  .\.venv\Scripts\python.exe tests/prueba_fallos_sap_offline.py
"""
import os
import sys

# El codigo de produccion imprime emojis y la consola de Windows viene en
# cp1252: sin esto el test truena en un print ajeno antes de probar nada.
# Mismo parche que usa api.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

import agentes

# Los PDFs de prueba van a una carpeta aparte, para no mezclarlos con los
# reportes de verdad de data/reportes_gira_zona.
CARPETA_PDF = os.path.join(RAIZ, "data", "pruebas_offline")
os.makedirs(CARPETA_PDF, exist_ok=True)
agentes.GIRA_ZONA_OUTPUT_DIR = CARPETA_PDF

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
# C0042 y C0347 son los grandes: tienen documentos de verdad. C0900 no tiene
# nada. Para los primeros se simula que SAP se cae; para el ultimo, que
# responde bien y de verdad no debe nada.
CAIDOS = {"C0042", "C0347"}
CON_DEUDA = {"C0040"}
SIN_DEUDA = {"C0900"}
TODOS = sorted(CAIDOS | CON_DEUDA | SIN_DEUDA)


class ConnFalsa:
    """Imita lo justo de ServiceLayerConnection, con fallos a pedido."""

    def __init__(self, caidos):
        self.caidos = set(caidos)
        self.logged_in = True
        self.pedidos = []

    def login(self):
        return True

    def logout(self):
        return True

    def get(self, endpoint, params=None):
        self.pedidos.append(endpoint)
        # Igual que el real: None ante cualquier fallo, dict si salio bien.
        for cc in self.caidos:
            if cc in str(endpoint) or cc in str(params):
                return None
        if endpoint.startswith("BusinessPartners("):
            return {"BPAddresses": []}
        return {"value": []}


def preparar(monkey_docs):
    """Instala los dobles de las funciones que hablan con SAP."""
    agentes.obtener_vendedores = lambda conn: {
        7: {"nombre": "Berny Marin Chavez", "correo": "berny@qu.cr"}
    }
    agentes.obtener_clientes_por_codigos = lambda conn, codigos, lote=15: [
        {"CardCode": c, "CardName": "CLIENTE " + c, "SalesPersonCode": 7}
        for c in codigos
    ]
    agentes.obtener_saldos_favor_masivo = lambda conn, codigos, lote=15: {}
    agentes.procesar_datos_cliente = monkey_docs

    # El PDF: un archivo de verdad pero vacio. Tiene que existir porque el
    # codigo despues lo renombra y lo mide; devolver None haria que la prueba
    # falle por el doble y no por lo que se esta probando.
    def pdf_falso(*a, **k):
        destino = os.path.join(CARPETA_PDF, "GIRA_PRUEBA.pdf")
        with open(destino, "wb") as f:
            f.write(b"%PDF-1.4 prueba")
        return destino

    agentes.generar_pdf_reporte_gira = pdf_falso


def docs_reales(conn, cliente, cache=None):
    """
    Lo que haria procesar_datos_cliente de verdad: consulta a SAP y, si la
    consulta falla, devuelve [] sin enterarse. Es el comportamiento exacto que
    produjo el bug.
    """
    cc = cliente["CardCode"]
    # Esto es lo que hace obtener_documentos_cliente por dentro
    if conn.get("Invoices", {"$filter": "CardCode eq '%s'" % cc}) is None:
        return []  # <- el fallo disfrazado de "no tiene documentos"
    if cc in CON_DEUDA:
        return [
            {
                "vendedor_asignado": 7,
                "cliente": {"codigo": cc, "nombre": "X", "zona_gira": "6"},
                "documentos": {"colones": [], "dolares": []},
                "totales": {"colones": 100.0, "dolares": 0.0},
            }
        ]
    return []


# ---------------------------------------------------------------------------
print("")
print("1. El caso real: SAP se cae consultando a los clientes grandes")
print("")

preparar(docs_reales)
conn = ConnFalsa(CAIDOS)
agentes.ServiceLayerConnection = lambda use_test_db=False: conn

res = agentes.ejecutar_gira_selectiva(
    agente_id=7, card_codes=TODOS, dry_run=True
)

detalle = res.get("omitidos_detalle") or {}

check(
    "los clientes que SAP no pudo responder van en su propio balde",
    sorted(detalle.get("no_evaluables") or []) == sorted(CAIDOS),
    repr(detalle.get("no_evaluables")),
)
check(
    "y NO se reportan como 'sin documentos' (era la mentira del 01/10/2026)",
    not (set(detalle.get("sin_documentos") or []) & CAIDOS),
    repr(detalle.get("sin_documentos")),
)
check(
    "el que de verdad no debe nada SI va en 'sin documentos'",
    sorted(detalle.get("sin_documentos") or []) == sorted(SIN_DEUDA),
    repr(detalle.get("sin_documentos")),
)
check(
    "el que tiene deuda entra al PDF igual",
    res.get("procesados") == 1,
    repr(res.get("procesados")),
)
check(
    "los no evaluables siguen contados en 'omitidos' (contrato de la web)",
    set(CAIDOS) <= set(res.get("omitidos") or []),
    repr(res.get("omitidos")),
)
check(
    "el mensaje avisa que hay que reintentar",
    "reintent" in (res.get("mensaje") or "").lower(),
    repr(res.get("mensaje")),
)

# ---------------------------------------------------------------------------
print("")
print("2. Arreglo 3: con SAP caido del todo, NO se genera PDF")
print("")

preparar(docs_reales)
conn = ConnFalsa(set(TODOS))  # se cae con todos
agentes.ServiceLayerConnection = lambda use_test_db=False: conn

res2 = agentes.ejecutar_gira_selectiva(
    agente_id=7, card_codes=TODOS, dry_run=True
)

check(
    "no se genera PDF cuando no se pudo evaluar a nadie",
    not res2.get("pdf"),
    repr(res2.get("pdf")),
)
check(
    "la corrida se reporta como NO ok",
    res2.get("ok") is False,
    repr(res2.get("ok")),
)
check(
    "el mensaje dice que SAP no respondio, no que no haya deuda",
    "no respond" in (res2.get("mensaje") or "").lower(),
    repr(res2.get("mensaje")),
)
check(
    "no hay nadie en 'sin documentos': no se sabe nada de nadie",
    not (res2.get("omitidos_detalle") or {}).get("sin_documentos"),
    repr((res2.get("omitidos_detalle") or {}).get("sin_documentos")),
)
check(
    "todos quedan como no evaluables",
    sorted((res2.get("omitidos_detalle") or {}).get("no_evaluables") or [])
    == sorted(TODOS),
    repr((res2.get("omitidos_detalle") or {}).get("no_evaluables")),
)

# ---------------------------------------------------------------------------
print("")
print("3. Sin fallos de SAP, nada cambia")
print("")

preparar(docs_reales)
conn = ConnFalsa(set())  # SAP sano
agentes.ServiceLayerConnection = lambda use_test_db=False: conn

res3 = agentes.ejecutar_gira_selectiva(
    agente_id=7, card_codes=TODOS, dry_run=True
)
d3 = res3.get("omitidos_detalle") or {}

check(
    "con SAP sano no hay no evaluables",
    not d3.get("no_evaluables"),
    repr(d3.get("no_evaluables")),
)
check(
    "los que no deben nada siguen en 'sin documentos', como siempre",
    set(CAIDOS | SIN_DEUDA) <= set(d3.get("sin_documentos") or []),
    repr(d3.get("sin_documentos")),
)
check(
    "el que debe entra al PDF",
    res3.get("procesados") == 1,
    repr(res3.get("procesados")),
)

# ---------------------------------------------------------------------------
print("")
print("4. El contador no se contagia entre clientes")
print("")

# Los hilos del pool se reusan: si el contador no se pone en cero al entrar,
# un cliente hereda los fallos del anterior que uso el mismo hilo y queda
# marcado como no evaluable sin motivo.
agentes._fallos_hilo.n = 99
preparar(docs_reales)
conn = ConnFalsa(set())
agentes.ServiceLayerConnection = lambda use_test_db=False: conn

res4 = agentes.ejecutar_gira_selectiva(
    agente_id=7, card_codes=sorted(CON_DEUDA), dry_run=True
)
check(
    "un contador sucio de antes no marca al cliente como no evaluable",
    not (res4.get("omitidos_detalle") or {}).get("no_evaluables"),
    repr((res4.get("omitidos_detalle") or {}).get("no_evaluables")),
)

# ---------------------------------------------------------------------------
print("")
print("5. Solo cuentan los endpoints que afectan plata o ruteo")
print("")

check(
    "Invoices cuenta",
    agentes._es_endpoint_critico("Invoices"),
)
check(
    "CreditNotes cuenta",
    agentes._es_endpoint_critico("CreditNotes"),
)
check(
    "BusinessPartners('C0042') cuenta (de ahi sale el ruteo por U_CODV)",
    agentes._es_endpoint_critico("BusinessPartners('C0042')"),
)
check(
    "PaymentTermsTypes NO cuenta: su fallo es cosmetico, no cambia el monto",
    not agentes._es_endpoint_critico("PaymentTermsTypes(3)"),
)

print("")
print("=" * 70)
if fallos:
    print("FALLARON %d de %d" % (len(fallos), pruebas))
    for f in fallos:
        print("   - %s" % f)
    sys.exit(1)
print("PASARON LAS %d PRUEBAS" % pruebas)
