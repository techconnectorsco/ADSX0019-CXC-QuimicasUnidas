"""
consignaciones.py - Químicas Unidas
Reporte de Toma Física de Inventario (Consignaciones) para Agentes.
Camino Largo: Cruce de datos 100% en Python usando solo tablas permitidas.
"""

import sys
import os
import time
from datetime import datetime
from fpdf import FPDF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.database.conexion import ServiceLayerConnection
from sendemailCXC import EmailSenderAgente

EMAIL_PRUEBA = "devs@techconnectors.co"
MODO_PRUEBA = True

AZUL_OSCURO = (11, 17, 75)
AZUL_CLARO = (40, 143, 204)
AZUL_FOOTER = (71, 93, 164)

class PDFConsignacion(FPDF):
    def __init__(self, agente_nombre):
        super().__init__(orientation='L', unit='mm', format='Legal')
        self.agente_nombre = agente_nombre
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 15, 10)

    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(*AZUL_OSCURO)
        self.cell(0, 8, 'DETALLE DE INVENTARIO - CONSIGNACIONES', 0, 1, 'L')
        
        self.set_font('Arial', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f'Agente / Vendedor: {self.agente_nombre}', 0, 1, 'L')
        
        self.set_xy(-60, 15)
        self.cell(50, 5, f'Fecha: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'R')
        self.set_xy(-60, 20)
        self.cell(50, 5, f'Hora: {datetime.now().strftime("%I:%M %p")}', 0, 1, 'R')
        
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.8)
        self.line(10, 28, self.w - 10, 28)
        self.set_y(32)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'R')

    def agregar_tabla(self, equipos):
        anchos = [20, 75, 25, 45, 110, 50]
        headers = ['Cliente', 'Nombre del Custodio', 'Zona', 'Cód. Artículo', 'Descripción', 'Número de Serie']
        
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 9)
        
        for i, h in enumerate(headers):
            self.cell(anchos[i], 7, h, 1, 0, 'C', True)
        self.ln()

        self.set_text_color(0, 0, 0)
        self.set_font('Arial', '', 8)
        fill = False
        
        for e in equipos:
            if self.get_y() > self.h - 40:
                self.add_page()
                self.set_fill_color(*AZUL_FOOTER)
                self.set_text_color(255, 255, 255)
                self.set_font('Arial', 'B', 9)
                for i, h in enumerate(headers):
                    self.cell(anchos[i], 7, h, 1, 0, 'C', True)
                self.ln()
                self.set_text_color(0, 0, 0)
                self.set_font('Arial', '', 8)

            if fill: self.set_fill_color(245, 245, 245)
            else: self.set_fill_color(255, 255, 255)
            
            self.cell(anchos[0], 6, str(e.get('CardCode', ''))[:10], 1, 0, 'C', fill)
            self.cell(anchos[1], 6, str(e.get('CardName', ''))[:45], 1, 0, 'L', fill)
            self.cell(anchos[2], 6, str(e.get('Zona', ''))[:10], 1, 0, 'C', fill)
            self.cell(anchos[3], 6, str(e.get('ItemCode', ''))[:20], 1, 0, 'C', fill)
            self.cell(anchos[4], 6, str(e.get('ItemName', ''))[:70], 1, 0, 'L', fill)
            self.cell(anchos[5], 6, str(e.get('SerialNumber', ''))[:25], 1, 1, 'C', fill)
            fill = not fill

    def agregar_firmas(self):
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(20)
        self.set_font('Arial', '', 10)
        self.cell(0, 6, 'El custodio da por aceptada la toma física de inventario realizado el ____________________ a las _____________.', 0, 1)
        self.ln(15)
        self.cell(100, 5, '_________________________________________________', 0, 0)
        self.cell(100, 5, '_________________________________________________', 0, 1)
        self.cell(100, 5, 'Custodio:', 0, 0)
        self.cell(100, 5, 'Hecho por:', 0, 1)

# =============================================================================
# EXTRACCIÓN Y CRUCE (CAMINO LARGO EN PYTHON)
# =============================================================================

def obtener_todos_paginado(conn, entidad, params):
    todos = []
    skip = 0
    params["$top"] = 50
    while True:
        params["$skip"] = skip
        res = conn.get(entidad, params)
        if not res or 'value' not in res or not res['value']: break
        todos.extend(res['value'])
        skip += 50
    return todos

def extraer_series_permitidas(conn):
    """Extrae series de las bodegas usando SOLO tablas permitidas (OSRQ y OSRN)."""
    query_code = f"TMP_RPA_{int(time.time())}"
    sql_text = """
    SELECT T0."WhsCode", T0."ItemCode", T1."DistNumber" AS "SerialNumber"
    FROM OSRQ T0
    INNER JOIN OSRN T1 ON T0."ItemCode" = T1."ItemCode" AND T0."SysNumber" = T1."SysNumber"
    WHERE T0."Quantity" > 0 AND (T0."WhsCode" LIKE '00%' OR T0."WhsCode" LIKE 'C0%')
    """
    
    url_post = f"{conn.base_url}/SQLQueries"
    url_del = f"{conn.base_url}/SQLQueries('{query_code}')"
    series = []

    try:
        conn.session.post(url_post, json={"SqlCode": query_code, "SqlName": "TMP", "SqlText": sql_text})
        skip = 0
        while True:
            res = conn.get(f"SQLQueries('{query_code}')/List?$skip={skip}")
            if not res or 'value' not in res or not res['value']: break
            series.extend(res['value'])
            skip += 20
    finally:
        try: conn.session.delete(url_del)
        except: pass
    return series

