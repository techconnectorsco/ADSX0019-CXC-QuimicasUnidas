"""
pdf_base.py - Químicas Unidas
Módulo base compartido para la generación de PDFs (Estado de Cuenta y Reporte de Gira).

Este módulo centraliza:
- Constantes de colores e identidad visual
- Formato de moneda latinoamericano
- Generación de QR
- Clase base FPDF con header/footer parametrizables
- Renderizado de filas de documentos (lógica común a ambos reportes)

Las clases hijas (PDFEstadoCuenta y PDFReporteGira) solo deben definir su
configuración específica (título, columnas a mostrar, secciones extra).

IMPORTANTE: Si Tania reporta un cambio en el formato de una fila, monto,
fecha, color de "Vencido", etc., el cambio se hace AQUÍ y aplica a ambos
reportes automáticamente.
"""

from fpdf import FPDF
from datetime import datetime
from typing import List, Dict, Optional
import os
import tempfile

try:
    import qrcode

    QR_DISPONIBLE = True
except ImportError:
    QR_DISPONIBLE = False

# =============================================================================
# CONSTANTES DE COLORES (identidad visual Químicas Unidas)
# =============================================================================

AZUL_OSCURO = (11, 17, 75)  # Header, títulos
AZUL_CLARO = (40, 143, 204)  # Línea decorativa, franja superior footer
AZUL_FOOTER = (71, 93, 164)  # Fondo footer, totales, separadores
ROJO = (220, 53, 69)  # Vencidos
VERDE = (40, 167, 69)  # Al día / A favor
GRIS = (100, 100, 100)  # Textos secundarios
GRIS_CLARO = (245, 245, 245)  # Fondo alternado (CXC)
AMARILLO_SUAVE = (255, 249, 230)  # Fondo separador cliente (Gira)

# =============================================================================
# UTILIDADES DE FORMATO
# =============================================================================


def formato_latino(valor: float) -> str:
    """
    Convierte formato US (1,234.56) a formato Latino (1.234,56).
    100% seguro sin depender del locale del sistema operativo.
    """
    if valor is None:
        valor = 0.0
    num_str = f"{abs(valor):,.2f}"
    num_str = num_str.replace(",", "X").replace(".", ",").replace("X", ".")
    return num_str


def formatear_fecha(fecha_str: str, formato_salida: str = "%d/%m/%Y") -> str:
    """
    Convierte una fecha en formato ISO (YYYY-MM-DD...) al formato deseado.
    Si la cadena es inválida o vacía, devuelve la cadena original recortada.

    Args:
        fecha_str: Cadena con la fecha (puede tener más de 10 caracteres)
        formato_salida: '%d/%m/%Y' para CXC (08/03/2025) o '%d/%m/%y' para Gira (08/03/25)
    """
    if not fecha_str or len(fecha_str) < 10:
        return fecha_str[:5] if fecha_str else ""
    try:
        return datetime.strptime(fecha_str[:10], "%Y-%m-%d").strftime(formato_salida)
    except Exception:
        return fecha_str[:10]


# =============================================================================
# GENERACIÓN DE QR (helper genérico)
# =============================================================================


def generar_qr_desde_lineas(lineas: List[str]) -> Optional[str]:
    """
    Genera un código QR a partir de una lista de líneas de texto.
    Devuelve la ruta al archivo temporal PNG, o None si qrcode no está disponible.

    Cada función específica (generar_qr_validacion en CXC,
    generar_qr_agente en Gira) construye su lista de líneas y llama a esta.
    """
    if not QR_DISPONIBLE:
        return None

    contenido = "\n".join(lineas)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(contenido)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img_qr.save(temp_file.name)
    temp_file.close()
    return temp_file.name


# =============================================================================
# CLASE BASE PDF
# =============================================================================


