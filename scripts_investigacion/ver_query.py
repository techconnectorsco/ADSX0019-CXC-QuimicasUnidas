"""
ver_query_completo.py
Busca la consulta 398 iterando la lista completa para evitar el error de llave primaria compuesta.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

def main():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        print("❌ Error de conexión a SAP")
        return

    print("="*80)
    print("🔍 EXTRAYENDO SQL COMPLETO DE LA CONSULTA 398")
    print("="*80)

    try:
        skip = 0
        encontrado = False
        
        # Paginación para traer las consultas
        while True:
            res = conn.get("UserQueries", {"$skip": skip})
            
            if not res or 'value' not in res or len(res['value']) == 0:
                break
            
            for q in res['value']:
                if q.get('InternalKey') == 398:
                    nombre = q.get('QueryDescription', 'Sin Nombre')
                    sql_text = q.get('Query', q.get('QueryString', 'Sin Texto'))
                    
                    print(f"\n{'='*80}")
                    print(f"🔹 ID: 398 | Nombre: {nombre}")
                    print(f"{'='*80}\n")
                    print(sql_text)
                    print(f"\n{'='*80}")
                    
                    encontrado = True
                    break
            
            if encontrado:
                break
                
            skip += 20
            
            if skip > 5000:
                break
                
        if not encontrado:
            print("⚠️ No se encontró la consulta 398 en el recorrido.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.logout()

if __name__ == "__main__":
    main()