def ejecutar_reportes_consignacion():
    print("="*80)
    print("📦 PROCESO: Reportes de Consignación (Toma Física)")
    print("="*80)
    
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login(): return
        
    try:
        # 1. Traer datos base
        print("📥 Descargando Series en Bodegas...")
        series_bodega = extraer_series_permitidas(conn)
        
        print("📥 Descargando Maestro de Clientes...")
        clientes_raw = obtener_todos_paginado(conn, "BusinessPartners", {"$select": "CardCode,CardName,SalesPersonCode,U_ZGIRA"})
        clientes_dict = {c['CardCode']: c for c in clientes_raw}

        print("📥 Descargando Artículos...")
        items_raw = obtener_todos_paginado(conn, "Items", {"$select": "ItemCode,ItemName"})
        items_dict = {i['ItemCode']: i['ItemName'] for i in items_raw}

        print("📥 Obteniendo Vendedores...")
        vends_raw = obtener_todos_paginado(conn, "SalesPersons", {"$select": "SalesEmployeeCode,SalesEmployeeName,Email"})
        vendedores_cache = {v['SalesEmployeeCode']: v for v in vends_raw}

        # 2. El cruce mágico en Python
        print("\n🔀 Cruzando datos en memoria...")
        equipos_procesados = []
        for s in series_bodega:
            bodega = s['WhsCode']
            
            # La lógica de Q.U.: Si la bodega es '0180', el cliente es 'C0180'
            posible_cliente = bodega if bodega in clientes_dict else f"C{bodega}"
            
            if posible_cliente in clientes_dict:
                cli = clientes_dict[posible_cliente]
                equipos_procesados.append({
                    'WhsCode': bodega,
                    'CardCode': cli['CardCode'],
                    'CardName': cli['CardName'],
                    'Zona': cli.get('U_ZGIRA', 'N/A'),
                    'SalesPersonCode': cli.get('SalesPersonCode', -1),
                    'ItemCode': s['ItemCode'],
                    'ItemName': items_dict.get(s['ItemCode'], 'Sin Descripción'),
                    'SerialNumber': s['SerialNumber']
                })

        # 3. Agrupar por Vendedor
        agrupados = {}
        for eq in equipos_procesados:
            vid = eq['SalesPersonCode']
            if vid not in agrupados: agrupados[vid] = []
            agrupados[vid].append(eq)

        # 4. Generar y Enviar
        sender = EmailSenderAgente()
        os.makedirs('data/consignaciones', exist_ok=True)
        resultados = {'procesados': 0, 'enviados': 0, 'errores': 0, 'sin_correo': 0}

        for vid, lista_equipos in agrupados.items():
            if '--test' in sys.argv and resultados['procesados'] >= 2: break
            
            # Ordenar por Zona y luego por Cliente
            lista_equipos.sort(key=lambda x: (str(x['Zona']).zfill(3), x['CardName']))

            info_vendedor = vendedores_cache.get(vid, {'SalesEmployeeName': 'No Asignado', 'Email': ''})
            nombre_agente = info_vendedor.get('SalesEmployeeName', 'No Asignado')
            correo_agente = info_vendedor.get('Email', '')
            
            print(f"\n👨‍💼 Procesando Agente: {nombre_agente} | Equipos a contar: {len(lista_equipos)}")

            pdf = PDFConsignacion(nombre_agente)
            pdf.add_page()
            pdf.agregar_tabla(lista_equipos)
            pdf.agregar_firmas()
            
            pdf_path = f"data/consignaciones/TomaFisica_{vid}_{datetime.now().strftime('%Y%m%d')}.pdf"
            pdf.output(pdf_path)
            
            destinatario = EMAIL_PRUEBA if MODO_PRUEBA else correo_agente
            if not destinatario or "@" not in str(destinatario):
                print(f"   ⚠️ Agente sin correo. Saltando envío.")
                resultados['sin_correo'] += 1
                continue

            if sender.enviar_reporte_gira(destinatario, nombre_agente, pdf_path):
                print(f"   ✅ Reporte enviado a {destinatario}")
                resultados['enviados'] += 1
            else:
                resultados['errores'] += 1
            
            resultados['procesados'] += 1

        print("\n" + "="*80)
        print("📊 RESUMEN DE TOMA FÍSICA")
        print(f"   Agentes procesados: {resultados['procesados']}")
        print(f"   Reportes enviados: {resultados['enviados']}")
        print("="*80)

    finally:
        conn.logout()

if __name__ == "__main__":
    ejecutar_reportes_consignacion()