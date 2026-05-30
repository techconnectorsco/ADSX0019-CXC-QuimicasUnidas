"""
generarpdf.py - Químicas Unidas
Generación de PDFs de Estado de Cuenta (CXC) para envío individual a clientes.

Características:
- Orientación horizontal tamaño OFICIO (Legal)
- Tabla unificada (USD primero, luego CRC)
- Sección de rangos de vencimiento (0-30, 31-60, 61-90, 91-120, 120+)
- QR de validación con datos del cliente

REFACTORIZADO: Usa pdf_base.PDFBaseQU como clase base.
Toda la lógica común (header, footer, formato de fila, fechas, montos, estatus)
vive en pdf_base.py. Aquí solo está lo ESPECÍFICO del Estado de Cuenta:
- Bloque de datos del cliente (con vendedor, condición de pago, etc.)
- Configuración de columnas de la tabla (8 columnas, sin "Destino")
- Totales finales por moneda
- Sección de rangos de vencimiento
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
    GRIS_CLARO,
    formato_latino,
    generar_qr_desde_lineas,
    limpiar_qr_temporal,
)

# =============================================================================
# QR ESPECÍFICO DE ESTADO DE CUENTA
# =============================================================================

# =============================================================================
# DATOS BANCARIOS - QUÍMICAS UNIDAS LTDA.
# =============================================================================
# Estos datos van dentro del QR para que el cliente pueda escanearlo y obtener
# las cuentas para pagar. Si cambian, modificar AQUÍ.
# Fuente: PDF oficial CUENTAS_QU.pdf

CUENTAS_BANCARIAS = [
    {
        "banco": "BCR",
        "moneda": "COLONES",
        "cuenta": "001-145244-4",
        "cc": "15201001014524442",
        "iban": "CR36015201001014524442",
    },
    {
        "banco": "BCR",
        "moneda": "DÓLARES",
        "cuenta": "001-0279168-4",
        "cc": None,  # BCR Dólares no tiene CC en el PDF oficial
        "iban": "CR52015201001027916847",
    },
    {
        "banco": "BN",
        "moneda": "COLONES",
        "cuenta": "100-01-000-016985-4",
        "cc": "15100010010169851",
        "iban": "CR50015100010010169851",
    },
    {
        "banco": "BAC SAN JOSÉ",
        "moneda": "COLONES",
        "cuenta": None,  # BAC solo muestra IBAN en el PDF oficial
        "cc": None,
        "iban": "CR60010200009019709051",
    },
]

CORREO_COMPROBANTES = "credito@qu.cr"


def generar_qr_validacion(
    datos_cliente: Dict, docs_usd: List, docs_crc: List, totales: Dict
) -> str:
    """
    Genera un QR con las cuentas bancarias de Químicas Unidas
    para que el cliente pueda pagar.

    Mantiene los parámetros datos_cliente/docs_usd/docs_crc/totales por
    compatibilidad con la firma original, aunque actualmente no se usan
    dentro del QR (se mantiene contenido mínimo para que escanee bien).
    """
    # --- Cuentas bancarias ---
    lineas = [
        "CUENTAS BANCARIAS - QUÍMICAS UNIDAS LTDA.",
        "",
    ]

    for cuenta in CUENTAS_BANCARIAS:
        lineas.append(f">> {cuenta['banco']} - {cuenta['moneda']}")
        if cuenta["cuenta"]:
            lineas.append(f"   Cuenta: {cuenta['cuenta']}")
        if cuenta["cc"]:
            lineas.append(f"   CC: {cuenta['cc']}")
        lineas.append(f"   IBAN: {cuenta['iban']}")
        lineas.append("")

    # --- Pie ---
    lineas.append(f"Comprobantes: {CORREO_COMPROBANTES}")

    return generar_qr_desde_lineas(lineas)


# =============================================================================
# CLASE PDF - ESTADO DE CUENTA
# =============================================================================


class PDFEstadoCuenta(PDFBaseQU):
    """
    PDF de Estado de Cuenta para envío individual a clientes.
    Hereda toda la maquinaria base de PDFBaseQU.
    """

    # Configuración específica del Estado de Cuenta
    titulo_principal = "Estado de Cuenta"
    mostrar_texto_qr = True  # Sí muestra "Escanear para validar"
    qr_size = (
        35  # QR más grande para que las cuentas bancarias escaneen bien al imprimir
    )
    formato_fecha_tabla = "%d/%m/%Y"  # Fecha completa con año de 4 dígitos
    formato_hora_header = "%I:%M %p"  # AM/PM
    color_header_tabla = (220, 220, 220)  # Gris claro
    color_texto_header_tabla = (0, 0, 0)  # Texto negro
    texto_footer_principal = [
        "Departamento de Crédito y Cobros | Tel: 2257-8484 ext. 207-208",
        "Correos: credito@qu.cr | creditodenis@qu.cr",
    ]

    # -------------------------------------------------------------------------
    # BLOQUE DE DATOS DEL CLIENTE (específico de CXC)
    # -------------------------------------------------------------------------

    def agregar_datos_cliente(self, cliente: Dict):
        """Renderiza el bloque gris con datos completos del cliente."""
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
        moneda_lim = cliente.get("moneda_limite", "CRC")  # Trae la moneda real
        self.cell(0, 5, f"{moneda_lim} {formato_latino(limite)}", 0, 1)

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

    # -------------------------------------------------------------------------
    # TABLA DE DOCUMENTOS (específica de CXC: 8 columnas, sin "Destino")
    # -------------------------------------------------------------------------

    def agregar_tabla_unica(
        self, docs_usd: List[Dict], docs_crc: List[Dict], totales: Dict
    ):
        """Renderiza la tabla unificada de documentos USD+CRC con totales al final."""
        todos_docs = self.ordenar_documentos_unificado(
            docs_usd, docs_crc, priorizar_vencidos=False
        )

        if not todos_docs:
            return

        # Definición de columnas del Estado de Cuenta (8 columnas)
        anchos = [40, 25, 25, 32, 15, 135, 33, 28]
        headers = [
            "No de Doc",
            "No de Orden",
            "Fecha Factura",
            "Fecha Vencimiento",
            "Tipo Doc",
            "Descripción",
            "Monto Factura",
            "Estatus",
        ]
        columnas = [
            {"campo": "consecutivo_fe", "ancho": anchos[0], "align": "C"},
            {
                "campo": "orden_compra",
                "ancho": anchos[1],
                "align": "C",
                "max_largo": 15,
            },
            {"campo": "fecha", "ancho": anchos[2], "align": "C"},
            {"campo": "fecha_vence", "ancho": anchos[3], "align": "C"},
            {"campo": "tipo_codigo", "ancho": anchos[4], "align": "C"},
            {"campo": "descripcion", "ancho": anchos[5], "align": "L", "max_largo": 80},
            {"campo": "monto", "ancho": anchos[6], "align": "R"},
            {"campo": "estatus", "ancho": anchos[7], "align": "C"},
        ]

        self.imprimir_encabezados_tabla(
            anchos, headers, tamano_fuente=9, altura_celda=7
        )

        fila_par = False
        for doc in todos_docs:
            if self.get_y() > self.h - 35:
                self.add_page()
                self.imprimir_encabezados_tabla(
                    anchos, headers, tamano_fuente=9, altura_celda=7
                )

            self.renderizar_fila_documento(
                doc, columnas, altura=6, tamano_fuente=8, fila_par=fila_par
            )
            fila_par = not fila_par

        # Totales generales al final de la tabla
        self.ln(2)
        ancho_blanco = sum(anchos[:-2])
        self.set_font("Arial", "B", 10)
        self.set_fill_color(*AZUL_FOOTER)
        self.set_text_color(255, 255, 255)

        if docs_usd:
            tot_usd = totales["dolares"]
            # El menos justo antes del número
            if tot_usd < 0:
                str_usd = f"(USD - {formato_latino(abs(tot_usd))})"
            else:
                str_usd = f"USD {formato_latino(tot_usd)}"

            self.cell(ancho_blanco, 6, "TOTAL GENERAL USD:", 1, 0, "R", True)
            self.cell(anchos[-2] + anchos[-1], 6, str_usd, 1, 1, "R", True)

        if docs_crc:
            tot_crc = totales["colones"]
            # El menos justo antes del número
            if tot_crc < 0:
                str_crc = f"(CRC - {formato_latino(abs(tot_crc))})"
            else:
                str_crc = f"CRC {formato_latino(tot_crc)}"

            self.cell(ancho_blanco, 6, "TOTAL GENERAL COLONES:", 1, 0, "R", True)
            self.cell(anchos[-2] + anchos[-1], 6, str_crc, 1, 1, "R", True)

        self.set_text_color(0, 0, 0)
        self.ln(5)

    # -------------------------------------------------------------------------
    # SECCIÓN DE RANGOS DE VENCIMIENTO (específica de CXC)
    # -------------------------------------------------------------------------

    def agregar_seccion_vencidos_unificada(self, rangos_usd: Dict, rangos_crc: Dict):
        """Renderiza las tablas de rangos 0-30, 31-60, 61-90, 91-120, 120+."""
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
# PUNTO DE ENTRADA - FIRMA IDÉNTICA A LA ORIGINAL
# =============================================================================


def generar_pdf_estado_cuenta(
    datos: Dict, output_dir: str = "data/estados_cuenta"
) -> str:
    """
    Genera el PDF de estado de cuenta para un cliente.

    Args:
        datos: Dict con la estructura de preparar_datos_cliente() de main.py
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
    if qr_path:
        pdf.set_qr_path(qr_path)

    pdf.add_page()

    # Datos del cliente
    pdf.agregar_datos_cliente(datos["cliente"])

    # Tabla unificada de documentos
    pdf.agregar_tabla_unica(
        datos["documentos"]["dolares"],
        datos["documentos"]["colones"],
        datos["totales"],
    )

    # Sección de vencidos
    pdf.agregar_seccion_vencidos_unificada(
        datos["rangos_vencimiento"].get("USD"),
        datos["rangos_vencimiento"].get("CRC"),
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
    limpiar_qr_temporal(qr_path)

    return filepath
