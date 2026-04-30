"""
investigar_agentes_zonas.py
Investigar la relación entre agentes, zonas y buscar inventario de bodegas.
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
        if skip >= 2000:  # Límite de seguridad
            break
    return todos


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*90)
    print("🔍 INVESTIGACIÓN: AGENTES, ZONAS E INVENTARIO DE BODEGAS")
    print("="*90)

    # =========================================================================
    # PARTE 1: VENDEDORES / AGENTES
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 1: VENDEDORES (SalesPersons) - TODOS LOS CAMPOS")
    print("="*90)
    
    vendedores = conn.get("SalesPersons", {"$top": 50})
    
    if vendedores and 'value' in vendedores:
        print(f"\n   Total: {len(vendedores['value'])}")
        
        # Mostrar TODOS los campos del primer vendedor
        print("\n   📋 CAMPOS DISPONIBLES EN SalesPersons:")
        if vendedores['value']:
            for k, v in vendedores['value'][0].items():
                print(f"      {k}: {v}")
        
        # Listar todos los vendedores
        print("\n   📋 LISTA DE VENDEDORES:")
        print(f"   {'CODE':6} | {'NOMBRE':30} | {'ACTIVO':8}")
        print("   " + "-"*50)
        for v in vendedores['value']:
            code = v.get('SalesEmployeeCode')
            name = v.get('SalesEmployeeName', '')
            active = 'Sí' if v.get('Active') == 'tYES' else 'No'
            print(f"   {code:6} | {name[:30]:30} | {active:8}")

    # =========================================================================
    # PARTE 2: BUSCAR TABLA DE ZONAS
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 2: BUSCAR TABLA DE ZONAS / GIRAS")
    print("="*90)
    
    # Intentar diferentes entidades que podrían tener las zonas
    posibles_entidades = [
        "SalesStages",
        "Territories",
        "SalesTaxAuthorities",
        "UserFieldsMD",
        "DistributionRules",
        "Projects",
    ]
    
    for entidad in posibles_entidades:
        print(f"\n   Probando {entidad}...")
        try:
            resultado = conn.get(entidad, {"$top": 5})
            if resultado and 'value' in resultado and len(resultado['value']) > 0:
                print(f"   ✅ {entidad}: {len(resultado['value'])} registros")
                print(f"      Campos: {list(resultado['value'][0].keys())[:8]}...")
            elif resultado and not 'value' in resultado:
                # Puede ser respuesta directa
                print(f"   ✅ {entidad}: Respuesta directa")
        except:
            print(f"   ❌ {entidad}: No accesible")

    # =========================================================================
    # PARTE 3: BUSCAR EN UserFieldsMD - Campos definidos por usuario
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 3: CAMPOS DE USUARIO (U_ZGIRA y similares)")
    print("="*90)
    
    # Buscar definición del campo U_ZGIRA
    udf = conn.get("UserFieldsMD", {
        "$filter": "contains(Name, 'ZGIRA') or contains(Name, 'GIRA') or contains(Name, 'ZONA')",
        "$top": 20
    })
    
    if udf and 'value' in udf:
        print(f"\n   Campos encontrados: {len(udf['value'])}")
        for campo in udf['value']:
            print(f"\n      Nombre: {campo.get('Name')}")
            print(f"      Tabla: {campo.get('TableName')}")
            print(f"      Descripción: {campo.get('Description')}")
            print(f"      Tipo: {campo.get('Type')}")
            # Si tiene valores válidos
            if campo.get('ValidValuesMD'):
                print(f"      Valores válidos:")
                for val in campo.get('ValidValuesMD', [])[:10]:
                    print(f"         {val.get('Value')}: {val.get('Description')}")
    else:
        print("   Buscando de otra forma...")
        
        # Intentar traer todos los UDF
        all_udf = obtener_todos_paginado(conn, "UserFieldsMD", {
            "$select": "Name,TableName,Description"
        }, "Name")
        
        gira_udf = [u for u in all_udf if 'GIRA' in (u.get('Name') or '').upper() or 'ZONA' in (u.get('Name') or '').upper()]
        print(f"\n   UDFs relacionados con GIRA/ZONA: {len(gira_udf)}")
        for u in gira_udf:
            print(f"      {u.get('TableName')}.{u.get('Name')}: {u.get('Description')}")

    # =========================================================================
    # PARTE 4: ANALIZAR U_ZGIRA EN CLIENTES
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 4: VALORES ÚNICOS DE U_ZGIRA EN CLIENTES")
    print("="*90)
    
    clientes = obtener_todos_paginado(conn, "BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and U_ZGIRA ne null",
        "$select": "CardCode,CardName,U_ZGIRA,SalesPersonCode"
    }, "CardCode")
    
    # Agrupar por zona
    zonas = {}
    for c in clientes:
        zona = str(c.get('U_ZGIRA', ''))
        vendedor = c.get('SalesPersonCode')
        
        if zona not in zonas:
            zonas[zona] = {'vendedores': set(), 'count': 0, 'ejemplo': ''}
        
        zonas[zona]['count'] += 1
        if not zonas[zona]['ejemplo']:
            zonas[zona]['ejemplo'] = c.get('CardName', '')[:30]
        if vendedor and vendedor != -1:
            zonas[zona]['vendedores'].add(vendedor)
    
    print(f"\n   Clientes con zona asignada: {len(clientes)}")
    print(f"   Zonas únicas encontradas: {len(zonas)}")
    
    print(f"\n   {'ZONA':6} | {'VENDEDOR(ES)':25} | {'CLIENTES':10} | EJEMPLO")
    print("   " + "-"*80)
    
    for z in sorted(zonas.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        vends = list(zonas[z]['vendedores'])
        count = zonas[z]['count']
        ejemplo = zonas[z]['ejemplo']
        print(f"   {z:6} | {str(vends):25} | {count:10} | {ejemplo}")

    # =========================================================================
    # PARTE 5: BUSCAR INVENTARIO / STOCK
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 5: BUSCAR INVENTARIO / STOCK / BODEGAS")
    print("="*90)
    
    entidades_inventario = [
        "Items",
        "Warehouses", 
        "InventoryGenEntries",
        "StockTransfers",
        "InventoryCountings",
        "BatchNumberDetails",
        "SerialNumberDetails",
    ]
    
    for entidad in entidades_inventario:
        print(f"\n   Probando {entidad}...")
        try:
            resultado = conn.get(entidad, {"$top": 3})
            if resultado and 'value' in resultado and len(resultado['value']) > 0:
                print(f"   ✅ {entidad}: Accesible")
                print(f"      Campos: {list(resultado['value'][0].keys())[:10]}...")
                
                # Si es Warehouses, mostrar las bodegas
                if entidad == "Warehouses":
                    print(f"\n      BODEGAS ENCONTRADAS:")
                    bodegas = conn.get("Warehouses", {"$top": 30})
                    if bodegas and 'value' in bodegas:
                        for b in bodegas['value']:
                            print(f"         {b.get('WarehouseCode')}: {b.get('WarehouseName')}")
                
        except Exception as e:
            print(f"   ❌ {entidad}: {str(e)[:50]}")

    # =========================================================================
    # PARTE 6: BUSCAR NÚMEROS DE SERIE (para inventario entre bodegas)
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 6: NÚMEROS DE SERIE / EQUIPOS EN CONSIGNACIÓN")
    print("="*90)
    
    # Los números de serie pueden estar asociados a agentes/bodegas
    series = conn.get("SerialNumberDetails", {
        "$top": 10,
        "$orderby": "ItemCode"
    })
    
    if series and 'value' in series:
        print(f"\n   SerialNumberDetails accesible: {len(series['value'])} registros de muestra")
        if series['value']:
            print(f"   Campos: {list(series['value'][0].keys())}")
    
    # =========================================================================
    # PARTE 7: MAPEO FINAL VENDEDOR -> ZONAS
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 7: MAPEO VENDEDOR → ZONAS (basado en clientes)")
    print("="*90)
    
    # Obtener nombres de vendedores
    vend_nombres = {}
    for v in vendedores.get('value', []):
        vend_nombres[v.get('SalesEmployeeCode')] = v.get('SalesEmployeeName', '')
    
    # Agrupar por vendedor
    vendedor_zonas = {}
    for c in clientes:
        vendedor = c.get('SalesPersonCode')
        zona = str(c.get('U_ZGIRA', ''))
        
        if vendedor and vendedor != -1:
            if vendedor not in vendedor_zonas:
                vendedor_zonas[vendedor] = {'zonas': set(), 'clientes': 0}
            vendedor_zonas[vendedor]['zonas'].add(zona)
            vendedor_zonas[vendedor]['clientes'] += 1
    
    print(f"\n   {'CODE':6} | {'VENDEDOR':30} | {'ZONAS':40} | CLIENTES")
    print("   " + "-"*90)
    
    for v in sorted(vendedor_zonas.keys()):
        nombre = vend_nombres.get(v, 'Desconocido')
        zonas_list = sorted(list(vendedor_zonas[v]['zonas']), key=lambda x: int(x) if x.isdigit() else 999)
        clientes_count = vendedor_zonas[v]['clientes']
        print(f"   {v:6} | {nombre[:30]:30} | {str(zonas_list):40} | {clientes_count}")

    conn.logout()
    
    print("\n" + "="*90)
    print("📋 RESUMEN DE HALLAZGOS")
    print("="*90)
    print("""
   1. VENDEDORES: Están en SalesPersons (ya los tenemos)
   
   2. ZONAS: El campo U_ZGIRA está en BusinessPartners (clientes)
      - Cada cliente tiene asignada UNA zona
      - La zona determina a qué vendedor pertenece
      - Podemos deducir el mapeo vendedor→zonas desde los clientes
   
   3. INVENTARIO BODEGAS: Buscar en SerialNumberDetails o InventoryGenEntries
      - Necesitamos ver cómo se asocian equipos a agentes
   
   4. REPORTE DE GIRAS: Es un consolidado de facturas por:
      - Vendedor (agente)
      - Zona
      - Clientes de esa zona con saldo pendiente
""")
    print("="*90)


if __name__ == "__main__":
    main()