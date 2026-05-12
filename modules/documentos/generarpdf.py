"""
generarpdf.py - Químicas Unidas
Generación de PDFs para Estados de Cuenta.

Características:
- Orientación horizontal tamaño OFICIO (Legal)
- Tabla unificada (Primero USD, luego CRC)
- Columnas Reordenadas y truncadas
- Formato de moneda Latinoamericano (puntos para miles, comas para decimales)
- QR de validación con datos del documento
"""

from fpdf import FPDF
from datetime import datetime
from typing import List, Dict
import os
import tempfile

# Intentar importar qrcode
try:
    import qrcode

    QR_DISPONIBLE = True
except ImportError:
    QR_DISPONIBLE = False

# =============================================================================
# CONSTANTES Y CONFIGURACIÓN DE COLORES
# =============================================================================

AZUL_OSCURO = (11, 17, 75)  # Header, títulos
AZUL_CLARO = (40, 143, 204)  # Línea decorativa
AZUL_FOOTER = (71, 93, 164)  # Fondo footer
ROJO = (220, 53, 69)  # Vencidos
VERDE = (40, 167, 69)  # Al día
GRIS = (100, 100, 100)  # Textos secundarios
GRIS_CLARO = (245, 245, 245)  # Fondo alternado

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================


def formato_latino(valor: float) -> str:
    """
    Convierte el formato US (1,234.56) a formato Latino (1.234,56).
    Es 100% seguro sin importar el idioma del sistema operativo.
    """
    if valor is None:
        valor = 0.0
    num_str = f"{abs(valor):,.2f}"
    num_str = num_str.replace(",", "X")
    num_str = num_str.replace(".", ",")
    num_str = num_str.replace("X", ".")
    return num_str


def generar_qr_validacion(
    datos_cliente: Dict, docs_usd: List, docs_crc: List, totales: Dict
) -> str:
    """
    Genera un código QR con información de validación del documento.

    Returns:
        Ruta al archivo temporal del QR o None si no está disponible
    """
    if not QR_DISPONIBLE:
        return None

    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    codigo_verificacion = f"QU-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Construir contenido del QR
    contenido = []
    contenido.append("══════════════════════════════════════════════════════════")
    contenido.append("   QUÍMICAS UNIDAS Ltda.")
    contenido.append("   Estado de Cuenta")
    contenido.append("═════════════════════════════")
    contenido.append("")
    contenido.append(f"Cliente: {datos_cliente.get('codigo', '')}")
    contenido.append(f"{datos_cliente.get('nombre', '')}")
    contenido.append("")
    contenido.append(f"Emisión: {fecha_emision}")
    contenido.append("")

    # Documentos USD
    cant_usd = len(docs_usd) if docs_usd else 0
    total_usd = totales.get("dolares", 0)
    if cant_usd > 0:
        contenido.append(f"DÓLARES (USD):")
        contenido.append(f"  {cant_usd} documento(s)")
        contenido.append(f"  Total: USD {formato_latino(total_usd)}")
        contenido.append("")

    # Documentos CRC
    cant_crc = len(docs_crc) if docs_crc else 0
    total_crc = totales.get("colones", 0)
    if cant_crc > 0:
        contenido.append(f"COLONES (CRC):")
        contenido.append(f"  {cant_crc} documento(s)")
        contenido.append(f"  Total: CRC {formato_latino(total_crc)}")
        contenido.append("")

    contenido.append("══════════════════════════════════════════════════════════")
    contenido.append("Crédito y Cobro:")
    contenido.append("Tel: 2257-8484 ext. 216-217")
    contenido.append("credito@qu.cr")
    contenido.append("creditodenis@qu.cr")
    contenido.append("══════════════════════════════════════════════════════════")
    contenido.append("")
    contenido.append(f"Verificación: {codigo_verificacion}")

    contenido_qr = "\n".join(contenido)

    # Generar QR
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(contenido_qr)
    qr.make(fit=True)

    img_qr = qr.make_image(fill_color="black", back_color="white")

    # Guardar en archivo temporal
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img_qr.save(temp_file.name)
    temp_file.close()

    return temp_file.name


# =============================================================================
# CLASE PRINCIPAL - PDF ESTADO DE CUENTA
# =============================================================================


