"""
logControlCXC.py - Químicas Unidas
Generación de Log de Control para el proceso de Estados de Cuenta.

Genera un PDF con el resumen ejecutivo y detalle de la ejecución del RPA.
Mismo estilo visual que los estados de cuenta.
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
# CONSTANTES Y COLORES (mismos que generarpdf.py)
# =============================================================================

AZUL_OSCURO = (11, 17, 75)
AZUL_CLARO = (40, 143, 204)
AZUL_FOOTER = (71, 93, 164)
VERDE = (40, 167, 69)
ROJO = (220, 53, 69)
AMARILLO = (255, 193, 7)
GRIS = (100, 100, 100)
GRIS_CLARO = (245, 245, 245)


def formato_latino(valor: float) -> str:
    """Formato latinoamericano para numeros."""
    if valor is None:
        valor = 0.0
    num_str = f"{abs(valor):,.2f}"
    num_str = num_str.replace(",", "X").replace(".", ",").replace("X", ".")
    return num_str


def generar_qr_log(stats: Dict, fecha: str, hora: str) -> str:
    """Genera QR de validacion para el log de control."""
    if not QR_DISPONIBLE:
        return None

    codigo_verificacion = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    contenido = []
    contenido.append("==============================")
    contenido.append("   QUIMICAS UNIDAS Ltda.")
    contenido.append("   Log de Control CXC")
    contenido.append("==============================")
    contenido.append("")
    contenido.append(f"Fecha: {fecha}")
    contenido.append(f"Hora: {hora}")
    contenido.append("")
    contenido.append(f"Clientes procesados: {stats.get('procesados', 0)}")
    contenido.append(f"Correos enviados: {stats.get('enviados', 0)}")
    contenido.append(f"Errores: {stats.get('errores', 0)}")
    contenido.append("")
    contenido.append(
        f"Cartera USD: ${formato_latino(stats.get('total_cartera_usd', 0))}"
    )
    contenido.append(
        f"Cartera CRC: {formato_latino(stats.get('total_cartera_crc', 0))}"
    )
    contenido.append("")
    contenido.append("==============================")
    contenido.append("Credito y Cobro:")
    contenido.append("Tel: 2257-8484 ext. 216-217")
    contenido.append("==============================")
    contenido.append("")
    contenido.append(f"Verificacion: {codigo_verificacion}")

    contenido_qr = "\n".join(contenido)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(contenido_qr)
    qr.make(fit=True)

    img_qr = qr.make_image(fill_color="black", back_color="white")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img_qr.save(temp_file.name)
    temp_file.close()

    return temp_file.name


# =============================================================================
# CLASE PRINCIPAL - PDF LOG DE CONTROL
# =============================================================================


class LogControlCXC(FPDF):
    """Genera el PDF de log de control del proceso CXC."""

    def __init__(self, logo_path: str = "images/QU.png"):
        super().__init__(orientation="L", unit="mm", format="Legal")
        self.logo_path = logo_path
        self.qr_path = None
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)
        self.datos_proceso = {}
        self.registros = []
        self.alertas = []
        self.inicio_proceso = None
        self.fin_proceso = None

    def set_qr_path(self, qr_path: str):
        """Establece la ruta del QR para el header."""
        self.qr_path = qr_path

    def header(self):
        # Logo izquierdo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 15, 8, 45)

        # Titulo centrado
        self.set_font("Arial", "B", 18)
        self.set_text_color(*AZUL_FOOTER)
        self.set_y(12)
        self.cell(0, 8, "Quimicas Unidas Ltda.", 0, 1, "C")

        self.set_font("Arial", "B", 14)
        self.cell(0, 6, "Log de Control - Estados de Cuenta", 0, 1, "C")

        # Fecha y hora
        self.set_font("Arial", "", 10)
        self.set_text_color(*GRIS)
        fecha = self.datos_proceso.get("fecha", datetime.now().strftime("%d/%m/%Y"))
        hora = self.datos_proceso.get("hora", datetime.now().strftime("%I:%M %p"))
        self.set_xy(-95, 12)
        self.cell(50, 5, f"Fecha: {fecha}", 0, 1, "R")
        self.set_xy(-95, 17)
        self.cell(50, 5, f"Hora: {hora}", 0, 1, "R")

        # QR de validacion (esquina superior derecha)
        if self.qr_path and os.path.exists(self.qr_path):
            self.image(self.qr_path, self.w - 38, 5, 30)
            self.set_font("Arial", "I", 6)
            self.set_text_color(*GRIS)
            self.set_xy(self.w - 40, 36)
            self.cell(32, 3, "Escanear para validar", 0, 0, "C")

        # Linea decorativa
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.8)
        self.line(10, 40, self.w - 10, 40)
        self.ln(8)
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

        # Bloque central
        self.set_font("Arial", "B", 11)
        self.set_y(-18)
        self.cell(
            0,
            5,
            "Departamento de Credito y Cobros | Tel: 2257-8484 ext. 216-217",
            0,
            1,
            "C",
        )
        self.cell(0, 5, "Correos: credito@qu.cr | creditodenis@qu.cr", 0, 1, "C")

        # Bloque izquierdo (Publicidad SX)
        self.set_font("Arial", "BI", 8)
        self.set_xy(10, -17)
        self.cell(80, 5, "Oficina de Transformacion Digital SX", 0, 0, "L")

        self.set_font("Arial", "I", 8)
        self.set_xy(10, -13)
        self.cell(80, 5, "SOPORTEXPERTO.COM", 0, 0, "L")

        # Bloque derecho (Paginacion)
        self.set_font("Arial", "I", 10)
        self.set_xy(-30, -13)
        self.cell(20, 5, f"Pagina {self.page_no()}", 0, 0, "R")

    def agregar_resumen_ejecutivo(self, stats: Dict):
        """Agrega la sección de resumen ejecutivo con los números clave."""
        self.set_font("Arial", "B", 12)
        self.set_text_color(*AZUL_FOOTER)
        self.cell(0, 8, "RESUMEN EJECUTIVO", 0, 1, "L")

        # Caja de resumen
        y_inicio = self.get_y()
        self.set_fill_color(*GRIS_CLARO)
        self.rect(10, y_inicio, self.w - 20, 35, "F")
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(10, y_inicio, 3, 35, "F")

        self.set_xy(15, y_inicio + 3)

        # Fila 1: Totales generales
        self.set_font("Arial", "B", 10)
        self.set_text_color(0, 0, 0)

        self.cell(
            60, 6, f"Clientes consultados: {stats.get('total_clientes', 0)}", 0, 0
        )
        self.cell(60, 6, f"Clientes procesados: {stats.get('procesados', 0)}", 0, 0)
        self.cell(60, 6, f"PDFs generados: {stats.get('pdfs_generados', 0)}", 0, 0)
        self.cell(60, 6, f"Correos enviados: {stats.get('enviados', 0)}", 0, 1)

        # Fila 2: Estados
        self.set_x(15)
        self.set_font("Arial", "", 10)

        # Enviados OK
        self.set_text_color(*VERDE)
        self.cell(60, 6, f"[OK] Exitosos: {stats.get('enviados', 0)}", 0, 0)

        # Sin correo
        self.set_text_color(*AMARILLO)
        self.cell(60, 6, f"[S/C] Sin correo: {stats.get('sin_correo', 0)}", 0, 0)

        # Errores
        self.set_text_color(*ROJO)
        self.cell(60, 6, f"[ERR] Errores: {stats.get('errores', 0)}", 0, 0)

        # Deshabilitados
        self.set_text_color(*GRIS)
        self.cell(
            60, 6, f"[DES] Envio deshabilitado: {stats.get('deshabilitados', 0)}", 0, 1
        )

        # Fila 3: Totales de cartera
        self.set_x(15)
        self.set_text_color(0, 0, 0)
        self.set_font("Arial", "B", 10)

        total_usd = stats.get("total_cartera_usd", 0)
        total_crc = stats.get("total_cartera_crc", 0)
        vencido_usd = stats.get("total_vencido_usd", 0)
        vencido_crc = stats.get("total_vencido_crc", 0)

        self.cell(80, 6, f"Cartera USD: ${formato_latino(total_usd)}", 0, 0)
        self.cell(80, 6, f"Cartera CRC: {formato_latino(total_crc)}", 0, 0)

        # Porcentaje vencido
        pct_vencido_usd = (vencido_usd / total_usd * 100) if total_usd > 0 else 0
        pct_vencido_crc = (vencido_crc / total_crc * 100) if total_crc > 0 else 0
        self.set_text_color(*ROJO)
        self.cell(
            80,
            6,
            f"Vencido: {pct_vencido_usd:.1f}% USD | {pct_vencido_crc:.1f}% CRC",
            0,
            1,
        )

        # Fila 4: Vencidos
        self.set_x(15)
        self.set_font("Arial", "", 10)
        self.cell(80, 6, f"Vencido USD: ${formato_latino(vencido_usd)}", 0, 0)
        self.cell(80, 6, f"Vencido CRC: {formato_latino(vencido_crc)}", 0, 1)

        self.set_text_color(0, 0, 0)
        self.ln(8)

    def agregar_tabla_detalle(self, registros: List[Dict]):
        """Agrega la tabla de detalle por cliente."""
        # Filtrar solo clientes que tienen documentos (docs_usd > 0 o docs_crc > 0)
        registros_con_docs = [
            r for r in registros if r.get("docs_usd", 0) > 0 or r.get("docs_crc", 0) > 0
        ]

        if not registros_con_docs:
            return

        self.set_font("Arial", "B", 12)
        self.set_text_color(*AZUL_FOOTER)
        self.cell(0, 8, "DETALLE POR CLIENTE", 0, 1, "L")

        # Encabezados - centrar tabla
        anchos = [18, 55, 60, 18, 18, 30, 35, 12, 12, 45]
        headers = [
            "Codigo",
            "Cliente",
            "Correo(s)",
            "Docs USD",
            "Docs CRC",
            "Total USD",
            "Total CRC",
            "PDF",
            "Email",
            "Observacion",
        ]

        # Calcular margen izquierdo para centrar
        ancho_tabla = sum(anchos)
        margen_izq = (self.w - ancho_tabla) / 2

        self._imprimir_encabezados(anchos, headers, margen_izq)

        self.set_font("Arial", "", 7)
        fila_par = False

        for reg in registros_con_docs:
            if self.get_y() > self.h - 25:
                self.add_page()
                self._imprimir_encabezados(anchos, headers, margen_izq)
                self.set_font("Arial", "", 7)

            if fila_par:
                self.set_fill_color(250, 250, 250)
            else:
                self.set_fill_color(255, 255, 255)
            fila_par = not fila_par

            self.set_text_color(0, 0, 0)
            self.set_x(margen_izq)  # Centrar fila

            # Codigo
            self.cell(anchos[0], 5, reg.get("codigo", "")[:10], 1, 0, "C", True)

            # Cliente
            nombre = reg.get("nombre", "")[:28]
            self.cell(anchos[1], 5, nombre, 1, 0, "L", True)

            # Correos
            correos = reg.get("correos", [])
            if len(correos) == 0:
                correo_txt = "(sin correo)"
            elif len(correos) == 1:
                correo_txt = correos[0][:30]
            else:
                correo_txt = f"{correos[0][:20]}... (+{len(correos)-1})"
            self.cell(anchos[2], 5, correo_txt, 1, 0, "L", True)

            # Docs USD
            self.cell(anchos[3], 5, str(reg.get("docs_usd", 0)), 1, 0, "C", True)

            # Docs CRC
            self.cell(anchos[4], 5, str(reg.get("docs_crc", 0)), 1, 0, "C", True)

            # Total USD
            total_usd = reg.get("total_usd", 0)
            self.cell(
                anchos[5],
                5,
                f"${formato_latino(total_usd)}" if total_usd != 0 else "-",
                1,
                0,
                "R",
                True,
            )

            # Total CRC
            total_crc = reg.get("total_crc", 0)
            self.cell(
                anchos[6],
                5,
                f"CRC {formato_latino(total_crc)}" if total_crc != 0 else "-",
                1,
                0,
                "R",
                True,
            )

            # PDF Status
            pdf_ok = reg.get("pdf_generado", False)
            if pdf_ok:
                self.set_text_color(*VERDE)
                self.cell(anchos[7], 5, "OK", 1, 0, "C", True)
            else:
                self.set_text_color(*ROJO)
                self.cell(anchos[7], 5, "NO", 1, 0, "C", True)

            # Email Status
            email_status = reg.get("email_status", "pendiente")
            if email_status == "enviado":
                self.set_text_color(*VERDE)
                self.cell(anchos[8], 5, "OK", 1, 0, "C", True)
            elif email_status == "sin_correo":
                self.set_text_color(*AMARILLO)
                self.cell(anchos[8], 5, "S/C", 1, 0, "C", True)
            elif email_status == "error":
                self.set_text_color(*ROJO)
                self.cell(anchos[8], 5, "ERR", 1, 0, "C", True)
            elif email_status == "deshabilitado":
                self.set_text_color(*GRIS)
                self.cell(anchos[8], 5, "DES", 1, 0, "C", True)
            else:
                self.set_text_color(*GRIS)
                self.cell(anchos[8], 5, "-", 1, 0, "C", True)

            # Observación
            self.set_text_color(0, 0, 0)
            obs = reg.get("observacion", "")[:25]
            self.cell(anchos[9], 5, obs, 1, 1, "L", True)

        self.ln(5)

    def _imprimir_encabezados(self, anchos, headers, margen_izq=10):
        """Imprime los encabezados de la tabla."""
        self.set_font("Arial", "B", 8)
        self.set_fill_color(220, 220, 220)
        self.set_text_color(0, 0, 0)
        self.set_x(margen_izq)  # Centrar encabezados
        for i, header in enumerate(headers):
            self.cell(anchos[i], 6, header, 1, 0, "C", True)
        self.ln()

    def agregar_seccion_alertas(self, alertas: List[Dict]):
        """Agrega la sección de alertas y atención requerida."""
        if not alertas:
            return

        if self.get_y() > self.h - 60:
            self.add_page()

        self.set_font("Arial", "B", 12)
        self.set_text_color(*ROJO)
        self.cell(0, 8, "ALERTAS - ATENCION REQUERIDA", 0, 1, "L")

        self.set_font("Arial", "", 9)
        self.set_text_color(0, 0, 0)

        for alerta in alertas[:15]:  # Máximo 15 alertas
            tipo = alerta.get("tipo", "")
            mensaje = alerta.get("mensaje", "")

            if tipo == "vencido_critico":
                self.set_text_color(*ROJO)
                icono = "[!]"
            elif tipo == "sin_correo":
                self.set_text_color(*AMARILLO)
                icono = "[?]"
            else:
                self.set_text_color(*GRIS)
                icono = "[-]"

            self.cell(8, 5, icono, 0, 0)
            self.set_text_color(0, 0, 0)
            self.cell(0, 5, mensaje[:120], 0, 1)

        if len(alertas) > 15:
            self.set_text_color(*GRIS)
            self.cell(0, 5, f"... y {len(alertas) - 15} alertas mas", 0, 1)

        self.ln(5)

    def agregar_top_saldos(self, top_clientes: List[Dict]):
        """Agrega el top 10 de clientes con mayor saldo."""
        if not top_clientes:
            return

        if self.get_y() > self.h - 80:
            self.add_page()

        self.set_font("Arial", "B", 12)
        self.set_text_color(*AZUL_FOOTER)
        self.cell(0, 8, "TOP 10 - CLIENTES CON MAYOR SALDO", 0, 1, "C")

        anchos = [12, 85, 50, 50]
        headers = ["#", "Cliente", "Saldo USD", "Saldo CRC"]

        # Calcular margen para centrar
        ancho_tabla = sum(anchos)
        margen_izq = (self.w - ancho_tabla) / 2

        self.set_font("Arial", "B", 9)
        self.set_fill_color(220, 220, 220)
        self.set_x(margen_izq)
        for i, header in enumerate(headers):
            self.cell(anchos[i], 6, header, 1, 0, "C", True)
        self.ln()

        self.set_font("Arial", "", 9)
        for idx, cliente in enumerate(top_clientes[:10], 1):
            self.set_fill_color(255, 255, 255)
            self.set_x(margen_izq)
            self.cell(anchos[0], 6, str(idx), 1, 0, "C", True)
            self.cell(anchos[1], 6, cliente.get("nombre", "")[:45], 1, 0, "L", True)
            self.cell(
                anchos[2],
                6,
                f"${formato_latino(cliente.get('total_usd', 0))}",
                1,
                0,
                "R",
                True,
            )
            self.cell(
                anchos[3],
                6,
                f"CRC {formato_latino(cliente.get('total_crc', 0))}",
                1,
                1,
                "R",
                True,
            )

        self.ln(5)

    def agregar_nota_duracion(self, duracion: str, inicio: str, fin: str):
        """Agrega nota con informacion de duracion del proceso."""
        if self.get_y() > self.h - 40:
            self.add_page()

        self.ln(5)

        # Caja de nota
        y_inicio = self.get_y()
        self.set_fill_color(*GRIS_CLARO)
        self.rect(10, y_inicio, self.w - 20, 18, "F")
        self.set_fill_color(*AZUL_CLARO)
        self.rect(10, y_inicio, 3, 18, "F")

        self.set_xy(15, y_inicio + 3)
        self.set_font("Arial", "B", 10)
        self.set_text_color(*AZUL_FOOTER)
        self.cell(0, 5, "INFORMACION DEL PROCESO", 0, 1)

        self.set_x(15)
        self.set_font("Arial", "", 9)
        self.set_text_color(0, 0, 0)
        self.cell(50, 5, f"Inicio: {inicio}", 0, 0)
        self.cell(50, 5, f"Fin: {fin}", 0, 0)
        self.cell(50, 5, f"Duracion: {duracion}", 0, 0)
        self.cell(0, 5, "Sistema RPA - Quimicas Unidas", 0, 1)

        self.ln(5)


# =============================================================================
# CLASE COLECTORA DE DATOS
# =============================================================================


class ControlCXC:
    """Clase para recolectar datos durante el proceso y generar el log."""

    def __init__(self):
        self.inicio = datetime.now()
        self.fin = None
        self.registros = []
        self.stats = {
            "total_clientes": 0,
            "procesados": 0,
            "pdfs_generados": 0,
            "enviados": 0,
            "sin_correo": 0,
            "errores": 0,
            "deshabilitados": 0,
            "total_cartera_usd": 0,
            "total_cartera_crc": 0,
            "total_vencido_usd": 0,
            "total_vencido_crc": 0,
        }
        self.alertas = []
        self.top_clientes = []

    def set_total_clientes(self, total: int):
        """Establece el total de clientes con saldo."""
        self.stats["total_clientes"] = total

    def agregar_registro(
        self,
        codigo: str,
        nombre: str,
        correos: List[str],
        docs_usd: int,
        docs_crc: int,
        total_usd: float,
        total_crc: float,
        vencido_usd: float,
        vencido_crc: float,
        pdf_generado: bool,
        email_status: str,  # 'enviado', 'error', 'sin_correo', 'deshabilitado', 'pendiente'
        observacion: str = "",
    ):
        """Agrega un registro de cliente procesado."""
        self.registros.append(
            {
                "codigo": codigo,
                "nombre": nombre,
                "correos": correos,
                "docs_usd": docs_usd,
                "docs_crc": docs_crc,
                "total_usd": total_usd,
                "total_crc": total_crc,
                "vencido_usd": vencido_usd,
                "vencido_crc": vencido_crc,
                "pdf_generado": pdf_generado,
                "email_status": email_status,
                "observacion": observacion,
            }
        )

        # Actualizar estadísticas
        self.stats["total_cartera_usd"] += total_usd
        self.stats["total_cartera_crc"] += total_crc
        self.stats["total_vencido_usd"] += vencido_usd
        self.stats["total_vencido_crc"] += vencido_crc

        if pdf_generado:
            self.stats["pdfs_generados"] += 1

        if email_status == "enviado":
            self.stats["enviados"] += 1
            self.stats["procesados"] += 1
        elif email_status == "error":
            self.stats["errores"] += 1
            self.stats["procesados"] += 1
        elif email_status == "sin_correo":
            self.stats["sin_correo"] += 1
            self.stats["procesados"] += 1
            self.alertas.append(
                {
                    "tipo": "sin_correo",
                    "mensaje": f"{codigo} - {nombre}: Sin correo electrónico configurado",
                }
            )
        elif email_status == "deshabilitado":
            self.stats["deshabilitados"] += 1

        # Alerta si vencido > 90 días (aproximado por monto alto vencido)
        if vencido_usd > 1000 or vencido_crc > 500000:
            self.alertas.append(
                {
                    "tipo": "vencido_critico",
                    "mensaje": f"{codigo} - {nombre}: Saldo vencido alto (USD ${formato_latino(vencido_usd)} / CRC {formato_latino(vencido_crc)})",
                }
            )

    def finalizar(self):
        """Finaliza el proceso y calcula el top de clientes."""
        self.fin = datetime.now()

        # Calcular top 5 por saldo total (USD + CRC convertido aproximado)
        for reg in self.registros:
            reg["saldo_total"] = reg["total_usd"] + (
                reg["total_crc"] / 500
            )  # Conversión aproximada

        self.top_clientes = sorted(
            self.registros, key=lambda x: x["saldo_total"], reverse=True
        )[:10]

    def generar_pdf(self, output_dir: str = "data/logs") -> str:
        """Genera el PDF del log de control."""
        self.finalizar()

        os.makedirs(output_dir, exist_ok=True)

        # Calcular duracion
        duracion = self.fin - self.inicio
        minutos = int(duracion.total_seconds() // 60)
        segundos = int(duracion.total_seconds() % 60)
        duracion_str = f"{minutos} min {segundos} seg"

        # Generar QR
        qr_path = generar_qr_log(
            self.stats,
            self.inicio.strftime("%d/%m/%Y"),
            self.inicio.strftime("%I:%M %p"),
        )

        pdf = LogControlCXC()

        # Datos del proceso
        pdf.datos_proceso = {
            "fecha": self.inicio.strftime("%d/%m/%Y"),
            "hora": self.inicio.strftime("%I:%M %p"),
            "duracion": duracion_str,
        }

        # Establecer QR
        if qr_path:
            pdf.set_qr_path(qr_path)

        pdf.add_page()

        # Secciones
        pdf.agregar_resumen_ejecutivo(self.stats)
        pdf.agregar_tabla_detalle(self.registros)
        # Alertas removidas por solicitud del cliente
        pdf.agregar_top_saldos(self.top_clientes)
        pdf.agregar_nota_duracion(
            duracion_str,
            self.inicio.strftime("%d/%m/%Y %I:%M %p"),
            self.fin.strftime("%d/%m/%Y %I:%M %p"),
        )

        # Guardar
        fecha_str = self.inicio.strftime("%Y%m%d_%H%M")
        filename = f"LogControl_CXC_{fecha_str}.pdf"
        filepath = os.path.join(output_dir, filename)

        pdf.output(filepath)

        # Limpiar QR temporal
        if qr_path and os.path.exists(qr_path):
            try:
                os.remove(qr_path)
            except:
                pass

        return filepath
