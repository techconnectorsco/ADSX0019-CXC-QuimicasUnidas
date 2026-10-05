import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
BASE = r"C:\Users\Admin\Documents\SoporteXperto\rpa_quimicas_unidas\ADSX0019-CXC-QuimicasUnidas"
os.chdir(BASE); sys.path.insert(0, BASE)
from modules.database.conexion import ServiceLayerConnection, ejecutar_sql_sl

ESPERADO = 1479407.52
SQL = ('SELECT T0."DocTotal" FROM "OINV" T0 '
       "WHERE T0.\"CardCode\" = 'C0104' AND T0.\"DocNum\" = '1074231'")

print("")
print("A. DENTRO DE UNA MISMA SESION, 6 veces el mismo query")
print("=" * 72)
conn = ServiceLayerConnection(use_test_db=False)
if conn.login():
    try:
        for i in range(6):
            f = ejecutar_sql_sl(conn, SQL)
            v = f[0].get("DocTotal") if f else None
            print(f"   intento {i+1}: {str(v):>13}  "
                  f"{'EXACTO' if v == ESPERADO else 'redondeado'}")
    finally:
        conn.logout()

print("")
print("B. SESIONES NUEVAS, una por vuelta")
print("=" * 72)
for i in range(6):
    c = ServiceLayerConnection(use_test_db=False)
    if not c.login():
        print(f"   sesion {i+1}: no se pudo conectar")
        continue
    try:
        f = ejecutar_sql_sl(c, SQL)
        v = f[0].get("DocTotal") if f else None
        print(f"   sesion {i+1}: {str(v):>13}  "
              f"{'EXACTO' if v == ESPERADO else 'redondeado'}")
    finally:
        c.logout()
