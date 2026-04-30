"""
generarpdf.py - Químicas Unidas
Generación de PDFs para Estados de Cuenta.

Características:
- Orientación horizontal (landscape) tamaño carta
- Todos los campos: Consecutivo FE, Descripción, Serie, Tipo, Estatus
- Sin columna "Saldo Acumulado" (confunde)
- Vencidos en ROJO
- Diseño limpio y profesional
"""

from fpdf import FPDF
from datetime import datetime
from typing import List, Dict
import os


# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

# Colores corporativos
AZUL_OSCURO = (11, 17, 75)       # Header, títulos
AZUL_CLARO = (40, 143, 204)      # Línea decorativa
AZUL_FOOTER = (71, 93, 164)      # Fondo footer
ROJO = (220, 53, 69)             # Vencidos
VERDE = (40, 167, 69)            # Al día
GRIS = (100, 100, 100)           # Textos secundarios
GRIS_CLARO = (245, 245, 245)     # Fondo alternado


# =============================================================================
# CLASE PRINCIPAL - PDF ESTADO DE CUENTA
# =============================================================================

class PDFEstadoCuenta(FPDF):
    """
    Genera PDF de Estado de Cuenta en formato horizontal.
    """

    def __init__(self, logo_path: str = 'images/QU.png'):
        # Landscape Letter: 279.4mm x 215.9mm
        super().__init__(orientation='L', unit='mm', format='Letter')
        self.logo_path = logo_path
        self.datos_cliente = {}
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)
        
    def header(self):
        """Encabezado con logo, título y fecha."""
        # Logo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 10, 8, 45)
        
        # Título
        self.set_font('Arial', 'B', 16)
        self.set_text_color(*AZUL_OSCURO)
        self.set_xy(60, 12)
        self.cell(0, 8, 'Químicas Unidas S.A.', 0, 1, 'L')
        
        self.set_font('Arial', 'B', 14)
        self.set_xy(60, 20)
        self.cell(0, 6, 'Estado de Cuenta', 0, 1, 'L')
        
        # Fecha y hora (derecha)
        self.set_font('Arial', '', 10)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime('%d/%m/%Y')
        hora = datetime.now().strftime('%I:%M %p')
        self.set_xy(-70, 12)
        self.cell(60, 5, f'Fecha: {fecha}', 0, 1, 'R')
        self.set_xy(-70, 17)
        self.cell(60, 5, f'Hora: {hora}', 0, 1, 'R')
        
        # Línea decorativa
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.8)
        self.line(10, 32, self.w - 10, 32)
        
        self.set_y(35)

    def footer(self):
        """Pie de página con información de contacto."""
        # Posición a 20mm del final
        self.set_y(-20)
        
        # Franja azul claro
        self.set_fill_color(*AZUL_CLARO)
        self.rect(0, self.h - 20, self.w, 3, 'F')
        
        # Fondo azul oscuro
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(0, self.h - 17, self.w, 17, 'F')
        
        # Texto
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', '', 9)
        self.set_y(-15)
        self.cell(0, 4, 'Departamento de Crédito y Cobro | Tel: 2257-8484 ext. 216-217', 0, 1, 'C')
        self.cell(0, 4, 'Correo: cxc@quimicasunidas.com | WhatsApp: 0000-0000', 0, 1, 'C')
        
        # Número de página
        self.set_font('Arial', 'I', 8)
        self.set_xy(-30, -7)
        self.cell(20, 5, f'Página {self.page_no()}', 0, 0, 'R')

    def agregar_datos_cliente(self, cliente: Dict):
        """
        Agrega sección con información del cliente.
        """
        self.datos_cliente = cliente
        
        # Fondo gris para la sección
        y_inicio = self.get_y()
        self.set_fill_color(*GRIS_CLARO)
        self.rect(10, y_inicio, self.w - 20, 28, 'F')
        
        # Borde izquierdo decorativo
        self.set_fill_color(*AZUL_OSCURO)
        self.rect(10, y_inicio, 3, 28, 'F')
        
        self.set_xy(15, y_inicio + 2)
        
        # Fila 1: Cliente y Código
        self.set_font('Arial', 'B', 11)
        self.set_text_color(*AZUL_OSCURO)
        self.cell(15, 6, 'Cliente:', 0, 0)
        self.set_font('Arial', '', 11)
        self.set_text_color(0, 0, 0)
        nombre = f"{cliente.get('codigo', '')} - {cliente.get('nombre', '')}"
        self.cell(120, 6, nombre[:60], 0, 0)
        
        # Límite de crédito
        self.set_font('Arial', 'B', 10)
        self.cell(30, 6, 'Límite Crédito:', 0, 0)
        self.set_font('Arial', '', 10)
        limite = cliente.get('limite_credito', 0)
        self.cell(40, 6, f'CRC {limite:,.2f}', 0, 1)
        
        # Fila 2: Teléfono y Contacto
        self.set_x(15)
        self.set_font('Arial', 'B', 10)
        self.cell(18, 5, 'Teléfono:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(50, 5, cliente.get('telefono', '') or 'No registrado', 0, 0)
        
        self.set_font('Arial', 'B', 10)
        self.cell(18, 5, 'Contacto:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(50, 5, cliente.get('contacto', '') or 'No especificado', 0, 0)
        
        # Condición de pago
        self.set_font('Arial', 'B', 10)
        self.cell(25, 5, 'Cond. Pago:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 5, cliente.get('condicion_pago', ''), 0, 1)
        
        # Fila 3: Correo y Vendedor
        self.set_x(15)
        self.set_font('Arial', 'B', 10)
        self.cell(14, 5, 'Correo:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(80, 5, cliente.get('correo', '') or 'No registrado', 0, 0)
        
        self.set_font('Arial', 'B', 10)
        self.cell(18, 5, 'Vendedor:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 5, cliente.get('vendedor', ''), 0, 1)
        
        # Fila 4: Dirección
        self.set_x(15)
        self.set_font('Arial', 'B', 10)
        self.cell(18, 5, 'Dirección:', 0, 0)
        self.set_font('Arial', '', 10)
        direccion = cliente.get('direccion', '') or 'No registrada'
        self.cell(0, 5, direccion[:100], 0, 1)
        
        self.ln(5)

    def agregar_tabla_documentos(self, documentos: List[Dict], moneda: str, total: float):
        """
        Agrega tabla de documentos para una moneda.
        
        Args:
            documentos: Lista de documentos procesados
            moneda: 'USD' o 'CRC'
            total: Total del saldo
        """
        if not documentos:
            return
        
        simbolo = '$' if moneda == 'USD' else 'CRC'
        
        # Verificar espacio disponible
        if self.get_y() > self.h - 60:
            self.add_page()
        
        # Título de sección
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(*AZUL_OSCURO)
        self.set_text_color(255, 255, 255)
        self.cell(self.w - 20, 7, f'  DOCUMENTOS EN {moneda}', 0, 1, 'L', True)
        
        # Encabezados de columnas
        # Anchos: Tipo(20) + Consecutivo(45) + Descripción(60) + Serie(35) + Fecha(22) + Vence(22) + Monto(28) + Saldo(28) + Estado(18) = 278
        anchos = [20, 45, 55, 35, 22, 22, 27, 27, 22]
        headers = ['Tipo', 'Consecutivo FE', 'Descripción', 'Serie', 'Fecha', 'Vence', 'Monto', 'Saldo', 'Estado']
        
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(220, 220, 220)
        self.set_text_color(0, 0, 0)
        
        for i, header in enumerate(headers):
            self.cell(anchos[i], 6, header, 1, 0, 'C', True)
        self.ln()
        
        # Filas de datos
        self.set_font('Arial', '', 8)
        fila_par = False
        
        for doc in documentos:
            # Verificar salto de página
            if self.get_y() > self.h - 35:
                self.add_page()
                # Repetir encabezados
                self.set_font('Arial', 'B', 8)
                self.set_fill_color(220, 220, 220)
                for i, header in enumerate(headers):
                    self.cell(anchos[i], 6, header, 1, 0, 'C', True)
                self.ln()
                self.set_font('Arial', '', 8)
            
            # Color de fondo alternado
            if fila_par:
                self.set_fill_color(250, 250, 250)
            else:
                self.set_fill_color(255, 255, 255)
            fila_par = not fila_par
            
            # Determinar si está vencido
            esta_vencido = doc.get('esta_vencido', False)
            saldo = doc.get('saldo', 0)
            
            # Color de texto según estado
            if esta_vencido and saldo > 0:
                self.set_text_color(*ROJO)
                self.set_font('Arial', 'B', 8)
            else:
                self.set_text_color(0, 0, 0)
                self.set_font('Arial', '', 8)
            
            # Tipo
            tipo = doc.get('tipo_texto', doc.get('tipo_codigo', ''))[:10]
            self.cell(anchos[0], 5, tipo, 1, 0, 'L', True)
            
            # Consecutivo FE
            consecutivo = doc.get('consecutivo_fe', '')
            if not consecutivo:
                consecutivo = str(doc.get('doc_num', ''))
            # Mostrar últimos 20 caracteres
            if len(consecutivo) > 20:
                consecutivo = '...' + consecutivo[-17:]
            self.cell(anchos[1], 5, consecutivo, 1, 0, 'C', True)
            
            # Descripción
            descripcion = doc.get('descripcion', '')[:28]
            self.cell(anchos[2], 5, descripcion, 1, 0, 'L', True)
            
            # Serie
            series = doc.get('series', [])
            serie_texto = series[0][:18] if series else ''
            self.cell(anchos[3], 5, serie_texto, 1, 0, 'C', True)
            
            # Fecha documento
            fecha = doc.get('fecha', '')
            if fecha and len(fecha) >= 10:
                try:
                    fecha_dt = datetime.strptime(fecha[:10], '%Y-%m-%d')
                    fecha = fecha_dt.strftime('%d/%m/%y')
                except:
                    pass
            self.cell(anchos[4], 5, fecha, 1, 0, 'C', True)
            
            # Fecha vencimiento
            fecha_vence = doc.get('fecha_vence', '')
            if fecha_vence and len(fecha_vence) >= 10:
                try:
                    fecha_dt = datetime.strptime(fecha_vence[:10], '%Y-%m-%d')
                    fecha_vence = fecha_dt.strftime('%d/%m/%y')
                except:
                    pass
            self.cell(anchos[5], 5, fecha_vence, 1, 0, 'C', True)
            
            # Monto
            monto = doc.get('total', 0)
            monto_str = f'{simbolo}{abs(monto):,.2f}'
            self.cell(anchos[6], 5, monto_str, 1, 0, 'R', True)
            
            # Saldo
            saldo_str = f'{simbolo}{abs(saldo):,.2f}'
            if saldo < 0:
                saldo_str = f'({saldo_str})'
            self.cell(anchos[7], 5, saldo_str, 1, 0, 'R', True)
            
            # Estado
            if saldo < 0:
                estado = 'A favor'
                self.set_text_color(*VERDE)
            elif esta_vencido:
                estado = 'Vencido'
                self.set_text_color(*ROJO)
            else:
                estado = 'Al día'
                self.set_text_color(*VERDE)
            
            self.set_font('Arial', 'B', 8)
            self.cell(anchos[8], 5, estado, 1, 1, 'C', True)
            
            # Reset color
            self.set_text_color(0, 0, 0)
            self.set_font('Arial', '', 8)
        
        # Fila de total
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(*AZUL_OSCURO)
        self.set_text_color(255, 255, 255)
        
        ancho_label = sum(anchos[:-2])
        self.cell(ancho_label, 6, f'TOTAL {moneda}:', 1, 0, 'R', True)
        self.cell(anchos[-2], 6, f'{simbolo}{total:,.2f}', 1, 0, 'R', True)
        self.cell(anchos[-1], 6, '', 1, 1, 'C', True)
        
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def agregar_resumen_vencimientos(self, rangos: Dict, moneda: str):
        """
        Agrega tabla resumen de vencimientos por rangos.
        
        Args:
            rangos: Dict con totales por rango de días
            moneda: 'USD' o 'CRC'
        """
        r = rangos.get(moneda, {})
        
        # Verificar si hay datos
        total = sum(r.values()) if r else 0
        if total == 0:
            return
        
        simbolo = '$' if moneda == 'USD' else 'CRC'
        
        # Verificar espacio
        if self.get_y() > self.h - 45:
            self.add_page()
        
        # Título
        self.set_font('Arial', 'B', 10)
        self.set_text_color(*AZUL_OSCURO)
        self.cell(0, 6, f'Resumen de Vencimientos ({moneda})', 0, 1, 'L')
        
        # Encabezados
        labels = ['No Vencido', '1-15 días', '16-30 días', '31-60 días', '61-90 días', '91-180 días', '+180 días']
        keys = ['no_vencido', '1_15', '16_30', '31_60', '61_90', '91_180', 'mas_180']
        ancho = 38
        
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(220, 220, 220)
        for label in labels:
            self.cell(ancho, 5, label, 1, 0, 'C', True)
        self.ln()
        
        # Valores
        self.set_font('Arial', '', 8)
        for key in keys:
            valor = r.get(key, 0)
            if valor > 0:
                self.set_fill_color(255, 230, 230)  # Rojo claro si tiene saldo
            else:
                self.set_fill_color(255, 255, 255)
            self.cell(ancho, 5, f'{simbolo}{valor:,.2f}', 1, 0, 'C', True)
        self.ln()
        
        self.ln(3)


# =============================================================================
# FUNCIÓN PRINCIPAL PARA GENERAR PDF
# =============================================================================

def generar_pdf_estado_cuenta(datos: Dict, output_dir: str = 'data/estados_cuenta') -> str:
    """
    Genera el PDF de estado de cuenta para un cliente.
    
    Args:
        datos: Dict con estructura de preparar_datos_cliente() del main.py
        output_dir: Directorio donde guardar el PDF
    
    Returns:
        Ruta del archivo PDF generado
    """
    # Crear directorio si no existe
    os.makedirs(output_dir, exist_ok=True)
    
    # Crear PDF
    pdf = PDFEstadoCuenta()
    pdf.add_page()
    
    # Datos del cliente
    pdf.agregar_datos_cliente(datos['cliente'])
    
    # Tabla de dólares (primero si hay)
    if datos['documentos']['dolares']:
        pdf.agregar_tabla_documentos(
            datos['documentos']['dolares'],
            'USD',
            datos['totales']['dolares']
        )
        pdf.agregar_resumen_vencimientos(datos['rangos_vencimiento'], 'USD')
    
    # Tabla de colones
    if datos['documentos']['colones']:
        pdf.agregar_tabla_documentos(
            datos['documentos']['colones'],
            'CRC',
            datos['totales']['colones']
        )
        pdf.agregar_resumen_vencimientos(datos['rangos_vencimiento'], 'CRC')
    
    # Generar nombre de archivo
    codigo = datos['cliente']['codigo']
    nombre = datos['cliente']['nombre'].replace(' ', '_')[:20]
    fecha = datetime.now().strftime('%Y%m%d')
    filename = f"EC_{codigo}_{nombre}_{fecha}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    # Guardar
    pdf.output(filepath)
    
    return filepath