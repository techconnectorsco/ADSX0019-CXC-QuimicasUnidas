"""
generarexcel.py - Químicas Unidas
Generación de Excel para Estados de Cuenta.

Características:
- Diseño financiero limpio, minimalista y profesional.
- Valores numéricos nativos (floats) con formato de moneda de Excel para permitir cálculos.
- Sin colores invasivos, optimizado para lectura y trabajo de datos.
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
from typing import List, Dict
import os

# =============================================================================
# CONFIGURACIÓN DE ESTILOS Y COLORES MINIMALISTAS
# =============================================================================

# Colores suaves y profesionales
COLOR_TITULO = "2C3E50"  # Gris azulado oscuro (elegante)
COLOR_HEADER_TABLA = "F4F6F7"  # Gris ultra claro para encabezados
COLOR_TEXTO = "333333"  # Gris oscuro para lectura cómoda
ROJO = "C0392B"  # Vencidos
VERDE = "27AE60"  # Al día / A favor

# Formatos Nativos de Excel (Permiten sumar y hacer fórmulas)
FORMATO_USD = '"USD" #,##0.00;[Red]-"USD" #,##0.00'
FORMATO_CRC = '"CRC" #,##0.00;[Red]-"CRC" #,##0.00'


# =============================================================================
# CLASE PRINCIPAL - EXCEL ESTADO DE CUENTA
# =============================================================================


class ExcelEstadoCuenta:
    """Genera Excel de Estado de Cuenta con estilo financiero y datos calculables."""

    def __init__(self):
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "Estado de Cuenta"
        self.row = 1

        # Configurar página para impresión limpia
        self.ws.page_setup.paperSize = self.ws.PAPERSIZE_LEGAL
        self.ws.page_setup.orientation = "landscape"
        self.ws.print_options.horizontalCentered = True
        self.ws.sheet_view.showGridLines = (
            False  # Ocultar cuadrícula para un look más limpio
        )

        # Márgenes
        self.ws.page_margins.left = 0.5
        self.ws.page_margins.right = 0.5
        self.ws.page_margins.top = 0.75
        self.ws.page_margins.bottom = 0.75

    def _obtener_fill(self, hex_color: str) -> PatternFill:
        return PatternFill(
            start_color=hex_color, end_color=hex_color, fill_type="solid"
        )

    def _obtener_borde_inferior(self) -> Border:
        """Solo línea abajo para un look más limpio de tabla."""
        thin = Side(style="thin", color="DDDDDD")
        return Border(bottom=thin)

    def _obtener_borde_completo(self) -> Border:
        thin = Side(style="thin", color="CCCCCC")
        return Border(left=thin, right=thin, top=thin, bottom=thin)

    def _establecer_ancho_columnas(self):
        anchos = {
            "A": 16,  # No de Doc
            "B": 16,  # No de Orden
            "C": 15,  # Fecha Factura
            "D": 16,  # Fecha Vencimiento
            "E": 12,  # Trans
            "F": 50,  # Descripción
            "G": 20,  # Monto Factura
            "H": 15,  # Estatus
        }
        for col, ancho in anchos.items():
            self.ws.column_dimensions[col].width = ancho

    def agregar_encabezado(self):
        """Encabezado limpio sin bloques de color gigante."""
        self.ws.merge_cells("A1:H1")
        cell = self.ws["A1"]
        cell.value = "QUÍMICAS UNIDAS Ltda."
        cell.font = Font(name="Calibri", size=18, bold=True, color=COLOR_TITULO)
        cell.alignment = Alignment(horizontal="left", vertical="center")

        self.ws.merge_cells("A2:H2")
        cell = self.ws["A2"]
        cell.value = "ESTADO DE CUENTA"
        cell.font = Font(name="Calibri", size=14, bold=False, color=COLOR_TEXTO)
        cell.alignment = Alignment(horizontal="left", vertical="center")

        self.ws.merge_cells("A3:H3")
        cell = self.ws["A3"]
        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime("%H:%M")
        cell.value = f"Generado el: {fecha} a las {hora}"
        cell.font = Font(name="Calibri", size=10, italic=True, color="7F8C8D")
        cell.alignment = Alignment(horizontal="left", vertical="center")

        # Línea separadora
        for col in range(1, 9):
            self.ws.cell(row=4, column=col).border = Border(
                bottom=Side(style="medium", color=COLOR_TITULO)
            )

        self.row = 6

    def agregar_datos_cliente(self, cliente: Dict):
        """Datos del cliente en formato de formulario limpio (sin celdas pintadas)."""
        datos = [
            (
                "Cliente:",
                f"{cliente.get('codigo', '')} - {cliente.get('nombre', '')}",
                "Contacto:",
                cliente.get("contacto", "") or "N/A",
            ),
            (
                "Correo:",
                cliente.get("correo", "") or "N/A",
                "Teléfono:",
                cliente.get("telefono", "") or "N/A",
            ),
            (
                "Dirección:",
                cliente.get("direccion", "") or "N/A",
                "Vendedor:",
                cliente.get("vendedor", "") or "N/A",
            ),
            (
                "Cond. Pago:",
                cliente.get("condicion_pago", ""),
                "Límite Crédito:",
                cliente.get("limite_credito", 0),
            ),
        ]

        for label1, val1, label2, val2 in datos:
            # Columna 1
            c1 = self.ws.cell(row=self.row, column=1)
            c1.value = label1
            c1.font = Font(name="Calibri", size=11, bold=True, color=COLOR_TITULO)

            c2 = self.ws.cell(row=self.row, column=2)
            c2.value = val1
            c2.font = Font(name="Calibri", size=11)
            self.ws.merge_cells(
                start_row=self.row, start_column=2, end_row=self.row, end_column=4
            )

            # Columna 2
            c3 = self.ws.cell(row=self.row, column=5)
            c3.value = label2
            c3.font = Font(name="Calibri", size=11, bold=True, color=COLOR_TITULO)

            c4 = self.ws.cell(row=self.row, column=6)
            if label2 == "Límite Crédito:":
                c4.value = val2
                c4.number_format = FORMATO_CRC
                c4.font = Font(name="Calibri", size=11, bold=True)
            else:
                c4.value = val2
                c4.font = Font(name="Calibri", size=11)
            self.ws.merge_cells(
                start_row=self.row, start_column=6, end_row=self.row, end_column=8
            )

            self.row += 1

        self.row += 2

    def agregar_tabla_documentos(
        self, docs_usd: List[Dict], docs_crc: List[Dict], totales: Dict
    ):
        """Agrega la tabla permitiendo cálculos matemáticos."""
        todos_docs = docs_usd + docs_crc if docs_usd or docs_crc else []
        if not todos_docs:
            return

        headers = [
            "No de Doc",
            "No de Orden",
            "Fecha Fact.",
            "Vencimiento",
            "Trans",
            "Descripción",
            "Monto Saldo",
            "Estatus",
        ]

        # Encabezados
        for col_num, header in enumerate(headers, 1):
            cell = self.ws.cell(row=self.row, column=col_num)
            cell.value = header
            cell.font = Font(name="Calibri", size=11, bold=True, color=COLOR_TITULO)
            cell.fill = self._obtener_fill(COLOR_HEADER_TABLA)
            cell.border = self._obtener_borde_completo()
            cell.alignment = Alignment(horizontal="center", vertical="center")

        self.row += 1

        # Datos
        borde_fila = self._obtener_borde_inferior()

        for doc in todos_docs:
            esta_vencido = doc.get("esta_vencido", False)
            saldo = doc.get("saldo", 0)
            moneda = doc.get("moneda", "")

            # Escribimos fechas reales como strings limpios (o Excel Date, pero string es seguro aquí)
            fecha = doc.get("fecha", "")[:10]
            if len(fecha) == 10:
                fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[2:4]}"

            fecha_vence = doc.get("fecha_vence", "")[:10]
            if len(fecha_vence) == 10:
                fecha_vence = (
                    f"{fecha_vence[8:10]}/{fecha_vence[5:7]}/{fecha_vence[2:4]}"
                )

            datos_fila = [
                doc.get("consecutivo_fe", "") or str(doc.get("doc_num", "")),
                str(doc.get("orden_compra", ""))[:15],
                fecha,
                fecha_vence,
                doc.get("tipo_codigo", ""),
                doc.get("descripcion", "")[:80],
            ]

            for col_num, valor in enumerate(datos_fila, 1):
                cell = self.ws.cell(row=self.row, column=col_num)
                cell.value = valor
                cell.font = Font(name="Calibri", size=10)
                cell.border = borde_fila
                if col_num in [1, 2, 3, 4, 5]:
                    cell.alignment = Alignment(horizontal="center")

            # Columna Monto (INYECCIÓN NUMÉRICA REAL PARA CÁLCULOS)
            cell_monto = self.ws.cell(row=self.row, column=7)
            cell_monto.value = saldo  # Número real (float)
            cell_monto.number_format = FORMATO_USD if moneda == "USD" else FORMATO_CRC
            cell_monto.font = Font(name="Calibri", size=10)
            cell_monto.border = borde_fila

            # Estatus
            cell_estatus = self.ws.cell(row=self.row, column=8)
            if saldo < 0:
                cell_estatus.value, color_est = "A favor", VERDE
            elif esta_vencido:
                cell_estatus.value, color_est = "Vencido", ROJO
            else:
                cell_estatus.value, color_est = "Al día", COLOR_TEXTO

            cell_estatus.font = Font(
                name="Calibri", size=10, bold=True, color=color_est
            )
            cell_estatus.alignment = Alignment(horizontal="center")
            cell_estatus.border = borde_fila

            self.row += 1

        self.row += 1

        # Totales Generales limpios
        for moneda, clave_total, formato in [
            ("USD", "dolares", FORMATO_USD),
            ("CRC", "colones", FORMATO_CRC),
        ]:
            if docs_usd if moneda == "USD" else docs_crc:
                self.ws.merge_cells(
                    start_row=self.row, start_column=5, end_row=self.row, end_column=6
                )
                c_lbl = self.ws.cell(row=self.row, column=5)
                c_lbl.value = f"TOTAL GENERAL {moneda}:"
                c_lbl.font = Font(
                    name="Calibri", size=11, bold=True, color=COLOR_TITULO
                )
                c_lbl.alignment = Alignment(horizontal="right")

                c_tot = self.ws.cell(row=self.row, column=7)
                c_tot.value = totales[clave_total]  # Valor numérico
                c_tot.number_format = formato
                c_tot.font = Font(name="Calibri", size=11, bold=True)

                # Doble línea abajo para totales financieros
                for col in [5, 6, 7]:
                    self.ws.cell(row=self.row, column=col).border = Border(
                        top=Side(style="thin"), bottom=Side(style="double")
                    )

                self.row += 1

        self.row += 2

    def agregar_seccion_vencidos(self, rangos_usd: Dict, rangos_crc: Dict):
        """Agrega análisis de vencimiento limpio, con números calculables."""
        vencido_usd = rangos_usd.get("total_vencido", 0) if rangos_usd else 0
        vencido_crc = rangos_crc.get("total_vencido", 0) if rangos_crc else 0

        if vencido_usd <= 0 and vencido_crc <= 0:
            return

        # Imprimir USD y/o CRC en columnas paralelas
        if vencido_usd > 0:
            self._crear_bloque_vencido(
                rangos_usd, "USD", FORMATO_USD, vencido_usd, col_inicio=1
            )

        if vencido_crc > 0:
            col = 5 if vencido_usd > 0 else 1
            self._crear_bloque_vencido(
                rangos_crc, "CRC", FORMATO_CRC, vencido_crc, col_inicio=col
            )

    def _crear_bloque_vencido(
        self, rangos: Dict, moneda: str, formato: str, total: float, col_inicio: int
    ):
        # Título del bloque
        self.ws.merge_cells(
            start_row=self.row,
            start_column=col_inicio,
            end_row=self.row,
            end_column=col_inicio + 2,
        )
        c_tit = self.ws.cell(row=self.row, column=col_inicio)
        c_tit.value = f"Análisis de Vencimiento ({moneda})"
        c_tit.font = Font(name="Calibri", size=11, bold=True, color=COLOR_TITULO)
        c_tit.fill = self._obtener_fill(COLOR_HEADER_TABLA)
        c_tit.border = self._obtener_borde_completo()

        fila_actual = self.row + 1
        labels = [
            ("De 0 a 30 días", "0_30"),
            ("De 31 a 60 días", "31_60"),
            ("De 61 a 90 días", "61_90"),
            ("De 91 a 120 días", "91_120"),
            ("Más de 120 días", "mas_120"),
        ]

        for label, key in labels:
            self.ws.merge_cells(
                start_row=fila_actual,
                start_column=col_inicio,
                end_row=fila_actual,
                end_column=col_inicio + 1,
            )
            c_lbl = self.ws.cell(row=fila_actual, column=col_inicio)
            c_lbl.value = label
            c_lbl.font = Font(name="Calibri", size=10)
            c_lbl.border = self._obtener_borde_inferior()

            c_val = self.ws.cell(row=fila_actual, column=col_inicio + 2)
            c_val.value = rangos.get(key, 0)  # NÚMERO REAL
            c_val.number_format = formato
            c_val.font = Font(name="Calibri", size=10)
            c_val.border = self._obtener_borde_inferior()

            fila_actual += 1

        # Fila Total Vencido
        self.ws.merge_cells(
            start_row=fila_actual,
            start_column=col_inicio,
            end_row=fila_actual,
            end_column=col_inicio + 1,
        )
        c_lbl = self.ws.cell(row=fila_actual, column=col_inicio)
        c_lbl.value = "TOTAL VENCIDO"
        c_lbl.font = Font(name="Calibri", size=10, bold=True, color=ROJO)

        c_val = self.ws.cell(row=fila_actual, column=col_inicio + 2)
        c_val.value = total
        c_val.number_format = formato
        c_val.font = Font(name="Calibri", size=10, bold=True, color=ROJO)
        c_val.border = Border(top=Side(style="thin"), bottom=Side(style="double"))

        # Actualizar self.row si esta tabla bajó más
        if fila_actual > self.row:
            self.row = fila_actual + 2

    def guardar(self, filepath: str) -> str:
        self._establecer_ancho_columnas()
        self.wb.save(filepath)
        return filepath


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================


def generar_excel_estado_cuenta(
    datos: Dict, output_dir: str = "data/estados_cuenta"
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    excel = ExcelEstadoCuenta()

    excel.agregar_encabezado()
    excel.agregar_datos_cliente(datos["cliente"])
    excel.agregar_tabla_documentos(
        datos["documentos"]["dolares"], datos["documentos"]["colones"], datos["totales"]
    )
    excel.agregar_seccion_vencidos(
        datos["rangos_vencimiento"].get("USD"), datos["rangos_vencimiento"].get("CRC")
    )

    codigo = datos["cliente"]["codigo"]
    nombre = datos["cliente"]["nombre"].replace(" ", "_")[:20]
    fecha = datetime.now().strftime("%Y%m%d")
    filepath = os.path.join(output_dir, f"EC_{codigo}_{nombre}_{fecha}.xlsx")

    return excel.guardar(filepath)
