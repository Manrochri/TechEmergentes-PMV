"""Agente conversacional que acompaña al estudiante hasta obtener su FUT.

Diseño
------
El modelo de lenguaje hace solo dos cosas: **extraer** datos del diálogo y **redactar**
la siguiente pregunta. Las decisiones (qué falta, si el formulario está completo, cuándo
generar el PDF) son deterministas y viven en Python. Así una alucinación del modelo nunca
produce un FUT incorrecto.

Ciclo de un turno:
    mensaje -> extraer datos -> fusionar estado -> validar -> ¿falta algo?
        sí  -> dejar en el cuadro de mensaje una plantilla con TODOS los datos que faltan
        no  -> generar PDF y ofrecer la descarga
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .catalogo_tramites import Tramite, TRAMITES_POR_CLAVE, buscarTramitePorTexto
from .configuracion import Configuracion, obtenerConfiguracion
from .extractor_determinista import contieneEtiquetas, extraerCamposDeterministas
from .llenador_fut import ErrorLlenadoFut, generarNombreArchivo, guardarFut, rellenarFut
from .modelos import PREFIJO_DATOS_TRAMITE, SolicitudFut
from .plantillas_prompt import (
    CAMPOS_OPCIONALES_PLANTILLA,
    ORDEN_PLANTILLA,
    construirEsquemaExtraccion,
    construirPlantillaDeDatos,
    construirPromptConversacion,
    construirPromptExtraccion,
    construirPromptFundamentacion,
    describirCampo,
)
from .errores_llm import ErrorServicioLlm
from .servicio_llm import ServicioLlm, seleccionarServicioLlm
from .validaciones import limpiarTexto, normalizarClave

registrador = logging.getLogger(__name__)

#: Texto que acompaña a la plantilla que la interfaz deja escrita en el cuadro de mensaje.
INSTRUCCIONES_PLANTILLA: str = (
    "Te dejé la plantilla escrita en el cuadro de mensaje de abajo: completa cada dato "
    "después de los dos puntos y envíala. Para pasar de un renglón a otro usa las flechas "
    "o haz clic en el renglón; si presionas Enter antes de terminar, se envía lo que lleves "
    "y te vuelvo a dejar solo lo que falte."
)

#: Campos a los que nunca se les asigna el mensaje completo como respuesta directa:
#: el trámite necesita coincidir exactamente con una clave del catálogo, y asignarle
#: texto arbitrario dejaría a la solicitud en un estado inconsistente.
CAMPOS_SIN_ASIGNACION_DIRECTA: frozenset[str] = frozenset({"tramiteClave"})

#: Mensajes que casi seguro NO son la respuesta al dato pedido (preguntas, saludos, cortesías).
_PALABRAS_NO_RESPUESTA: frozenset[str] = frozenset({
    "ok", "okay", "vale", "gracias", "hola", "listo", "si", "sí", "no", "porque", "por que", "por qué",
})
_INICIOS_DE_PREGUNTA: frozenset[str] = frozenset({
    "cuanto", "cuánto", "cuando", "cuándo", "donde", "dónde", "como", "cómo", "que", "qué", "cual", "cuál",
})

#: Frases (ya sin tildes, comparadas con texto normalizado) que el modelo a veces usa
#: para dar por terminado el trámite aunque todavía falten datos. Si aparecen mientras
#: `camposFaltantes()` no está vacío, se descarta la respuesta del modelo por completo:
#: es preferible una pregunta genérica de respaldo a una afirmación falsa.
_FRASES_PROHIBIDAS_SI_INCOMPLETO: tuple[str, ...] = (
    "ya tengo todos los datos",
    "tengo todos los datos necesarios",
    "esta listo",
    "esta completo",
    "tramite esta listo",
    "solicitud esta lista",
    "puedes imprimir",
    "puedes descargar",
    "ya puedes imprimir",
    "ya puedes descargar",
    "procedere con tu solicitud",
    "procesare tu solicitud",
    "trámite ha sido completado",
    "tramite ha sido completado",
)


@dataclass
class RespuestaAgente:
    """Resultado de procesar un turno de conversación."""

    mensaje: str
    solicitud: SolicitudFut
    camposActualizados: list[str] = field(default_factory=list)
    formularioListo: bool = False
    pdf: bytes | None = None
    nombreArchivo: str | None = None
    rutaCopiaLocal: str | None = None
    advertencias: list[str] = field(default_factory=list)
    #: Campos que se acaban de preguntar; el llamador debe pasarlos de vuelta en el
    #: siguiente turno como ``camposEsperados`` para habilitar la asignación directa.
    camposPreguntados: list[str] = field(default_factory=list)
    #: Plantilla "Etiqueta: " con los datos que faltan. La interfaz la escribe en el
    #: cuadro de mensaje del chat para que el estudiante solo la rellene y la envíe.
    plantilla: str = ""


class AgenteFut:
    """Orquesta la conversación, el estado de la solicitud y la generación del PDF."""

    def __init__(
        self,
        servicio: ServicioLlm | None = None,
        configuracion: Configuracion | None = None,
        nombreProveedor: str | None = None,
        detalleProveedor: str | None = None,
    ) -> None:
        self.configuracion = configuracion or obtenerConfiguracion()
        if servicio is not None:
            # Servicio inyectado explícitamente (p. ej. en pruebas): se respeta tal
            # cual y no se ejecuta la selección automática Qwen3 / Gemini.
            self.servicio = servicio
            self.nombreProveedor = nombreProveedor or "Modelo personalizado"
            self.detalleProveedor = detalleProveedor or ""
        else:
            self.servicio, self.nombreProveedor, self.detalleProveedor = seleccionarServicioLlm(
                self.configuracion
            )
        self._esquemaExtraccion = construirEsquemaExtraccion()

    # ------------------------------------------------------------------ turno
    def procesarMensaje(
        self,
        mensaje: str,
        solicitud: SolicitudFut,
        historial: list[dict[str, str]],
        camposEsperados: list[str] | None = None,
    ) -> RespuestaAgente:
        """Procesa un mensaje del estudiante y devuelve la respuesta del asistente.

        ``camposEsperados`` son los campos que el propio asistente pidió en su mensaje
        anterior (los devuelve como ``camposPreguntados`` en la respuesta previa). Es el
        respaldo final: si ni la extracción determinista ni el modelo interpretan nada
        del mensaje, y el asistente había pedido exactamente un dato, se asume que el
        mensaje completo es la respuesta a ese dato.
        """
        advertencias: list[str] = []

        actualizados = self.extraerYFusionar(mensaje, solicitud, historial, advertencias)
        if not actualizados and camposEsperados:
            actualizados = self.asignarRespuestaDirecta(mensaje, solicitud, camposEsperados)
            if actualizados:
                registrador.debug("Asignación directa aplicó el mensaje completo a: %s", actualizados)

        registrador.debug("Campos actualizados en este turno: %s", actualizados)

        self.identificarTramiteSiFalta(mensaje, solicitud, actualizados)
        solicitud.aplicarValoresDelTramite()

        # Un dato con formato inválido se vacía para que vuelva a figurar como faltante:
        # reaparece en la plantilla y el valor corregido se captura en el siguiente turno.
        errores = solicitud.erroresDeFormato()
        correccion = ""
        if errores:
            solicitud.limpiarCampos(list(errores))
            actualizados = [c for c in actualizados if c not in errores]
            correccion = self.redactarCorreccion(errores)

        faltantes = solicitud.camposFaltantes()
        registrador.debug("Campos faltantes tras este turno: %s", faltantes)
        if faltantes:
            camposPlantilla = self.camposParaPlantilla(solicitud, faltantes)
            texto = self.redactarPregunta(
                mensaje, solicitud, historial, faltantes, advertencias,
                camposPlantilla=camposPlantilla, correccion=correccion,
            )
            # Los datos con error van primero: si el estudiante responde solo con el valor
            # corregido, la asignación directa lo coloca en el campo correcto.
            preguntados = [c for c in errores if c in faltantes]
            preguntados += [c for c in (camposPlantilla or faltantes) if c not in preguntados]
            return RespuestaAgente(
                mensaje=texto,
                solicitud=solicitud,
                camposActualizados=actualizados,
                advertencias=advertencias,
                camposPreguntados=preguntados,
                plantilla=construirPlantillaDeDatos(camposPlantilla) if camposPlantilla else "",
            )

        return self.completarYGenerar(solicitud, actualizados, advertencias)

    def asignarRespuestaDirecta(
        self, mensaje: str, solicitud: SolicitudFut, camposEsperados: list[str]
    ) -> list[str]:
        """Asigna el mensaje completo al primer campo esperado que siga faltando.

        Solo actúa cuando nada más (regex ni modelo) interpretó el mensaje, y el propio
        texto parece una respuesta directa y no una pregunta o una cortesía. Cualquier
        valor mal formado que entre por aquí lo detecta igualmente
        :meth:`SolicitudFut.erroresDeFormato` en el siguiente paso, así que no hay riesgo
        de guardar un dato inválido sin que se le pida corregirlo.
        """
        if not self._pareceRespuestaDirecta(mensaje):
            return []

        faltantesActuales = set(solicitud.camposFaltantes())
        valor = limpiarTexto(mensaje)

        for campo in camposEsperados:
            if campo in CAMPOS_SIN_ASIGNACION_DIRECTA or campo not in faltantesActuales:
                continue
            if campo.startswith("empresa."):
                cambios: dict[str, object] = {"empresa": {campo.split(".", 1)[1]: valor}}
            elif campo.startswith(PREFIJO_DATOS_TRAMITE):
                cambios = {"datosTramite": {campo[len(PREFIJO_DATOS_TRAMITE):]: valor}}
            else:
                cambios = {campo: valor}
            actualizados = solicitud.fusionar(cambios)
            if actualizados:
                return actualizados
        return []

    @staticmethod
    def _pareceRespuestaDirecta(mensaje: str) -> bool:
        """Descarta preguntas, saludos y cortesías antes de asignarlas a un campo."""
        texto = mensaje.strip()
        if not texto or len(texto) > 160 or texto.endswith("?") or texto.endswith("¿"):
            return False
        # Una plantilla enviada sin rellenar ("Celular (9 dígitos): ") no es un dato.
        if contieneEtiquetas(texto):
            return False
        normalizado = re.sub(r"[^\w\s]", " ", normalizarClave(texto))
        palabras = normalizado.split()
        if not palabras:
            return False
        # Un mensaje corto formado solo por cortesías ("hola, gracias") no es un dato.
        if len(palabras) <= 3 and all(p in _PALABRAS_NO_RESPUESTA for p in palabras):
            return False
        return palabras[0] not in _INICIOS_DE_PREGUNTA

    # ------------------------------------------------------------------ extracción
    def extraerYFusionar(
        self,
        mensaje: str,
        solicitud: SolicitudFut,
        historial: list[dict[str, str]],
        advertencias: list[str],
    ) -> list[str]:
        """Integra al estado los datos del último mensaje.

        Primero corre el extractor determinista (regex), que no depende del LLM y
        cubre los campos con formato validable (DNI, celular, correo, RUC). Luego se
        completa con lo que el modelo de lenguaje identifique en texto libre (nombres,
        dirección, escuela, trámite). Si el modelo propone un valor distinto para un
        campo que el extractor determinista ya fijó en este mismo turno, se descarta el
        del modelo: el dato con formato validado es más confiable que una lectura libre.
        """
        actualizadosRegex = solicitud.fusionar(extraerCamposDeterministas(mensaje, solicitud))
        registrador.debug("Extractor determinista (regex/etiquetas) actualizó: %s", actualizadosRegex)

        mensajes = [
            {"role": "system", "content": construirPromptExtraccion()},
            *self.recortarHistorial(historial),
            {"role": "user", "content": mensaje},
        ]
        try:
            datos = self.servicio.extraerEstructurado(mensajes, self._esquemaExtraccion)
        except ErrorServicioLlm as error:
            registrador.warning("Extracción con el modelo falló: %s", error)
            advertencias.append(str(error))
            datos = {}

        registrador.debug("El modelo propuso (antes de depurar): %s", datos)
        datos = self._depurarDatosDelModelo(datos, actualizadosRegex)
        registrador.debug("El modelo propuso (después de depurar): %s", datos)
        actualizadosModelo = solicitud.fusionar(datos)

        return list(dict.fromkeys([*actualizadosRegex, *actualizadosModelo]))

    @staticmethod
    def _depurarDatosDelModelo(datos: dict, yaActualizadosPorRegex: list[str]) -> dict:
        """Descarta valores vacíos, el trámite si no está en el catálogo, y lo que ya fijó la regex."""
        datos = {clave: valor for clave, valor in datos.items() if valor not in (None, "", {})}

        clave = datos.get("tramiteClave")
        if clave is not None and clave not in TRAMITES_POR_CLAVE:
            datos.pop("tramiteClave", None)

        for campo in yaActualizadosPorRegex:
            if campo.startswith("empresa."):
                if isinstance(datos.get("empresa"), dict):
                    datos["empresa"].pop(campo.split(".", 1)[1], None)
            elif campo.startswith(PREFIJO_DATOS_TRAMITE):
                if isinstance(datos.get("datosTramite"), dict):
                    datos["datosTramite"].pop(campo[len(PREFIJO_DATOS_TRAMITE):], None)
            else:
                datos.pop(campo, None)

        for bloque in ("empresa", "datosTramite"):
            if bloque not in datos:
                continue
            if isinstance(datos[bloque], dict):
                datos[bloque] = {k: v for k, v in datos[bloque].items() if v not in (None, "")}
            if not isinstance(datos[bloque], dict) or not datos[bloque]:
                datos.pop(bloque)

        return datos

    def identificarTramiteSiFalta(
        self, mensaje: str, solicitud: SolicitudFut, actualizados: list[str]
    ) -> Tramite | None:
        """Respaldo determinista: busca el trámite por palabras clave en el mensaje."""
        if solicitud.tramiteClave:
            return solicitud.tramite
        tramite = buscarTramitePorTexto(mensaje)
        if tramite is not None:
            solicitud.tramiteClave = tramite.clave
            actualizados.append("tramiteClave")
        return tramite

    # ------------------------------------------------------------------ redacción
    @staticmethod
    def camposParaPlantilla(solicitud: SolicitudFut, faltantes: list[str]) -> list[str]:
        """Datos que se muestran en la plantilla: todos los obligatorios que faltan, más
        los opcionales del FUT que siguen vacíos, en el orden del formulario impreso.

        Devuelve una lista vacía mientras no se conozca el trámite: primero hay que
        saber cuál es (la carta de presentación, por ejemplo, pide datos extra).
        """
        if solicitud.tramite is None:
            return []
        pendientes = set(faltantes)
        # Los datos propios del trámite (curso, secciones...) van antes de los de la empresa.
        orden = list(ORDEN_PLANTILLA)
        posicion = orden.index("empresa.nombreInstitucion")
        orden[posicion:posicion] = [
            f"{PREFIJO_DATOS_TRAMITE}{c.clave}" for c in solicitud.tramite.camposAdicionales
        ]
        campos = [
            campo
            for campo in orden
            if campo in pendientes
            or (campo in CAMPOS_OPCIONALES_PLANTILLA and not getattr(solicitud, campo, ""))
        ]
        # Salvaguarda: cualquier faltante que no esté en ORDEN_PLANTILLA también se pide.
        campos += [c for c in faltantes if c not in campos and c != "tramiteClave"]
        return campos

    def redactarPregunta(
        self,
        mensaje: str,
        solicitud: SolicitudFut,
        historial: list[dict[str, str]],
        faltantes: list[str],
        advertencias: list[str],
        camposPlantilla: list[str] | None = None,
        correccion: str = "",
    ) -> str:
        """Arma la respuesta cuando aún faltan datos.

        Mientras no se conozca el trámite, el modelo pregunta cuál es. Una vez conocido,
        se arma una plantilla con TODOS los datos pendientes ("Etiqueta: ") que la interfaz
        escribe directamente en el cuadro de mensaje del chat (``RespuestaAgente.plantilla``);
        aquí solo se redacta el texto que la acompaña. La plantilla la arma Python, no el
        modelo, para que nunca se omita ningún dato.

        El texto del modelo nunca es la última palabra sobre si el trámite está listo:
        eso lo decide únicamente ``solicitud.camposFaltantes()``. Se descarta cualquier
        respuesta del modelo que dé a entender que ya se puede imprimir o descargar el
        FUT mientras siga habiendo campos pendientes.
        """
        if camposPlantilla is None:
            camposPlantilla = self.camposParaPlantilla(solicitud, faltantes)

        mensajes = [
            {
                "role": "system",
                "content": construirPromptConversacion(
                    contextoTramite=self.describirTramite(solicitud),
                    datosRegistrados=self.resumirDatos(solicitud),
                    datosFaltantes="\n".join(f"- {describirCampo(c)}" for c in faltantes),
                ),
            },
            *self.recortarHistorial(historial),
            {"role": "user", "content": mensaje},
        ]
        try:
            respuestaModelo = self.servicio.conversar(mensajes)
        except ErrorServicioLlm as error:
            advertencias.append(str(error))
            respuestaModelo = ""

        registrador.debug("Respuesta cruda del modelo (conversación): %s", respuestaModelo[:300])

        respuestaModelo = respuestaModelo.strip()
        if respuestaModelo and self._afirmaFalsaCompletitud(respuestaModelo):
            registrador.warning(
                "Se descartó una respuesta del modelo que insinuaba que el trámite ya "
                "estaba completo, pero todavía faltan datos: %s", respuestaModelo[:300],
            )
            respuestaModelo = ""

        if not camposPlantilla:
            # Todavía no se sabe qué trámite es: no hay plantilla que mostrar aún.
            introduccion = respuestaModelo or self.preguntaDeRespaldo(faltantes)
            partes = [introduccion, correccion]
            partes.append(
                "_Primero necesito saber qué trámite harás; luego te dejaré en el cuadro de "
                "mensaje una plantilla con todos los datos que hacen falta._"
            )
            return "\n\n".join(p for p in partes if p)

        introduccion = respuestaModelo or self.introduccionDeRespaldo(solicitud, correccion)
        obligatorios = [c for c in camposPlantilla if c not in CAMPOS_OPCIONALES_PLANTILLA]
        partes = [
            introduccion,
            correccion,
            INSTRUCCIONES_PLANTILLA,
            self._pieDeFaltantes(len(obligatorios), hayOpcionales=len(obligatorios) < len(camposPlantilla)),
        ]
        return "\n\n".join(p for p in partes if p)

    @staticmethod
    def _afirmaFalsaCompletitud(texto: str) -> bool:
        """Detecta si el modelo dio a entender, incorrectamente, que el trámite ya terminó."""
        normalizado = normalizarClave(texto)
        return any(frase in normalizado for frase in _FRASES_PROHIBIDAS_SI_INCOMPLETO)

    @staticmethod
    def _pieDeFaltantes(cantidadObligatorios: int, hayOpcionales: bool) -> str:
        """Pie exacto calculado en Python, para no depender de lo que diga el modelo."""
        if cantidadObligatorios == 1:
            texto = "_Aún falta 1 dato obligatorio."
        else:
            texto = f"_Aún faltan {cantidadObligatorios} datos obligatorios."
        if hayOpcionales:
            texto += " Los marcados como (opcional) puedes dejarlos en blanco."
        return f"{texto}_"

    @staticmethod
    def introduccionDeRespaldo(solicitud: SolicitudFut, correccion: str = "") -> str:
        """Frase de entrada sin modelo, por si ni Qwen3 ni Gemini están disponibles."""
        if correccion:
            return ""
        tramite = solicitud.tramite
        if tramite is None:
            return "Para generar tu FUT necesito los siguientes datos."
        return f"Para generar tu FUT de {tramite.nombre.lower()} necesito los siguientes datos."

    @staticmethod
    def preguntaDeRespaldo(campos: list[str]) -> str:
        """Pregunta sin modelo, por si ni Qwen3 ni Gemini están disponibles."""
        if "tramiteClave" in campos:
            return (
                "¿Qué trámite necesitas hacer? Por ejemplo: constancia de estudios, "
                "rectificación de matrícula o carta de presentación para prácticas."
            )
        etiquetas = [describirCampo(c).lower() for c in campos]
        if not etiquetas:
            return "¿Me confirmas los datos que faltan?"
        return f"Para continuar necesito: {', '.join(etiquetas)}."

    @staticmethod
    def redactarCorreccion(errores: dict[str, str]) -> str:
        """Aviso de los datos que no pasaron la validación (se vuelven a pedir en la plantilla)."""
        if len(errores) == 1:
            campo, detalle = next(iter(errores.items()))
            return (
                f"Revisemos {describirCampo(campo).lower()}: {detalle} "
                "Vuelve a escribirlo en la plantilla de abajo."
            )
        detalles = "; ".join(f"{describirCampo(c).lower()}: {d}" for c, d in errores.items())
        return f"Revisemos estos datos ({detalles}). Vuelve a escribirlos en la plantilla de abajo."

    def redactarFundamentacion(self, solicitud: SolicitudFut, motivo: str = "") -> str:
        """Genera el texto de la fundamentación.

        En la carta de presentación el bloque de datos de la empresa se añade siempre,
        sin depender del modelo: es un requisito formal de la FIIS.
        """
        tramite = solicitud.tramite
        if tramite is None:
            return solicitud.construirFundamentacion()

        encabezado = ""
        if not solicitud.esCartaPresentacion:
            mensajes = [
                {
                    "role": "system",
                    "content": construirPromptFundamentacion(
                        nombreTramite=tramite.nombre,
                        dependencia=solicitud.dependencia,
                        motivo=motivo,
                    ),
                },
                {"role": "user", "content": "Redacta la fundamentación."},
            ]
            try:
                encabezado = self.servicio.conversar(mensajes, temperatura=0.3)
            except ErrorServicioLlm as error:
                registrador.info("Fundamentación por plantilla: %s", error)
                encabezado = ""

        return solicitud.construirFundamentacion(encabezado)

    # ------------------------------------------------------------------ generación
    def completarYGenerar(
        self,
        solicitud: SolicitudFut,
        actualizados: list[str],
        advertencias: list[str],
    ) -> RespuestaAgente:
        """Redacta la fundamentación, arma el PDF y prepara la descarga."""
        if not solicitud.fundamentacion:
            solicitud.fundamentacion = self.redactarFundamentacion(solicitud)

        try:
            pdf = rellenarFut(solicitud, self.configuracion.rutaPlantillaFut)
        except ErrorLlenadoFut as error:
            return RespuestaAgente(
                mensaje=f"No pude generar el PDF: {error}",
                solicitud=solicitud,
                camposActualizados=actualizados,
                advertencias=[*advertencias, str(error)],
            )
        except Exception as error:  # salvaguarda: un fallo inesperado nunca debe quedar en silencio
            registrador.exception("Fallo inesperado al generar el FUT")
            return RespuestaAgente(
                mensaje=(
                    "Tengo todos tus datos, pero ocurrió un error inesperado al generar el PDF. "
                    "Intenta de nuevo o usa 'Revisar y corregir datos' en el panel lateral."
                ),
                solicitud=solicitud,
                camposActualizados=actualizados,
                advertencias=[*advertencias, f"Error inesperado al generar el PDF: {error}"],
            )

        nombreArchivo = generarNombreArchivo(solicitud)
        rutaCopia: str | None = None
        if self.configuracion.guardarCopiaLocal:
            try:
                rutaCopia = str(
                    guardarFut(pdf, self.configuracion.directorioSalidas, nombreArchivo)
                )
            except OSError as error:
                advertencias.append(f"No se pudo guardar la copia local: {error}")

        return RespuestaAgente(
            mensaje=self.redactarCierre(solicitud),
            solicitud=solicitud,
            camposActualizados=actualizados,
            formularioListo=True,
            pdf=pdf,
            nombreArchivo=nombreArchivo,
            rutaCopiaLocal=rutaCopia,
            advertencias=advertencias,
        )

    @staticmethod
    def redactarCierre(solicitud: SolicitudFut) -> str:
        """Texto breve de cierre.

        En la interfaz este mensaje se muestra como una tarjeta (estado, pago, acciones y
        pasos; ver ``renderizarTarjetaFutListo`` en ``app.py``). El texto queda en el
        historial para que el modelo sepa que el FUT ya se generó y con qué costo.
        """
        tramite = solicitud.tramite
        if tramite is None:
            return "Tu FUT está listo. Imprímelo y fírmalo a mano antes de presentarlo."
        return (
            f"Tu FUT de {tramite.nombre.lower()} está listo. Costo: {tramite.resumirCosto()}. "
            "Imprímelo, fírmalo a mano y preséntalo en la Oficina de Trámite Documentario."
        )

    # ------------------------------------------------------------------ auxiliares
    def recortarHistorial(self, historial: list[dict[str, str]]) -> list[dict[str, str]]:
        """Limita el historial enviado al modelo para no desbordar la ventana de contexto."""
        limite = self.configuracion.mensajesEnHistorial
        return [
            {"role": m["role"], "content": m["content"]}
            for m in historial[-limite:]
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ]

    @staticmethod
    def describirTramite(solicitud: SolicitudFut) -> str:
        tramite = solicitud.tramite
        if tramite is None:
            return ""
        return (
            f"{tramite.nombre}. Costo: {tramite.montoFormateado}. "
            f"Código de pago: {tramite.codigoPago}. "
            f"Dependencia de destino: {solicitud.dependencia or tramite.dependencia}."
        )

    @staticmethod
    def resumirDatos(solicitud: SolicitudFut) -> str:
        """Resumen compacto del estado, para que el modelo no vuelva a preguntar lo mismo."""
        lineas: list[str] = []
        for clave, valor in solicitud.aCamposDelFormulario().items():
            if valor and clave not in {"fundamentacion", "documentosAdjuntos"}:
                lineas.append(f"- {describirCampo(clave)}: {valor}")
        lineas += [f"- {linea}" for linea in solicitud.lineasDatosTramite()]
        if solicitud.esCartaPresentacion:
            for clave in ("nombreInstitucion", "ruc", "correo", "telefono", "direccion", "destinatario"):
                valor = getattr(solicitud.empresa, clave, "")
                if valor:
                    lineas.append(f"- {describirCampo(f'empresa.{clave}')}: {valor}")
        return "\n".join(lineas)


__all__ = ["AgenteFut", "RespuestaAgente"]