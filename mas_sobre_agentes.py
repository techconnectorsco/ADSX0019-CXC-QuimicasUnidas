"""
investigar_detalles_adicionales.py
Investigar bodegas de agentes, tabla de giras y nombres de zonas.
"""

import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection


def obtener_todos_paginado(conn, entidad, params, campo_orden):
    """Obtiene todos los registros con paginación."""
    todos = []
    skip = 0
    params["$top"] = 20
    params["$orderby"] = campo_orden
    
    while True:
        params["$skip"] = skip
        resultado = conn.get(entidad, params)
        if not resultado or 'value' not in resultado or len(resultado['value']) == 0:
            break
        todos.extend(resultado['value'])
        skip += 20
        if skip >= 2000:
            break
    return todos


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*90)
    print("🔍 INVESTIGACIÓN ADICIONAL")
    print("="*90)

    # =========================================================================
    # 1. TODAS LAS BODEGAS - Ver cuáles son de agentes
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 1: TODAS LAS BODEGAS (Warehouses)")
    print("="*90)
    
    bodegas = obtener_todos_paginado(conn, "Warehouses", {
        "$select": "WarehouseCode,WarehouseName,Inactive,Street,City"
    }, "WarehouseCode")
    
    print(f"\n   Total bodegas: {len(bodegas)}")
    print(f"\n   {'CÓDIGO':12} | {'NOMBRE':45} | {'ACTIVA':8}")
    print("   " + "-"*70)
    
    for b in bodegas:
        code = b.get('WarehouseCode', '')
        name = b.get('WarehouseName', '')[:45]
        activa = 'No' if b.get('Inactive') == 'tYES' else 'Sí'
        print(f"   {code:12} | {name:45} | {activa:8}")

    # =========================================================================
    # 2. TABLA @MGIRAS - Tabla de usuario de giras
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 2: TABLA @MGIRAS (Giras)")
    print("="*90)
    
    # Las tablas de usuario se acceden con el prefijo
    try:
        mgiras = conn.get("MGIRAS", {"$top": 20})
        if mgiras and 'value' in mgiras:
            print(f"\n   MGIRAS encontrada: {len(mgiras['value'])} registros")
            if mgiras['value']:
                print(f"   Campos: {list(mgiras['value'][0].keys())}")
                for g in mgiras['value'][:10]:
                    print(f"      {g}")
        else:
            print("   MGIRAS: Sin datos o no accesible directamente")
    except Exception as e:
        print(f"   MGIRAS: Error - {str(e)[:50]}")
    
    # Intentar con U_
    try:
        mgiras2 = conn.get("U_MGIRAS", {"$top": 20})
        if mgiras2:
            print(f"\n   U_MGIRAS: {mgiras2}")
    except:
        pass

    # =========================================================================
    # 3. BUSCAR DEFINICIÓN DE ZONAS - UserTablesMD
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 3: TABLAS DE USUARIO (UserTablesMD)")
    print("="*90)
    
    try:
        user_tables = conn.get("UserTablesMD", {"$top": 50})
        if user_tables and 'value' in user_tables:
            print(f"\n   Tablas de usuario encontradas: {len(user_tables['value'])}")
            for t in user_tables['value']:
                print(f"      {t.get('TableName')}: {t.get('TableDescription')}")
    except Exception as e:
        print(f"   Error: {str(e)[:50]}")

    # =========================================================================
    # 4. BUSCAR SI HAY CATÁLOGO DE ZONAS
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 4: BUSCAR CATÁLOGO DE ZONAS")
    print("="*90)
    
    # Intentar diferentes posibles tablas
    posibles = ["ZGIRAS", "GIRAS", "ZONAS", "Zones"]
    
    for tabla in posibles:
        try:
            result = conn.get(tabla, {"$top": 30})
            if result and 'value' in result:
                print(f"\n   {tabla}: {len(result['value'])} registros")
                for r in result['value'][:15]:
                    print(f"      {r}")
        except:
            pass

    # =========================================================================
    # 5. ValidValues del campo U_ZGIRA
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 5: VALORES VÁLIDOS DE U_ZGIRA")
    print("="*90)
    
    try:
        udf = conn.get("UserFieldsMD", {
            "$filter": "Name eq 'ZGIRA' and TableName eq 'OCRD'"
        })
        
        if udf and 'value' in udf:
            for campo in udf['value']:
                print(f"\n   Campo: {campo.get('Name')}")
                print(f"   Tabla: {campo.get('TableName')}")
                print(f"   Descripción: {campo.get('Description')}")
                
                # Obtener con ValidValuesMD
                campo_id = campo.get('FieldID')
                tabla = campo.get('TableName')
                
                # Intentar obtener el campo completo con sus valores
                campo_completo = conn.get(f"UserFieldsMD(TableName='{tabla}',FieldID={campo_id})")
                if campo_completo:
                    valores = campo_completo.get('ValidValuesMD', [])
                    if valores:
                        print(f"\n   VALORES VÁLIDOS (Zonas):")
                        print(f"   {'VALOR':6} | DESCRIPCIÓN")
                        print("   " + "-"*50)
                        for v in valores:
                            print(f"   {v.get('Value'):6} | {v.get('Description')}")
                    else:
                        print("   No tiene valores predefinidos (campo libre)")
    except Exception as e:
        print(f"   Error: {str(e)}")

    # =========================================================================
    # 6. INVENTARIO POR BODEGA - Equipos en consignación
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 6: EQUIPOS EN BODEGAS DE AGENTES (muestra)")
    print("="*90)
    
    # Buscar una bodega que parece de agente (ej: 0017 AGROLAND)
    try:
        # Items con stock en bodega específica
        items_bodega = conn.get("Items", {
            "$select": "ItemCode,ItemName,QuantityOnStock",
            "$filter": "QuantityOnStock gt 0",
            "$top": 10
        })
        
        if items_bodega and 'value' in items_bodega:
            print(f"\n   Items con stock: {len(items_bodega['value'])}")
            
        # Mejor buscar en ItemWarehouseInfoCollection
        # Esto muestra el stock por bodega
        item_ejemplo = conn.get("Items('HYW F2067')", {
            "$select": "ItemCode,ItemName,ItemWarehouseInfoCollection"
        })
        
        if item_ejemplo:
            print(f"\n   Ejemplo Item: {item_ejemplo.get('ItemCode')}")
            warehouses = item_ejemplo.get('ItemWarehouseInfoCollection', [])
            print(f"   Stock por bodega:")
            for w in warehouses:
                if w.get('InStock', 0) > 0:
                    print(f"      Bodega {w.get('WarehouseCode')}: {w.get('InStock')} unidades")
    except Exception as e:
        print(f"   Error: {str(e)[:80]}")

    # =========================================================================
    # 7. SERIES/EQUIPOS - Ver estructura completa
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 7: NÚMEROS DE SERIE - DETALLE")
    print("="*90)
    
    series = conn.get("SerialNumberDetails", {
        "$top": 5
    })
    
    if series and 'value' in series:
        print("\n   Ejemplo de SerialNumberDetails:")
        for s in series['value'][:3]:
            print(f"\n      ItemCode: {s.get('ItemCode')}")
            print(f"      SerialNumber: {s.get('SerialNumber')}")
            print(f"      MfrSerialNo: {s.get('MfrSerialNo')}")
            print(f"      Location: {s.get('Location')}")
            print(f"      Details: {s.get('Details')}")
            print(f"      Todos los campos: {list(s.keys())}")

    conn.logout()
    print("\n" + "="*90)
    print("✅ Investigación completada")
    print("="*90)


if __name__ == "__main__":
    main()