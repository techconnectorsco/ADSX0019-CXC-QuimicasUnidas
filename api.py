import sys
import os
import threading
import queue
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from modules.database.conexion import ServiceLayerConnection
from main import obtener_clientes_con_saldo

# Asegurar que el script encuentre main.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main

# ==========================================
# INICIALIZACIÓN
# ==========================================
app = FastAPI(title="API RPA CXC - Sistema de Colas Local")

cola_tareas = queue.Queue()


# Actualizado para que coincida exactamente con el payload de SvelteKit
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

        print(f"\n[{job_id}] 🔄 Iniciando trabajo encolado...")

        try:
            # 1. Configurar destino del Log de Control
            if correo_logs:
                main.EMAIL_LOG_CONTROL = [correo_logs]
                print(f"[{job_id}] ⚙️ LOGS: Redirigidos a {correo_logs}")
            else:
                main.EMAIL_LOG_CONTROL = [
                    "credito@qu.cr",
                    "devs@techconnectors.co",
                    "creditodenis@qu.cr",
                    "asistente1@powermotorsca.com",
                ]
                print(f"[{job_id}] ⚙️ LOGS: Enviados al equipo completo por defecto")

            # 2. Configurar modo Prueba vs Real (Destino de los PDFs)
            if solo_prueba:
                main.MODO_PRUEBA = True
                # Usar el correo dinámico de la web, o un fallback de seguridad
                correo_prueba_final = (
                    correo_destino if correo_destino else "devs@techconnectors.co"
                )
                main.EMAIL_PRUEBA = correo_prueba_final

                print(
                    f"[{job_id}] ⚙️ MODO PRUEBA: PDFs enviados a {correo_prueba_final}"
                )
            else:
                main.MODO_PRUEBA = False
                print(
                    f"[{job_id}] ⚙️ MODO REAL: Correos enviados directamente a los clientes"
                )

            # 3. Alcance de ejecución
            if clientes is None:
                print(
                    f"[{job_id}] 🌍 ALCANCE: Ejecutando para TODOS los clientes con saldo"
                )
            else:
                print(
                    f"[{job_id}] 🎯 ALCANCE: Ejecutando para {len(clientes)} clientes específicos"
                )

            # 4. Ejecutar el proceso principal
            main.ejecutar_proceso_cxc(lista_clientes=clientes)

            print(f"[{job_id}] ✅ Trabajo finalizado con éxito.")

        except Exception as e:
            print(f"[{job_id}] ❌ Error en el proceso: {str(e)}")

        finally:
            cola_tareas.task_done()


# Arrancar el trabajador al iniciar la API
threading.Thread(target=procesador_cola, daemon=True).start()


# ==========================================
# ENDPOINTS DE LA API
# ==========================================
@app.post("/api/ejecutar-cxc")
def encolar_rpa(peticion: PeticionCXC):
    if not peticion.ejecutar_todos and not peticion.clientes:
        return {
            "estado": "error",
            "mensaje": "Debe seleccionar clientes o activar la opción 'ejecutar_todos'",
        }

    # Validación adicional: si es modo prueba, exigir el correo destino
    if peticion.solo_prueba and not peticion.correo_destino:
        return {
            "estado": "error",
            "mensaje": "Debe proporcionar un 'correo_destino' al activar el modo de revisión",
        }

    job_id = str(uuid.uuid4())[:8]
    clientes_a_procesar = None if peticion.ejecutar_todos else peticion.clientes

    # Mandar a la cola local
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
        "mensaje": f"Encolado correctamente para {alcance}. PDFs a: {destino_pdf}.",
        "job_id": job_id,
    }


@app.get("/api/clientes-con-saldo")
def listar_clientes():
    """Devuelve la lista de clientes con saldo directamente desde SAP (Rápido por estar en red local)"""
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
