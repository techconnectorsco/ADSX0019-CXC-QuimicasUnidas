"""
investigar_limite.py
Investigar por qué solo devuelve 20 registros y buscar cliente específico.
"""

import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*80)
    print("🔍 INVESTIGACIÓN: Límite de registros en Service Layer")
    print("="*80)

    # =================================================================
    # TEST 1: Buscar cliente específico que sabemos que existe
    # =================================================================
    print("\n📌 TEST 1: Buscar cliente C0243 (Marin Villegas)")
    
    cliente_especifico = conn.get("BusinessPartners('C0243')")
    
    if cliente_especifico:
        print(f"   ✅ ENCONTRADO!")
        print(f"   Código: {cliente_especifico.get('CardCode')}")
        print(f"   Nombre: {cliente_especifico.get('CardName')}")
        print(f"   Válido: {cliente_especifico.get('Valid')}")
        print(f"   Tipo: {cliente_especifico.get('CardType')}")
    else:
        print("   ❌ No encontrado directamente")
        
        # Intentar buscar por nombre
        print("\n   Buscando por nombre 'marin'...")
        busqueda = conn.get("BusinessPartners", {
            "$filter": "contains(CardName, 'MARIN') or contains(CardName, 'Marin')",
            "$select": "CardCode,CardName,Valid,CardType",
            "$top": 10
        })
        
        if busqueda and 'value' in busqueda:
            print(f"   Encontrados: {len(busqueda['value'])}")
            for c in busqueda['value']:
                print(f"      {c.get('CardCode')} | {c.get('CardName')} | Valid={c.get('Valid')}")

    # =================================================================
    # TEST 2: Probar diferentes valores de $top
    # =================================================================
    print("\n" + "="*80)
    print("📌 TEST 2: Probar diferentes valores de $top")
    print("="*80)
    
    for top_value in [10, 20, 50, 100, 500]:
        result = conn.get("BusinessPartners", {
            "$filter": "CardType eq 'cCustomer'",
            "$select": "CardCode",
            "$top": top_value
        })
        
        count = len(result['value']) if result and 'value' in result else 0
        print(f"   $top={top_value:4} → Devuelve: {count} registros")

    # =================================================================
    # TEST 3: Usar paginación con $skip
    # =================================================================
    print("\n" + "="*80)
    print("📌 TEST 3: Probar paginación con $skip")
    print("="*80)
    
    total_con_paginacion = 0
    skip = 0
    page_size = 20
    
    print(f"   Paginando de {page_size} en {page_size}...")
    
    while True:
        result = conn.get("BusinessPartners", {
            "$filter": "CardType eq 'cCustomer'",
            "$select": "CardCode,CardName",
            "$orderby": "CardCode",
            "$top": page_size,
            "$skip": skip
        })
        
        if not result or 'value' not in result or len(result['value']) == 0:
            break
        
        count = len(result['value'])
        total_con_paginacion += count
        
        # Mostrar primer y último de cada página
        primero = result['value'][0].get('CardCode')
        ultimo = result['value'][-1].get('CardCode')
        print(f"   Página {skip//page_size + 1}: {count} registros ({primero} ... {ultimo})")
        
        skip += page_size
        
        # Seguridad: máximo 50 páginas (1000 registros)
        if skip >= 1000:
            print("   ... (cortando en 1000 registros)")
            break
    
    print(f"\n   📊 TOTAL CON PAGINACIÓN: {total_con_paginacion} clientes")

    # =================================================================
    # TEST 4: Sin filtro de Valid
    # =================================================================
    print("\n" + "="*80)
    print("📌 TEST 4: Clientes sin filtro de Valid (activos + inactivos)")
    print("="*80)
    
    skip = 0
    total_todos = 0
    
    while True:
        result = conn.get("BusinessPartners", {
            "$filter": "CardType eq 'cCustomer'",
            "$select": "CardCode",
            "$top": 20,
            "$skip": skip
        })
        
        if not result or 'value' not in result or len(result['value']) == 0:
            break
        
        total_todos += len(result['value'])
        skip += 20
        
        if skip >= 2000:
            break
    
    print(f"   Total clientes (activos + inactivos): {total_todos}")

    # =================================================================
    # TEST 5: Buscar rango alto de códigos
    # =================================================================
    print("\n" + "="*80)
    print("📌 TEST 5: Buscar clientes con código > C0200")
    print("="*80)
    
    result = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and CardCode gt 'C0200'",
        "$select": "CardCode,CardName,Valid",
        "$orderby": "CardCode",
        "$top": 50
    })
    
    if result and 'value' in result:
        print(f"   Encontrados con código > C0200: {len(result['value'])}")
        for c in result['value'][:15]:
            print(f"      {c.get('CardCode')} | {c.get('CardName')[:40]} | Valid={c.get('Valid')}")
        if len(result['value']) > 15:
            print(f"      ... y {len(result['value']) - 15} más")

    conn.logout()
    print("\n" + "="*80)
    print("✅ Investigación completada")
    print("="*80)


if __name__ == "__main__":
    main()