class PDFBaseQU(FPDF):
    """
    Clase base con header/footer y utilidades de tabla comunes.

    Las clases hijas DEBEN definir (como atributos de instancia o de clase):
        - titulo_principal: str   -> Ej: "Estado de Cuenta"
        - texto_footer_principal: List[str] -> Líneas centradas del footer
        - mostrar_texto_qr: bool  -> Mostrar "Escanear para validar" debajo del QR
        - color_header_tabla: tuple -> Color de fondo de los encabezados de tabla
        - color_texto_header_tabla: tuple -> Color del texto de los encabezados
        - formato_fecha_tabla: str -> '%d/%m/%Y' o '%d/%m/%y'

    Las clases hijas pueden sobreescribir métodos puntuales si necesitan algo
    fuera del patrón común, pero por defecto la mayoría del trabajo está aquí.
    """

    # Defaults sensatos (las hijas los pueden sobreescribir)
    titulo_principal: str = "Documento"
    subtitulo: str = ""
    texto_footer_principal: List[str] = []
    mostrar_texto_qr: bool = False
    color_header_tabla: tuple = AZUL_FOOTER
    color_texto_header_tabla: tuple = (255, 255, 255)
    formato_fecha_tabla: str = "%d/%m/%Y"
    formato_hora_header: str = "%I:%M %p"  # CXC usa AM/PM, Gira usa 24h

    def __init__(self, logo_path: str = "images/QU.png"):
        super().__init__(orientation="L", unit="mm", format="Legal")
        self.logo_path = logo_path
        self.qr_path: Optional[str] = None
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(10, 10, 10)

    def set_qr_path(self, qr_path: Optional[str]):
        """Establece la ruta al QR antes de llamar a add_page()."""
        self.qr_path = qr_path

    # -------------------------------------------------------------------------
    # HEADER (común a todos los reportes)
    # -------------------------------------------------------------------------

    def header(self):
        # Logo izquierdo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 15, 8, 45)

        # Título centrado
        self.set_font("Arial", "B", 18)
        self.set_text_color(*AZUL_FOOTER)
        self.set_y(12)
        self.cell(0, 8, "Químicas Unidas Ltda.", 0, 1, "C")

        # Subtítulo (específico de cada reporte)
        self.set_font("Arial", "B", 15)
        self.cell(0, 6, self.titulo_principal, 0, 1, "C")

        # Fecha y hora a la izquierda del QR
        self.set_font("Arial", "", 10)
        self.set_text_color(*GRIS)
        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime(self.formato_hora_header)
        self.set_xy(-95, 12)
        self.cell(50, 5, f"Fecha: {fecha}", 0, 1, "R")
        self.set_xy(-95, 17)
        self.cell(50, 5, f"Hora: {hora}", 0, 1, "R")

        # QR de validación
        if self.qr_path and os.path.exists(self.qr_path):
            self.image(self.qr_path, self.w - 38, 5, 30)
            if self.mostrar_texto_qr:
                self.set_font("Arial", "I", 6)
                self.set_text_color(*GRIS)
                self.set_xy(self.w - 40, 36)
                self.cell(32, 3, "Cuentas Bancarias", 0, 0, "C")

        # Línea decorativa
        self.set_draw_color(*AZUL_CLARO)
        self.set_line_width(0.99)
        self.line(10, 40, self.w - 10, 40)

        self.set_y(43)

    # -------------------------------------------------------------------------
    # FOOTER (común a todos los reportes)
    # -------------------------------------------------------------------------

    def footer(self):
        self.set_y(-23)

        # Franja azul claro superior
        self.set_fill_color(*AZUL_CLARO)
        self.rect(0, self.h - 24, self.w, 3, "F")

        # Fondo azul oscuro principal
        self.set_fill_color(*AZUL_FOOTER)
        self.rect(0, self.h - 22, self.w, 22, "F")

        self.set_text_color(255, 255, 255)

        # Bloque central (texto específico de cada reporte)
        if self.texto_footer_principal:
            # Si hay 1 línea, ponerla un poco más abajo (centrada vertical).
            # Si hay 2+ líneas, empezar arriba.
            y_inicio = -18 if len(self.texto_footer_principal) >= 2 else -16
            self.set_font("Arial", "B", 11)
            self.set_y(y_inicio)
            for linea in self.texto_footer_principal:
                self.cell(0, 5, linea, 0, 1, "C")

        # Bloque izquierdo (Publicidad SX) - común a TODOS los reportes
        self.set_font("Arial", "BI", 8)
        self.set_xy(10, -17)
        self.cell(80, 5, "Oficina de Transformación Digital SX", 0, 0, "L")

        self.set_font("Arial", "I", 8)
        self.set_xy(10, -13)
        self.cell(80, 5, "SOPORTEXPERTO.COM", 0, 0, "L")

        # Bloque derecho (Paginación) - común a TODOS los reportes
        self.set_font("Arial", "I", 10)
        self.set_xy(-30, -13)
        self.cell(20, 5, f"Página {self.page_no()}", 0, 0, "R")

    # -------------------------------------------------------------------------
    # UTILIDADES DE TABLA
    # -------------------------------------------------------------------------

    def imprimir_encabezados_tabla(
        self,
        anchos: List[float],
        headers: List[str],
        tamano_fuente: int = 9,
        altura_celda: float = 7,
    ):
        """
        Imprime una fila de encabezados de tabla con los anchos y textos dados.
        Usa los colores configurados en la clase (color_header_tabla).
        """
        self.set_font("Arial", "B", tamano_fuente)
        self.set_fill_color(*self.color_header_tabla)
        self.set_text_color(*self.color_texto_header_tabla)
        for i, header in enumerate(headers):
            self.cell(anchos[i], altura_celda, header, 1, 0, "C", True)
        self.ln()
        self.set_text_color(0, 0, 0)

    def _calcular_estado_documento(self, doc: Dict) -> tuple:
        """
        Devuelve (texto_estado, color_rgb, es_vencido_real) para un documento.
        Centraliza la lógica "A favor / Vencido / Al día".
        """
        saldo = doc.get("saldo", 0)
        esta_vencido = doc.get("esta_vencido", False)

        if saldo < 0:
            return ("A favor", VERDE, False)
        elif esta_vencido:
            return ("Vencido", ROJO, True)
        else:
            return ("Al día", VERDE, False)

    def _formatear_monto(self, doc: Dict) -> str:
        """
        Devuelve la cadena del monto en formato 'USD 1.234,56' o '(CRC 500,00)' si es negativo.
        """
        saldo = doc.get("saldo", 0)
        moneda = doc.get("moneda", "")
        simbolo = "USD" if moneda == "USD" else "CRC"
        monto_str = f"{simbolo} {formato_latino(abs(saldo))}"
        if saldo < 0:
            monto_str = f"({monto_str})"
        return monto_str

    def renderizar_fila_documento(
        self,
        doc: Dict,
        columnas: List[Dict],
        altura: float = 6,
        tamano_fuente: int = 8,
        fila_par: bool = False,
    ):
        """
        Renderiza una fila completa de un documento en una tabla.

        Args:
            doc: Diccionario con datos del documento (consecutivo_fe, orden_compra,
                 fecha, fecha_vence, tipo_codigo, destino, descripcion, saldo,
                 moneda, esta_vencido, dias_vencido, etc.)
            columnas: Lista de dicts describiendo cada columna a renderizar.
                      Cada dict tiene:
                        - 'campo': str (ej: 'consecutivo_fe', 'destino')
                                   o 'estatus' o 'dias' o 'monto' (especiales)
                        - 'ancho': float
                        - 'align': 'L'|'C'|'R'
                        - 'max_largo': int (opcional, para truncar)
                        - 'fecha_formato': str (opcional, para campos de fecha)
            altura: altura de la celda
            tamano_fuente: tamaño de fuente para el contenido
            fila_par: si True, fondo gris claro; si False, fondo blanco
        """
        # Color de fondo alternado
        if fila_par:
            self.set_fill_color(250, 250, 250)
        else:
            self.set_fill_color(255, 255, 255)

        self.set_font("Arial", "", tamano_fuente)
        self.set_text_color(0, 0, 0)

        for col in columnas:
            campo = col["campo"]
            ancho = col["ancho"]
            align = col.get("align", "L")
            max_largo = col.get("max_largo")

            # --- Columnas especiales ---
            if campo == "monto":
                texto = self._formatear_monto(doc)
                self.cell(ancho, altura, texto, 1, 0, align, True)

            elif campo == "estatus":
                texto, color, _ = self._calcular_estado_documento(doc)
                self.set_text_color(*color)
                self.set_font("Arial", "B", tamano_fuente)
                self.cell(ancho, altura, texto, 1, 0, align, True)
                self.set_text_color(0, 0, 0)
                self.set_font("Arial", "", tamano_fuente)

            elif campo == "dias":
                _, _, es_vencido = self._calcular_estado_documento(doc)
                dias_vencido = doc.get("dias_vencido", 0)
                if es_vencido:
                    self.set_text_color(*ROJO)
                    self.set_font("Arial", "B", tamano_fuente)
                    dias_str = str(dias_vencido)
                else:
                    dias_str = "0"
                self.cell(ancho, altura, dias_str, 1, 0, align, True)
                self.set_text_color(0, 0, 0)
                self.set_font("Arial", "", tamano_fuente)

            # --- Columnas de fecha ---
            elif campo in ("fecha", "fecha_vence"):
                fecha_formato = col.get("fecha_formato", self.formato_fecha_tabla)
                valor = formatear_fecha(doc.get(campo, ""), fecha_formato)
                self.cell(ancho, altura, valor, 1, 0, align, True)

            # --- Columnas de texto genérico ---
            else:
                # Caso especial: consecutivo_fe usa doc_num como fallback
                if campo == "consecutivo_fe":
                    valor = doc.get("consecutivo_fe", "") or str(doc.get("doc_num", ""))
                else:
                    valor = doc.get(campo, "")

                valor = str(valor) if valor is not None else ""
                if max_largo:
                    valor = valor[:max_largo]
                self.cell(ancho, altura, valor, 1, 0, align, True)

        # Saltar línea al final de la fila
        self.ln()

    # -------------------------------------------------------------------------
    # ORDENAMIENTO DE DOCUMENTOS (común a ambos reportes)
    # -------------------------------------------------------------------------

    @staticmethod
    def ordenar_documentos_unificado(
        docs_usd: List[Dict], docs_crc: List[Dict], priorizar_vencidos: bool = False
    ) -> List[Dict]:
        """
        Ordena documentos para mostrar en una tabla unificada.

        Si priorizar_vencidos=True (estilo Gira): vencidos primero (más vencidos arriba),
        luego al día. Primero todos los USD, luego todos los CRC.

        Si priorizar_vencidos=False (estilo CXC): solo concatena USD + CRC en el orden
        que ya viene.
        """
        if not priorizar_vencidos:
            todos = []
            if docs_usd:
                todos.extend(docs_usd)
            if docs_crc:
                todos.extend(docs_crc)
            return todos

        # Modo Gira: vencidos primero por moneda
        todos = []
        for grupo in (docs_usd, docs_crc):
            vencidos = [d for d in grupo if d.get("esta_vencido", False)]
            vencidos.sort(key=lambda x: x.get("dias_vencido", 0), reverse=True)
            al_dia = [d for d in grupo if not d.get("esta_vencido", False)]
            todos.extend(vencidos)
            todos.extend(al_dia)
        return todos


# =============================================================================
# HELPER PARA LIMPIAR ARCHIVOS TEMPORALES DEL QR
# =============================================================================


def limpiar_qr_temporal(qr_path: Optional[str]):
    """Elimina el archivo temporal del QR si existe."""
    if qr_path and os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except Exception:
            pass
