"""Pruebas de la plantilla "Etiqueta: " que el asistente muestra en el chat.

El asistente ya no pide los datos de dos en dos: en cuanto conoce el trámite, arma una
plantilla con TODOS los datos que faltan, que la interfaz deja escrita en el cuadro de
mensaje para que el estudiante la rellene y la envíe en un solo mensaje. Estas pruebas comprueban que la plantilla nombre todos los datos
y que, una vez rellenada, se lea completa sin depender del modelo de lenguaje.
"""

from __future__ import annotations

from src.agente_fut import AgenteFut
from src.catalogo_tramites import normalizarEscuela
from src.extractor_determinista import extraerSegmentosEtiquetados
from src.modelos import SolicitudFut
from src.plantillas_prompt import (
    ETIQUETAS_PLANTILLA,
    ORDEN_PLANTILLA,
    construirPlantillaDeDatos,
)


class _ModeloMudo:
    """Simula un modelo que no extrae ni redacta nada (peor caso)."""

    def extraerEstructurado(self, mensajes, esquema, temperatura: float = 0.0) -> dict:
        return {}

    def conversar(self, mensajes, temperatura: float | None = None) -> str:
        return ""


def _agente() -> AgenteFut:
    return AgenteFut(servicio=_ModeloMudo())


def _rellenar(plantilla: str, valores: dict[str, str]) -> str:
    """Simula al estudiante escribiendo cada valor después de los dos puntos."""
    def _etiqueta(renglon: str) -> str:
        return renglon.split(" (", 1)[0].split(":", 1)[0].strip()

    renglones = []
    for renglon in plantilla.splitlines():
        campo = next(
            (c for c in valores if _etiqueta(construirPlantillaDeDatos([c])) == _etiqueta(renglon)),
            None,
        )
        renglones.append(renglon + (valores[campo] if campo else ""))
    return "\n".join(renglones)


def testCadaEtiquetaDeLaPlantillaLaReconoceElExtractor() -> None:
    """Si alguien cambia una etiqueta de la plantilla, esta prueba avisa que falta en el extractor."""
    for campo in ORDEN_PLANTILLA:
        renglon = construirPlantillaDeDatos([campo]) + "valor de prueba 123"
        cambios = extraerSegmentosEtiquetados(renglon)
        if campo.startswith("empresa."):
            leido = cambios.get("empresa", {}).get(campo.split(".", 1)[1])
        else:
            leido = cambios.get(campo)
        assert leido == "valor de prueba 123", f"La etiqueta de '{campo}' no se reconoce: {renglon!r}"


def testTodasLasEtiquetasTienenTextoEnLaPlantilla() -> None:
    assert set(ORDEN_PLANTILLA) == set(ETIQUETAS_PLANTILLA)


def testAlIdentificarElTramiteSeNombranTodosLosDatos() -> None:
    agente = _agente()
    respuesta = agente.procesarMensaje(
        "necesito una carta de presentacion para mis practicas", SolicitudFut(), [], []
    )
    for campo in ORDEN_PLANTILLA:
        assert ETIQUETAS_PLANTILLA[campo] in respuesta.plantilla, campo
    assert "(opcional)" in respuesta.plantilla
    # La plantilla va al cuadro de mensaje, no dentro del texto del chat.
    assert "```" not in respuesta.mensaje
    assert "cuadro de mensaje" in respuesta.mensaje


def testSinTramiteSePreguntaPrimeroElTramite() -> None:
    respuesta = _agente().procesarMensaje("hola", SolicitudFut(), [], [])
    assert respuesta.plantilla == ""
    assert "trámite" in respuesta.mensaje.lower()


