import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection


def investigar():
    conn = ServiceLayerConnection(use_test_db=False)
    if conn.login():
        print("🔍 Consultando la moneda real de C0470...")
        res = conn.get(
            "BusinessPartners('C0470')",
            {"$select": "CardCode, CardName, Currency, CreditLimit"},
        )
        print(json.dumps(res, indent=4))
        conn.logout()


if __name__ == "__main__":
    investigar()
