"""
main.py - Químicas Unidas
Archivo principal de la automatización CXC.

Este archivo orquesta todo el proceso:
1. Conecta a SAP
2. Obtiene datos (clientes, facturas)
3. Procesa la información
4. Genera PDFs
5. Envía correos

Uso:
    python main.py                      # Test de obtención de datos
    python main.py --proceso cxc        # Estados de cuenta (días 15 y 30)
    python main.py --proceso giras      # Reportes de gira (martes)
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database.conexion import ServiceLayerConnection


# =============================================================================
# FUNCIONES DE OBTENCIÓN DE DATOS
# =============================================================================

def obtener_clientes_con_saldo(conn: ServiceLayerConnection) -> List[Dict]:
    """
    Obtiene clientes activos con saldo pendiente.
    """
    clientes = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES' and CurrentAccountBalance gt 0",
        "$select": "CardCode,CardName,EmailAddress,Phone1,CurrentAccountBalance,SalesPersonCode,U_ZGIRA,U_NVT_CorreoEstadoCuenta,U_NTV_EnvioAutomatico,CreditLimit",
        "$orderby": "CardName",
        "$top": 500
    })
    
    if clientes and 'value' in clientes:
        return clientes['value']
    return []


def obtener_facturas_cliente(conn: ServiceLayerConnection, card_code: str) -> List[Dict]:
    """
    Obtiene facturas pendientes de un cliente.
    """
    facturas = conn.get("Invoices", {
        "$filter": f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
        "$select": "DocNum,DocDate,DocDueDate,DocTotal,PaidToDate,DocCurrency,U_TDOC,U_NUM_CONSE",
        "$orderby": "DocDueDate"
    })
    
    if facturas and 'value' in facturas:
        return facturas['value']
    return []


# =============================================================================
# FUNCIONES DE PROCESAMIENTO DE DATOS
# =============================================================================

def determinar_correo_cliente(cliente: Dict) -> str:
    """
    Determina qué correo usar para un cliente.
    Prioridad: U_NVT_CorreoEstadoCuenta > EmailAddress
    """
    correo_cxc = cliente.get('U_NVT_CorreoEstadoCuenta')
    if correo_cxc and correo_cxc.strip():
        return correo_cxc.strip()
    
    correo_principal = cliente.get('EmailAddress')
    if correo_principal and correo_principal.strip():
        return correo_principal.strip()
    
    return None


def procesar_factura(factura: Dict) -> Dict:
    """
    Procesa una factura y calcula campos adicionales.
    """
    hoy = datetime.now().date()
    
    total = factura.get('DocTotal', 0) or 0
    pagado = factura.get('PaidToDate', 0) or 0
    saldo = total - pagado
    
    fecha_vence_str = factura.get('DocDueDate', '')
    dias_vencido = 0
    esta_vencido = False
    
    if fecha_vence_str:
        try:
            fecha_vence = datetime.strptime(str(fecha_vence_str)[:10], '%Y-%m-%d').date()
            dias_vencido = (hoy - fecha_vence).days
            esta_vencido = dias_vencido > 0
        except:
            pass
    
    tipo_doc = factura.get('U_TDOC', '') or ''
    tipo_texto = traducir_tipo_documento(tipo_doc)
    
    moneda = factura.get('DocCurrency', 'COL')
    moneda_display = 'USD' if moneda in ['USD', 'US$', 'DOL'] else 'CRC'
    
    return {
        'doc_num': factura.get('DocNum'),
        'consecutivo_fe': factura.get('U_NUM_CONSE') or '',
        'tipo_codigo': tipo_doc,
        'tipo_texto': tipo_texto,
        'fecha': str(factura.get('DocDate', ''))[:10],
        'fecha_vence': str(fecha_vence_str)[:10] if fecha_vence_str else '',
        'total': total,
        'pagado': pagado,
        'saldo': saldo,
        'moneda': moneda_display,
        'dias_vencido': dias_vencido,
        'esta_vencido': esta_vencido
    }


def traducir_tipo_documento(tipo: str) -> str:
    """Traduce código de tipo de documento a texto legible."""
    traducciones = {
        'FRM': 'Factura',
        'FEC': 'Fact. Equipo',
        'NC': 'Nota Crédito',
        'N/C': 'Nota Crédito',
        'RC': 'Pago Recibido',
        'ND': 'Nota Débito',
        'N/D': 'Nota Débito',
    }
    return traducciones.get(tipo.upper() if tipo else '', tipo or 'Documento')


def separar_por_moneda(facturas: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Separa facturas por moneda."""
    colones = [f for f in facturas if f['moneda'] == 'CRC']
    dolares = [f for f in facturas if f['moneda'] == 'USD']
    return colones, dolares


# =============================================================================
# FUNCIÓN PRINCIPAL DE PRUEBA
# =============================================================================

def test_obtener_datos():
    """Test de obtención y procesamiento de datos."""
    print("="*70)
    print("🧪 TEST: Obtención y procesamiento de datos")
    print("="*70)
    
    conn = ServiceLayerConnection(use_test_db=False)
    
    if not conn.login():
        print("❌ Error de conexión")
        return
    
    try:
        # 1. Obtener clientes con saldo
        print("\n📋 Obteniendo clientes con saldo...")
        clientes = obtener_clientes_con_saldo(conn)
        print(f"   Encontrados: {len(clientes)}")
        
        if not clientes:
            print("   No hay clientes con saldo")
            return
        
        # 2. Tomar el primer cliente como ejemplo
        cliente = clientes[0]
        print(f"\n📌 Cliente ejemplo: {cliente.get('CardCode')} - {cliente.get('CardName')}")
        print(f"   Saldo total: {cliente.get('CurrentAccountBalance'):,.2f}")
        print(f"   Correo a usar: {determinar_correo_cliente(cliente) or 'SIN CORREO'}")
        
        # 3. Obtener sus facturas
        print(f"\n📄 Obteniendo facturas...")
        facturas_raw = obtener_facturas_cliente(conn, cliente.get('CardCode'))
        print(f"   Facturas pendientes: {len(facturas_raw)}")
        
        # 4. Procesar facturas
        print(f"\n🔄 Procesando facturas...")
        facturas_procesadas = [procesar_factura(f) for f in facturas_raw]
        
        # 5. Separar por moneda
        colones, dolares = separar_por_moneda(facturas_procesadas)
        print(f"   En colones (CRC): {len(colones)}")
        print(f"   En dólares (USD): {len(dolares)}")
        
        # 6. Mostrar detalle
        for moneda, facturas in [('USD', dolares), ('CRC', colones)]:
            if facturas:
                print(f"\n   📊 FACTURAS EN {moneda}:")
                print(f"   {'NUM':10} | {'TIPO':12} | {'VENCE':12} | {'SALDO':>12} | ESTADO")
                print("   " + "-"*60)
                for f in facturas:
                    estado = "🔴 VENCIDO" if f['esta_vencido'] else "🟢 Al día"
                    print(f"   {f['doc_num']:10} | {f['tipo_texto']:12} | {f['fecha_vence']:12} | {f['saldo']:>12,.2f} | {estado}")
                
                total = sum(f['saldo'] for f in facturas)
                print(f"   {'':10}   {'':12}   {'TOTAL:':12}   {total:>12,.2f}")
        
        print("\n" + "="*70)
        print("✅ Test completado - Datos listos para generar PDF")
        print("="*70)
        
    finally:
        conn.logout()


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    test_obtener_datos()