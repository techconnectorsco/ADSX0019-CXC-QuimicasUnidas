"""
buscar_consultas.py
Busca consultas SQL guardadas en el Query Manager de SAP (UserQueries).
Sin restricción de campos para evitar errores de versión.
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
    print("🔍 BUSCANDO CONSULTAS EN QUERY MANAGER (UserQueries)")
    print("="*80)

    try:
        todas_consultas = []
        skip = 0
        
        # Paginación para traer las consultas sin el parámetro $select
        while True:
            res = conn.get("UserQueries", {"$skip": skip})
            
            if not res or 'value' not in res or len(res['value']) == 0:
                break
            
            todas_consultas.extend(res['value'])
            
            if len(res['value']) < 20:
                break
                
            skip += 20
            
            # Límite de seguridad
            if skip > 5000:
                break
            
        print(f"✅ Se encontraron {len(todas_consultas)} consultas en el Query Manager.")
        
        if todas_consultas:
            print(f"📌 Los campos reales que devuelve tu SAP son: {list(todas_consultas[0].keys())}")
        
        # Filtramos por las palabras clave
        palabras_clave = ['inventario', 'bodega', 'serie', 'consignacion', 'custodio', 'entre']
        
        encontradas = []
        for q in todas_consultas:
            # Buscamos en las propiedades más comunes (QueryDescription, Query, SqlText, etc.)
            nombre = str(q.get('QueryDescription', q.get('SqlName', ''))).lower()
            texto = str(q.get('Query', q.get('SqlText', ''))).lower()
            
            if any(p in nombre for p in palabras_clave) or any(p in texto for p in palabras_clave):
                encontradas.append(q)
                
        print(f"\n📊 CONSULTAS RELACIONADAS ENCONTRADAS ({len(encontradas)}):")
        print("-" * 80)
        for q in encontradas:
            internal_key = q.get('InternalKey', q.get('SqlCode', 'N/A'))
            query_desc = q.get('QueryDescription', q.get('SqlName', 'Sin Nombre'))
            query_text = q.get('Query', q.get('SqlText', 'Sin Texto'))
            
            print(f"🔹 InternalKey : {internal_key}")
            print(f"   Nombre      : {query_desc}")
            sql_text = str(query_text)[:150].replace('\n', ' ')
            print(f"   Query       : {sql_text}...")
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.logout()

if __name__ == "__main__":
    main()