def testLaPlantillaRellenadaCompletaElFutEnUnSoloMensaje() -> None:
    agente = _agente()
    solicitud = SolicitudFut()
    primera = agente.procesarMensaje(
        "necesito una carta de presentacion para mis practicas", solicitud, [], []
    )
    plantilla = primera.plantilla

    relleno = _rellenar(plantilla, {
        "apellidosNombres": "Quispe Ramírez, Christian",
        "escuelaProfesional": "sistemas",
        "codigoEstudiante": "2021015432",
        "documentoIdentidad": "74125896",
        "direccion": "Av. Los Próceres 1450",
        "distrito": "San Isidro",
        "celular": "987654321",
        "correoElectronico": "christian.quispe@unfv.edu.pe",
        "empresa.nombreInstitucion": "Consultora Andina S.A.C.",
        "empresa.ruc": "20512345671",
        "empresa.correo": "rrhh@andina.com.pe",
        "empresa.telefono": "014567890",
        "empresa.direccion": "Av. Javier Prado Este 2050",
        "empresa.destinatario": "Ing. María Torres - Jefa de RR. HH.",
    })

    respuesta = agente.procesarMensaje(relleno, primera.solicitud, [], primera.camposPreguntados)
    assert respuesta.formularioListo, respuesta.mensaje
    assert respuesta.pdf
    s = respuesta.solicitud
    assert s.escuelaProfesional == "Ingeniería de Sistemas"
    assert s.empresa.correo == "rrhh@andina.com.pe"
    assert s.correoElectronico == "christian.quispe@unfv.edu.pe"
    assert s.telefonoFijo == "" and s.numeroDepartamento == ""


def testUnDatoInvalidoReapareceEnLaPlantillaYSePuedeCorregir() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = agente.procesarMensaje("DNI o pasaporte: 123", solicitud, [], [])
    assert respuesta.solicitud.documentoIdentidad == ""
    assert "DNI o pasaporte (8 dígitos si es DNI):" in respuesta.plantilla

    corregida = agente.procesarMensaje(
        "DNI o pasaporte: 74125896", respuesta.solicitud, [], respuesta.camposPreguntados
    )
    assert corregida.solicitud.documentoIdentidad == "74125896"


def testNormalizarEscuelaAceptaAbreviaturas() -> None:
    assert normalizarEscuela("sistemas") == "Ingeniería de Sistemas"
    assert normalizarEscuela("Ing. Industrial") == "Ingeniería Industrial"
    assert normalizarEscuela("agroindustrial") == "Ingeniería Agroindustrial"
    assert normalizarEscuela("mecatronica") == "Ingeniería Mecatrónica"
    assert normalizarEscuela("Transporte") == "Ingeniería de Transportes"
    assert normalizarEscuela("Arquitectura") == "Arquitectura"


def testUnDatoEtiquetadoNoSeReasignaComoDatoSuelto() -> None:
    """El correo del estudiante no debe copiarse como correo de la empresa, ni el teléfono
    de la empresa como celular del estudiante."""
    from src.extractor_determinista import extraerCamposDeterministas

    solicitud = SolicitudFut(tramiteClave="carta_presentacion")
    cambios = extraerCamposDeterministas(
        "Correo electrónico: ana@unfv.edu.pe\nTeléfono de la empresa: 014567890", solicitud
    )
    assert cambios["correoElectronico"] == "ana@unfv.edu.pe"
    assert cambios["empresa"] == {"telefono": "014567890"}
    assert "celular" not in cambios


_DATOS_ESTUDIANTE: dict[str, str] = {
    "apellidosNombres": "Pérez López, Ana",
    "escuelaProfesional": "Industrial",
    "codigoEstudiante": "2020123456",
    "documentoIdentidad": "74125896",
    "direccion": "Jr. Las Begonias 120",
    "distrito": "Lince",
    "celular": "987654321",
    "correoElectronico": "ana.perez@unfv.edu.pe",
}


def _iniciarRectificacion():
    agente = _agente()
    primera = agente.procesarMensaje(
        "quiero hacer una rectificacion de matricula", SolicitudFut(), [], []
    )
    return agente, primera


_DOS_CURSOS: list[dict[str, str]] = [
    {"curso": "Investigación de Operaciones I", "seccionOrigen": "01", "seccionDestino": "03"},
    {"curso": "Física II", "seccionOrigen": "02", "seccionDestino": "01"},
]


def _confirmar(agente, solicitud, cursos):
    assert solicitud.confirmarCursos(cursos) == []
    return agente.continuarTrasConfirmarCursos(solicitud, [], "Confirmo los cursos.")


