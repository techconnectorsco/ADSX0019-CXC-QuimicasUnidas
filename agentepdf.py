"""
agentepdf.py - Químicas Unidas
Generación de PDFs consolidados de Reporte de Gira para Agentes/Vendedores.

Características:
- Orientación horizontal tamaño OFICIO (Legal)
- Un PDF con N clientes del agente
- Separador visual amarillo entre clientes con saldo y datos resumidos
- Tabla por cliente: 10 columnas incluyendo "Destino" (ShipToCode)
- Documentos vencidos primero (ordenados por días de vencimiento)
- QR de validación con datos del agente

REFACTORIZADO: Usa pdf_base.PDFBaseQU como clase base.
Toda la lógica común (header, footer, formato de fila, fechas, montos, estatus)
vive en pdf_base.py. Aquí solo está lo ESPECÍFICO del Reporte de Gira:
- Cabecera del agente
- Separador amarillo por cliente
- Configuración de columnas de la tabla (10 columnas, con "Destino")
"""

from fpdf import FPDF
from datetime import datetime
from typing import List, Dict
import os

from pdf_base import (
    PDFBaseQU,
    AZUL_OSCURO,
    AZUL_CLARO,
    AZUL_FOOTER,
    ROJO,
    VERDE,
    GRIS,
    AMARILLO_SUAVE,
    formato_latino,
    generar_qr_desde_lineas,
    limpiar_qr_temporal,
)

# =============================================================================
# QR ESPECÍFICO DEL REPORTE DE GIRA
# =============================================================================


