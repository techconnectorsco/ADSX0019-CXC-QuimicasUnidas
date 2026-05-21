"""
agentepdf.py - Químicas Unidas
Generación de PDFs consolidados para Reportes de Gira de Agentes.
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

AZUL_OSCURO = (11, 17, 75)
AZUL_CLARO = (40, 143, 204)
AZUL_FOOTER = (71, 93, 164)
ROJO = (220, 53, 69)
VERDE = (40, 167, 69)
GRIS = (100, 100, 100)
GRIS_CLARO = (245, 245, 245)
AMARILLO_SUAVE = (255, 249, 230)


def formato_latino(valor: float) -> str:
    if valor is None:
        valor = 0.0
    num_str = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return num_str


def generar_qr_agente(datos_agente: Dict, totales_generales: Dict) -> str:
    if not QR_DISPONIBLE:
        return None
    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    codigo_verificacion = f"GIRA-{datetime.now().strftime('%Y%m%d%H%M')}"
    contenido = [
        "════════════════════════════════════════",
        "   QUÍMICAS UNIDAS LTDA.",
        "   Reporte de Gira (Uso Interno)",
        "════════════════════════════════════════",
        "",
        f"Agente: {datos_agente.get('nombre', 'N/A')}",
        f"Zonas: {datos_agente.get('zonas', 'Varias')}",
        f"Emisión: {fecha_emision}",
        "",
    ]
    if totales_generales.get("dolares", 0) > 0:
        contenido.append(
            f"TOTAL A COBRAR (USD): {formato_latino(totales_generales['dolares'])}"
        )
    if totales_generales.get("colones", 0) > 0:
        contenido.append(
            f"TOTAL A COBRAR (CRC): {formato_latino(totales_generales['colones'])}"
        )

    contenido.append("════════════════════════════════════════")
    contenido.append(f"Verificación: {codigo_verificacion}")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data("\n".join(contenido))
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img_qr.save(temp_file.name)
    temp_file.close()
    return temp_file.name


class PDFReporteGira(FPDF):
    def __init__(self, logo_path: str = "images/QU.png"):
        super().__init__(orientation="L", unit="mm", format="Legal")
        self.logo_path = logo_path
        self.qr_path = None
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)

    def set_qr_path(self, qr_path: str):
        self.qr_path = qr_path

    def header(self):
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 15, 8, 45)
        self.set_font("Arial", "B", 18)
        self.set_text_color(*AZUL_FOOTER)
        self.set_y(12)
        self.cell(0, 8, "Químicas Unidas Ltda.", 0, 1, "C")
        self.set_font("Arial", "B", 15)
        self.cell(0, 6, "Reporte de Gira - Gestión de Cobro", 0, 1, "C")
        self.set_font("Arial", "", 10)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime("%H:%M")
        self.set_xy(-95, 12)
        self.cell(50, 5, f"Fecha: {fecha}", 0, 1, "R")
        self.set_xy(-95, 17)
        self.cell(50, 5, f"Hora: {hora}", 0, 1, "R")
        if self.qr_path and os.path.exists(self.qr_path):
            self.image(self.qr_path, self.w - 38, 5, 30)
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.99)
        self.line(10, 40, self.w - 10, 40)
        self.set_y(43)

    def footer(self):
        self.set_y(-23)
        self.set_fill_color(*AZUL_CLARO)
        self.rect(0, self.h - 24, self.w, 3, "F")
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(0, self.h - 22, self.w, 22, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 11)
        self.set_y(-18)
        self.cell(
            0,
            5,
            "Documento de Uso Interno - Departamento de Ventas y Cobros",
            0,
            1,
            "C",
        )
        self.set_font("Arial", "BI", 8)
        self.set_xy(10, -17)
        self.cell(80, 5, "Oficina de Transformación Digital SX", 0, 0, "L")
        self.set_font("Arial", "I", 8)
        self.set_xy(10, -13)
        self.cell(80, 5, "SOPORTEXPERTO.COM", 0, 0, "L")
        self.set_font("Arial", "I", 10)
        self.set_xy(-30, -13)
        self.cell(20, 5, f"Página {self.page_no()}", 0, 0, "R")

    def agregar_info_agente(self, agente: Dict, totales: Dict):
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 12)
        self.cell(
            0,
            8,
            f" AGENTE: {agente.get('nombre', 'No especificado')} | ZONAS: {agente.get('zonas', 'Varias')}",
            0,
            1,
            "L",
            True,
        )
        self.ln(3)

    def agregar_separador_cliente(self, cliente: Dict, totales: Dict):
        if self.get_y() > self.h - 50:
            self.add_page()
        y_inicio = self.get_y()
        self.set_fill_color(*AMARILLO_SUAVE)
        self.rect(10, y_inicio, self.w - 20, 20, "F")
        self.set_fill_color(*AZUL_CLARO)
        self.rect(10, y_inicio, 3, 20, "F")

        self.set_xy(15, y_inicio + 2)
        self.set_font("Arial", "B", 11)
        self.set_text_color(*AZUL_OSCURO)

        nombre_str = f"{cliente.get('codigo', '')} - {cliente.get('nombre', '')}"
        self.cell(140, 6, nombre_str[:70], 0, 0)

        deuda_str = "SALDO:"
        if totales.get("dolares", 0) > 0:
            deuda_str += f" USD {formato_latino(totales['dolares'])} |"
        if totales.get("colones", 0) > 0:
            deuda_str += f" CRC {formato_latino(totales['colones'])}"

        self.set_font("Arial", "B", 10)
        self.set_text_color(*ROJO)
        self.cell(0, 6, deuda_str, 0, 1, "R")

        self.set_x(15)
        self.set_font("Arial", "", 9)
        self.set_text_color(0, 0, 0)

        plazo = cliente.get("plazo_dias", 30)
        descuento = cliente.get("descuento_porcent", 0)
        grupo = cliente.get("grupo_descuento", -1)

        contacto_str = (
            f"Tel: {cliente.get('telefono', 'N/A')} | {cliente.get('contacto', 'N/A')}"
        )
        self.cell(100, 5, contacto_str, 0, 0)
        self.set_font("Arial", "B", 8)
        self.cell(
            0, 5, f"Plazo: {plazo}d | Desc: {descuento}% | Grp: {grupo}", 0, 1, "R"
        )

        self.set_x(15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(GRIS[0], GRIS[1], GRIS[2])
        self.cell(140, 5, f"Dir: {str(cliente.get('direccion', ''))[:80]}", 0, 0)

        self.set_font("Arial", "", 8)
        # ACÁ SE IMPRIME LA MONEDA DEL LIMITE DINÁMICAMENTE
        limite_str = f"Límite: {cliente.get('moneda_limite', 'CRC')} {formato_latino(cliente.get('limite_credito', 0))}"
        self.cell(0, 5, limite_str, 0, 1, "R")
        self.ln(2)

    def agregar_tabla_documentos(self, docs_usd: List[Dict], docs_crc: List[Dict]):
        todos_docs = []

        vencidos_usd = [d for d in docs_usd if d.get("esta_vencido", False)]
        vencidos_usd.sort(key=lambda x: x.get("dias_vencido", 0), reverse=True)
        todos_docs.extend(vencidos_usd)
        al_dia_usd = [d for d in docs_usd if not d.get("esta_vencido", False)]
        todos_docs.extend(al_dia_usd)

        vencidos_crc = [d for d in docs_crc if d.get("esta_vencido", False)]
        vencidos_crc.sort(key=lambda x: x.get("dias_vencido", 0), reverse=True)
        todos_docs.extend(vencidos_crc)
        al_dia_crc = [d for d in docs_crc if not d.get("esta_vencido", False)]
        todos_docs.extend(al_dia_crc)

        if not todos_docs:
            self.set_font("Arial", "I", 9)
            self.cell(0, 8, "Sin documentos pendientes.", 0, 1, "C")
            self.ln(5)
            return

        # SE AMPLIAN DOC/ORDEN, SE REDUCE DESCRIPCIÓN Y SE AGREGA DESTINO
        anchos = [45, 30, 20, 20, 18, 25, 95, 33, 22, 12]
        headers = [
            "No de Doc",
            "No de Orden",
            "Fecha Fac",
            "Fecha Vence",
            "TIPO DOC",
            "Destino",
            "Descripción",
            "Monto",
            "Estatus",
            "Días",
        ]

        self._imprimir_encabezados_tabla(anchos, headers)
        self.set_font("Arial", "", 8)
        fila_par = False

        for doc in todos_docs:
            if self.get_y() > self.h - 35:
                self.add_page()
                self._imprimir_encabezados_tabla(anchos, headers)
                self.set_font("Arial", "", 8)

            (
                self.set_fill_color(250, 250, 250)
                if fila_par
                else self.set_fill_color(255, 255, 255)
            )
            fila_par = not fila_par

            esta_vencido = doc.get("esta_vencido", False)
            saldo = doc.get("saldo", 0)
            simbolo = "USD" if doc.get("moneda", "") == "USD" else "CRC"
            dias_vencido = doc.get("dias_vencido", 0)

            # No Doc ampliado
            consecutivo = doc.get("consecutivo_fe", "") or str(doc.get("doc_num", ""))
            self.cell(anchos[0], 6, consecutivo[:22], 1, 0, "C", True)

            # No Orden ampliado
            orden = str(doc.get("orden_compra", ""))[:15]
            self.cell(anchos[1], 6, orden, 1, 0, "C", True)

            fecha = doc.get("fecha", "")
            if len(fecha) >= 10:
                try:
                    fecha = datetime.strptime(fecha[:10], "%Y-%m-%d").strftime(
                        "%d/%m/%y"
                    )
                except:
                    fecha = fecha[:5]
            self.cell(anchos[2], 6, fecha, 1, 0, "C", True)

            fecha_vence = doc.get("fecha_vence", "")
            if len(fecha_vence) >= 10:
                try:
                    fecha_vence = datetime.strptime(
                        fecha_vence[:10], "%Y-%m-%d"
                    ).strftime("%d/%m/%y")
                except:
                    fecha_vence = fecha_vence[:5]
            self.cell(anchos[3], 6, fecha_vence, 1, 0, "C", True)

            trans = doc.get("tipo_codigo", "")[:6]
            self.cell(anchos[4], 6, trans, 1, 0, "C", True)

            # NUEVA COLUMNA DESTINO
            destino = doc.get("destino", "")[:15]
            self.cell(anchos[5], 6, destino, 1, 0, "C", True)

            desc = doc.get("descripcion", "")[:60]
            self.cell(anchos[6], 6, desc, 1, 0, "L", True)

            monto_str = f"{simbolo} {formato_latino(abs(saldo))}"
            if saldo < 0:
                monto_str = f"({monto_str})"
            self.cell(anchos[7], 6, monto_str, 1, 0, "R", True)

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
            self.cell(anchos[8], 6, estatus, 1, 0, "C", True)
            self.set_text_color(0, 0, 0)
            self.set_font("Arial", "", 8)

            if esta_vencido:
                self.set_text_color(*ROJO)
                self.set_font("Arial", "B", 8)
                dias_str = str(dias_vencido)
            else:
                self.set_text_color(0, 0, 0)
                self.set_font("Arial", "", 8)
                dias_str = "0"

            self.cell(anchos[9], 6, dias_str, 1, 1, "C", True)
            self.set_text_color(0, 0, 0)
            self.set_font("Arial", "", 8)
        self.ln(8)

    def _imprimir_encabezados_tabla(self, anchos, headers):
        self.set_font("Arial", "B", 8)
        self.set_fill_color(71, 93, 164)
        self.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            self.cell(anchos[i], 7, header, 1, 0, "C", True)
        self.ln()
        self.set_text_color(0, 0, 0)


def generar_pdf_reporte_gira(
    datos: Dict, output_dir: str = "data/reportes_gira"
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    qr_path = generar_qr_agente(
        datos.get("agente", {}), datos.get("totales_agente", {})
    )
    pdf = PDFReporteGira()
    if qr_path:
        pdf.set_qr_path(qr_path)
    pdf.add_page()
    pdf.agregar_info_agente(datos.get("agente", {}), datos.get("totales_agente", {}))

    for cliente_data in datos.get("clientes", []):
        pdf.agregar_separador_cliente(cliente_data["cliente"], cliente_data["totales"])
        pdf.agregar_tabla_documentos(
            cliente_data["documentos"]["dolares"], cliente_data["documentos"]["colones"]
        )

    codigo_agente = datos["agente"].get("codigo", "DESC")
    nombre_agente = datos["agente"].get("nombre", "Agente").replace(" ", "_")[:20]
    fecha = datetime.now().strftime("%Y%m%d")
    filename = f"GIRA_{codigo_agente}_{nombre_agente}_{fecha}.pdf"
    filepath = os.path.join(output_dir, filename)

    pdf.output(filepath)
    if qr_path and os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except:
            pass
    return filepath
