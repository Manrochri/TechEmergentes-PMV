"""Modelos de dominio de la solicitud del FUT.

El estado de la conversación vive en :class:`SolicitudFut`. La comprobación de qué
falta por preguntar es **determinista** (no la decide el modelo de lenguaje), de modo
que el formulario nunca se genera incompleto.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import validaciones as val
from .catalogo_tramites import (
    CLAVE_CARTA_PRESENTACION,
    FACULTAD_PREDETERMINADA,
    NUMERAL_OTROS,
    Tramite,
    normalizarEscuela,
    obtenerTramite,
)

TipoSolicitante = Literal[
    "estudiante", "docente", "administrativo", "empresa", "persona_natural"
]

#: Campos que siempre deben estar presentes antes de generar el PDF.
CAMPOS_OBLIGATORIOS: tuple[str, ...] = (
    "tramiteClave",
    "apellidosNombres",
    "escuelaProfesional",
    "codigoEstudiante",
    "documentoIdentidad",
    "direccion",
    "distrito",
    "celular",
    "correoElectronico",
)

#: Prefijo de los datos propios de un trámite (ver ``Tramite.camposAdicionales``) en
#: las listas de campos faltantes, p. ej. ``"tramite.curso"``.
PREFIJO_DATOS_TRAMITE: str = "tramite."

#: Prefijo de los datos por curso en las listas de campos: ``"curso.<n>.<clave>"``,
#: con ``n`` desde 1 (p. ej. ``"curso.2.seccionDestino"``).
PREFIJO_CURSO: str = "curso."

#: Tope de cursos por FUT (evita que un número mal escrito cree cientos de filas).
MAXIMO_CURSOS: int = 10

#: Pseudo-campo que figura como faltante mientras el estudiante no haya confirmado,
#: en la tabla del chat, la lista de cursos del trámite.
CAMPO_CURSOS: str = "cursos"


def claveCampoCurso(numero: int, clave: str) -> str:
    """``claveCampoCurso(2, "seccionOrigen")`` -> ``"curso.2.seccionOrigen"``."""
    return f"{PREFIJO_CURSO}{numero}.{clave}"


def separarCampoCurso(campo: str) -> tuple[int, str] | None:
    """Inverso de :func:`claveCampoCurso`; ``None`` si no es un campo de curso."""
    if not campo.startswith(PREFIJO_CURSO):
        return None
    partes = campo.split(".")
    if len(partes) != 3 or not partes[1].isdigit():
        return None
    return int(partes[1]), partes[2]


#: Campos adicionales obligatorios cuando el trámite es la carta de presentación.
CAMPOS_OBLIGATORIOS_EMPRESA: tuple[str, ...] = (
    "nombreInstitucion",
    "ruc",
    "correo",
    "telefono",
    "direccion",
    "destinatario",
)


def validarFilasCursos(filas, camposPorCurso) -> tuple[list[dict[str, str]], list[str]]:
    """Limpia las filas de la tabla de cursos y explica qué falta corregir.

    Reglas: las filas totalmente vacías se ignoran; debe quedar al menos un curso y como
    máximo ``MAXIMO_CURSOS``; cada curso necesita todos sus datos; y si el trámite pide
    secciones de origen y destino, no pueden ser la misma.

    Devuelve ``(cursosLimpios, errores)``; ``cursosLimpios`` solo es útil si no hay errores.
    """
    claves = [c.clave for c in camposPorCurso]
    etiquetas = {c.clave: c.etiqueta for c in camposPorCurso}
    cursos: list[dict[str, str]] = []
    for fila in filas or []:
        if not isinstance(fila, dict):
            continue
        limpia = {k: val.limpiarTexto(str(fila.get(k) or "")) for k in claves}
        if any(limpia.values()):
            cursos.append(limpia)

    errores: list[str] = []
    if not cursos:
        errores.append("Agrega al menos un curso.")
    if len(cursos) > MAXIMO_CURSOS:
        errores.append(f"Puedes rectificar como máximo {MAXIMO_CURSOS} cursos en un mismo FUT.")
    for numero, curso in enumerate(cursos, start=1):
        vacios = [etiquetas[k].lower() for k in claves if not curso[k]]
        if vacios:
            errores.append(f"Curso {numero}: falta {', '.join(vacios)}.")
        elif (
            "seccionOrigen" in curso
            and "seccionDestino" in curso
            and val.normalizarClave(curso["seccionOrigen"]) == val.normalizarClave(curso["seccionDestino"])
        ):
            errores.append(
                f"Curso {numero}: la sección de destino debe ser distinta de la de origen."
            )
    return cursos, errores


class DatosEmpresa(BaseModel):
    """Datos del centro de prácticas exigidos en la carta de presentación."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nombreInstitucion: str = ""
    ruc: str = ""
    correo: str = ""
    telefono: str = ""
    direccion: str = ""
    destinatario: str = Field(
        default="",
        description="Nombre, apellidos y cargo de la persona a quien va dirigida la carta.",
    )

    @field_validator("ruc", mode="before")
    @classmethod
    def normalizarRuc(cls, valor: object) -> str:
        return val.soloDigitos(str(valor or ""))

    @field_validator("telefono", mode="before")
    @classmethod
    def normalizarTelefono(cls, valor: object) -> str:
        return val.limpiarTexto(str(valor or ""))

    def camposFaltantes(self) -> list[str]:
        """Campos de la empresa aún sin completar."""
        return [c for c in CAMPOS_OBLIGATORIOS_EMPRESA if not getattr(self, c, "").strip()]

    def erroresDeFormato(self) -> dict[str, str]:
        """Campos completados pero con formato inválido."""
        errores: dict[str, str] = {}
        if self.ruc and not val.esRucValido(self.ruc):
            errores["ruc"] = "El RUC debe tener 11 dígitos y un dígito verificador válido."
        if self.correo and not val.esCorreoValido(self.correo):
            errores["correo"] = "El correo de la empresa no tiene un formato válido."
        if self.telefono and not val.esTelefonoValido(self.telefono):
            errores["telefono"] = "El teléfono de la empresa no parece válido."
        return errores

    def aLineasFundamentacion(self) -> list[str]:
        """Bloque de líneas exigido por la FIIS dentro de la fundamentación."""
        return [
            f"Nombre de la Institución o Empresa: {self.nombreInstitucion}",
            f"RUC de la Empresa: {self.ruc}",
            f"Correo: {self.correo}",
            f"Teléfono de la empresa: {self.telefono}",
            f"Dirección de la Institución o Empresa: {self.direccion}",
            f"Nombre, Apellidos y cargo a quien va dirigido: {self.destinatario}",
        ]