def generar_qr_agente(datos_agente: Dict, totales_generales: Dict) -> str:
    """Genera un QR con información del agente y totales del reporte."""
    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    codigo_verificacion = f"GIRA-{datetime.now().strftime('%Y%m%d%H%M')}"

    lineas = [
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
        lineas.append(
            f"TOTAL A COBRAR (USD): {formato_latino(totales_generales['dolares'])}"
        )
    if totales_generales.get("colones", 0) > 0:
        lineas.append(
            f"TOTAL A COBRAR (CRC): {formato_latino(totales_generales['colones'])}"
        )

    lineas.append("════════════════════════════════════════")
    lineas.append(f"Verificación: {codigo_verificacion}")

    return generar_qr_desde_lineas(lineas)


# =============================================================================
# CLASE PDF - REPORTE DE GIRA
# =============================================================================


class PDFReporteGira(PDFBaseQU):
    """
    PDF de Reporte de Gira (consolidado por agente).
    Hereda toda la maquinaria base de PDFBaseQU.
    """

    # Configuración específica del Reporte de Gira
    titulo_principal = "Reporte de Gira - Gestión de Cobro"
    mostrar_texto_qr = False  # Gira no muestra el texto debajo del QR
    formato_fecha_tabla = "%d/%m/%y"  # Fecha compacta con año de 2 dígitos
    formato_hora_header = "%H:%M"  # 24 horas
    color_header_tabla = AZUL_FOOTER  # Fondo azul
    color_texto_header_tabla = (255, 255, 255)  # Texto blanco
    texto_footer_principal = [
        "Documento de Uso Interno - Departamento de Ventas y Cobros",
    ]

    # -------------------------------------------------------------------------
    # CABECERA DEL AGENTE
    # -------------------------------------------------------------------------

    def agregar_info_agente(self, agente: Dict, totales: Dict):
        """Banda azul oscura al inicio del PDF con nombre del agente y zonas."""
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 12)
        texto = (
            f" AGENTE: {agente.get('nombre', 'No especificado')} | "
            f"ZONAS: {agente.get('zonas', 'Varias')}"
        )
        self.cell(0, 8, texto, 0, 1, "L", True)
        self.ln(3)

    # -------------------------------------------------------------------------
    # SEPARADOR DE CLIENTE
    # -------------------------------------------------------------------------

    def agregar_separador_cliente(self, cliente: Dict, totales: Dict):
        """
        Bloque amarillo con datos del cliente y saldo a la derecha.
        Se renderiza antes de la tabla de documentos de ese cliente.
        """
        if self.get_y() > self.h - 50:
            self.add_page()

        y_inicio = self.get_y()
        self.set_fill_color(*AMARILLO_SUAVE)
        self.rect(10, y_inicio, self.w - 20, 20, "F")
        self.set_fill_color(*AZUL_CLARO)
        self.rect(10, y_inicio, 3, 20, "F")

        # Primera línea: Código + Nombre | SALDO
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

        # Segunda línea: Teléfono y contacto | Plazo, Desc, Grupo
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

        # Tercera línea: Dirección | Límite de crédito
        self.set_x(15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(*GRIS)
        self.cell(140, 5, f"Dir: {str(cliente.get('direccion', ''))[:80]}", 0, 0)

        self.set_font("Arial", "", 8)
        limite_str = (
            f"Límite: {cliente.get('moneda_limite', 'CRC')} "
            f"{formato_latino(cliente.get('limite_credito', 0))}"
        )
        self.cell(0, 5, limite_str, 0, 1, "R")
        self.ln(2)

    # -------------------------------------------------------------------------
    # TABLA DE DOCUMENTOS POR CLIENTE
    # -------------------------------------------------------------------------

    def agregar_tabla_documentos(self, docs_usd: List[Dict], docs_crc: List[Dict]):
        """Tabla de 10 columnas con vencidos primero (estilo Gira)."""
        todos_docs = self.ordenar_documentos_unificado(
            docs_usd, docs_crc, priorizar_vencidos=True
        )

        if not todos_docs:
            self.set_font("Arial", "I", 9)
            self.cell(0, 8, "Sin documentos pendientes.", 0, 1, "C")
            self.ln(5)
            return

        # Definición de columnas del Reporte de Gira (10 columnas)
        anchos = [45, 30, 20, 20, 18, 25, 95, 33, 22, 12]
        headers = [
            "No de Doc",
            "No de Orden",
            "Fecha Fac",
            "Fecha Vence",
            "Tipo Doc",
            "Destino",
            "Descripción",
            "Monto",
            "Estatus",
            "Días",
        ]
        columnas = [
            {
                "campo": "consecutivo_fe",
                "ancho": anchos[0],
                "align": "C",
                "max_largo": 22,
            },
            {
                "campo": "orden_compra",
                "ancho": anchos[1],
                "align": "C",
                "max_largo": 15,
            },
            {"campo": "fecha", "ancho": anchos[2], "align": "C"},
            {"campo": "fecha_vence", "ancho": anchos[3], "align": "C"},
            {"campo": "tipo_codigo", "ancho": anchos[4], "align": "C", "max_largo": 6},
            {"campo": "destino", "ancho": anchos[5], "align": "C", "max_largo": 15},
            {"campo": "descripcion", "ancho": anchos[6], "align": "L", "max_largo": 60},
            {"campo": "monto", "ancho": anchos[7], "align": "R"},
            {"campo": "estatus", "ancho": anchos[8], "align": "C"},
            {"campo": "dias", "ancho": anchos[9], "align": "C"},
        ]

        self.imprimir_encabezados_tabla(
            anchos, headers, tamano_fuente=8, altura_celda=7
        )

        fila_par = False
        for doc in todos_docs:
            if self.get_y() > self.h - 35:
                self.add_page()
                self.imprimir_encabezados_tabla(
                    anchos, headers, tamano_fuente=8, altura_celda=7
                )

            self.renderizar_fila_documento(
                doc, columnas, altura=6, tamano_fuente=8, fila_par=fila_par
            )
            fila_par = not fila_par

        self.ln(8)


# =============================================================================
# PUNTO DE ENTRADA - FIRMA IDÉNTICA A LA ORIGINAL
# =============================================================================


def generar_pdf_reporte_gira(
    datos: Dict, output_dir: str = "data/reportes_gira"
) -> str:
    """
    Genera el PDF de Reporte de Gira para un agente.

    Args:
        datos: Dict con estructura {agente, totales_agente, clientes: [{cliente, documentos, totales}]}
        output_dir: Directorio donde guardar el PDF

    Returns:
        Ruta del archivo PDF generado
    """
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
            cliente_data["documentos"]["dolares"],
            cliente_data["documentos"]["colones"],
        )

    codigo_agente = datos["agente"].get("codigo", "DESC")
    nombre_agente = datos["agente"].get("nombre", "Agente").replace(" ", "_")[:20]
    fecha = datetime.now().strftime("%Y%m%d")
    filename = f"GIRA_{codigo_agente}_{nombre_agente}_{fecha}.pdf"
    filepath = os.path.join(output_dir, filename)

    pdf.output(filepath)
    limpiar_qr_temporal(qr_path)

    return filepath
