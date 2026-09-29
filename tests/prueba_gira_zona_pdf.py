"""
Nivel 1 del plan de pruebas de "Giras por Zona" (PLAN_GIRAS_POR_ZONA.md, sección 9).

NO toca SAP. NO manda correo. NO sube nada a SharePoint. NO importa api.py.
Solo arma un datos_reporte inventado, lo pasa por generar_pdf_reporte_gira()
y comprueba el renombrado que evita pisar el PDF de la gira completa.

Uso:
    python tests/prueba_gira_zona_pdf.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La consola de Windows viene en cp1252 y revienta con los emoji de los mensajes.
# Mismo parche que usa api.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from agentepdf import generar_pdf_reporte_gira
from agentes import (
    GIRA_ZONA_OUTPUT_DIR,
    GIRA_ZONA_FORZAR_DRY_RUN,
    GIRA_ZONA_CC_ACTIVO,
    _nombre_archivo_gira_zona,
)


def _documento(doc_num, tipo, fecha, vence, total, moneda, vencido, dias):
    return {
        "doc_num": doc_num,
        "consecutivo_fe": f"FE{doc_num}",
        "tipo_codigo": tipo,
        "destino": "GUANACASTE",
        "descripcion": "Documento de prueba generado localmente",
        "fecha": fecha,
        "fecha_vence": vence,
        "total": total,
        "saldo": total,
        "moneda": moneda,
        "esta_vencido": vencido,
        "dias_vencido": dias,
        "orden_compra": "OC-PRUEBA",
    }


def datos_inventados():
    """Misma forma exacta que arma ejecutar_gira_selectiva()."""
    cliente_a = {
        "cliente": {
            "codigo": "C9001",
            "nombre": "CLIENTE DE PRUEBA UNO S.A.",
            "telefono": "2222-3333",
            "direccion": "Liberia, Guanacaste",
            "contacto": "Contacto Uno",
            "plazo_dias": 30,
            "descuento_porcent": 12.0,
            "grupo_descuento": -1,
            "limite_credito": 5000000,
            "moneda_limite": "CRC",
            "zona_gira": "GUANACASTE",
        },
        "documentos": {
            "colones": [
                _documento(101, "FAC", "2026-07-15", "2026-08-14", 850000.0, "CRC", True, 40),
                _documento(102, "FAC", "2026-09-01", "2026-10-01", 415500.5, "CRC", False, 0),
            ],
            "dolares": [
                _documento(103, "FAC", "2026-08-20", "2026-09-19", 1250.75, "USD", True, 4),
            ],
        },
        "totales": {"colones": 1265500.5, "dolares": 1250.75},
    }

    cliente_b = {
        "cliente": {
            "codigo": "C9002",
            "nombre": "SUCURSAL DE PRUEBA DOS S.A.",
            "telefono": "2666-7777",
            "direccion": "Cañas, Guanacaste",
            "contacto": "Contacto Dos",
            "plazo_dias": 15,
            "descuento_porcent": 0.0,
            "grupo_descuento": -1,
            "limite_credito": 0,
            "moneda_limite": "USD",
            "zona_gira": "GUANACASTE",
        },
        "documentos": {
            "colones": [],
            "dolares": [
                _documento(201, "FAC", "2026-06-10", "2026-06-25", 3200.0, "USD", True, 90),
                _documento(202, "N/C", "2026-07-02", "2026-07-02", -500.0, "USD", False, 0),
            ],
        },
        "totales": {"colones": 0, "dolares": 2700.0},
    }

    return {
        "agente": {
            "codigo": "7",
            "nombre": "Agente De Prueba",
            "correo": "no-enviar@ejemplo.local",
            # ejecutar_gira_selectiva siempre convierte esto a string antes del PDF
            "zonas": "GUANACASTE 1 SHINDAIWA",
        },
        "totales_agente": {"colones": 1265500.5, "dolares": 3950.75},
        "clientes": [cliente_a, cliente_b],
    }


def main():
    print("=" * 72)
    print("NIVEL 1 — PDF de gira por zona, sin SAP y sin correo")
    print("=" * 72)
    print(f"   GIRA_ZONA_FORZAR_DRY_RUN = {GIRA_ZONA_FORZAR_DRY_RUN}")
    print(f"   GIRA_ZONA_CC_ACTIVO      = {GIRA_ZONA_CC_ACTIVO}")
    print(f"   Carpeta de salida        = {GIRA_ZONA_OUTPUT_DIR}")
    print()

    datos = datos_inventados()

    pdf_path = generar_pdf_reporte_gira(datos, output_dir=GIRA_ZONA_OUTPUT_DIR)
    print(f"1) PDF generado:  {pdf_path}")
    assert os.path.exists(pdf_path), "el PDF no quedó en disco"

    final = _nombre_archivo_gira_zona(
        pdf_path,
        datos["agente"]["codigo"],
        datos["agente"]["nombre"],
        "GUANACASTE 1 SHINDAIWA",
    )
    print(f"2) PDF renombrado: {final}")

    nombre = os.path.basename(final)
    assert os.path.exists(final), "el archivo renombrado no existe"
    assert not os.path.exists(pdf_path), "quedó un duplicado con el nombre viejo"
    assert "GUANACASTE_1_SHINDAIWA" in nombre, "falta la zona en el nombre"
    assert nombre != os.path.basename(pdf_path), "el nombre no cambió"

    # Lo que importa: no puede coincidir con el patrón de la gira completa,
    # que es GIRA_{codigo}_{nombre}_{YYYYMMDD}.pdf sin zona ni hora.
    partes = nombre.replace(".pdf", "").split("_")
    assert len(partes[-1]) == 4 and partes[-1].isdigit(), "falta la marca de hora"
    print("3) Nombre distinto al de la gira completa: OK (lleva zona y hora)")

    # Caracteres que SharePoint no acepta
    sucio = _nombre_archivo_gira_zona(
        final, "9", "José Chacón", 'SUR 1 ECHO SANTOS (02,03)/"*?'
    )
    print(f"4) Zona con caracteres raros -> {os.path.basename(sucio)}")
    for c in '\\/:*?"<>|,':
        assert c not in os.path.basename(sucio), f"quedó el carácter {c!r}"
    print("   sin caracteres inválidos: OK")

    # Sin zona (selección mixta de varias zonas)
    mixto = _nombre_archivo_gira_zona(sucio, "6", "Siviany González", None)
    print(f"5) Sin zona -> {os.path.basename(mixto)}")
    assert "SELECCION" in os.path.basename(mixto)

    print()
    print("=" * 72)
    print(f"✅ Nivel 1 completo. Revisá el PDF a mano: {mixto}")
    print("=" * 72)


if __name__ == "__main__":
    main()
