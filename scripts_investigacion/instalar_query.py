"""
instalar_query.py
Registra el query de consignaciones optimizado para el Service Layer.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection

def instalar():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login(): return

    query_code = "RPA_REPORTE_CONSIGNACION"
    
    # SQL optimizado: Cambiamos SalesPersonCode por SlpCode (su nombre real en la BD)
    sql_text = """
    SELECT DISTINCT  
        T0."WhsCode",
        T2."CardCode", 
        T1."ItemCode", 
        T2."CardName", 
        T3."U_ZGIRA" AS "Zona", 
        T3."SlpCode" AS "SalesPersonCode",
        T2."ShipToCode", 
        T2."DocDate", 
        T2."DocNum",
        T4."Dscription",
        T1."SysSerial", 
        T1."SuppSerial" 
    FROM SRI1 T0  
    INNER JOIN OSRI T1 ON T0."SysSerial" = T1."SysSerial" and T0."ItemCode" = T1."ItemCode" AND T0."WhsCode"=T1."WhsCode"  
    INNER JOIN OWTR T2 on T2."DocNum"= T0."BaseNum" 
    INNER JOIN OCRD T3 ON T3."CardCode" = T2."CardCode" 
    INNER JOIN WTR1 T4 on T4."DocEntry" = T2."DocEntry" and T1."ItemCode"=T4."ItemCode" and T0."ItemCode" = T4."ItemCode" and T0."WhsCode"=T4."WhsCode"  
    WHERE T1."Status" = 0
    """

    payload = {
        "SqlCode": query_code,
        "SqlName": "RPA - Inventario Consignacion Agentes",
        "SqlText": sql_text
    }

    print(f"🚀 Registrando consulta {query_code}...")
    
    try:
        conn.session.delete(f"{conn.base_url}/SQLQueries('{query_code}')")
    except:
        pass

    res = conn.session.post(f"{conn.base_url}/SQLQueries", json=payload)
    
    if res.status_code in [201, 204]:
        print("✅ ¡Éxito! Consulta registrada permanentemente.")
    elif "already exists" in res.text:
        print("ℹ️ La consulta ya existe, no es necesario hacer nada.")
    else:
        print(f"❌ Error: {res.status_code} - {res.text}")
        conn.logout()
        return
        
    print("\n📥 Probando extracción (primeros registros)...")
    resultado = conn.get(f"SQLQueries('{query_code}')/List?$top=5")
    if resultado and 'value' in resultado:
        equipos = resultado['value']
        print(f"🎉 ¡ÉXITO! Se extrajeron los equipos correctamente.")
    else:
        print(f"❌ Error al ejecutar el Get: {resultado}")
    
    conn.logout()

if __name__ == "__main__":
    instalar()