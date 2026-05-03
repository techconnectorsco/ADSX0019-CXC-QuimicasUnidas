"""
investigar_campos_email.py
Investigar campos de comentarios y validar flujo de envío de correos.
"""

import sys
import re
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection


def extraer_correos_texto(texto: str) -> list:
    """
    Extrae correos electrónicos de un texto usando regex.
    """
    if not texto:
        return []
    
    # Patrón para encontrar emails
    patron = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    correos = re.findall(patron, texto)
    
    # Limpiar y retornar únicos
    return list(set([c.lower().strip() for c in correos]))


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*90)
    print("🔍 INVESTIGACIÓN: CAMPOS PARA ENVÍO DE CORREOS CXC")
    print("="*90)

    # =========================================================================
    # 1. Ver TODOS los campos disponibles en BusinessPartners
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 1: CAMPOS RELACIONADOS CON COMENTARIOS EN BusinessPartners")
    print("="*90)
    
    # Obtener un cliente de ejemplo con todos los campos
    cliente = conn.get("BusinessPartners('C0006')")
    
    if cliente:
        print("\n   Campos que podrían tener comentarios:")
        campos_interes = [
            'Notes', 'FreeText', 'Remarks', 'Comments', 
            'AdditionalID', 'UnifiedFederalTaxID',
            'U_NVT_CorreoEstadoCuenta', 'U_NTV_EnvioAutomatico',
            'EmailAddress', 'E_Mail'
        ]
        
        for campo in campos_interes:
            valor = cliente.get(campo)
            if valor:
                print(f"\n      {campo}:")
                print(f"         {str(valor)[:200]}")
        
        # Buscar cualquier campo que contenga @ (posible email)
        print("\n   Campos con posibles correos (@):")
        for key, value in cliente.items():
            if value and isinstance(value, str) and '@' in value:
                print(f"      {key}: {value[:100]}")

    # =========================================================================
    # 2. Revisar campos U_ definidos por usuario en OCRD
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 2: CAMPOS DE USUARIO EN BusinessPartners (OCRD)")
    print("="*90)
    
    udf = conn.get("UserFieldsMD", {
        "$filter": "TableName eq 'OCRD'",
        "$select": "Name,Description,Type",
        "$top": 100
    })
    
    if udf and 'value' in udf:
        print(f"\n   Campos de usuario en OCRD: {len(udf['value'])}")
        
        # Buscar campos relacionados con correo o comentarios
        for campo in udf['value']:
            nombre = campo.get('Name', '').upper()
            desc = campo.get('Description', '').upper()
            
            if any(x in nombre or x in desc for x in ['CORREO', 'EMAIL', 'MAIL', 'NOTA', 'COMMENT', 'OBS', 'ENVIO']):
                print(f"      U_{campo.get('Name')}: {campo.get('Description')} ({campo.get('Type')})")

    # =========================================================================
    # 3. Muestra de clientes con sus campos de correo
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 3: MUESTRA DE CLIENTES CON CAMPOS DE CORREO")
    print("="*90)
    
    # Obtener clientes con saldo
    clientes = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and CurrentAccountBalance ne 0",
        "$select": "CardCode,CardName,EmailAddress,FreeText,Notes,U_NVT_CorreoEstadoCuenta,U_NTV_EnvioAutomatico",
        "$top": 20
    })
    
    if clientes and 'value' in clientes:
        print(f"\n   Analizando {len(clientes['value'])} clientes con saldo:")
        
        stats = {
            'con_correo_cxc': 0,
            'con_notas': 0,
            'correo_en_notas': 0,
            'envio_auto_S': 0,
            'envio_auto_N': 0,
            'envio_auto_vacio': 0,
        }
        
        print(f"\n   {'Código':8} | {'EnvioAuto':10} | {'CorreoCXC':30} | {'EmailPpal':30} | Notas")
        print("   " + "-"*100)
        
        for c in clientes['value']:
            codigo = c.get('CardCode', '')
            envio_auto = c.get('U_NTV_EnvioAutomatico', '')
            correo_cxc = c.get('U_NVT_CorreoEstadoCuenta', '') or ''
            email_ppal = c.get('EmailAddress', '') or ''
            notas = c.get('FreeText', '') or c.get('Notes', '') or ''
            
            # Estadísticas
            if correo_cxc:
                stats['con_correo_cxc'] += 1
            if notas:
                stats['con_notas'] += 1
                correos_notas = extraer_correos_texto(notas)
                if correos_notas:
                    stats['correo_en_notas'] += 1
            
            if envio_auto == 'S':
                stats['envio_auto_S'] += 1
            elif envio_auto == 'N':
                stats['envio_auto_N'] += 1
            else:
                stats['envio_auto_vacio'] += 1
            
            # Mostrar
            notas_preview = notas[:30] + '...' if len(notas) > 30 else notas
            print(f"   {codigo:8} | {envio_auto or '(vacío)':10} | {correo_cxc[:30]:30} | {email_ppal[:30]:30} | {notas_preview}")
        
        print(f"\n   📊 ESTADÍSTICAS:")
        print(f"      Con U_NVT_CorreoEstadoCuenta: {stats['con_correo_cxc']}")
        print(f"      Con notas/comentarios: {stats['con_notas']}")
        print(f"      Con correo EN notas: {stats['correo_en_notas']}")
        print(f"      EnvioAutomatico = 'S': {stats['envio_auto_S']}")
        print(f"      EnvioAutomatico = 'N': {stats['envio_auto_N']}")
        print(f"      EnvioAutomatico vacío: {stats['envio_auto_vacio']}")

    # =========================================================================
    # 4. Ver ejemplo de notas con correos
    # =========================================================================
    print("\n" + "="*90)
    print("📊 PARTE 4: EJEMPLOS DE NOTAS CON POSIBLES CORREOS")
    print("="*90)
    
    if clientes and 'value' in clientes:
        for c in clientes['value']:
            notas = c.get('FreeText', '') or c.get('Notes', '') or ''
            if notas:
                correos = extraer_correos_texto(notas)
                if correos:
                    print(f"\n   Cliente: {c.get('CardCode')} - {c.get('CardName', '')[:30]}")
                    print(f"   Notas: {notas[:150]}...")
                    print(f"   Correos encontrados: {correos}")

    conn.logout()
    print("\n" + "="*90)
    print("✅ Investigación completada")
    print("="*90)


if __name__ == "__main__":
    main()