def testRectificacionPrimeroMuestraLaTablaDeCursos() -> None:
    _, respuesta = _iniciarRectificacion()
    assert respuesta.solicitud.tramiteClave == "rectificacion_matricula"
    assert respuesta.mostrarSelectorCursos
    # Todavía no se piden los datos personales: primero los cursos.
    assert respuesta.plantilla == ""
    assert "tabla" in respuesta.mensaje
    assert "S/ 8.40 por curso" in respuesta.mensaje


def testEscribirEnElChatAntesDeConfirmarNoSaltaLaTabla() -> None:
    agente, primera = _iniciarRectificacion()
    respuesta = agente.procesarMensaje("DNI o pasaporte: 74125896", primera.solicitud, [], [])
    assert respuesta.mostrarSelectorCursos
    assert respuesta.solicitud.documentoIdentidad == "74125896"  # el dato igual se guarda


def testOtrosTramitesNoMuestranTablaNiPidenCursos() -> None:
    respuesta = _agente().procesarMensaje("necesito mi boleta de notas", SolicitudFut(), [], [])
    assert not respuesta.mostrarSelectorCursos
    assert "Curso" not in respuesta.plantilla


def testValidacionDeLaTablaDeCursos() -> None:
    from src.catalogo_tramites import CAMPOS_CURSO_RECTIFICACION as campos
    from src.modelos import validarFilasCursos

    _, errores = validarFilasCursos([], campos)
    assert errores == ["Agrega al menos un curso."]

    _, errores = validarFilasCursos([{"curso": "", "seccionOrigen": None, "seccionDestino": ""}], campos)
    assert errores == ["Agrega al menos un curso."]  # una fila vacía no cuenta como curso

    _, errores = validarFilasCursos([{"curso": "Física I", "seccionOrigen": "01", "seccionDestino": ""}], campos)
    assert errores == ["Curso 1: falta sección de destino."]

    _, errores = validarFilasCursos([{"curso": "Física I", "seccionOrigen": "01", "seccionDestino": "01"}], campos)
    assert "distinta" in errores[0]

    cursos, errores = validarFilasCursos(
        [*_DOS_CURSOS, {"curso": None, "seccionOrigen": None, "seccionDestino": None}], campos
    )
    assert errores == [] and len(cursos) == 2


def testUnaListaInvalidaNoSeConfirma() -> None:
    _, primera = _iniciarRectificacion()
    solicitud = primera.solicitud
    errores = solicitud.confirmarCursos([{"curso": "Física I", "seccionOrigen": "", "seccionDestino": ""}])
    assert errores
    assert not solicitud.cursosConfirmados
    assert "cursos" in solicitud.camposFaltantes()


def testTrasConfirmarLosCursosSePidenLosDemasDatos() -> None:
    agente, primera = _iniciarRectificacion()
    respuesta = _confirmar(agente, primera.solicitud, _DOS_CURSOS)
    assert not respuesta.mostrarSelectorCursos
    assert "Apellidos y nombres" in respuesta.plantilla
    # Los cursos ya se dieron en la tabla: no se repiten en la plantilla.
    assert "Curso" not in respuesta.plantilla and "Sección" not in respuesta.plantilla
    assert "Aún faltan 8 datos obligatorios" in respuesta.mensaje


def testRectificacionDeDosCursosCalculaElTotalYLosImprime() -> None:
    agente, primera = _iniciarRectificacion()
    segunda = _confirmar(agente, primera.solicitud, _DOS_CURSOS)
    relleno = _rellenar(segunda.plantilla, _DATOS_ESTUDIANTE)
    respuesta = agente.procesarMensaje(relleno, segunda.solicitud, [], segunda.camposPreguntados)

    assert respuesta.formularioListo, respuesta.mensaje
    solicitud = respuesta.solicitud
    assert solicitud.cantidadCursos == 2
    assert "S/ 16.80 (2 cursos × S/ 8.40 c/u)" in respuesta.mensaje
    fundamentacion = solicitud.fundamentacion
    assert "Cursos a rectificar:" in fundamentacion
    assert "1. Investigación de Operaciones I: de la sección 01 a la sección 03" in fundamentacion
    assert "2. Física II: de la sección 02 a la sección 01" in fundamentacion


