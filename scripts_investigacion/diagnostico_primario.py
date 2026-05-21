"""
diagnostico_datos.py - Químicas Unidas
Análisis profundo de datos para entender la estructura antes de desarrollar.

OBJETIVO: Responder estas preguntas:
1. ¿Los vendedores tienen email en SAP? Si no, ¿de dónde los sacamos?
2. ¿Cómo se relacionan vendedores → zonas → clientes?
3. ¿Los campos nuevos U_NVT_CorreoEstadoCuenta y U_NTV_EnvioAutomatico están llenos?
4. ¿Cuántos clientes tienen correo para enviarles estado de cuenta?
5. ¿Cuántas facturas pendientes hay por cliente?

Ejecutar: python diagnostico_datos.py
"""

import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection
from datetime import datetime


def main():
    conn = ServiceLayerConnection(use_test_db=False)  # PRODUCCIÓN

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*80)
    print("🔍 DIAGNÓSTICO COMPLETO DE DATOS - QUÍMICAS UNIDAS")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*80)

    # =========================================================================
    # PARTE 1: VENDEDORES
    # =========================================================================
    print("\n" + "="*80)
    print("📊 PARTE 1: ANÁLISIS DE VENDEDORES (SalesPersons)")
    print("="*80)
    
    vendedores = conn.get("SalesPersons", {"$top": 100})
    vendedores_dict = {}
    
    if vendedores and 'value' in vendedores:
        activos = [v for v in vendedores['value'] if v.get('Active') == 'tYES']
        inactivos = [v for v in vendedores['value'] if v.get('Active') != 'tYES']
        
        print(f"\n   Total vendedores: {len(vendedores['value'])}")
        print(f"   Activos: {len(activos)}")
        print(f"   Inactivos: {len(inactivos)}")
        
        # Verificar emails
        con_email = [v for v in activos if v.get('Email')]
        sin_email = [v for v in activos if not v.get('Email')]
        
        print(f"\n   📧 EMAILS DE VENDEDORES:")
        print(f"      Con email: {len(con_email)}")
        print(f"      Sin email: {len(sin_email)}")
        
        print(f"\n   {'CODE':6} | {'NOMBRE':30} | {'EMAIL':30} | {'TELEFONO':15}")
        print("   " + "-"*90)
        
        for v in activos:
            code = v.get('SalesEmployeeCode')
            name = v.get('SalesEmployeeName') or ''
            email = v.get('Email') or '❌ SIN EMAIL'
            tel = v.get('Mobile') or v.get('Telephone') or ''
            vendedores_dict[code] = {'nombre': name, 'email': v.get('Email')}
            
            # Excluir el -1 (ningún vendedor)
            if code != -1:
                print(f"   {code:6} | {name[:30]:30} | {email[:30]:30} | {tel[:15]}")
        
        if sin_email:
            print(f"\n   ⚠️ ACCIÓN REQUERIDA: {len(sin_email)} vendedores sin email configurado")
            print("      Necesitamos los emails para enviar reportes de gira los martes")

    # =========================================================================
    # PARTE 2: CLIENTES - CAMPOS NUEVOS
    # =========================================================================
    print("\n" + "="*80)
    print("📊 PARTE 2: CAMPOS NUEVOS EN CLIENTES")
    print("="*80)
    
    # Traer TODOS los clientes activos
    clientes = conn.get("BusinessPartners", {
        "$filter": "CardType eq 'cCustomer' and Valid eq 'tYES'",
        "$select": "CardCode,CardName,EmailAddress,U_NVT_CorreoEstadoCuenta,U_NTV_EnvioAutomatico,SalesPersonCode,U_ZGIRA,CurrentAccountBalance",
        "$top": 2000  # Traer muchos para tener el panorama completo
    })
    
    if clientes and 'value' in clientes:
        total = len(clientes['value'])
        print(f"\n   Total clientes activos: {total}")
        
        # Análisis de U_NVT_CorreoEstadoCuenta
        con_correo_cxc = [c for c in clientes['value'] if c.get('U_NVT_CorreoEstadoCuenta')]
        sin_correo_cxc = [c for c in clientes['value'] if not c.get('U_NVT_CorreoEstadoCuenta')]
        
        print(f"\n   📧 CAMPO: U_NVT_CorreoEstadoCuenta (correo específico para CXC)")
        print(f"      Con valor: {len(con_correo_cxc)} ({len(con_correo_cxc)*100//total}%)")
        print(f"      Vacío:     {len(sin_correo_cxc)} ({len(sin_correo_cxc)*100//total}%)")
        
        # Análisis de U_NTV_EnvioAutomatico
        envio_si = [c for c in clientes['value'] if c.get('U_NTV_EnvioAutomatico') == 'S']
        envio_no = [c for c in clientes['value'] if c.get('U_NTV_EnvioAutomatico') == 'N']
        envio_vacio = [c for c in clientes['value'] if not c.get('U_NTV_EnvioAutomatico')]
        
        print(f"\n   🔄 CAMPO: U_NTV_EnvioAutomatico (control de envío)")
        print(f"      'S' (Sí enviar):  {len(envio_si)}")
        print(f"      'N' (No enviar):  {len(envio_no)}")
        print(f"      Vacío:            {len(envio_vacio)}")
        
        # Análisis de EmailAddress (correo principal)
        con_email_principal = [c for c in clientes['value'] if c.get('EmailAddress')]
        sin_email_principal = [c for c in clientes['value'] if not c.get('EmailAddress')]
        
        print(f"\n   📧 CAMPO: EmailAddress (correo principal)")
        print(f"      Con valor: {len(con_email_principal)} ({len(con_email_principal)*100//total}%)")
        print(f"      Vacío:     {len(sin_email_principal)} ({len(sin_email_principal)*100//total}%)")
        
        # ¿Cuántos tienen AL MENOS UN correo?
        con_algun_correo = [c for c in clientes['value'] 
                           if c.get('U_NVT_CorreoEstadoCuenta') or c.get('EmailAddress')]
        sin_ningun_correo = [c for c in clientes['value'] 
                            if not c.get('U_NVT_CorreoEstadoCuenta') and not c.get('EmailAddress')]
        
        print(f"\n   📊 RESUMEN DE CORREOS:")
        print(f"      Con algún correo (CXC o principal): {len(con_algun_correo)}")
        print(f"      Sin ningún correo:                  {len(sin_ningun_correo)}")
        
        # Clientes con saldo pero sin correo
        con_saldo = [c for c in clientes['value'] if (c.get('CurrentAccountBalance') or 0) > 0]
        con_saldo_sin_correo = [c for c in con_saldo 
                                if not c.get('U_NVT_CorreoEstadoCuenta') and not c.get('EmailAddress')]
        
        print(f"\n   ⚠️ CLIENTES CON SALDO PERO SIN CORREO: {len(con_saldo_sin_correo)}")
        if con_saldo_sin_correo:
            print(f"\n      {'CÓDIGO':10} | {'NOMBRE':40} | {'SALDO':>15}")
            print("      " + "-"*70)
            for c in con_saldo_sin_correo[:15]:  # Mostrar máximo 15
                print(f"      {c.get('CardCode'):10} | {c.get('CardName')[:40]:40} | {c.get('CurrentAccountBalance'):>15,.2f}")
            if len(con_saldo_sin_correo) > 15:
                print(f"      ... y {len(con_saldo_sin_correo) - 15} más")

    # =========================================================================
    # PARTE 3: ZONAS Y RELACIÓN CON VENDEDORES
    # =========================================================================
    print("\n" + "="*80)
    print("📊 PARTE 3: ZONAS DE GIRA (U_ZGIRA)")
    print("="*80)
    
    if clientes and 'value' in clientes:
        # Agrupar por zona
        zonas = {}
        sin_zona = []
        
        for c in clientes['value']:
            zona = c.get('U_ZGIRA')
            vendedor = c.get('SalesPersonCode')
            
            if not zona:
                sin_zona.append(c)
                continue
            
            zona_str = str(zona)
            if zona_str not in zonas:
                zonas[zona_str] = {
                    'vendedores': set(),
                    'clientes': [],
                    'con_saldo': 0,
                    'total_saldo': 0
                }
            
            zonas[zona_str]['clientes'].append(c)
            if vendedor and vendedor != -1:
                zonas[zona_str]['vendedores'].add(vendedor)
            
            saldo = c.get('CurrentAccountBalance') or 0
            if saldo > 0:
                zonas[zona_str]['con_saldo'] += 1
                zonas[zona_str]['total_saldo'] += saldo
        
        print(f"\n   Total zonas encontradas: {len(zonas)}")
        print(f"   Clientes SIN zona: {len(sin_zona)}")
        
        print(f"\n   {'ZONA':6} | {'VENDEDOR(ES)':25} | {'CLIENTES':10} | {'CON SALDO':10} | {'TOTAL SALDO':>15}")
        print("   " + "-"*85)
        
        for z in sorted(zonas.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            vends = list(zonas[z]['vendedores'])
            vend_nombres = ', '.join([vendedores_dict.get(v, {}).get('nombre', str(v))[:12] for v in vends])
            total_cli = len(zonas[z]['clientes'])
            con_saldo = zonas[z]['con_saldo']
            total_saldo = zonas[z]['total_saldo']
            print(f"   {z:6} | {vend_nombres[:25]:25} | {total_cli:10} | {con_saldo:10} | {total_saldo:>15,.2f}")
        
        # Verificar consistencia: ¿Hay zonas con múltiples vendedores?
        zonas_multi_vendedor = {z: v for z, v in zonas.items() if len(v['vendedores']) > 1}
        if zonas_multi_vendedor:
            print(f"\n   ⚠️ ZONAS CON MÚLTIPLES VENDEDORES:")
            for z, data in zonas_multi_vendedor.items():
                vends = [vendedores_dict.get(v, {}).get('nombre', str(v)) for v in data['vendedores']]
                print(f"      Zona {z}: {vends}")

    # =========================================================================
    # PARTE 4: RESUMEN POR VENDEDOR
    # =========================================================================
    print("\n" + "="*80)
    print("📊 PARTE 4: CARTERA POR VENDEDOR (para reportes de gira)")
    print("="*80)
    
    if clientes and 'value' in clientes:
        vendedores_cartera = {}
        
        for c in clientes['value']:
            vendedor = c.get('SalesPersonCode')
            if not vendedor or vendedor == -1:
                continue
            
            if vendedor not in vendedores_cartera:
                vendedores_cartera[vendedor] = {
                    'nombre': vendedores_dict.get(vendedor, {}).get('nombre', 'Desconocido'),
                    'email': vendedores_dict.get(vendedor, {}).get('email'),
                    'clientes': 0,
                    'con_saldo': 0,
                    'total_saldo': 0,
                    'zonas': set()
                }
            
            vendedores_cartera[vendedor]['clientes'] += 1
            
            zona = c.get('U_ZGIRA')
            if zona:
                vendedores_cartera[vendedor]['zonas'].add(str(zona))
            
            saldo = c.get('CurrentAccountBalance') or 0
            if saldo > 0:
                vendedores_cartera[vendedor]['con_saldo'] += 1
                vendedores_cartera[vendedor]['total_saldo'] += saldo
        
        print(f"\n   {'CÓDIGO':8} | {'NOMBRE':25} | {'EMAIL':12} | {'CLIENTES':10} | {'CON SALDO':10} | {'CARTERA':>15} | ZONAS")
        print("   " + "-"*110)
        
        for v in sorted(vendedores_cartera.keys()):
            data = vendedores_cartera[v]
            tiene_email = "✅" if data['email'] else "❌"
            zonas_str = ','.join(sorted(data['zonas'], key=lambda x: int(x) if x.isdigit() else 999))
            print(f"   {v:8} | {data['nombre'][:25]:25} | {tiene_email:12} | {data['clientes']:10} | {data['con_saldo']:10} | {data['total_saldo']:>15,.2f} | {zonas_str}")

    # =========================================================================
    # PARTE 5: FACTURAS PENDIENTES (MUESTRA)
    # =========================================================================
    print("\n" + "="*80)
    print("📊 PARTE 5: MUESTRA DE FACTURAS PENDIENTES")
    print("="*80)
    
    # Tomar un cliente con saldo para ver sus facturas
    if clientes and 'value' in clientes:
        cliente_ejemplo = None
        for c in clientes['value']:
            if (c.get('CurrentAccountBalance') or 0) > 100000:  # Buscar uno con saldo significativo
                cliente_ejemplo = c
                break
        
        if cliente_ejemplo:
            codigo = cliente_ejemplo.get('CardCode')
            print(f"\n   Cliente ejemplo: {codigo} - {cliente_ejemplo.get('CardName')}")
            print(f"   Saldo total: {cliente_ejemplo.get('CurrentAccountBalance'):,.2f}")
            
            facturas = conn.get("Invoices", {
                "$filter": f"CardCode eq '{codigo}' and DocumentStatus eq 'bost_Open'",
                "$select": "DocNum,DocDate,DocDueDate,DocTotal,PaidToDate,DocCurrency,U_TDOC,U_NUM_CONSE",
                "$top": 20
            })
            
            if facturas and 'value' in facturas:
                print(f"\n   Facturas pendientes: {len(facturas['value'])}")
                print(f"\n   {'NUM':8} | {'CONSEC_FE':20} | {'TIPO':8} | {'FECHA':12} | {'VENCE':12} | {'TOTAL':>12} | {'SALDO':>12} | MON")
                print("   " + "-"*110)
                
                hoy = datetime.now().date()
                
                for f in facturas['value']:
                    num = f.get('DocNum', '')
                    consec = f.get('U_NUM_CONSE', '') or ''
                    tipo = f.get('U_TDOC', '') or ''
                    fecha = str(f.get('DocDate', ''))[:10]
                    vence = str(f.get('DocDueDate', ''))[:10]
                    total = f.get('DocTotal', 0) or 0
                    pagado = f.get('PaidToDate', 0) or 0
                    saldo = total - pagado
                    moneda = f.get('DocCurrency', '')
                    
                    # Calcular si está vencido
                    try:
                        fecha_vence = datetime.strptime(vence, '%Y-%m-%d').date()
                        dias_venc = (hoy - fecha_vence).days
                        venc_str = f"{'🔴' if dias_venc > 0 else '🟢'} {vence}"
                    except:
                        venc_str = vence
                    
                    print(f"   {num:8} | {consec[:20]:20} | {tipo:8} | {fecha:12} | {venc_str:12} | {total:>12,.2f} | {saldo:>12,.2f} | {moneda}")

    # =========================================================================
    # RESUMEN FINAL Y ACCIONES REQUERIDAS
    # =========================================================================
    print("\n" + "="*80)
    print("📋 RESUMEN Y ACCIONES REQUERIDAS")
    print("="*80)
    
    print("\n   ✅ DATOS DISPONIBLES:")
    print("      - Clientes con saldo")
    print("      - Facturas pendientes")
    print("      - Zonas de gira")
    print("      - Vendedores activos")
    
    print("\n   ⚠️ DATOS FALTANTES O PENDIENTES:")
    
    # Vendedores sin email
    if vendedores and 'value' in vendedores:
        activos_sin_email = [v for v in vendedores['value'] 
                            if v.get('Active') == 'tYES' 
                            and not v.get('Email')
                            and v.get('SalesEmployeeCode') != -1]
        if activos_sin_email:
            print(f"      ❌ {len(activos_sin_email)} vendedores sin email (necesario para reportes de gira)")
    
    # Clientes con saldo sin correo
    if clientes and 'value' in clientes:
        if con_saldo_sin_correo:
            print(f"      ❌ {len(con_saldo_sin_correo)} clientes con saldo pero sin ningún correo")
        
        if envio_vacio:
            print(f"      ⚠️ {len(envio_vacio)} clientes con U_NTV_EnvioAutomatico vacío (¿asumir 'S'?)")
    
    print("\n   📝 RECOMENDACIONES:")
    print("      1. Solicitar emails de vendedores para reportes de gira")
    print("      2. Revisar clientes con saldo sin correo")
    print("      3. Definir comportamiento cuando U_NTV_EnvioAutomatico está vacío")

    conn.logout()
    print("\n" + "="*80)
    print("✅ Diagnóstico completado")
    print("="*80)


if __name__ == "__main__":
    main()