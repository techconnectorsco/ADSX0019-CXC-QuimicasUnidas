import os
import sys

# ==============================================================================
# 1. PARCHE DE ENTORNO (PATH Y ENCODING PARA WINDOWS)
# ==============================================================================
# Asegurar que el script encuentre main.py y los módulos locales de inmediato
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Parche anti-crash para entornos sin ventana + Forzar UTF-8 nativo en consola Windows
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
elif hasattr(sys.stdout, "reconfigure"):
    # Esto inmuniza los prints contra acentos, eñes y caracteres raros de SAP
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
elif hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


# ==============================================================================
# 2. IMPORTS SÓLIDOS (Llamados después de asegurar los paths)
# ==============================================================================
import queue
import threading
import uuid
from typing import List, Optional

import main
import uvicorn
from fastapi import FastAPI
from main import obtener_clientes_con_saldo
from modules.database.conexion import ServiceLayerConnection
from pydantic import BaseModel
import agentes

# ==========================================
# INICIALIZACIÓN
# ==========================================
app = FastAPI(title="API RPA CXC - Sistema de Colas Local")
cola_tareas = queue.Queue()


# Payload coordinado con la interfaz Svelte
class PeticionCXC(BaseModel):
    clientes: List[str] = []
    solo_prueba: bool = False
    ejecutar_todos: bool = False
    correo_destino: Optional[str] = (
        None  # Correo al que llegarán los PDFs en modo prueba
    )
    correo_logs: Optional[str] = None  # Correo al que llegará el Log de Control


# ==========================================
# HILO TRABAJADOR (WORKER)
# ==========================================
def procesador_cola():
    while True:
        tarea = cola_tareas.get()
        job_id = tarea["job_id"]
        clientes = tarea["clientes"]
        solo_prueba = tarea["solo_prueba"]
        correo_destino = tarea["correo_destino"]
        correo_logs = tarea["correo_logs"]

        print(f"\n[{job_id}] Iniciando trabajo...")

        try:
            # 1. Configurar destino del Log de Control
            if correo_logs:
                main.EMAIL_LOG_CONTROL = main.parsear_correos_campo(correo_logs)
                print(f"[{job_id}] LOGS: Redirigidos a {correo_logs}")
            else:
                main.EMAIL_LOG_CONTROL = [
                    "credito@qu.cr",
                    "devs@techconnectors.co",
                    "creditodenis@qu.cr",
                    "asistente1@powermotorsca.com",
                ]
                print(f"[{job_id}] LOGS: Enviados al equipo completo por defecto")

            # 2. Configurar modo Prueba vs Real (Destino de los PDFs)
            if solo_prueba:
                main.MODO_PRUEBA = True
                correo_prueba_final = (
                    correo_destino if correo_destino else "devs@techconnectors.co"
                )
                main.EMAIL_PRUEBA = main.parsear_correos_campo(correo_prueba_final)
                print(f"[{job_id}] MODO PRUEBA: PDFs enviados a {correo_prueba_final}")
            else:
                main.MODO_PRUEBA = False
                print(
                    f"[{job_id}] MODO REAL: Correos enviados directamente a los clientes"
                )

            # 3. Alcance de ejecución
            if clientes is None:
                print(
                    f"[{job_id}] ALCANCE: Ejecutando para TODOS los clientes con saldo"
                )
            else:
                print(
                    f"[{job_id}] ALCANCE: Ejecutando para {len(clientes)} clientes específicos"
                )

            # 4. Ejecutar el proceso principal en main.py
            main.ejecutar_proceso_cxc(lista_clientes=clientes)
            print(f"[{job_id}] Trabajo finalizado con éxito.")

        except Exception as e:
            # Gracias al reconfigure de arriba, si 'e' trae acentos o texto raro, ya no crashea
            print(f"[{job_id}] Error en el proceso: {str(e)}")

        finally:
            cola_tareas.task_done()


# Arrancar el trabajador en segundo plano
threading.Thread(target=procesador_cola, daemon=True).start()


class PeticionGira(BaseModel):
    agente_codigo: str
    solo_prueba: bool = False
    correo_destino: Optional[str] = None


cola_tareas_gira = queue.Queue()


