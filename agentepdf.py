"""
agentepdf.py - Químicas Unidas
Generación de PDFs consolidados para Reportes de Gira de Agentes.

Características:
- Orientación horizontal tamaño OFICIO (Legal)
- Múltiples clientes en un solo documento
- Separadores visuales por cliente con información de contacto
- Columnas idénticas al Estado de Cuenta de CXC (sin tabla de vencidos)
- Formato de moneda Latinoamericano
"""

from fpdf import FPDF
from datetime import datetime
from typing import List, Dict
import os
import tempfile

try:
    import qrcode
    QR_DISPONIBLE = True
except ImportError:
    QR_DISPONIBLE = False

# =============================================================================
# CONSTANTES Y CONFIGURACIÓN DE COLORES
# =============================================================================

AZUL_OSCURO = (11, 17, 75)       # Header, títulos
AZUL_CLARO = (40, 143, 204)      # Línea decorativa
AZUL_FOOTER = (71, 93, 164)      # Fondo footer
ROJO = (220, 53, 69)             # Vencidos
VERDE = (40, 167, 69)            # Al día
GRIS = (100, 100, 100)           # Textos secundarios
GRIS_CLARO = (245, 245, 245)     # Fondo alternado
AMARILLO_SUAVE = (255, 249, 230) # Fondo para encabezado de cliente

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def formato_latino(valor: float) -> str:
    """Convierte el formato US (1,234.56) a formato Latino (1.234,56)."""
    if valor is None:
        valor = 0.0
    num_str = f"{abs(valor):,.2f}"
    num_str = num_str.replace(',', 'X')
    num_str = num_str.replace('.', ',')
    num_str = num_str.replace('X', '.')
    return num_str


def generar_qr_agente(datos_agente: Dict, totales_generales: Dict) -> str:
    """Genera un código QR con el resumen de la gira del agente."""
    if not QR_DISPONIBLE:
        return None
    
    fecha_emision = datetime.now().strftime('%d/%m/%Y %H:%M')
    codigo_verificacion = f"GIRA-{datetime.now().strftime('%Y%m%d%H%M')}"
    
    contenido = []
    contenido.append("════════════════════════════════════════")
    contenido.append("   QUÍMICAS UNIDAS S.A.")
    contenido.append("   Reporte de Gira (Uso Interno)")
    contenido.append("════════════════════════════════════════")
    contenido.append("")
    contenido.append(f"Agente: {datos_agente.get('nombre', 'N/A')}")
    contenido.append(f"Zonas: {datos_agente.get('zonas', 'Varias')}")
    contenido.append(f"Emisión: {fecha_emision}")
    contenido.append("")
    
    if totales_generales.get('dolares', 0) > 0:
        contenido.append(f"TOTAL A COBRAR (USD): {formato_latino(totales_generales['dolares'])}")
    if totales_generales.get('colones', 0) > 0:
        contenido.append(f"TOTAL A COBRAR (CRC): {formato_latino(totales_generales['colones'])}")
        
    contenido.append("════════════════════════════════════════")
    contenido.append(f"Verificación: {codigo_verificacion}")
    
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data("\n".join(contenido))
    qr.make(fit=True)
    
    img_qr = qr.make_image(fill_color="black", back_color="white")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    img_qr.save(temp_file.name)
    temp_file.close()
    
    return temp_file.name


# =============================================================================
# CLASE PRINCIPAL - PDF REPORTE DE GIRA
# =============================================================================

