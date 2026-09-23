"""Cliente delgado sobre Ollama.

Aísla toda la comunicación con el modelo ``qwen2.5:7b`` para que el resto de la
aplicación no dependa de la librería ni de sus errores. Usa **salidas estructuradas**
(el parámetro ``format`` con un JSON Schema), disponible desde Ollama 0.5, para que la
extracción de datos sea fiable y no requiera parsear texto libre.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ollama import Client, ResponseError

from .configuracion import Configuracion, obtenerConfiguracion
from .errores_llm import ErrorServicioLlm

registrador = logging.getLogger(__name__)


class ErrorOllama(ErrorServicioLlm):
    """Error de comunicación o de configuración con el servidor de Ollama."""


class ServicioOllama:
    """Envoltorio de las dos operaciones que necesita el asistente: chatear y extraer."""

    def __init__(self, configuracion: Configuracion | None = None) -> None:
        self.configuracion = configuracion or obtenerConfiguracion()
        self._cliente = Client(
            host=self.configuracion.ollamaHost,
            timeout=self.configuracion.ollamaTiempoEspera,
        )

    # ------------------------------------------------------------------ diagnóstico
    def verificarDisponibilidad(self) -> tuple[bool, str]:
        """Comprueba que el servidor responde y que el modelo está descargado."""
        try:
            respuesta = self._cliente.list()
        except Exception as error:
            return False, (
                f"No se pudo conectar con Ollama en {self.configuracion.ollamaHost}. "
                f"Verifica que el servicio esté activo (`ollama serve`). Detalle: {error}"
            )

        modelos = {self._nombreModelo(m) for m in getattr(respuesta, "models", []) or []}
        objetivo = self.configuracion.ollamaModelo
        if objetivo not in modelos and objetivo.split(":")[0] not in {m.split(":")[0] for m in modelos}:
            return False, (
                f"El modelo '{objetivo}' no está descargado. "
                f"Ejecuta: ollama pull {objetivo}"
            )
        return True, f"Ollama disponible con el modelo '{objetivo}'."

    @staticmethod
    def _nombreModelo(modelo: Any) -> str:
        return str(getattr(modelo, "model", None) or getattr(modelo, "name", "") or "")

    # ------------------------------------------------------------------ generación
    def conversar(
        self,
        mensajes: list[dict[str, str]],
        temperatura: float | None = None,
    ) -> str:
        """Genera una respuesta en lenguaje natural."""
        try:
            respuesta = self._cliente.chat(
                model=self.configuracion.ollamaModelo,
                messages=mensajes,
                options=self._opciones(temperatura),
            )
        except ResponseError as error:
            raise ErrorOllama(f"Ollama rechazó la solicitud: {error}") from error
        except Exception as error:
            raise ErrorOllama(f"Fallo al consultar a Ollama: {error}") from error

        return (respuesta.message.content or "").strip()

    def extraerEstructurado(
        self,
        mensajes: list[dict[str, str]],
        esquema: dict[str, Any],
        temperatura: float = 0.0,
    ) -> dict[str, Any]:
        """Pide una respuesta que cumpla un JSON Schema y la devuelve ya parseada.

        Devuelve un diccionario vacío si el modelo entrega algo que no es JSON válido:
        la conversación continúa y el dato se vuelve a preguntar, nunca se inventa.
        Nunca lanza si el problema es solo un JSON mal formado, para que un fallo aquí
        jamás congele la conversación; solo se propaga si Ollama no responde en absoluto.
        """
        try:
            respuesta = self._cliente.chat(
                model=self.configuracion.ollamaModelo,
                messages=mensajes,
                format=esquema,
                options=self._opciones(temperatura),
            )
        except ResponseError as error:
            raise ErrorOllama(f"Ollama rechazó la extracción: {error}") from error
        except Exception as error:
            raise ErrorOllama(f"Fallo al extraer datos con Ollama: {error}") from error

        contenido = (respuesta.message.content or "").strip()
        registrador.debug("Respuesta cruda de extracción: %s", contenido[:500])
        return self._analizarJson(contenido)

    def _analizarJson(self, contenido: str) -> dict[str, Any]:
        """Extrae el primer objeto JSON válido de una respuesta, tolerando ruido alrededor.

        Algunos modelos, pese a recibir ``format`` con un JSON Schema, igual envuelven la
        respuesta en una cerca de código markdown o añaden una frase antes o después. En
        vez de exigir una coincidencia exacta, se recorta al primer ``{`` y al último ``}``
        antes de parsear.
        """
        if not contenido:
            return {}

        texto = contenido.strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            if texto[:4].lower() == "json":
                texto = texto[4:]

        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fin == -1 or fin < inicio:
            registrador.warning("La respuesta no contiene un objeto JSON: %s", contenido[:200])
            return {}

        fragmento = texto[inicio : fin + 1]
        try:
            datos = json.loads(fragmento)
        except json.JSONDecodeError:
            registrador.warning("JSON inválido tras recortar la respuesta: %s", fragmento[:300])
            return {}
        return datos if isinstance(datos, dict) else {}

    def _opciones(self, temperatura: float | None) -> dict[str, Any]:
        return {
            "temperature": self.configuracion.ollamaTemperatura if temperatura is None else temperatura,
            "num_ctx": self.configuracion.ollamaVentanaContexto,
            "num_predict": self.configuracion.ollamaMaxTokens,
        }


__all__ = ["ServicioOllama", "ErrorOllama"]