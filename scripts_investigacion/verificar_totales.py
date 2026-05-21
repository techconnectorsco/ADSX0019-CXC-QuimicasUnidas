"""
verificar_totales.py
Verificar cuántos clientes realmente hay en la base de datos.
"""

import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*60)
    print("🔍 VERIFICANDO TOTALES REALES")
    print("="*60)

    # Método 1: Usar $count si está disponible
    print("\n📊 Intentando obtener conteo...")
    
    # Traer solo CardCode para contar (más liviano)
    clientes = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES'",
        "$select": "CardCode",
        "$top": 5000  # Poner un número alto
    })
    
    if clientes and 'value' in clientes:
        total = len(clientes['value'])
        print(f"\n   Total clientes activos: {total}")
        
        # Si son exactamente 20, probablemente hay un límite
        if total == 20:
            print("\n   ⚠️ El Service Layer puede tener un límite de 20 registros por defecto")
            print("   Verificando configuración...")
    
    # Probar con clientes con saldo
    con_saldo = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and CurrentAccountBalance gt 0",
        "$select": "CardCode,CardName,CurrentAccountBalance",
        "$top": 500
    })
    
    if con_saldo and 'value' in con_saldo:
        print(f"\n   Clientes con saldo > 0: {len(con_saldo['value'])}")
        
        total_cartera = sum(c.get('CurrentAccountBalance', 0) for c in con_saldo['value'])
        print(f"   Cartera total: {total_cartera:,.2f}")
        
        print(f"\n   Primeros 10 con saldo:")
        for c in con_saldo['value'][:10]:
            print(f"      {c.get('CardCode'):10} | {c.get('CardName')[:35]:35} | {c.get('CurrentAccountBalance'):>15,.2f}")

    # Verificar facturas abiertas
    facturas = conn.get("Invoices", {
        "$filter": "DocumentStatus eq 'bost_Open'",
        "$select": "DocNum,CardCode",
        "$top": 500
    })
    
    if facturas and 'value' in facturas:
        print(f"\n   Facturas abiertas: {len(facturas['value'])}")
        
        # Clientes únicos con facturas abiertas
        clientes_unicos = set(f.get('CardCode') for f in facturas['value'])
        print(f"   Clientes únicos con facturas: {len(clientes_unicos)}")

    conn.logout()
    print("\n✅ Verificación completada")


if __name__ == "__main__":
    main()