class PDFReporteGira(FPDF):

    def __init__(self, logo_path: str = 'images/QU.png'):
        super().__init__(orientation='L', unit='mm', format='Legal')
        self.logo_path = logo_path
        self.qr_path = None 
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)
    
    def set_qr_path(self, qr_path: str):
        self.qr_path = qr_path
        
    def header(self):
        # Logo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 15, 8, 45)
        
        # Título centrado
        self.set_font('Arial', 'B', 18)
        self.set_text_color(*AZUL_FOOTER)
        self.set_y(12)
        self.cell(0, 8, 'Químicas Unidas S.A.', 0, 1, 'C')
        
        self.set_font('Arial', 'B', 15)
        self.cell(0, 6, 'Reporte de Gira - Gestión de Cobro', 0, 1, 'C')
        
        # Fecha y hora
        self.set_font('Arial', '', 10)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime('%d/%m/%Y')
        hora = datetime.now().strftime('%I:%M %p')
        self.set_xy(-95, 12)
        self.cell(50, 5, f'Fecha: {fecha}', 0, 1, 'R')
        self.set_xy(-95, 17)
        self.cell(50, 5, f'Hora: {hora}', 0, 1, 'R')
        
        # QR
        if self.qr_path and os.path.exists(self.qr_path):
            self.image(self.qr_path, self.w - 38, 5, 30)
        
        # Línea decorativa
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.99)
        self.line(10, 40, self.w - 10, 40)
        
        self.set_y(43)

    def footer(self):
        self.set_y(-23)
        self.set_fill_color(*AZUL_CLARO)
        self.rect(0, self.h - 24, self.w, 3, 'F')
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(0, self.h - 22, self.w, 22, 'F')
        
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 11)
        self.set_y(-18)
        self.cell(0, 5, 'Documento de Uso Interno - Departamento de Ventas y Cobros', 0, 1, 'C')
        
        self.set_font('Arial', 'BI', 8)
        self.set_xy(10, -17)
        self.cell(80, 5, 'Oficina de Transformación Digital SX', 0, 0, 'L')

        self.set_font('Arial', 'I', 8)
        self.set_xy(10, -13)
        self.cell(80, 5, 'SOPORTEXPERTO.COM', 0, 0, 'L')
        
        self.set_font('Arial', 'I', 10)
        self.set_xy(-30, -13)
        self.cell(20, 5, f'Página {self.page_no()}', 0, 0, 'R')

    def agregar_info_agente(self, agente: Dict, totales: Dict):
        """Bloque principal con la información del vendedor al inicio del reporte."""
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, f" AGENTE: {agente.get('nombre', 'No especificado')} | ZONAS: {agente.get('zonas', 'Varias')}", 0, 1, 'L', True)
        self.ln(3)

    def agregar_separador_cliente(self, cliente: Dict, totales: Dict):
        """Franja que separa y muestra la info de contacto de un cliente antes de sus facturas."""
        # Evitar que el separador quede viudo al final de la página
        if self.get_y() > self.h - 50:
            self.add_page()
            
        y_inicio = self.get_y()
        self.set_fill_color(*AMARILLO_SUAVE)
        self.rect(10, y_inicio, self.w - 20, 16, 'F')
        self.set_fill_color(*AZUL_CLARO)
        self.rect(10, y_inicio, 3, 16, 'F')
        
        self.set_xy(15, y_inicio + 2)
        self.set_font('Arial', 'B', 11)
        self.set_text_color(*AZUL_OSCURO)
        
        # Fila 1: Cliente y Deuda Total
        nombre_str = f"{cliente.get('codigo', '')} - {cliente.get('nombre', '')}"
        self.cell(160, 6, nombre_str[:80], 0, 0)
        
        deuda_str = "SALDO TOTAL:"
        if totales.get('dolares', 0) > 0:
            deuda_str += f" USD {formato_latino(totales['dolares'])} |"
        if totales.get('colones', 0) > 0:
            deuda_str += f" CRC {formato_latino(totales['colones'])}"
        
        self.set_font('Arial', 'B', 10)
        self.set_text_color(*ROJO)
        self.cell(0, 6, deuda_str, 0, 1, 'R')
        
        # Fila 2: Contacto
        self.set_x(15)
        self.set_font('Arial', '', 9)
        self.set_text_color(0, 0, 0)
        contacto_str = f"Tel: {cliente.get('telefono', 'N/A')} | Contacto: {cliente.get('contacto', 'N/A')} | Límite: CRC {formato_latino(cliente.get('limite_credito', 0))}"
        self.cell(160, 5, contacto_str, 0, 0)
        
        self.set_font('Arial', 'I', 8)
        self.cell(0, 5, f"Dir: {str(cliente.get('direccion', ''))[:90]}", 0, 1, 'R')
        self.ln(2)

    def agregar_tabla_documentos(self, docs_usd: List[Dict], docs_crc: List[Dict]):
        """Tabla de facturas idéntica a la de CXC, pero sin totales por tabla."""
        todos_docs = []
        if docs_usd: todos_docs.extend(docs_usd)
        if docs_crc: todos_docs.extend(docs_crc)
        
        if not todos_docs:
            self.set_font('Arial', 'I', 9)
            self.cell(0, 8, 'Sin documentos pendientes.', 0, 1, 'C')
            self.ln(5)
            return

        anchos = [40, 25, 25, 32, 15, 135, 33, 28]
        headers = ['No de Doc', 'No de Orden', 'Fecha Factura', 'Fecha Vencimiento', 'Trans', 'Descripción', 'Monto Factura', 'Estatus']
        
        self._imprimir_encabezados_tabla(anchos, headers)
        
        self.set_font('Arial', '', 8)
        fila_par = False
        
        for doc in todos_docs:
            if self.get_y() > self.h - 35:
                self.add_page()
                self._imprimir_encabezados_tabla(anchos, headers)
                self.set_font('Arial', '', 8)
            
            if fila_par: self.set_fill_color(250, 250, 250)
            else: self.set_fill_color(255, 255, 255)
            fila_par = not fila_par
            
            esta_vencido = doc.get('esta_vencido', False)
            saldo = doc.get('saldo', 0)
            moneda = doc.get('moneda', '')
            simbolo = 'USD' if moneda == 'USD' else 'CRC'

            consecutivo = doc.get('consecutivo_fe', '') or str(doc.get('doc_num', ''))
            self.cell(anchos[0], 6, consecutivo, 1, 0, 'C', True)
            
            orden = str(doc.get('orden_compra', ''))
            if len(orden) > 15: orden = orden[:12] + "..."
            self.cell(anchos[1], 6, orden, 1, 0, 'C', True)
            
            fecha = doc.get('fecha', '')
            if len(fecha) >= 10:
                try: fecha = datetime.strptime(fecha[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
                except: pass
            self.cell(anchos[2], 6, fecha, 1, 0, 'C', True)
            
            fecha_vence = doc.get('fecha_vence', '')
            if len(fecha_vence) >= 10:
                try: fecha_vence = datetime.strptime(fecha_vence[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
                except: pass
            self.cell(anchos[3], 6, fecha_vence, 1, 0, 'C', True)
            
            trans = doc.get('tipo_codigo', '')
            self.cell(anchos[4], 6, trans, 1, 0, 'C', True)
            
            desc = doc.get('descripcion', '')[:80]
            self.cell(anchos[5], 6, desc, 1, 0, 'L', True)
            
            monto_str = f"{simbolo} {formato_latino(abs(saldo))}"
            if saldo < 0: monto_str = f"({monto_str})"
            self.cell(anchos[6], 6, monto_str, 1, 0, 'R', True)
            
            if saldo < 0:
                estatus = 'A favor'
                self.set_text_color(*VERDE)
            elif esta_vencido:
                estatus = 'Vencido'
                self.set_text_color(*ROJO)
            else:
                estatus = 'Al día'
                self.set_text_color(*VERDE)
                
            self.set_font('Arial', 'B', 8)
            self.cell(anchos[7], 6, estatus, 1, 1, 'C', True)
            self.set_text_color(0, 0, 0)
            self.set_font('Arial', '', 8)

        self.ln(8)

    def _imprimir_encabezados_tabla(self, anchos, headers):
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(220, 220, 220)
        self.set_text_color(0, 0, 0)
        for i, header in enumerate(headers):
            self.cell(anchos[i], 7, header, 1, 0, 'C', True)
        self.ln()


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def generar_pdf_reporte_gira(datos: Dict, output_dir: str = 'data/reportes_gira') -> str:
    """
    Genera el PDF del Reporte de Gira para un agente.
    
    Args:
        datos: Dict con estructura:
               {
                   'agente': {'codigo': '...', 'nombre': '...', 'zonas': '...'},
                   'totales_agente': {'dolares': 0, 'colones': 0},
                   'clientes': [
                       {
                           'cliente': {...}, 
                           'documentos': {'dolares': [], 'colones': []}, 
                           'totales': {'dolares': 0, 'colones': 0}
                       }, ...
                   ]
               }
        output_dir: Directorio donde guardar el PDF
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Generar QR para el agente
    qr_path = generar_qr_agente(datos.get('agente', {}), datos.get('totales_agente', {}))
    
    # Crear PDF
    pdf = PDFReporteGira()
    if qr_path:
        pdf.set_qr_path(qr_path)
        
    pdf.add_page()
    
    # Info del Vendedor (Cabecera Principal)
    pdf.agregar_info_agente(datos.get('agente', {}), datos.get('totales_agente', {}))
    
    # Iterar sobre cada cliente asignado al agente
    for cliente_data in datos.get('clientes', []):
        # 1. Separador visual del cliente
        pdf.agregar_separador_cliente(cliente_data['cliente'], cliente_data['totales'])
        
        # 2. Tabla de facturas del cliente
        pdf.agregar_tabla_documentos(
            cliente_data['documentos']['dolares'],
            cliente_data['documentos']['colones']
        )
    
    # Generar nombre de archivo
    codigo_agente = datos['agente'].get('codigo', 'DESC')
    nombre_agente = datos['agente'].get('nombre', 'Agente').replace(' ', '_')[:20]
    fecha = datetime.now().strftime('%Y%m%d')
    filename = f"GIRA_{codigo_agente}_{nombre_agente}_{fecha}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    # Guardar
    pdf.output(filepath)
    
    # Limpiar archivo temporal del QR
    if qr_path and os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except:
            pass
            
    return filepath