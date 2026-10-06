"""Cliente delgado sobre la API de Gemini (Google AI Studio / Generative Language API).

Se usa como respaldo cuando Qwen3 (servido por Ollama) no está disponible. Expone
exactamente la misma interfaz pública que :class:`~src.servicio_ollama.ServicioOllama`
(``verificarDisponibilidad``, ``conversar``, ``extraerEstructurado``) para que
``AgenteFut`` pueda usar cualquiera de los dos sin ningún cambio en su lógica: ver
``src/servicio_llm.py`` para la selección entre ambos.

No se usa el SDK oficial ``google-genai`` a propósito, para mantener la misma filosofía
que ``servicio_ollama.py``: una única dependencia liviana (``requests``) y una llamada
HTTP directa y fácil de auditar.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from .configuracion import Configuracion, obtenerConfiguracion
from .errores_llm import ErrorServicioLlm

registrador = logging.getLogger(__name__)

_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

#: Códigos HTTP transitorios de Google (servidor saturado o límite de tasa) que vale la
#: pena reintentar: no son un error de nuestra solicitud, suelen resolverse solos.
_CODIGOS_REINTENTABLES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_INTENTOS_MAXIMOS: int = 3
_ESPERA_BASE_SEGUNDOS: float = 1.0


class ErrorGemini(ErrorServicioLlm):
    """Error de comunicación o de configuración con la API de Gemini."""


class ServicioGemini:
    """Envoltorio de las dos operaciones que necesita el asistente: chatear y extraer."""

    def __init__(self, configuracion: Configuracion | None = None) -> None:
        self.configuracion = configuracion or obtenerConfiguracion()

    # ------------------------------------------------------------------ diagnóstico
    def verificarDisponibilidad(self) -> tuple[bool, str]:
        """Comprueba que hay una clave de API configurada y que Google la acepta."""
        clave = self.configuracion.geminiApiKey
        modelo = self.configuracion.geminiModelo
        if not clave:
            return False, (
                "No se configuró GEMINI_API_KEY: no se puede usar Gemini como respaldo del LLM."
            )
        try:
            respuesta = requests.get(
                f"{_URL_BASE}/{modelo}",
                headers={"x-goog-api-key": clave},
                timeout=self.configuracion.geminiTiempoEspera,
            )
            respuesta.raise_for_status()
        except requests.RequestException as error:
            return False, (
                f"No se pudo conectar con la API de Gemini (modelo '{modelo}'). "
                f"Verifica GEMINI_API_KEY y la conexión a internet. Detalle: {error}"
            )
        return True, f"Gemini disponible con el modelo '{modelo}'."

    # ------------------------------------------------------------------ generación
    def conversar(
        self,
        mensajes: list[dict[str, str]],
        temperatura: float | None = None,
    ) -> str:
        """Genera una respuesta en lenguaje natural."""
        cuerpo = self._construirCuerpo(mensajes, temperatura)
        datos = self._llamar(cuerpo)
        return self._extraerTexto(datos).strip()

    def extraerEstructurado(
        self,
        mensajes: list[dict[str, str]],
        esquema: dict[str, Any],
        temperatura: float = 0.0,
    ) -> dict[str, Any]:
        """Pide una respuesta que cumpla un JSON Schema y la devuelve ya parseada.

        Igual que en :class:`ServicioOllama`, un JSON mal formado nunca lanza una
        excepción: se registra y se devuelve un diccionario vacío para que la
        conversación continúe y el dato se vuelva a preguntar en vez de inventarse.
        """
        cuerpo = self._construirCuerpo(mensajes, temperatura)
        # `responseJsonSchema` acepta JSON Schema estándar (a diferencia de
        # `responseSchema`, que exige el subconjunto de OpenAPI de Google), así que el
        # mismo esquema que ya arma `construirEsquemaExtraccion()` para Ollama sirve tal cual.
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
        cuerpo["generationConfig"]["responseJsonSchema"] = esquema

        datos = self._llamar(cuerpo)
        contenido = self._extraerTexto(datos).strip()
        registrador.debug("Respuesta cruda de extracción (Gemini): %s", contenido[:500])
        return self._analizarJson(contenido)

    # ------------------------------------------------------------------ internos
    def _construirCuerpo(
        self, mensajes: list[dict[str, str]], temperatura: float | None
    ) -> dict[str, Any]:
        """Traduce el formato de mensajes estilo Ollama/OpenAI al formato de Gemini.

        Gemini separa el mensaje de sistema (``systemInstruction``) del resto de la
        conversación, y llama ``model`` (no ``assistant``) al rol del asistente.
        """
        instrucciones = "\n\n".join(
            m["content"] for m in mensajes if m.get("role") == "system" and m.get("content")
        )
        contenidos = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in mensajes
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ]
        if not contenidos:
            # Gemini exige al menos un mensaje en `contents`.
            contenidos = [{"role": "user", "parts": [{"text": ""}]}]

        cuerpo: dict[str, Any] = {
            "contents": contenidos,
            "generationConfig": {
                "temperature": (
                    self.configuracion.geminiTemperatura if temperatura is None else temperatura
                ),
                "maxOutputTokens": self.configuracion.geminiMaxTokens,
            },
        }
        if instrucciones:
            cuerpo["systemInstruction"] = {"parts": [{"text": instrucciones}]}
        return cuerpo

    def _llamar(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        """Llama a Gemini con reintentos ante errores transitorios (503, 429, etc.).

        Un 503 "Service Unavailable" significa que los servidores de Google están
        saturados en ese instante, no que la solicitud esté mal formada: casi siempre se
        resuelve solo en un par de segundos. Sin reintento, como en la nube Gemini es el
        único proveedor (no hay Ollama de respaldo), ese pico momentáneo tumbaba el turno
        completo del estudiante. Se reintenta con espera creciente (1 s, 2 s) y solo para
        esos códigos; un error real (clave inválida, 400, etc.) se propaga de inmediato.
        """
        modelo = self.configuracion.geminiModelo
        clave = self.configuracion.geminiApiKey
        if not clave:
            raise ErrorGemini("No se configuró GEMINI_API_KEY.")

        ultimoError: Exception | None = None
        for intento in range(1, _INTENTOS_MAXIMOS + 1):
            try:
                respuesta = requests.post(
                    f"{_URL_BASE}/{modelo}:generateContent",
                    headers={"x-goog-api-key": clave, "Content-Type": "application/json"},
                    data=json.dumps(cuerpo),
                    timeout=self.configuracion.geminiTiempoEspera,
                )
                respuesta.raise_for_status()
            except requests.RequestException as error:
                ultimoError = error
                codigo = getattr(error.response, "status_code", None)
                if codigo not in _CODIGOS_REINTENTABLES or intento == _INTENTOS_MAXIMOS:
                    raise ErrorGemini(f"Fallo al consultar a Gemini: {error}") from error
                espera = _ESPERA_BASE_SEGUNDOS * intento
                registrador.warning(
                    "Gemini devolvió %s (intento %d/%d); reintentando en %.0fs.",
                    codigo, intento, _INTENTOS_MAXIMOS, espera,
                )
                time.sleep(espera)
                continue

            try:
                return respuesta.json()
            except ValueError as error:
                raise ErrorGemini(f"Gemini devolvió una respuesta que no es JSON: {error}") from error

        # Inalcanzable en la práctica (el bucle siempre retorna o lanza), pero deja el
        # tipo de retorno correcto ante cualquier cambio futuro en la lógica de arriba.
        raise ErrorGemini(f"Fallo al consultar a Gemini tras reintentos: {ultimoError}")

    @staticmethod
    def _extraerTexto(datos: dict[str, Any]) -> str:
        """Concatena las partes de texto del primer candidato devuelto por Gemini."""
        try:
            partes = datos["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            registrador.warning("Respuesta de Gemini sin texto utilizable: %s", str(datos)[:300])
            return ""
        return "".join(parte.get("text", "") for parte in partes if isinstance(parte, dict))

    @staticmethod
    def _analizarJson(contenido: str) -> dict[str, Any]:
        """Extrae el primer objeto JSON válido de una respuesta, tolerando ruido alrededor.

        Mismo criterio tolerante que :meth:`ServicioOllama._analizarJson`: se recorta al
        primer ``{`` y al último ``}`` antes de parsear, por si el modelo envuelve la
        respuesta en una cerca de código markdown o añade una frase alrededor.
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
            registrador.warning("La respuesta de Gemini no contiene un objeto JSON: %s", contenido[:200])
            return {}

        fragmento = texto[inicio : fin + 1]
        try:
            datos = json.loads(fragmento)
        except json.JSONDecodeError:
            registrador.warning("JSON inválido tras recortar la respuesta de Gemini: %s", fragmento[:300])
            return {}
        return datos if isinstance(datos, dict) else {}


__all__ = ["ServicioGemini", "ErrorGemini"]