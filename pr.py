import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

conn = ServiceLayerConnection(use_test_db=False)
if conn.login():
    try:
        # Traer un pago cualquiera y ver todas sus llaves
        pago = conn.get("IncomingPayments", {"$top": 1})["value"][0]
        print("\n".join(pago.keys()))
    finally:
        conn.logout()
