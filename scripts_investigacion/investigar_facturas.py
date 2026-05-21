"""
investigar_facturas.py
Investigar todos los campos disponibles en Invoices para el PDF de CXC.
Buscar: consecutivo GSE, descripción, número de serie, tipo transacción.
"""

import sys
sys.path.insert(0, '.')
from modules.database.conexion import ServiceLayerConnection


def main():
    conn = ServiceLayerConnection(use_test_db=False)

    if not conn.login():
        print("❌ Error de conexión")
        return

    print("="*90)
    print("🔍 INVESTIGACIÓN: CAMPOS DE FACTURAS (Invoices)")
    print("="*90)

    # =========================================================================
    # 1. Buscar un cliente con facturas - C0243 (Marin Villegas)
    # =========================================================================
    print("\n📌 Buscando facturas del cliente C0243 (MARIN VILLEGAS HUMBERTO)...")
    
    # Obtener UNA factura con TODOS los campos
    factura_completa = conn.get("Invoices", {
        "$filter": "CardCode eq 'C0243' and DocumentStatus eq 'bost_Open'",
        "$top": 1
    })
    
    if factura_completa and 'value' in factura_completa and factura_completa['value']:
        factura = factura_completa['value'][0]
        
        print("\n" + "="*90)
        print("📋 TODOS LOS CAMPOS DE UNA FACTURA:")
        print("="*90)
        
        for key, value in sorted(factura.items()):
            # Saltar arrays muy grandes
            if isinstance(value, list) and len(value) > 2:
                print(f"   {key}: [Lista con {len(value)} elementos]")
            else:
                print(f"   {key}: {value}")
        
        # Buscar campos que parecen ser los que necesitamos
        print("\n" + "="*90)
        print("🔍 CAMPOS RELEVANTES ENCONTRADOS:")
        print("="*90)
        
        campos_interes = [
            'DocNum', 'DocEntry', 'NumAtCard',  # Números de documento
            'U_NUM_CONSE', 'U_TDOC', 'U_GSE',    # Campos de usuario
            'Comments', 'JournalMemo',           # Descripciones
            'Series', 'SeriesString',            # Series
            'TransNum', 'TrackingNumber',        # Tracking
            'DocDate', 'DocDueDate', 'TaxDate',  # Fechas
            'DocTotal', 'PaidToDate', 'DocCurrency',  # Montos
        ]
        
        print("\n   NÚMEROS Y REFERENCIAS:")
        for campo in ['DocNum', 'DocEntry', 'NumAtCard', 'U_NUM_CONSE', 'U_TDOC', 'U_GSE', 'Series', 'SeriesString', 'TransNum']:
            valor = factura.get(campo, 'NO EXISTE')
            print(f"      {campo}: {valor}")
        
        print("\n   DESCRIPCIONES:")
        for campo in ['Comments', 'JournalMemo']:
            valor = factura.get(campo, 'NO EXISTE')
            if valor:
                print(f"      {campo}: {str(valor)[:80]}...")
            else:
                print(f"      {campo}: (vacío)")
        
        # Buscar DocumentLines para descripción y serie
        print("\n" + "="*90)
        print("📋 LÍNEAS DEL DOCUMENTO (DocumentLines):")
        print("="*90)
        
        lineas = factura.get('DocumentLines', [])
        if lineas:
            print(f"\n   Total líneas: {len(lineas)}")
            
            # Mostrar primera línea completa
            if lineas:
                print("\n   CAMPOS DE LA PRIMERA LÍNEA:")
                for key, value in sorted(lineas[0].items()):
                    if isinstance(value, list) and len(value) > 2:
                        print(f"      {key}: [Lista con {len(value)} elementos]")
                    elif value is not None and value != '':
                        print(f"      {key}: {value}")
                
                # Campos específicos de interés en líneas
                print("\n   CAMPOS DE INTERÉS EN LÍNEAS:")
                for linea in lineas[:3]:  # Primeras 3 líneas
                    print(f"\n      Línea {linea.get('LineNum', '?')}:")
                    print(f"         ItemCode: {linea.get('ItemCode')}")
                    print(f"         ItemDescription: {linea.get('ItemDescription')}")
                    print(f"         SerialNum: {linea.get('SerialNum')}")
                    print(f"         Quantity: {linea.get('Quantity')}")
                    print(f"         Price: {linea.get('Price')}")
                    print(f"         LineTotal: {linea.get('LineTotal')}")
                    
                    # Buscar SerialNumbers dentro de la línea
                    serial_nums = linea.get('SerialNumbers', [])
                    if serial_nums:
                        print(f"         SerialNumbers: {serial_nums}")
                    
                    batch_nums = linea.get('BatchNumbers', [])
                    if batch_nums:
                        print(f"         BatchNumbers: {batch_nums}")

    # =========================================================================
    # 2. Buscar campos U_ (definidos por usuario) en Invoices
    # =========================================================================
    print("\n" + "="*90)
    print("📋 CAMPOS DE USUARIO (U_) EN INVOICES:")
    print("="*90)
    
    udf = conn.get("UserFieldsMD", {
        "$filter": "TableName eq 'OINV'",
        "$select": "Name,Description,Type",
        "$top": 50
    })
    
    if udf and 'value' in udf:
        print(f"\n   Campos de usuario en OINV (Invoices): {len(udf['value'])}")
        for campo in udf['value']:
            print(f"      U_{campo.get('Name')}: {campo.get('Description')} ({campo.get('Type')})")

    # =========================================================================
    # 3. Buscar varias facturas para ver patrones
    # =========================================================================
    print("\n" + "="*90)
    print("📋 MUESTRA DE FACTURAS (campos clave):")
    print("="*90)
    
    facturas = conn.get("Invoices", {
        "$filter": "CardCode eq 'C0243' and DocumentStatus eq 'bost_Open'",
        "$select": "DocNum,DocDate,DocDueDate,DocTotal,PaidToDate,DocCurrency,U_TDOC,U_NUM_CONSE,Comments,NumAtCard,Series",
        "$top": 10,
        "$orderby": "DocDate desc"
    })
    
    if facturas and 'value' in facturas:
        print(f"\n   {'DocNum':12} | {'U_TDOC':8} | {'U_NUM_CONSE':25} | {'NumAtCard':20} | {'Moneda':6} | {'Saldo':>12}")
        print("   " + "-"*95)
        
        for f in facturas['value']:
            doc_num = f.get('DocNum', '')
            tipo = f.get('U_TDOC', '')
            consec = f.get('U_NUM_CONSE', '') or ''
            num_at_card = f.get('NumAtCard', '') or ''
            moneda = f.get('DocCurrency', '')
            total = f.get('DocTotal', 0) or 0
            pagado = f.get('PaidToDate', 0) or 0
            saldo = total - pagado
            
            print(f"   {doc_num:12} | {tipo:8} | {consec[:25]:25} | {num_at_card[:20]:20} | {moneda:6} | {saldo:>12,.2f}")

    # =========================================================================
    # 4. Investigar DocumentLines para descripción
    # =========================================================================
    print("\n" + "="*90)
    print("📋 DESCRIPCIÓN DE LÍNEAS (ItemDescription):")
    print("="*90)
    
    # Obtener factura con líneas expandidas
    factura_lineas = conn.get("Invoices", {
        "$filter": "CardCode eq 'C0243' and DocumentStatus eq 'bost_Open'",
        "$top": 3,
        "$expand": "DocumentLines"
    })
    
    if factura_lineas and 'value' in factura_lineas:
        for f in factura_lineas['value']:
            print(f"\n   Factura {f.get('DocNum')}:")
            lineas = f.get('DocumentLines', [])
            for linea in lineas[:3]:
                desc = linea.get('ItemDescription', '') or ''
                serial = linea.get('SerialNum', '') or ''
                print(f"      - {desc[:50]} | Serie: {serial}")

    # =========================================================================
    # 5. Buscar en SerialNumbers
    # =========================================================================
    print("\n" + "="*90)
    print("📋 NÚMEROS DE SERIE EN LÍNEAS:")
    print("="*90)
    
    # Las series pueden estar en DocumentLines.SerialNumbers
    if factura_completa and 'value' in factura_completa:
        factura = factura_completa['value'][0]
        lineas = factura.get('DocumentLines', [])
        
        for linea in lineas:
            serial_nums = linea.get('SerialNumbers', [])
            if serial_nums:
                print(f"\n   Línea {linea.get('LineNum')}: {linea.get('ItemDescription', '')[:40]}")
                for sn in serial_nums:
                    print(f"      SerialNumber: {sn}")

    conn.logout()
    print("\n" + "="*90)
    print("✅ Investigación completada")
    print("="*90)


if __name__ == "__main__":
    main()