"""
Script: buscar_vendedores.py
Ejecutar localmente para obtener la tabla de vendedores y su relación con zonas de gira.
"""
import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection

def main():
    conn = ServiceLayerConnection(use_test_db=False)  # PRODUCCIÓN

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*70)
    print("🔍 TABLA DE VENDEDORES/AGENTES EN SAP")
    print("="*70)
    
    # 1. SalesPersons - Vendedores
    print("\n📋 SalesPersons (Vendedores):")
    vendedores = conn.get("SalesPersons", {"$top": 50})
    vendedores_dict = {}
    
    if vendedores and 'value' in vendedores:
        print(f"   ✅ {len(vendedores['value'])} vendedores encontrados\n")
        
        activos = [v for v in vendedores['value'] if v.get('Active') == 'tYES']
        print(f"   ACTIVOS ({len(activos)}):")
        print("   " + "-"*65)
        print(f"   {'CODE':6} | {'NOMBRE':30} | {'EMAIL':25}")
        print("   " + "-"*65)
        
        for v in activos:
            code = v.get('SalesEmployeeCode')
            name = v.get('SalesEmployeeName') or ''
            email = v.get('Email') or v.get('E_Mail') or 'Sin email'
            vendedores_dict[code] = {'nombre': name, 'email': email}
            print(f"   {code:6} | {name[:30]:30} | {email[:25]}")
        
        # Mostrar todos los campos del primer registro
        print("\n\n   CAMPOS DISPONIBLES en SalesPersons:")
        print("   " + "-"*50)
        if vendedores['value']:
            for k, val in vendedores['value'][0].items():
                print(f"   {k}: {val}")
    
    # 2. Relación Zona - Vendedor - Clientes
    print("\n" + "="*70)
    print("📊 MAPEO: ZONA GIRA (U_ZGIRA) → VENDEDOR (SalesPersonCode)")
    print("="*70)
    
    todos = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES'",
        "$select": "CardCode,CardName,U_ZGIRA,SalesPersonCode,EmailAddress",
        "$top": 1000
    })
    
    if todos and 'value' in todos:
        total_clientes = len(todos['value'])
        print(f"\n   Total clientes activos consultados: {total_clientes}")
        
        # Agrupar por zona
        zonas = {}
        sin_zona = 0
        for c in todos['value']:
            gira = c.get('U_ZGIRA')
            vend = c.get('SalesPersonCode')
            
            if not gira:
                sin_zona += 1
                continue
                
            gira_str = str(gira)
            if gira_str not in zonas:
                zonas[gira_str] = {'vendedores': set(), 'clientes': 0, 'lista': []}
            zonas[gira_str]['clientes'] += 1
            zonas[gira_str]['lista'].append(c.get('CardCode'))
            if vend and vend != -1:
                zonas[gira_str]['vendedores'].add(vend)
        
        print(f"   Clientes SIN zona asignada: {sin_zona}")
        print(f"   Total zonas encontradas: {len(zonas)}")
        
        print("\n   ZONA | VENDEDOR(ES)        | # CLIENTES | EJEMPLOS")
        print("   " + "-"*70)
        for g in sorted(zonas.keys(), key=lambda x: int(x) if str(x).isdigit() else 999):
            vends = list(zonas[g]['vendedores'])
            cant = zonas[g]['clientes']
            ejemplos = ', '.join(zonas[g]['lista'][:3])
            print(f"   {g:4} | {str(vends):19} | {cant:10} | {ejemplos[:30]}")
        
        # Agrupar por vendedor para el reporte de giras
        print("\n" + "="*70)
        print("📊 RESUMEN POR VENDEDOR (para reporte de giras)")
        print("="*70)
        vendedores_map = {}
        for c in todos['value']:
            gira = c.get('U_ZGIRA')
            vend = c.get('SalesPersonCode')
            if vend and vend != -1:
                if vend not in vendedores_map:
                    vendedores_map[vend] = {'zonas': set(), 'clientes': 0}
                vendedores_map[vend]['clientes'] += 1
                if gira:
                    vendedores_map[vend]['zonas'].add(str(gira))
        
        print("\n   VENDEDOR | NOMBRE                    | ZONAS                  | # CLIENTES")
        print("   " + "-"*80)
        for v in sorted(vendedores_map.keys()):
            zonas_v = sorted(list(vendedores_map[v]['zonas']), key=lambda x: int(x) if x.isdigit() else 999)
            cant = vendedores_map[v]['clientes']
            nombre = vendedores_dict.get(v, {}).get('nombre', 'Desconocido')[:25]
            print(f"   {v:8} | {nombre:25} | {str(zonas_v):22} | {cant}")
        
        # Ejemplo de clientes de una zona específica
        print("\n" + "="*70)
        print("📋 EJEMPLO: Clientes de Zona 26 (primeros 10)")
        print("="*70)
        
        clientes_zona26 = conn.get("BusinessPartners", {
            "$filter": "U_ZGIRA eq '26' and CardType eq 'cCustomer' and Valid eq 'tYES'",
            "$select": "CardCode,CardName,EmailAddress,SalesPersonCode,CurrentAccountBalance",
            "$top": 10
        })
        
        if clientes_zona26 and 'value' in clientes_zona26:
            print(f"\n   {'CÓDIGO':10} | {'NOMBRE':35} | {'SALDO':>15} | VENDEDOR")
            print("   " + "-"*75)
            for c in clientes_zona26['value']:
                saldo = c.get('CurrentAccountBalance', 0)
                print(f"   {c.get('CardCode'):10} | {c.get('CardName')[:35]:35} | {saldo:>15,.2f} | {c.get('SalesPersonCode')}")
    
    conn.logout()
    print("\n✅ Consulta completada")


if __name__ == "__main__":
    main()