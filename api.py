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
    agente_codigo: Optional[str] = None  # None = todos los agentes con correo
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

        if agente_codigo:
            print(f"\n[{job_id}] Iniciando gira manual del agente {agente_codigo}...")
        else:
            print(f"\n[{job_id}] Iniciando gira manual para TODOS los agentes...")

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
        f"revisión ({peticion.correo_destino})"
        if peticion.solo_prueba
        else "el/los agente(s)"
    )
    alcance = (
        f"el agente {peticion.agente_codigo}"
        if peticion.agente_codigo
        else "TODOS los agentes"
    )

    return {
        "estado": "exito",
        "mensaje": f"Gira procesada para {alcance}. Destino: {destino}.",
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


# ==========================================
# GIRA SELECTIVA POR ZONA
# ==========================================
# Bloque AGREGADO por el módulo "Giras por Zona" (ver PLAN_GIRAS_POR_ZONA.md,
# sección 7.2). Cola propia, worker propio y endpoints propios: no toca
# cola_tareas, cola_tareas_gira ni ninguno de los endpoints existentes.


class PeticionGiraZona(BaseModel):
    agente_codigo: str
    card_codes: List[str]
    solo_prueba: bool = False
    correo_destino: Optional[str] = None
    zona_nombre: Optional[str] = None
    dry_run: bool = False


cola_tareas_gira_zona = queue.Queue()

# Estado de los trabajos en memoria, para que la interfaz pueda consultarlo.
# Se pierde al reiniciar PM2 — es intencional, no hace falta persistirlo.
estados_gira_zona = {}


def procesador_cola_gira_zona():
    while True:
        tarea = cola_tareas_gira_zona.get()
        job_id = tarea["job_id"]

        estados_gira_zona[job_id] = {"estado": "procesando", "resultado": None}
        print(
            f"\n[{job_id}] Gira selectiva: agente {tarea['agente_codigo']}, "
            f"{len(tarea['card_codes'])} clientes..."
        )

        try:
            # modo_prueba y email_prueba van como ARGUMENTOS, nunca escribiendo
            # agentes.MODO_PRUEBA: dos colas tocando ese global producen una
            # race condition con la gira completa (sección 6.1 del plan).
            resultado = agentes.ejecutar_gira_selectiva(
                agente_id=tarea["agente_codigo"],
                card_codes=tarea["card_codes"],
                modo_prueba=tarea["solo_prueba"],
                email_prueba=tarea["correo_destino"] or "credito@qu.cr",
                zona_nombre=tarea["zona_nombre"],
                dry_run=tarea["dry_run"],
            )
            estados_gira_zona[job_id] = {
                "estado": "terminado" if resultado.get("ok") else "con_avisos",
                "resultado": resultado,
            }
            print(f"[{job_id}] {resultado.get('mensaje')}")

        except Exception as e:
            estados_gira_zona[job_id] = {
                "estado": "error",
                "resultado": {"ok": False, "mensaje": str(e)},
            }
            print(f"[{job_id}] Error en gira selectiva: {str(e)}")

        finally:
            cola_tareas_gira_zona.task_done()


threading.Thread(target=procesador_cola_gira_zona, daemon=True).start()


@app.post("/api/ejecutar-gira-zona")
def encolar_gira_zona(peticion: PeticionGiraZona):
    # Validar ANTES de encolar: un error dentro del worker no llega al usuario,
    # solo queda en los logs de PM2.
    if not peticion.agente_codigo or not str(peticion.agente_codigo).strip():
        return {"estado": "error", "mensaje": "Falta agente_codigo"}

    try:
        int(peticion.agente_codigo)
    except (TypeError, ValueError):
        return {
            "estado": "error",
            "mensaje": f"agente_codigo debe ser numérico, llegó: {peticion.agente_codigo!r}",
        }

    if not peticion.card_codes:
        return {"estado": "error", "mensaje": "Seleccione al menos un cliente"}

    if peticion.solo_prueba and not peticion.correo_destino:
        return {
            "estado": "error",
            "mensaje": "Debe proporcionar un 'correo_destino' en modo revisión",
        }

    job_id = str(uuid.uuid4())[:8]
    estados_gira_zona[job_id] = {"estado": "en_cola", "resultado": None}

    cola_tareas_gira_zona.put(
        {
            "job_id": job_id,
            "agente_codigo": str(peticion.agente_codigo).strip(),
            "card_codes": peticion.card_codes,
            "solo_prueba": peticion.solo_prueba,
            "correo_destino": peticion.correo_destino,
            "zona_nombre": peticion.zona_nombre,
            "dry_run": peticion.dry_run,
        }
    )

    # Si el interruptor de seguridad del módulo está puesto, avisarlo en la
    # respuesta: si no, la interfaz diría "gira encolada" y nunca llegaría nada.
    aviso = ""
    if getattr(agentes, "GIRA_ZONA_FORZAR_DRY_RUN", False):
        aviso = " [MODO ENSAYO: se genera el PDF pero no se envía ni se sube]"

    return {
        "estado": "exito",
        "mensaje": (
            f"Gira selectiva encolada: agente {peticion.agente_codigo}, "
            f"{len(peticion.card_codes)} clientes.{aviso}"
        ),
        "job_id": job_id,
        "modo_ensayo": bool(getattr(agentes, "GIRA_ZONA_FORZAR_DRY_RUN", False)),
    }


@app.get("/api/estado-gira-zona/{job_id}")
def estado_gira_zona(job_id: str):
    estado = estados_gira_zona.get(job_id)
    if not estado:
        return {"estado": "desconocido", "mensaje": "job_id no encontrado"}
    return estado


@app.get("/api/config-gira-zona")
def config_gira_zona():
    """
    Diagnóstico de solo lectura: en qué modo está el módulo antes de disparar
    nada. Útil para confirmar desde la web (o con un curl) que el interruptor
    de ensayo sigue puesto sin tener que entrar al VPS a leer el archivo.
    """
    return {
        "forzar_dry_run": bool(getattr(agentes, "GIRA_ZONA_FORZAR_DRY_RUN", False)),
        "cc_activo": bool(getattr(agentes, "GIRA_ZONA_CC_ACTIVO", False)),
        "subir_sharepoint": bool(
            getattr(agentes, "GIRA_ZONA_SUBIR_SHAREPOINT", False)
        ),
        "solo_revision": bool(getattr(agentes, "GIRA_ZONA_SOLO_REVISION", False)),
        "max_workers": getattr(agentes, "GIRA_ZONA_MAX_WORKERS", None),
        "output_dir": getattr(agentes, "GIRA_ZONA_OUTPUT_DIR", None),
        "tareas_en_cola": cola_tareas_gira_zona.qsize(),
    }


@app.get("/api/arbol-gira-zona")
def arbol_gira_zona(agente: int, refrescar: int = 0):
    """
    El arbol de zonas y clientes de un agente, con la elegibilidad resuelta.

    Solo lectura: NO encola nada, no toca cola_tareas_gira_zona ni ninguno de
    los endpoints existentes. Misma disciplina que siguio el resto del modulo.

    Reemplaza a obtenerArbolAgente() de sap.ts, que armaba el arbol con los
    clientes cuya FICHA tenia SalesPersonCode = agente. Ese criterio no es el
    del PDF, que rutea por U_CODV de la direccion del documento, y de ahi venia
    el reclamo: la pantalla dejaba marcar clientes que nunca salian. Aca los
    elegibles salen del mismo criterio del PDF.

    El frontend debe proxear a este endpoint SIN fallback al arbol viejo: si
    esto no responde, un error explicito es mejor que un arbol con el universo
    equivocado.

    ?refrescar=1 fuerza el recalculo. El cache dura 12 minutos (ver
    GIRA_ZONA_CACHE_TTL_SEGS): el mapa es de toda la empresa y cuesta ~100s en
    horario de oficina, asi que sin cache la pantalla es inusable.

    OJO con los montos: son APROXIMADOS. La precision de /SQLQueries depende de
    la sesion y redondea a 6 cifras significativas. La elegibilidad NO depende
    del monto, sino del ruteo y del conteo de documentos, que salen exactos.
    """
    conn = ServiceLayerConnection(use_test_db=False)
    if not conn.login():
        return {
            "error": "No se pudo conectar al Service Layer de SAP",
            "agente": None,
            "zonas": [],
            "sinZona": [],
        }

    try:
        return agentes.construir_arbol_gira_zona(
            conn, agente, refrescar=bool(refrescar)
        )
    except ValueError as e:
        # Agente que no existe: es culpa del pedido, no del servidor
        return {"error": str(e), "agente": None, "zonas": [], "sinZona": []}
    except RuntimeError as e:
        # SAP no contesto o rechazo una consulta. Devolver un arbol vacio en
        # silencio seria peor que el error: pareceria que el agente no tiene
        # ningun cliente con carga.
        return {
            "error": f"SAP no devolvio los datos completos: {e}",
            "agente": None,
            "zonas": [],
            "sinZona": [],
        }
    finally:
        try:
            conn.logout()
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8050)
