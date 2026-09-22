"""Genera un FUT de ejemplo sin usar el modelo de lenguaje.

Sirve para validar las coordenadas del formulario tras cambiar la plantilla.

Uso:
    python scripts/prueba_llenado.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.configuracion import obtenerConfiguracion  # noqa: E402
from src.llenador_fut import generarNombreArchivo, guardarFut, rellenarFut  # noqa: E402
from src.modelos import DatosEmpresa, SolicitudFut  # noqa: E402


def construirSolicitudDeEjemplo() -> SolicitudFut:
    """Solicitud de carta de presentación con todos los campos completos."""
    solicitud = SolicitudFut(
        tramiteClave="carta_presentacion",
        apellidosNombres="Quispe Ramírez, Christian Alonso",
        escuelaProfesional="Ingeniería de Sistemas",
        codigoEstudiante="2021015432",
        documentoIdentidad="74125896",
        direccion="Av. Los Próceres 1450 - Urb. San Rafael",
        numeroDepartamento="Dpto. 302",
        distrito="San Isidro",
        telefonoFijo="016543210",
        celular="987654321",
        correoElectronico="christian.quispe@unfv.edu.pe",
        empresa=DatosEmpresa(
            nombreInstitucion="Consultora Andina de Sistemas S.A.C.",
            ruc="20512345671",
            correo="practicas@andinasistemas.com.pe",
            telefono="014567890",
            direccion="Av. Javier Prado Este 2050, San Isidro",
            destinatario="Ing. María Fernanda Torres Loayza - Jefa de Recursos Humanos",
        ),
    )
    solicitud.aplicarValoresDelTramite()
    solicitud.fundamentacion = solicitud.construirFundamentacion()
    return solicitud


def principal() -> int:
    configuracion = obtenerConfiguracion()
    solicitud = construirSolicitudDeEjemplo()
    contenido = rellenarFut(solicitud, configuracion.rutaPlantillaFut)
    destino = guardarFut(contenido, configuracion.directorioSalidas, generarNombreArchivo(solicitud))
    print(f"FUT de ejemplo generado en: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
