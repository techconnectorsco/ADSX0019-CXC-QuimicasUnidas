import sys, os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def moda_descuento_bp(grupos):
    valores = [
        float(g.get("DiscountPercentage", 0) or 0)
        for g in (grupos or [])
        if float(g.get("DiscountPercentage", 0) or 0) > 0
    ]
    if not valores:
        return 0.0
    conteo = Counter(valores)
    top = max(conteo.items(), key=lambda x: (x[1], x[0]))
    return top[0]


# Lo que Tania dice que DEBERÍA ser cada uno (para comparar a ojo)
ESPERADO = {
    "C0085": "25%",
    "C0084": "25%",
    "C0449": "25%",
    "C0456": "no le salía descuento",
    "C0461": "no le salía descuento",
    "C0088": "30%",
    "C0087": "30%",
    "C0476": "30%",
    "C0119": "20% (le salía 23%)",
    "C0118": "20% (le salía 23%)",
}

conn = ServiceLayerConnection(use_test_db=False)
if conn.login():
    for code, esperado in ESPERADO.items():
        bp = conn.get(f"BusinessPartners('{code}')", {})
        grupos = bp.get("DiscountGroups", []) if bp else []
        desc = moda_descuento_bp(grupos)
        valores = [
            float(g.get("DiscountPercentage", 0) or 0)
            for g in grupos
            if float(g.get("DiscountPercentage", 0) or 0) > 0
        ]
        conteo = dict(Counter(valores))
        print(f"{code}: moda = {desc}%  | Tania dice: {esperado}")
        print(
            f"        desglose: {conteo}  (grupos con desc: {len(valores)} de {len(grupos)})"
        )
    conn.logout()
