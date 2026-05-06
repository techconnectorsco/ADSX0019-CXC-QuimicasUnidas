"""
investigar_inventario_sql.py
Usa el endpoint SQLQueries de Service Layer para obtener el inventario 
exacto en consignación (con series). Método reutilizable.
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
    print("🔍 OBTENIENDO INVENTARIO EN CONSIGNACIÓN")
    print("="*80)

    # Consulta corregida: SysNumber en T0
    sql_text = """
    SELECT 
        T0.WhsCode AS "Bodega", 
        T1.ItemCode AS "CodigoArticulo", 
        T2.ItemName AS "Descripcion", 
        T1.IntrSerial AS "NumeroSerie",
        T0.Quantity AS "Cantidad"
    FROM OSRQ T0 
    INNER JOIN OSRI T1 ON T0.ItemCode = T1.ItemCode AND T0.SysNumber = T1.SysSerial 
    INNER JOIN OITM T2 ON T0.ItemCode = T2.ItemCode 
    WHERE T0.Quantity > 0 AND (T0.WhsCode LIKE '00%' OR T0.WhsCode LIKE 'C0%')
    """

    # Nombre oficial y único para Químicas Unidas
    query_name = "QU_RptConsignacion"

    try:
        # 1. Intentamos registrarla (solo funcionará la primera vez)
        payload = {
            "SqlCode": query_name,
            "SqlName": "Inventario Consignacion QU",
            "SqlText": sql_text
        }
        url_post = f"{conn.base_url}/SQLQueries"
        creacion = conn.session.post(url_post, json=payload)
        
        if creacion.status_code in [200, 201]:
            print("✅ Consulta registrada exitosamente en SAP por primera vez.")
        elif creacion.status_code == 400 and "already exists" in creacion.text.lower():
            print("✅ La consulta ya existe en SAP. Reutilizando...")
        else:
            pass # Silencioso si hay otro detalle, intentaremos el GET de todos modos

        # 2. Ejecutar la consulta (GET puro, no invasivo)
        print("\n🚀 Obteniendo equipos en bodegas de clientes...")
        resultado = conn.get(f"SQLQueries('{query_name}')/List")
        
        if resultado and 'value' in resultado:
            equipos = resultado['value']
            print(f"\n📊 RESULTADOS OBTENIDOS: {len(equipos)} equipos\n")
            
            if equipos:
                print(f"| {'BODEGA':8} | {'CÓDIGO':15} | {'N. SERIE':20} | {'DESCRIPCIÓN'}")
                print("-" * 80)
                # Mostramos solo los primeros 20 para no saturar la consola
                for e in equipos[:20]:
                    bodega = e.get('Bodega', '')
                    codigo = e.get('CodigoArticulo', '')
                    serie = e.get('NumeroSerie', '')
                    desc = str(e.get('Descripcion', ''))[:35]
                    print(f"| {bodega:8} | {codigo:15} | {serie:20} | {desc}")
                
                if len(equipos) > 20:
                    print(f"... y {len(equipos) - 20} equipos más.")
            else:
                print("⚠️ No hay equipos con serie en esas bodegas en este momento.")
        else:
            print("❌ Error al ejecutar la consulta para traer los datos.")

    except Exception as e:
        print(f"\n❌ Error general: {e}")
        
    finally:
        print("\nℹ️ Finalizando proceso...")
        conn.logout()

if __name__ == "__main__":
    main()