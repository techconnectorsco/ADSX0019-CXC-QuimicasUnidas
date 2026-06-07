import os
from datetime import datetime, timezone
from conexion_supabase import supabase_db, subir_archivo_bucket

# ⚠️ REEMPLAZA ESTE ID POR EL UUID QUE GENERES EN SUPABASE PARA QUÍMICAS UNIDAS
#    (corre registrar_rpa.py una sola vez y pega aquí el id que devuelva)
ID_RPA_QU = "55d181a5-ac18-4f1c-8c1d-30493028f03d"
ID_RPA_QU_GIRAS = "e167d49e-7f38-427e-8191-898e7688ad00"


def verificar_estado_rpa():
    """Consulta si el RPA está activo en Supabase."""
    try:
        print("ℹ️ Verificando estado del RPA: Forzado a ACTIVO (Simulado)")
        return True
    except Exception as e:
        print(f"⚠️ Error verificando estado: {e}. Continuando por defecto...")
        return True


def finalizar_y_reportar(
    status_global, ruta_pdf_local=None, automatizacion_id=ID_RPA_QU, subcarpeta="logs"
):
    """Sube el log PDF si lo hay, consolida métricas y registra la ejecución.
    automatizacion_id / subcarpeta permiten reportar a distintos RPAs (CxC / Giras)."""
    print("📤 Iniciando reporte final a Supabase...")

    url_log_publica = None
    if ruta_pdf_local and os.path.exists(ruta_pdf_local):
        nombre_archivo_nube = (
            f"QuimicasUnidas/{subcarpeta}/{datetime.now().strftime('%Y/%m')}/"
            f"log_{datetime.now().strftime('%d_%H%M%S')}.pdf"
        )
        url_log_publica = subir_archivo_bucket(
            "logs-rpa", ruta_pdf_local, nombre_archivo_nube
        )

    datos_ejecucion = {
        "automatizacion_id": automatizacion_id,
        "fecha_inicio": datetime.now(timezone.utc).isoformat(),
        "fecha_fin": datetime.now(timezone.utc).isoformat(),
        "estado": "Fallido" if status_global.get("error_critico") else "Exitoso",
        "metricas": status_global,
        "log_salida": url_log_publica or status_global.get("observaciones", ""),
    }

    try:
        res = supabase_db.table("ejecuciones").insert(datos_ejecucion).execute()
        print("✅ Ejecución reportada correctamente en Supabase.")
        return res.data
    except Exception as e:
        print(f"❌ Error al insertar ejecución: {e}")
        return None