class SolicitudFut(BaseModel):
    """Estado completo de un FUT en construcción."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    # Trámite
    tramiteClave: str | None = None
    tipoSolicitante: TipoSolicitante = "estudiante"
    dependencia: str = ""
    numeroTramite: str = NUMERAL_OTROS
    sumilla: str = ""

    # Identificación
    apellidosNombres: str = ""
    facultad: str = FACULTAD_PREDETERMINADA
    escuelaProfesional: str = ""
    codigoEstudiante: str = ""
    documentoIdentidad: str = ""

    # Domicilio
    direccion: str = ""
    numeroDepartamento: str = ""
    distrito: str = ""

    # Contacto
    telefonoFijo: str = ""
    celular: str = ""
    correoElectronico: str = ""
    correoNotificacion: str = ""

    # Cuerpo del formulario
    fundamentacion: str = ""
    documentosAdjuntos: list[str] = Field(default_factory=list)
    totalFolios: int | None = None

    # Pie
    ciudad: str = "Lima"
    fechaSolicitud: date = Field(default_factory=date.today)

    # Solo para la carta de presentación
    empresa: DatosEmpresa = Field(default_factory=DatosEmpresa)

    # Datos propios del trámite (clave de CampoAdicional -> valor), p. ej. el curso y
    # las secciones de origen y destino en la rectificación de matrícula.
    datosTramite: dict[str, str] = Field(default_factory=dict)

    # Cursos del trámite cuando se tramita por asignatura (p. ej. rectificación de
    # matrícula): una entrada por curso con las claves de ``Tramite.camposPorCurso``.
    cursos: list[dict[str, str]] = Field(default_factory=list)
    #: True cuando el estudiante revisó y confirmó la lista de cursos (tabla del chat o
    #: formulario manual). Hasta entonces no se piden los demás datos.
    cursosConfirmados: bool = False

    # ------------------------------------------------------------------ validadores
    @field_validator("apellidosNombres", mode="before")
    @classmethod
    def normalizarNombres(cls, valor: object) -> str:
        return val.aMayusculas(str(valor or ""))

    @field_validator("escuelaProfesional", mode="before")
    @classmethod
    def normalizarEscuelaProfesional(cls, valor: object) -> str:
        return normalizarEscuela(str(valor or ""))

    @field_validator("celular", mode="before")
    @classmethod
    def normalizarCelular(cls, valor: object) -> str:
        return val.normalizarCelular(str(valor or ""))

    @field_validator("documentoIdentidad", "codigoEstudiante", mode="before")
    @classmethod
    def normalizarIdentificadores(cls, valor: object) -> str:
        return val.limpiarTexto(str(valor or "")).replace(" ", "")

    # ------------------------------------------------------------------ propiedades
    @property
    def tramite(self) -> Tramite | None:
        return obtenerTramite(self.tramiteClave)

    @property
    def esCartaPresentacion(self) -> bool:
        return self.tramiteClave == CLAVE_CARTA_PRESENTACION

    @property
    def lugarFecha(self) -> str:
        return val.construirLugarYFecha(self.ciudad, self.fechaSolicitud)

    @property
    def postFirma(self) -> str:
        if not self.apellidosNombres:
            return ""
        documento = f" - DNI {self.documentoIdentidad}" if self.documentoIdentidad else ""
        return f"{self.apellidosNombres}{documento}"

    # ------------------------------------------------------------------ completitud
    def camposFaltantes(self) -> list[str]:
        """Lista ordenada de campos obligatorios que aún faltan."""
        faltantes = [c for c in CAMPOS_OBLIGATORIOS if not self._tieneValor(c)]
        faltantes += [f"{PREFIJO_DATOS_TRAMITE}{c}" for c in self.camposAdicionalesFaltantes()]
        faltantes += self.camposDeCursoFaltantes()
        if self.esCartaPresentacion:
            faltantes += [f"empresa.{c}" for c in self.empresa.camposFaltantes()]
        return faltantes

    def camposAdicionalesFaltantes(self) -> list[str]:
        """Claves de los datos propios del trámite actual que siguen vacíos."""
        tramite = self.tramite
        if tramite is None:
            return []
        return [
            c.clave for c in tramite.camposAdicionales
            if not str(self.datosTramite.get(c.clave, "")).strip()
        ]

    # ------------------------------------------------------------------ cursos
    def cursosRegistrados(self) -> list[tuple[int, dict[str, str]]]:
        """``(número, datos)`` de los cursos con al menos un dato (se ignoran filas vacías)."""
        return [
            (numero, curso)
            for numero, curso in enumerate(self.cursos, start=1)
            if any(str(v).strip() for v in curso.values())
        ]

    @property
    def cantidadCursos(self) -> int:
        """Cursos que se están tramitando; determina el monto total si se cobra por curso."""
        return len(self.cursosRegistrados())

    def camposDeCursoFaltantes(self) -> list[str]:
        """Datos por curso pendientes.

        Mientras la lista de cursos no esté confirmada, falta el pseudo-campo
        ``"cursos"`` (la interfaz muestra la tabla de cursos). Ya confirmada, se revisa
        por si algún dato se vació después (p. ej. por una corrección).
        """
        tramite = self.tramite
        if tramite is None or not tramite.camposPorCurso:
            return []
        if not self.cursosConfirmados:
            return [CAMPO_CURSOS]
        registrados = self.cursosRegistrados() or [(1, {})]
        return [
            claveCampoCurso(numero, campo.clave)
            for numero, curso in registrados
            for campo in tramite.camposPorCurso
            if not str(curso.get(campo.clave, "")).strip()
        ]

    def confirmarCursos(self, filas: list[dict[str, object]]) -> list[str]:
        """Valida y guarda la lista de cursos de la tabla; devuelve los errores (o ``[]``).

        Solo si no hay errores se reemplaza la lista completa y queda confirmada.
        """
        tramite = self.tramite
        if tramite is None or not tramite.camposPorCurso:
            return ["Este trámite no lleva cursos."]
        cursos, errores = validarFilasCursos(filas, tramite.camposPorCurso)
        if errores:
            return errores
        self.cursos = cursos
        self.cursosConfirmados = True
        # Si los cursos cambian después de haber generado el FUT, la fundamentación
        # (que los lista) debe volver a redactarse.
        self.fundamentacion = ""
        return []

    def asignarDatoDeCurso(self, numero: int, clave: str, valor: str) -> bool:
        """Guarda un dato del curso ``numero`` (desde 1), creando las filas necesarias."""
        texto = val.limpiarTexto(valor)
        if not texto or not 1 <= numero <= MAXIMO_CURSOS:
            return False
        while len(self.cursos) < numero:
            self.cursos.append({})
        self.cursos[numero - 1][clave] = texto
        return True

    def lineasCursos(self) -> list[str]:
        """Un renglón por curso para la fundamentación, p. ej.
        "1. Física I: de la sección 01 a la sección 03"."""
        lineas: list[str] = []
        for posicion, (_, curso) in enumerate(self.cursosRegistrados(), start=1):
            nombre = curso.get("curso", "") or "(curso sin nombre)"
            origen = curso.get("seccionOrigen", "")
            destino = curso.get("seccionDestino", "")
            if origen or destino:
                lineas.append(f"{posicion}. {nombre}: de la sección {origen} a la sección {destino}")
            else:
                lineas.append(f"{posicion}. {nombre}")
        return lineas

    def lineasDatosTramite(self) -> list[str]:
        """Renglones "Etiqueta: valor" de los datos propios del trámite actual."""
        tramite = self.tramite
        if tramite is None:
            return []
        return [
            f"{c.etiqueta}: {self.datosTramite.get(c.clave, '')}"
            for c in tramite.camposAdicionales
            if str(self.datosTramite.get(c.clave, "")).strip()
        ]

    def _tieneValor(self, campo: str) -> bool:
        valor = getattr(self, campo, None)
        if valor is None:
            return False
        if isinstance(valor, str):
            return bool(valor.strip())
        return True

    def estaCompleta(self) -> bool:
        return not self.camposFaltantes()

    def erroresDeFormato(self) -> dict[str, str]:
        """Campos ya completados cuyo formato no es válido."""
        errores: dict[str, str] = {}
        if self.documentoIdentidad and not val.esDocumentoIdentidadValido(self.documentoIdentidad):
            errores["documentoIdentidad"] = "El documento debe ser un DNI de 8 dígitos o un pasaporte/carné válido."
        if self.codigoEstudiante and not val.esCodigoEstudianteValido(self.codigoEstudiante):
            errores["codigoEstudiante"] = "El código de estudiante no tiene un formato reconocible."
        if self.celular and not val.esTelefonoValido(self.celular, minimo=9, maximo=9):
            errores["celular"] = "El celular debe tener 9 dígitos."
        if self.telefonoFijo and not val.esTelefonoValido(self.telefonoFijo):
            errores["telefonoFijo"] = "El teléfono fijo no parece válido."
        if self.correoElectronico and not val.esCorreoValido(self.correoElectronico):
            errores["correoElectronico"] = "El correo electrónico no tiene un formato válido."
        if self.correoNotificacion and not val.esCorreoValido(self.correoNotificacion):
            errores["correoNotificacion"] = "El correo de notificación no tiene un formato válido."
        if self.esCartaPresentacion:
            errores.update({f"empresa.{k}": v for k, v in self.empresa.erroresDeFormato().items()})
        return errores

    def limpiarCampos(self, campos: list[str]) -> None:
        """Vacía los campos indicados (p. ej. los que no pasaron la validación).

        Así vuelven a figurar como faltantes, reaparecen en la plantilla del chat y el
        extractor determinista puede capturar el valor corregido en el siguiente turno
        (ese extractor nunca sobrescribe un campo que ya tiene valor).
        """
        for campo in campos:
            datoCurso = separarCampoCurso(campo)
            if datoCurso is not None:
                numero, clave = datoCurso
                if 1 <= numero <= len(self.cursos):
                    self.cursos[numero - 1].pop(clave, None)
            elif campo.startswith(PREFIJO_DATOS_TRAMITE):
                self.datosTramite.pop(campo[len(PREFIJO_DATOS_TRAMITE):], None)
            elif campo.startswith("empresa."):
                nombre = campo.split(".", 1)[1]
                if nombre in DatosEmpresa.model_fields:
                    setattr(self.empresa, nombre, "")
            elif campo in type(self).model_fields and isinstance(getattr(self, campo, None), str):
                setattr(self, campo, "")

    # ------------------------------------------------------------------ derivaciones
    def aplicarValoresDelTramite(self) -> None:
        """Rellena dependencia, sumilla, numeral y adjuntos sugeridos según el trámite."""
        tramite = self.tramite
        if tramite is None:
            return
        if not self.dependencia:
            dependencia = tramite.dependencia
            if dependencia.startswith("Escuela Profesional") and self.escuelaProfesional:
                dependencia = f"Escuela Profesional de {self.escuelaProfesional} - FIIS"
            self.dependencia = dependencia
        if not self.sumilla:
            self.sumilla = tramite.sumilla or tramite.nombre
        if not self.numeroTramite:
            self.numeroTramite = tramite.numeralFut
        if not self.documentosAdjuntos:
            self.documentosAdjuntos = list(tramite.documentosSugeridos)
        if self.totalFolios is None and self.documentosAdjuntos:
            self.totalFolios = len(self.documentosAdjuntos)
        if not self.correoNotificacion and self.correoElectronico:
            self.correoNotificacion = self.correoElectronico

    def construirFundamentacion(self, textoBase: str = "") -> str:
        """Arma el texto del campo ``Fundamentación de lo Solicitado``.

        Para la carta de presentación se antepone el encabezado y se añade, de forma
        obligatoria, el bloque de datos del centro de prácticas exigido por la FIIS. Si el
        trámite tiene datos propios (p. ej. curso y secciones en la rectificación de
        matrícula), se añaden debajo del encabezado como "Etiqueta: valor".
        """
        tramite = self.tramite
        encabezado = val.limpiarTexto(textoBase)

        if not encabezado and tramite is not None:
            if self.esCartaPresentacion:
                encabezado = (
                    "Solicito a usted se me expida la Carta de Presentación para realizar "
                    "mis prácticas pre profesionales, según los siguientes datos:"
                )
            else:
                encabezado = (
                    f"Solicito a usted se sirva disponer a quien corresponda la atención de "
                    f"mi solicitud de {tramite.nombre.lower()}, para lo cual adjunto los "
                    f"documentos requeridos."
                )

        cursos = self.lineasCursos()
        if cursos:
            cursos = ["Cursos a rectificar:" if len(cursos) > 1 else "Curso a rectificar:", *cursos]
        lineas = [encabezado, *self.lineasDatosTramite(), *cursos]
        if self.esCartaPresentacion:
            lineas += self.empresa.aLineasFundamentacion()
        return "\n".join(linea for linea in lineas if linea.strip())

    def aCamposDelFormulario(self) -> dict[str, str]:
        """Diccionario ``clave de campo -> texto`` que consume el llenador del PDF."""
        adjuntos = "\n".join(f"{i}. {d}" for i, d in enumerate(self.documentosAdjuntos, start=1))
        return {
            "dependencia": self.dependencia,
            "numeroTramite": self.numeroTramite,
            "sumilla": self.sumilla,
            "apellidosNombres": self.apellidosNombres,
            "facultad": self.facultad,
            "escuelaProfesional": self.escuelaProfesional,
            "codigoEstudiante": self.codigoEstudiante,
            "documentoIdentidad": self.documentoIdentidad,
            "direccion": self.direccion,
            "numeroDepartamento": self.numeroDepartamento,
            "distrito": self.distrito,
            "telefonoFijo": self.telefonoFijo,
            "celular": self.celular,
            "correoElectronico": self.correoElectronico,
            "correoNotificacion": self.correoNotificacion or self.correoElectronico,
            "fundamentacion": self.fundamentacion or self.construirFundamentacion(),
            "documentosAdjuntos": adjuntos,
            "totalFolios": "" if self.totalFolios is None else str(self.totalFolios),
            "lugarFecha": self.lugarFecha,
            "postFirma": self.postFirma,
        }

    def fusionar(self, cambios: dict[str, object]) -> list[str]:
        """Aplica cambios parciales al estado y devuelve los campos efectivamente tocados.

        Ignora claves desconocidas y valores vacíos para que una extracción pobre del
        modelo de lenguaje nunca borre información ya confirmada por el estudiante.
        """
        modificados: list[str] = []
        cambios = dict(cambios)  # no alterar el diccionario del llamador
        datosEmpresa = cambios.pop("empresa", None)
        datosTramite = cambios.pop("datosTramite", None)
        datosCursos = cambios.pop("cursos", None)

        for clave, valor in cambios.items():
            if clave not in type(self).model_fields or valor in (None, "", []):
                continue
            try:
                setattr(self, clave, valor)
            except Exception:  # valor inválido: se descarta y se vuelve a preguntar
                continue
            modificados.append(clave)

        if isinstance(datosEmpresa, dict):
            for clave, valor in datosEmpresa.items():
                if clave not in DatosEmpresa.model_fields or valor in (None, ""):
                    continue
                try:
                    setattr(self.empresa, clave, valor)
                except Exception:
                    continue
                modificados.append(f"empresa.{clave}")

        if isinstance(datosTramite, dict):
            for clave, valor in datosTramite.items():
                texto = val.limpiarTexto(str(valor or ""))
                if not texto:
                    continue
                self.datosTramite[str(clave)] = texto
                modificados.append(f"{PREFIJO_DATOS_TRAMITE}{clave}")

        # Cursos: {número: {clave: valor}} o una lista (posición 0 = curso 1).
        if isinstance(datosCursos, list):
            datosCursos = {i: c for i, c in enumerate(datosCursos, start=1)}
        if isinstance(datosCursos, dict):
            for numero, curso in datosCursos.items():
                if not isinstance(curso, dict):
                    continue
                try:
                    numero = int(numero)
                except (TypeError, ValueError):
                    continue
                for clave, valor in curso.items():
                    if self.asignarDatoDeCurso(numero, str(clave), str(valor or "")):
                        modificados.append(claveCampoCurso(numero, str(clave)))

        return modificados


__all__ = [
    "CAMPO_CURSOS",
    "validarFilasCursos",
    "PREFIJO_CURSO",
    "MAXIMO_CURSOS",
    "claveCampoCurso",
    "separarCampoCurso",
    "PREFIJO_DATOS_TRAMITE",
    "TipoSolicitante",
    "CAMPOS_OBLIGATORIOS",
    "CAMPOS_OBLIGATORIOS_EMPRESA",
    "DatosEmpresa",
    "SolicitudFut",
]