def procesador_cola_gira():
    while True:
        tarea = cola_tareas_gira.get()
        job_id = tarea["job_id"]
        agente_codigo = tarea["agente_codigo"]
        solo_prueba = tarea["solo_prueba"]
        correo_destino = tarea["correo_destino"]

        print(f"\n[{job_id}] Iniciando gira manual del agente {agente_codigo}...")

        try:
            if solo_prueba:
                agentes.MODO_PRUEBA = True
                agentes.EMAIL_PRUEBA = correo_destino or "credito@qu.cr"
                print(f"[{job_id}] MODO REVISIÓN: PDF enviado a {agentes.EMAIL_PRUEBA}")
            else:
                agentes.MODO_PRUEBA = False
                print(f"[{job_id}] MODO REAL: Enviando al correo del agente en SAP")

            agentes.ejecutar_reportes_gira(agente_id=agente_codigo)
            print(f"[{job_id}] Gira finalizada con éxito.")

        except Exception as e:
            print(f"[{job_id}] Error en la gira: {str(e)}")

        finally:
            cola_tareas_gira.task_done()


threading.Thread(target=procesador_cola_gira, daemon=True).start()


# ==========================================
# ENDPOINTS DE LA API
# ==========================================


@app.get("/api/health")
def health_check():
    return {
        "estado": "online",
        "mensaje": "API RPA CXC operando correctamente en segundo plano",
        "tareas_en_cola": cola_tareas.qsize(),
    }


@app.post("/api/ejecutar-cxc")
def encolar_rpa(peticion: PeticionCXC):
    if not peticion.ejecutar_todos and not peticion.clientes:
        return {
            "estado": "error",
            "mensaje": "Debe seleccionar clientes o activar la opción 'ejecutar_todos'",
        }

    if peticion.solo_prueba and not peticion.correo_destino:
        return {
            "estado": "error",
            "mensaje": "Debe proporcionar un 'correo_destino' al activar el modo de revisión",
        }

    job_id = str(uuid.uuid4())[:8]
    clientes_a_procesar = None if peticion.ejecutar_todos else peticion.clientes

    cola_tareas.put(
        {
            "job_id": job_id,
            "clientes": clientes_a_procesar,
            "solo_prueba": peticion.solo_prueba,
            "correo_destino": peticion.correo_destino,
            "correo_logs": peticion.correo_logs,
        }
    )

    destino_pdf = (
        f"Revisión ({peticion.correo_destino})" if peticion.solo_prueba else "Clientes"
    )
    alcance = (
        "TODOS los clientes"
        if peticion.ejecutar_todos
        else f"{len(peticion.clientes)} clientes"
    )

    return {
        "estado": "exito",
        "mensaje": f"Enviado correctamente para {alcance}. PDFs a: {destino_pdf}.",
        "job_id": job_id,
    }


@app.post("/api/ejecutar-gira")
def encolar_gira(peticion: PeticionGira):
    if not peticion.agente_codigo:
        return {"estado": "error", "mensaje": "Debe seleccionar un agente"}

    if peticion.solo_prueba and not peticion.correo_destino:
        return {
            "estado": "error",
            "mensaje": "Debe proporcionar un 'correo_destino' al activar el modo de revisión",
        }

    job_id = str(uuid.uuid4())[:8]

    cola_tareas_gira.put(
        {
            "job_id": job_id,
            "agente_codigo": peticion.agente_codigo,
            "solo_prueba": peticion.solo_prueba,
            "correo_destino": peticion.correo_destino,
        }
    )

    destino = (
        f"revisión ({peticion.correo_destino})" if peticion.solo_prueba else "el agente"
    )

    return {
        "estado": "exito",
        "mensaje": f"Gira del agente {peticion.agente_codigo} procesada con exito. Destino: {destino}.",
        "job_id": job_id,
    }


@app.get("/api/clientes-con-saldo")
def listar_clientes():
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return {"estado": "error", "mensaje": "No se pudo conectar a SAP SL"}

    try:
        clientes = obtener_clientes_con_saldo(conn)
        return {"estado": "exito", "total": len(clientes), "clientes": clientes}
    except Exception as e:
        return {"estado": "error", "mensaje": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8050)
