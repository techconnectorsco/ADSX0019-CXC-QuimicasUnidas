"""
Módulo generarpdf.py - Químicas Unidas
Genera PDFs de estados de cuenta usando fpdf.
Adaptado del proyecto Vedova y Obando.
"""

import os
from datetime import datetime
from fpdf import FPDF
from collections import defaultdict

try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


class PDF(FPDF):
    """
    Clase PDF para estados de cuenta de Químicas Unidas.
    """

    def __init__(self, logo_path='images/QU.png', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.qr_data = None  # Aquí guardaremos la info del cliente para el QR
        self.logo_path = logo_path  # Recibe la ruta del logo dinámicamente

    def header(self):
        """Cabecera del PDF con logo, título, fecha y QR de validación."""
        # Logo de empresa
        if os.path.exists(self.logo_path):
            self.image(self.logo_path, 5, self.get_y(), 50)
        else:
            self.set_font('Arial', 'B', 8)
            self.set_xy(5, 10)
            self.cell(50, 10, "[LOGO NO ENCONTRADO]", border=1, align='C')

        self.set_font('Arial', 'B', 14)
        self.cell(0, 9, 'Quimicas Unidas S.A.', ln=1, align='C')
        self.cell(0, 6, '', ln=1, align='C')
        self.cell(0, 9, 'Estado de Cuenta Clientes.', ln=1, align='C')
        self.ln(2)

        # Fecha y hora
        current_datetime = datetime.now()
        self.set_font('Arial', 'B', 10)
        fecha_hora = f'Fecha: {current_datetime.strftime("%d/%m/%Y")}  Hora: {current_datetime.strftime("%I:%M %p")}'
        self.set_xy(-70, self.get_y())
        self.cell(60, 23, fecha_hora, 0, 1, 'R')

        # QR con información del cliente
        if QR_AVAILABLE and self.qr_data:
            self._agregar_qr_cliente()

    def _agregar_qr_cliente(self):
        """Genera y agrega QR con datos del cliente al header."""
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(self.qr_data)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        qr_img_path = 'temp_qr.png'
        img_qr.save(qr_img_path)
        self.image(qr_img_path, self.w - 40, 15, 25)

        self.set_text_color(100, 100, 100)
        self.set_xy(self.w - 40, 42)
        self.set_font('Arial', '', 7)
        self.cell(25, 0, "Datos del Cliente", align="C")
        self.set_text_color(0, 0, 0)

        # Limpiar imagen temporal
        if os.path.exists(qr_img_path):
            os.remove(qr_img_path)

    def footer(self):
            """Pie de página con franja y fondo azul."""
            footer_height = 20
            page_width = self.w
            y_base = self.h - footer_height

            # Franja fina (#288fcc)
            self.set_fill_color(40, 143, 204)
            self.rect(0, y_base - 3, page_width, 3, 'F')

            # Fondo parte más gruesa (#475da4)
            self.set_fill_color(71, 93, 164)
            self.rect(0, y_base, page_width, footer_height, 'F')

            # Texto footer
            self.set_text_color(255, 255, 255)
            self.set_font('Arial', '', 9)
            texto_footer = (
                "Cuentas por Cobrar | 0000-0000 Ext 000 |\n"
                "Reportar los pagos al correo cxc@quimicasunidas.com"
            )
            self.set_y(y_base + 4)
            self.set_x(10)
            self.multi_cell(page_width - 20, 4.5, texto_footer, align='C')

            # Número de página
            self.set_font('Arial', 'BI', 8)
            self.set_y(-7)
            self.cell(0, 5, f'Pagina {self.page_no()} de {{nb}}', 0, 0, 'R')
            self.set_text_color(0, 0, 0)

    def chapter_title(self, cliente_id_nombre, telefono, contacto, direccion, email):
        """Información del cliente."""
        self.ln(8)

        campos = [
            ("Cliente:", cliente_id_nombre),
            ("Telefono:", telefono),
            ("Correo:", email),
            ("Direccion:", direccion),
            ("Contacto:", contacto),
        ]

        for etiqueta, valor in campos:
            self.set_font('Arial', 'B', 10)
            self.cell(20, 7, etiqueta, ln=False)
            self.set_font('Arial', '', 10)
            self.cell(0, 7, str(valor) if valor else "No especificado", ln=True)

        self.ln(4)

    def add_table(self, data):
        """
        Agrega tabla de documentos.

        Args:
            data: Lista de listas con [documento, fecha_doc, fecha_vence, monto, saldo, moneda, tipo]

        Returns:
            Tuple (saldo_por_moneda, documentos_en_tabla)
        """
        self.set_font('Arial', 'B', 9)
        col_widths = [38, 32, 30, 31, 31, 23]
        headers = ["DOCUMENTO", "FECHA FACTURA", "FECHA VENCE", "MONTO FACTURA", "SALDO FACTURA", "MONEDA"]

        for header, width in zip(headers, col_widths):
            self.cell(width, 8, header, border='TB', align="C")
        self.ln()

        self.set_font('Arial', '', 9)
        documentos_en_tabla = 0
        saldo_por_moneda = {}

        def parse_fecha(fecha):
            if isinstance(fecha, str):
                for fmt in ['%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(fecha.split(" ")[0], fmt)
                    except ValueError:
                        continue
                return datetime.min
            return fecha if isinstance(fecha, datetime) else datetime.min

        data_ordenada = sorted(data, key=lambda x: (x[5], parse_fecha(x[1])))
        tipos_que_restan = {"DEP", "N", "N/C", "NC", "REC", "TEF", "O/C", "RC"}
        hoy = datetime.now()

        for row in data_ordenada:
            documento = str(row[0])
            fecha_factura = row[1].split(" ")[0] if isinstance(row[1], str) else row[1].strftime('%d/%m/%Y')
            fecha_venc = row[2].split(" ")[0] if isinstance(row[2], str) else row[2].strftime('%d/%m/%Y')
            monto = float(row[3])
            saldo = float(row[4])
            moneda_doc = str(row[5])
            tipo = str(row[6]).strip().upper()

            # Calcular días vencido
            fecha_venc_dt = parse_fecha(row[2])
            dias_vencido = (hoy - fecha_venc_dt).days if fecha_venc_dt != datetime.min else 0

            if tipo in tipos_que_restan:
                monto = -monto
                saldo = -saldo

            if moneda_doc not in saldo_por_moneda:
                saldo_por_moneda[moneda_doc] = 0.0
            saldo_por_moneda[moneda_doc] += saldo
            documentos_en_tabla += 1

            # Color ROJO si está vencido
            if dias_vencido > 0 and tipo not in tipos_que_restan:
                self.set_text_color(220, 53, 69)
            else:
                self.set_text_color(0, 0, 0)

            fila = [documento, fecha_factura, fecha_venc, f"{monto:,.2f}", f"{saldo:,.2f}", moneda_doc]

            for value, width in zip(fila, col_widths):
                self.cell(width, 8, value, border='TB', align="C")
            self.ln()

            self.set_text_color(0, 0, 0)

            if self.get_y() > 260:
                self.add_page()
                self.ln(15)

        # Totales por moneda
        self.set_font('Arial', 'B', 9)
        for moneda, total in saldo_por_moneda.items():
            self.cell(sum(col_widths[:-2]), 8, f"TOTAL SALDO EN {moneda}", align="R")
            self.cell(col_widths[-2], 8, f"{total:,.2f}", align="C")
            self.cell(col_widths[-1], 8, moneda, align="C")
            self.ln(6)

        if 17 <= len(data_ordenada) <= 20:
            self.add_page()
            self.ln(10)

        self.ln(5)
        self.add_vencimientos(data)

        return saldo_por_moneda, documentos_en_tabla

    def add_vencimientos(self, data):
        """Tabla de control de atraso por rangos de días."""
        self.set_font('Arial', 'B', 10)
        self.cell(0, 10, 'Control de Atraso (a la fecha final del reporte)', ln=1, align='C')

        headers = ['NO VENCIDO', '1-15 dias', '16-30 dias', '31-60 dias', '61-90 dias', '91-180 dias', '+180 dias']
        col_widths = [28, 26, 26, 26, 26, 26, 27]

        self.set_font('Arial', 'B', 9)
        for header, width in zip(headers, col_widths):
            self.cell(width, 10, header, border="TB", align='C')
        self.ln()

        hoy = datetime.now()
        tipos_que_restan = {"DEP", "N", "N/C", "NC", "REC", "TEF", "RC"}

        docs_por_moneda = defaultdict(list)
        for row in data:
            docs_por_moneda[row[5]].append(row)

        self.set_font('Arial', '', 9)

        for moneda, lista in docs_por_moneda.items():
            rangos = [0.0] * 7  # no_vencido, 1-15, 16-30, 31-60, 61-90, 91-180, +180

            for row in lista:
                tipo = str(row[6]).strip().upper()
                if tipo in tipos_que_restan:
                    continue

                fecha_venc = row[2]
                saldo = float(row[4])

                if isinstance(fecha_venc, str):
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            fecha_venc = datetime.strptime(fecha_venc.split(" ")[0], fmt)
                            break
                        except ValueError:
                            continue

                if not isinstance(fecha_venc, datetime):
                    continue

                dias_venc = (hoy - fecha_venc).days

                if dias_venc <= 0:
                    rangos[0] += saldo
                elif dias_venc <= 15:
                    rangos[1] += saldo
                elif dias_venc <= 30:
                    rangos[2] += saldo
                elif dias_venc <= 60:
                    rangos[3] += saldo
                elif dias_venc <= 90:
                    rangos[4] += saldo
                elif dias_venc <= 180:
                    rangos[5] += saldo
                else:
                    rangos[6] += saldo

            for valor, width in zip(rangos, col_widths):
                self.cell(width, 10, f"{moneda} {valor:,.2f}", border='TB', align='C')
            self.ln()

        self.ln(5)


class LogPDF(FPDF):
    """Clase para generar log PDF de correos enviados."""

    def __init__(self):
        super().__init__()
        self.headers_added = False

    def header(self):
        if not self.headers_added:
            if os.path.exists('logo_quimicas_unidas.png'):
                self.image('logo_quimicas_unidas.png', 5, self.get_y(), 50)

            self.set_font('Arial', 'B', 14)
            self.cell(0, 8, 'Control de Correos Enviados', ln=1, align='C')
            self.cell(0, 6, 'Quimicas Unidas S.A.', ln=1, align='C')

            current_datetime = datetime.now()
            self.set_font('Arial', '', 10)
            fecha_hora = f'Fecha: {current_datetime.strftime("%d/%m/%Y")}  Hora: {current_datetime.strftime("%I:%M %p")}'
            self.set_xy(-70, self.get_y())
            self.cell(60, 10, fecha_hora, 0, 1, 'R')

            self.ln(5)
            self.set_font('Arial', 'B', 10)
            self.ln(10)
            self.cell(80, 10, "Nombre - Codigo", border=1, align='C')
            self.cell(60, 10, "Correo Electronico", border=1, align='C')
            self.cell(15, 10, "Enviado", border=1, align='C')
            self.cell(35, 10, "Error", border=1, align='C')
            self.ln(10)
            self.headers_added = True

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(0)
        self.set_line_width(0.3)
        self.line(6, self.get_y(), 200, self.get_y())
        self.set_y(-12)
        self.set_font('Arial', 'B', 10)
        self.cell(0, 10, f'Pagina {self.page_no()} de {{nb}}', 0, 0, 'L')
        self.cell(0, 10, 'cxc@quimicasunidas.com', 0, 0, 'R')

    def add_log_entry(self, nombre_codigo, email, status, error_message=None):
        """Agrega una entrada al log."""
        self.set_font('Arial', '', 9)

        if self.get_y() > 260:
            self.add_page()

        self.cell(80, 8, nombre_codigo[:40], border=1, align='C')
        self.cell(60, 8, email[:40] if email else "SIN CORREO", border=1, align='C')
        self.cell(15, 8, status, border=1, align='C')
        self.cell(35, 8, (error_message if error_message else 'N/A')[:45], border=1, align='C')
        self.ln()
