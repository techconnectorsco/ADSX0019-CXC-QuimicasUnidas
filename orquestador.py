from datetime import datetime, timedelta
import os
import subprocess
import pytz


def debe_ejecutarse_hoy():
    tz_cr = pytz.timezone("America/Costa_Rica")
    hoy = datetime.now(tz_cr).date()

    dia = hoy.day
    dia_semana = hoy.weekday()  # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo

    if dia in [15, 30] and dia_semana < 5:
        return True

    if dia_semana == 4:  # Hoy es Viernes y mañana es 15 o 30
        manana = hoy + timedelta(days=1)
        if manana.day in [15, 30]:
            return True

    if dia_semana == 0:  # Hoy es Lunes y ayer fue 15 o 30
        ayer = hoy - timedelta(days=1)
        if ayer.day in [15, 30]:
            return True

    return False


def ejecutar_proceso_principal():
    print(f"[{datetime.now()}] Iniciando automatización CxC Químicas Unidas...")

    # 1. Obtener la ruta de la carpeta donde están parados los scripts actualmente
    carpeta_raiz = os.path.dirname(os.path.abspath(__file__))

    # 2. Construir las rutas dinámicas para main.py y el entorno virtual
    script_principal = os.path.join(carpeta_raiz, "main.py")

    # Supongamos que tu entorno virtual se llama 'env' o 'venv'. Cambia 'env' por su nombre real:
    nombre_entorno = "venv"
    python_entorno = os.path.join(carpeta_raiz, nombre_entorno, "Scripts", "python.exe")

    # 3. Lanzar el proceso usando el Python del entorno virtual
    try:
        resultado = subprocess.run(
            [python_entorno, script_principal],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Proceso finalizado con éxito.")
        print(resultado.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el proceso principal: {e}")
        print(e.stderr)


if __name__ == "__main__":
    if debe_ejecutarse_hoy():
        ejecutar_proceso_principal()
    else:
        print(
            f"[{datetime.now()}] Hoy no corresponde ejecución según las reglas del negocio."
        )