class PDFEstadoCuenta(FPDF):

    def __init__(self, logo_path: str = "images/QU.png"):
        super().__init__(orientation="L", unit="mm", format="Legal")
        self.logo_path = logo_path
        self.qr_path = None  # Se establecerá antes de agregar página
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)

    def set_qr_path(self, qr_path: str):
        """Establece la ruta del QR para el header."""
        self.qr_path = qr_path

    def header(self):
        # Logo izquierdo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 15, 8, 45)

        # Título centrado
        self.set_font("Arial", "B", 18)
        self.set_text_color(*AZUL_FOOTER)
        self.set_y(12)
        self.cell(0, 8, "Químicas Unidas Ltda.", 0, 1, "C")

        self.set_font("Arial", "B", 15)
        self.cell(0, 6, "Estado de Cuenta", 0, 1, "C")

        # Fecha y hora (antes del QR)
        self.set_font("Arial", "", 10)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime("%I:%M %p")
        self.set_xy(-95, 12)
        self.cell(50, 5, f"Fecha: {fecha}", 0, 1, "R")
        self.set_xy(-95, 17)
        self.cell(50, 5, f"Hora: {hora}", 0, 1, "R")

        # QR de validación (esquina superior derecha)
        if self.qr_path and os.path.exists(self.qr_path):
            self.image(self.qr_path, self.w - 38, 5, 30)
            # Texto pequeño debajo del QR
            self.set_font("Arial", "I", 6)
            self.set_text_color(*GRIS)
            self.set_xy(self.w - 40, 36)
            self.cell(32, 3, "Escanear para validar", 0, 0, "C")

        # Línea decorativa
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.99)
        self.line(10, 40, self.w - 10, 40)

        self.set_y(43)

    def footer(self):
        self.set_y(-23)

        # Franja azul claro superior
        self.set_fill_color(*AZUL_CLARO)
        self.rect(0, self.h - 24, self.w, 3, "F")

        # Fondo azul oscuro principal
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(0, self.h - 22, self.w, 22, "F")

        self.set_text_color(255, 255, 255)

        # Bloque central (Contacto Químicas Unidas)
        self.set_font("Arial", "B", 11)
        self.set_y(-18)
        self.cell(
            0,
            5,
            "Departamento de Crédito y Cobros | Tel: 2257-8484 ext. 207-208",
            0,
            1,
            "C",
        )
        self.cell(0, 5, "Correos: credito@qu.cr | creditodenis@qu.cr", 0, 1, "C")

        # Bloque izquierdo (Publicidad SX)
        self.set_font("Arial", "BI", 8)
        self.set_xy(10, -17)
        self.cell(80, 5, "Oficina de Transformación Digital SX", 0, 0, "L")

        self.set_font("Arial", "I", 8)
        self.set_xy(10, -13)
        self.cell(80, 5, "SOPORTEXPERTO.COM", 0, 0, "L")

        # Bloque derecho (Paginación)
        self.set_font("Arial", "I", 10)
        self.set_xy(-30, -13)
        self.cell(20, 5, f"Página {self.page_no()}", 0, 0, "R")

    def agregar_datos_cliente(self, cliente: Dict):
        y_inicio = self.get_y()
        self.set_fill_color(*GRIS_CLARO)
        self.rect(10, y_inicio, self.w - 20, 22, "F")
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(10, y_inicio, 3, 22, "F")

        self.set_xy(15, y_inicio + 3)
        self.set_font("Arial", "B", 10)

        self.set_text_color(*AZUL_FOOTER)
        self.cell(20, 5, "Cliente:", 0, 0)
        self.set_text_color(0, 0, 0)
        self.set_font("Arial", "", 10)
        nombre = f"{cliente.get('codigo', '')} - {cliente.get('nombre', '')}"
        self.cell(110, 5, nombre[:55], 0, 0)

        self.set_font("Arial", "B", 10)
        self.cell(25, 5, "Contacto:", 0, 0)
        self.set_font("Arial", "", 10)
        self.cell(80, 5, cliente.get("contacto", "") or "No especificado", 0, 0)

        self.set_font("Arial", "B", 10)
        self.cell(30, 5, "Límite Crédito:", 0, 0)
        self.set_font("Arial", "", 10)
        limite = cliente.get("limite_credito", 0)
        self.cell(0, 5, f"CRC {formato_latino(limite)}", 0, 1)

        self.set_x(15)
        self.set_font("Arial", "B", 10)
        self.cell(20, 5, "Correo:", 0, 0)
        self.set_font("Arial", "", 10)
        self.cell(110, 5, cliente.get("correo", "") or "No registrado", 0, 0)

        self.set_font("Arial", "B", 10)
        self.cell(25, 5, "Teléfono:", 0, 0)
        self.set_font("Arial", "", 10)
        self.cell(80, 5, cliente.get("telefono", "") or "No registrado", 0, 0)

        self.set_font("Arial", "B", 10)
        self.cell(30, 5, "Cond. Pago:", 0, 0)
        self.set_font("Arial", "", 10)
        self.cell(0, 5, cliente.get("condicion_pago", ""), 0, 1)

        self.set_x(15)
        self.set_font("Arial", "B", 10)
        self.cell(20, 5, "Dirección:", 0, 0)
        self.set_font("Arial", "", 10)
        direccion = cliente.get("direccion", "") or "No registrada"
        self.cell(110, 5, direccion[:70], 0, 0)

        self.set_font("Arial", "B", 10)
        self.cell(25, 5, "Vendedor:", 0, 0)
        self.set_font("Arial", "", 10)
        self.cell(0, 5, cliente.get("vendedor", ""), 0, 1)

        self.ln(6)

    def agregar_tabla_unica(
        self, docs_usd: List[Dict], docs_crc: List[Dict], totales: Dict
    ):
        todos_docs = []
        if docs_usd:
            todos_docs.extend(docs_usd)
        if docs_crc:
            todos_docs.extend(docs_crc)

        if not todos_docs:
            return

        anchos = [40, 25, 25, 32, 15, 135, 33, 28]
        headers = [
            "No de Doc",
            "No de Orden",
            "Fecha Factura",
            "Fecha Vencimiento",
            "Trans",
            "Descripción",
            "Monto Factura",
            "Estatus",
        ]

        self._imprimir_encabezados_tabla(anchos, headers)

        self.set_font("Arial", "", 8)
        fila_par = False

        for doc in todos_docs:
            if self.get_y() > self.h - 35:
                self.add_page()
                self._imprimir_encabezados_tabla(anchos, headers)
                self.set_font("Arial", "", 8)

            if fila_par:
                self.set_fill_color(250, 250, 250)
            else:
                self.set_fill_color(255, 255, 255)
            fila_par = not fila_par

            esta_vencido = doc.get("esta_vencido", False)
            saldo = doc.get("saldo", 0)
            moneda = doc.get("moneda", "")
            simbolo = "USD" if moneda == "USD" else "CRC"

            consecutivo = doc.get("consecutivo_fe", "") or str(doc.get("doc_num", ""))
            self.cell(anchos[0], 6, consecutivo, 1, 0, "C", True)

            orden = str(doc.get("orden_compra", ""))
            if len(orden) > 15:
                orden = orden[:12] + "..."
            self.cell(anchos[1], 6, orden, 1, 0, "C", True)

            fecha = doc.get("fecha", "")
            if len(fecha) >= 10:
                try:
                    fecha = datetime.strptime(fecha[:10], "%Y-%m-%d").strftime(
                        "%d/%m/%Y"
                    )
                except:
                    pass
            self.cell(anchos[2], 6, fecha, 1, 0, "C", True)

            fecha_vence = doc.get("fecha_vence", "")
            if len(fecha_vence) >= 10:
                try:
                    fecha_vence = datetime.strptime(
                        fecha_vence[:10], "%Y-%m-%d"
                    ).strftime("%d/%m/%Y")
                except:
                    pass
            self.cell(anchos[3], 6, fecha_vence, 1, 0, "C", True)

            trans = doc.get("tipo_codigo", "")
            self.cell(anchos[4], 6, trans, 1, 0, "C", True)

            desc = doc.get("descripcion", "")[:80]
            self.cell(anchos[5], 6, desc, 1, 0, "L", True)

            monto_str = f"{simbolo} {formato_latino(abs(saldo))}"
            if saldo < 0:
                monto_str = f"({monto_str})"
            self.cell(anchos[6], 6, monto_str, 1, 0, "R", True)

            if saldo < 0:
                estatus = "A favor"
                self.set_text_color(*VERDE)
            elif esta_vencido:
                estatus = "Vencido"
                self.set_text_color(*ROJO)
            else:
                estatus = "Al día"
                self.set_text_color(*VERDE)

            self.set_font("Arial", "B", 8)
            self.cell(anchos[7], 6, estatus, 1, 1, "C", True)

            self.set_text_color(0, 0, 0)
            self.set_font("Arial", "", 8)

        self.ln(2)
        ancho_blanco = sum(anchos[:-2])
        self.set_font("Arial", "B", 10)
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)

        if docs_usd:
            self.cell(ancho_blanco, 6, "TOTAL GENERAL USD:", 1, 0, "R", True)
            self.cell(
                anchos[-2] + anchos[-1],
                6,
                f"USD {formato_latino(totales['dolares'])}",
                1,
                1,
                "R",
                True,
            )

        if docs_crc:
            self.cell(ancho_blanco, 6, "TOTAL GENERAL COLONES:", 1, 0, "R", True)
            self.cell(
                anchos[-2] + anchos[-1],
                6,
                f"CRC {formato_latino(totales['colones'])}",
                1,
                1,
                "R",
                True,
            )

        self.set_text_color(0, 0, 0)
        self.ln(5)

    def _imprimir_encabezados_tabla(self, anchos, headers):
        self.set_font("Arial", "B", 9)
        self.set_fill_color(220, 220, 220)
        self.set_text_color(0, 0, 0)
        for i, header in enumerate(headers):
            self.cell(anchos[i], 7, header, 1, 0, "C", True)
        self.ln()

    def agregar_seccion_vencidos_unificada(self, rangos_usd: Dict, rangos_crc: Dict):
        vencido_usd = rangos_usd.get("total_vencido", 0) if rangos_usd else 0
        vencido_crc = rangos_crc.get("total_vencido", 0) if rangos_crc else 0

        if vencido_usd <= 0 and vencido_crc <= 0:
            return

        if self.get_y() > self.h - 75:
            self.add_page()

        w_tabla = 120
        gap = 20
        dibujar_usd = vencido_usd > 0
        dibujar_crc = vencido_crc > 0

        if dibujar_usd and dibujar_crc:
            ancho_bloque = (w_tabla * 2) + gap
        else:
            ancho_bloque = w_tabla

        x_inicio = (self.w - ancho_bloque) / 2
        y_tabla_inicio = self.get_y()

        def dibujar_tabla_individual(x_pos, rangos, moneda_texto, prefijo, total_v):
            self.set_xy(x_pos, y_tabla_inicio)

            self.set_font("Arial", "B", 9)
            self.set_text_color(*AZUL_FOOTER)
            titulo = f"Total de Facturas Vencidas a la fecha en {moneda_texto}"
            self.multi_cell(w_tabla, 5, titulo, 0, "C")

            self.ln(2)
            labels = [
                ("Total 0-30", "0_30"),
                ("Total 31-60", "31_60"),
                ("Total 61-90", "61_90"),
                ("Total 91-120", "91_120"),
                ("Total 120+", "mas_120"),
            ]

            self.set_font("Arial", "", 9)
            self.set_text_color(0, 0, 0)

            for label, key in labels:
                valor = rangos.get(key, 0)
                self.set_x(x_pos)
                self.set_font("Arial", "B", 8)
                self.cell(w_tabla * 0.5, 6, label, 1, 0, "L")
                self.set_font("Arial", "", 8)
                val_str = f"{prefijo} {formato_latino(valor)}" if valor > 0 else ""
                self.cell(w_tabla * 0.5, 6, val_str, 1, 1, "R")

            self.set_x(x_pos)
            self.set_font("Arial", "B", 9)
            self.set_fill_color(*AZUL_FOOTER)
            self.set_text_color(255, 255, 255)
            self.cell(w_tabla * 0.5, 7, "TOTAL VENCIDO", 1, 0, "L", True)
            self.cell(
                w_tabla * 0.5,
                7,
                f"{prefijo} {formato_latino(total_v)}",
                1,
                1,
                "R",
                True,
            )

            self.set_text_color(0, 0, 0)
            return self.get_y()

        final_y_usd = y_tabla_inicio
        final_y_crc = y_tabla_inicio

        if dibujar_usd:
            final_y_usd = dibujar_tabla_individual(
                x_inicio, rangos_usd, "Dolares", "USD", vencido_usd
            )

        if dibujar_crc:
            x_pos_crc = (x_inicio + w_tabla + gap) if dibujar_usd else x_inicio
            final_y_crc = dibujar_tabla_individual(
                x_pos_crc, rangos_crc, "Colones", "CRC", vencido_crc
            )

        self.set_y(max(final_y_usd, final_y_crc) + 10)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================


