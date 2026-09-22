"""Mapa de coordenadas de los campos del Formulario Único de Trámite (SG-UNFV-001).

Las coordenadas se obtuvieron leyendo la estructura vectorial real de la plantilla
``assets/FUT_SG-FORMULARIO.pdf`` (tablas, celdas y etiquetas), no por estimación visual.

Sistema de referencia
---------------------
Se usa el sistema "top-down" de pdfplumber: el origen está en la esquina superior
izquierda y ``y`` crece hacia abajo. El módulo :mod:`src.llenador_fut` convierte estas
coordenadas al sistema "bottom-up" de ReportLab al momento de dibujar.

Si alguna vez la Secretaría General publica una nueva versión de la plantilla, este es
el único archivo que hay que reajustar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Dimensiones de la página 1 de la plantilla original (en puntos PostScript).
ANCHO_PAGINA: float = 595.56
ALTO_PAGINA: float = 842.04

# La plantilla tiene 2 páginas: el formulario y el reverso con la lista de trámites.
PAGINA_FORMULARIO: int = 0


@dataclass(frozen=True)
class CampoFut:
    """Describe el área rectangular donde se imprime el valor de un campo del FUT."""

    clave: str
    x: float
    y: float
    ancho: float
    alto: float
    tamanoFuente: float = 9.0
    fuente: str = "Helvetica"
    multilinea: bool = False
    interlineado: float = 11.0
    centrado: bool = False
    tamanoMinimo: float = 6.0

    @property
    def limiteLineas(self) -> int:
        """Número máximo de líneas que caben en el alto disponible."""
        if not self.multilinea:
            return 1
        return max(1, int(self.alto // self.interlineado))


def _campo(clave: str, x: float, y: float, ancho: float, alto: float, **extra) -> CampoFut:
    return CampoFut(clave=clave, x=x, y=y, ancho=ancho, alto=alto, **extra)


#: Campos de texto del formulario, indexados por el nombre del atributo del modelo.
#: ``y`` es la **línea base** de la primera línea de texto (sistema top-down).
CAMPOS_TEXTO: dict[str, CampoFut] = {
    # --- Encabezado -------------------------------------------------------------
    "dependencia": _campo(
        "dependencia", x=66.0, y=180.0, ancho=268.0, alto=24.0,
        tamanoFuente=8.5, multilinea=True, interlineado=10.0,
    ),
    "numeroTramite": _campo(
        "numeroTramite", x=410.0, y=180.0, ancho=58.0, alto=10.0, tamanoFuente=9.0,
    ),
    "sumilla": _campo(
        "sumilla", x=378.0, y=190.0, ancho=178.0, alto=15.0,
        tamanoFuente=7.0, multilinea=True, interlineado=7.5,
    ),
    # --- Datos del solicitante --------------------------------------------------
    "apellidosNombres": _campo(
        "apellidosNombres", x=68.0, y=296.0, ancho=484.0, alto=14.0, tamanoFuente=10.0,
    ),
    "facultad": _campo(
        "facultad", x=66.0, y=330.0, ancho=178.0, alto=17.0,
        tamanoFuente=7.5, multilinea=True, interlineado=8.5,
    ),
    "escuelaProfesional": _campo(
        "escuelaProfesional", x=250.0, y=330.0, ancho=205.0, alto=17.0,
        tamanoFuente=7.5, multilinea=True, interlineado=8.5,
    ),
    "codigoEstudiante": _campo(
        "codigoEstudiante", x=463.0, y=336.0, ancho=92.0, alto=12.0, tamanoFuente=9.0,
    ),
    # --- Documento y domicilio --------------------------------------------------
    "documentoIdentidad": _campo(
        "documentoIdentidad", x=66.0, y=390.0, ancho=100.0, alto=13.0, tamanoFuente=9.5,
    ),
    "direccion": _campo(
        "direccion", x=172.0, y=385.0, ancho=242.0, alto=18.0,
        tamanoFuente=8.0, multilinea=True, interlineado=9.0,
    ),
    "numeroDepartamento": _campo(
        "numeroDepartamento", x=420.0, y=390.0, ancho=37.0, alto=13.0, tamanoFuente=8.0,
    ),
    "distrito": _campo(
        "distrito", x=462.0, y=390.0, ancho=94.0, alto=13.0, tamanoFuente=8.0,
    ),
    # --- Contacto ---------------------------------------------------------------
    "telefonoFijo": _campo(
        "telefonoFijo", x=66.0, y=431.0, ancho=85.0, alto=13.0, tamanoFuente=9.0,
    ),
    "celular": _campo(
        "celular", x=158.0, y=431.0, ancho=114.0, alto=13.0, tamanoFuente=9.0,
    ),
    "correoElectronico": _campo(
        "correoElectronico", x=279.0, y=431.0, ancho=276.0, alto=13.0, tamanoFuente=9.0,
    ),
    "correoNotificacion": _campo(
        "correoNotificacion", x=280.0, y=464.0, ancho=274.0, alto=12.0, tamanoFuente=9.0,
    ),
    # --- Cuerpo de la solicitud -------------------------------------------------
    "fundamentacion": _campo(
        "fundamentacion", x=68.0, y=508.0, ancho=482.0, alto=84.0,
        tamanoFuente=8.5, multilinea=True, interlineado=10.5,
    ),
    "documentosAdjuntos": _campo(
        "documentosAdjuntos", x=68.0, y=634.0, ancho=378.0, alto=63.0,
        tamanoFuente=8.5, multilinea=True, interlineado=10.5,
    ),
    "totalFolios": _campo(
        "totalFolios", x=452.7, y=640.0, ancho=105.8, alto=13.0,
        tamanoFuente=10.0, centrado=True,
    ),
    # --- Pie --------------------------------------------------------------------
    "lugarFecha": _campo(
        "lugarFecha", x=68.0, y=742.0, ancho=306.0, alto=14.0, tamanoFuente=9.5,
    ),
    "postFirma": _campo(
        "postFirma", x=381.7, y=770.0, ancho=176.8, alto=11.0,
        tamanoFuente=8.0, centrado=True,
    ),
}

#: Casillas "( )" de la fila "DATOS DEL SOLICITANTE".
#: ``x`` es el centro del paréntesis, ``y`` la línea base de la marca.
CASILLAS_TIPO_SOLICITANTE: dict[str, tuple[float, float]] = {
    "estudiante": (126.0, 254.0),
    "docente": (198.5, 254.0),
    "administrativo": (298.2, 254.0),
    "empresa": (443.5, 254.0),
    "persona_natural": (544.3, 254.0),
}

#: Marca que se imprime dentro de la casilla seleccionada.
MARCA_CASILLA: str = "X"
FUENTE_MARCA: str = "Helvetica-Bold"
TAMANO_MARCA: float = 9.0

#: Campos que nunca se autocompletan: los llena el estudiante a mano.
CAMPOS_MANUALES: tuple[str, ...] = ("firma", "selloRecepcion")

#: Orden en que se listan los campos en la interfaz de revisión.
ORDEN_REVISION: tuple[str, ...] = (
    "dependencia",
    "numeroTramite",
    "sumilla",
    "apellidosNombres",
    "facultad",
    "escuelaProfesional",
    "codigoEstudiante",
    "documentoIdentidad",
    "direccion",
    "numeroDepartamento",
    "distrito",
    "telefonoFijo",
    "celular",
    "correoElectronico",
    "correoNotificacion",
    "fundamentacion",
    "documentosAdjuntos",
    "totalFolios",
    "lugarFecha",
)

#: Etiquetas legibles para mostrar en la interfaz.
ETIQUETAS: dict[str, str] = {
    "dependencia": "Dependencia a quien se dirige",
    "numeroTramite": "N° de trámite (reverso del FUT)",
    "sumilla": "Sumilla",
    "tipoSolicitante": "Tipo de solicitante",
    "apellidosNombres": "Apellidos y nombres",
    "facultad": "Facultad",
    "escuelaProfesional": "Escuela profesional",
    "codigoEstudiante": "Código de estudiante",
    "documentoIdentidad": "DNI / Pasaporte / C. Extranjería",
    "direccion": "Dirección domiciliaria",
    "numeroDepartamento": "N° y/o Dpto.",
    "distrito": "Distrito",
    "telefonoFijo": "Teléfono fijo",
    "celular": "Celular",
    "correoElectronico": "Correo electrónico",
    "correoNotificacion": "Correo para notificaciones",
    "fundamentacion": "Fundamentación de lo solicitado",
    "documentosAdjuntos": "Documentos que se adjuntan",
    "totalFolios": "Total de folios",
    "lugarFecha": "Lugar y fecha",
    "postFirma": "Post firma",
}

__all__ = [
    "ANCHO_PAGINA",
    "ALTO_PAGINA",
    "PAGINA_FORMULARIO",
    "CampoFut",
    "CAMPOS_TEXTO",
    "CASILLAS_TIPO_SOLICITANTE",
    "MARCA_CASILLA",
    "FUENTE_MARCA",
    "TAMANO_MARCA",
    "CAMPOS_MANUALES",
    "ORDEN_REVISION",
    "ETIQUETAS",
]
