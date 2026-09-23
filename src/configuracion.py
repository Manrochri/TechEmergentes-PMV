"""Configuración de la aplicación, leída desde variables de entorno y ``.env``.

Se usa ``pydantic-settings`` para que cada valor quede validado y tipado en un solo
lugar. Ningún otro módulo debería leer ``os.environ`` directamente.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO: Path = Path(__file__).resolve().parent.parent


class Configuracion(BaseSettings):
    """Parámetros de ejecución del asistente de trámites."""

    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Ollama -----------------------------------------------------------------
    ollamaHost: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollamaModelo: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODELO")
    ollamaTemperatura: float = Field(default=0.2, ge=0.0, le=2.0, alias="OLLAMA_TEMPERATURA")
    ollamaTiempoEspera: int = Field(default=120, ge=10, alias="OLLAMA_TIEMPO_ESPERA")
    ollamaVentanaContexto: int = Field(default=8192, ge=2048, alias="OLLAMA_NUM_CTX")
    ollamaMaxTokens: int = Field(default=1024, ge=128, alias="OLLAMA_MAX_TOKENS")

    # --- Gemini (respaldo cuando Qwen3 no está disponible) -----------------------
    geminiApiKey: str = Field(default="", alias="GEMINI_API_KEY")
    geminiModelo: str = Field(default="gemini-3.6-flash", alias="GEMINI_MODELO")
    geminiTemperatura: float = Field(default=0.2, ge=0.0, le=2.0, alias="GEMINI_TEMPERATURA")
    geminiTiempoEspera: int = Field(default=60, ge=10, alias="GEMINI_TIEMPO_ESPERA")
    geminiMaxTokens: int = Field(default=1024, ge=128, alias="GEMINI_MAX_TOKENS")

    # --- Selección de proveedor de LLM -------------------------------------------
    #: Switch SOLO para pruebas manuales: "" (por defecto) = automático (Qwen3 y, si no
    #: está disponible, Gemini); "qwen" o "gemini" fuerzan ese proveedor sin comprobar
    #: antes si Qwen3 responde.
    proveedorLlmManual: str = Field(default="", alias="PROVEEDOR_LLM_MANUAL")

    # --- Rutas ------------------------------------------------------------------
    rutaPlantillaFut: Path = Field(
        default=RAIZ_PROYECTO / "assets" / "FUT_SG-FORMULARIO.pdf",
        alias="RUTA_PLANTILLA_FUT",
    )
    rutaLogo: Path = Field(
        default=RAIZ_PROYECTO / "assets" / "Logo_fiis_nuevo.png",
        alias="RUTA_LOGO",
    )
    rutaEstilos: Path = Field(
        default=RAIZ_PROYECTO / "assets" / "estilos.css",
        alias="RUTA_ESTILOS",
    )
    directorioSalidas: Path = Field(
        default=RAIZ_PROYECTO / "salidas",
        alias="DIRECTORIO_SALIDAS",
    )

    # --- Comportamiento ---------------------------------------------------------
    ciudadPredeterminada: str = Field(default="Lima", alias="CIUDAD_PREDETERMINADA")
    guardarCopiaLocal: bool = Field(default=True, alias="GUARDAR_COPIA_LOCAL")
    mensajesEnHistorial: int = Field(default=12, ge=2, alias="MENSAJES_EN_HISTORIAL")
    modoDepuracion: bool = Field(default=False, alias="MODO_DEPURACION")

    # --- Identidad visual -------------------------------------------------------
    colorPrincipal: str = Field(default="#792D2F", alias="COLOR_PRINCIPAL")
    nombreAplicacion: str = Field(default="Asistente de trámites FIIS", alias="NOMBRE_APLICACION")

    @field_validator("rutaPlantillaFut", "rutaLogo", "rutaEstilos", "directorioSalidas", mode="before")
    @classmethod
    def resolverRutaRelativa(cls, valor: object) -> Path:
        ruta = Path(str(valor))
        return ruta if ruta.is_absolute() else (RAIZ_PROYECTO / ruta)

    def verificarRutas(self) -> list[str]:
        """Devuelve la lista de problemas encontrados en las rutas configuradas."""
        problemas: list[str] = []
        if not self.rutaPlantillaFut.is_file():
            problemas.append(f"No se encontró la plantilla del FUT en {self.rutaPlantillaFut}")
        if not self.rutaLogo.is_file():
            problemas.append(f"No se encontró el logo de la FIIS en {self.rutaLogo}")
        return problemas


@lru_cache(maxsize=1)
def obtenerConfiguracion() -> Configuracion:
    """Instancia única de la configuración (se cachea durante la vida del proceso)."""
    configuracion = Configuracion()
    configuracion.directorioSalidas.mkdir(parents=True, exist_ok=True)
    return configuracion


__all__ = ["Configuracion", "obtenerConfiguracion", "RAIZ_PROYECTO"]