def testUnSoloCursoCobraElMontoIndividual() -> None:
    agente, primera = _iniciarRectificacion()
    segunda = _confirmar(agente, primera.solicitud, _DOS_CURSOS[1:])
    relleno = _rellenar(segunda.plantilla, _DATOS_ESTUDIANTE)
    respuesta = agente.procesarMensaje(relleno, segunda.solicitud, [], segunda.camposPreguntados)
    assert respuesta.formularioListo, respuesta.mensaje
    assert "S/ 8.40 (1 curso × S/ 8.40 c/u)" in respuesta.mensaje
    assert "Curso a rectificar:" in respuesta.solicitud.fundamentacion


def testSiYaTieneSusDatosAlConfirmarLosCursosSeGeneraElFut() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="rectificacion_matricula")
    solicitud.fusionar({k: v for k, v in _DATOS_ESTUDIANTE.items()})
    respuesta = _confirmar(agente, solicitud, _DOS_CURSOS)
    assert respuesta.formularioListo
    assert respuesta.pdf


def testTercerCursoAgregadoAMano() -> None:
    from src.extractor_determinista import extraerSegmentosEtiquetados

    cambios = extraerSegmentosEtiquetados(
        "Curso 3: Química\nSección de origen 3: 05\nSección de destino 3: 06"
    )
    assert cambios["cursos"] == {3: {"curso": "Química", "seccionOrigen": "05", "seccionDestino": "06"}}


def testBloquesSinNumerarSeAgrupanPorOrden() -> None:
    from src.extractor_determinista import extraerSegmentosEtiquetados

    cambios = extraerSegmentosEtiquetados(
        "Curso: Física I\nSección de origen: 01\nSección de destino: 03\n"
        "Curso: Química\nSección de origen: 02\nSección de destino: 04"
    )
    assert cambios["cursos"] == {
        1: {"curso": "Física I", "seccionOrigen": "01", "seccionDestino": "03"},
        2: {"curso": "Química", "seccionOrigen": "02", "seccionDestino": "04"},
    }


def testUnaRespuestaSueltaSeAsignaAlDatoDelCursoPendiente() -> None:
    """Si solo falta la sección de destino del curso 1 y responde "03", se asigna ahí."""
    solicitud = SolicitudFut(
        tramiteClave="rectificacion_matricula",
        cursos=[{"curso": "Física I", "seccionOrigen": "01"}],
        cursosConfirmados=True,
    )
    respuesta = _agente().procesarMensaje(
        "03", solicitud, [], camposEsperados=["curso.1.seccionDestino"]
    )
    assert respuesta.solicitud.cursos[0]["seccionDestino"] == "03"


def testMontoPorCurso() -> None:
    from src.catalogo_tramites import obtenerTramite

    rectificacion = obtenerTramite("rectificacion_matricula")
    assert rectificacion.montoUnitarioTexto == "S/ 8.40 por curso"
    assert rectificacion.montoTotalFormateado(3) == "S/ 25.20"
    assert rectificacion.detalleMonto(2) == "2 cursos × S/ 8.40 c/u"
    carta = obtenerTramite("carta_presentacion")
    assert carta.montoTotalFormateado(3) == "S/ 16.90"
    assert carta.detalleMonto(3) == ""


def testUnaPlantillaEnviadaSinRellenarNoSeTomaComoDato() -> None:
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = _agente().procesarMensaje(
        "Celular (9 dígitos): ", solicitud, [], camposEsperados=["celular"]
    )
    assert respuesta.solicitud.celular == ""
    assert "Revisemos" not in respuesta.mensaje


def testCambiarLosCursosRegeneraLaFundamentacion() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="rectificacion_matricula")
    solicitud.fusionar(dict(_DATOS_ESTUDIANTE))
    primera = _confirmar(agente, solicitud, _DOS_CURSOS)
    assert "Física II" in primera.solicitud.fundamentacion

    # El estudiante pulsa «Cambiar cursos», quita uno y vuelve a confirmar.
    solicitud.cursosConfirmados = False
    segunda = _confirmar(agente, solicitud, _DOS_CURSOS[:1])
    assert segunda.formularioListo
    assert "Física II" not in segunda.solicitud.fundamentacion
    assert "S/ 8.40 (1 curso × S/ 8.40 c/u)" in segunda.mensaje