def generar_pdf_estado_cuenta(
    datos: Dict, output_dir: str = "data/estados_cuenta"
) -> str:
    """
    Genera el PDF de estado de cuenta para un cliente.

    Args:
        datos: Dict con estructura de preparar_datos_cliente() del main.py
        output_dir: Directorio donde guardar el PDF

    Returns:
        Ruta del archivo PDF generado
    """
    os.makedirs(output_dir, exist_ok=True)

    # Generar QR de validación
    qr_path = generar_qr_validacion(
        datos["cliente"],
        datos["documentos"]["dolares"],
        datos["documentos"]["colones"],
        datos["totales"],
    )

    # Crear PDF
    pdf = PDFEstadoCuenta()

    # Establecer QR antes de agregar la primera página
    if qr_path:
        pdf.set_qr_path(qr_path)

    pdf.add_page()

    # Datos del cliente
    pdf.agregar_datos_cliente(datos["cliente"])

    # Tabla unificada de documentos
    pdf.agregar_tabla_unica(
        datos["documentos"]["dolares"], datos["documentos"]["colones"], datos["totales"]
    )

    # Sección de vencidos
    pdf.agregar_seccion_vencidos_unificada(
        datos["rangos_vencimiento"].get("USD"), datos["rangos_vencimiento"].get("CRC")
    )

    # Generar nombre de archivo
    codigo = datos["cliente"]["codigo"]
    nombre = datos["cliente"]["nombre"].replace(" ", "_")[:20]
    fecha = datetime.now().strftime("%Y%m%d")
    filename = f"EC_{codigo}_{nombre}_{fecha}.pdf"
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
