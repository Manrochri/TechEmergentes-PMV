"""Asistente de trámites FIIS - UNFV.

Interfaz web del agente que conversa con el estudiante, completa el Formulario Único
de Trámite sobre la plantilla oficial y lo entrega listo para descargar.

Ejecución:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import streamlit as st

from src.agente_fut import AgenteFut, RespuestaAgente
from src.catalogo_tramites import ESCUELAS_PROFESIONALES, listarTramites, obtenerTramite
from src.configuracion import Configuracion, obtenerConfiguracion
from src.llenador_fut import ErrorLlenadoFut, generarNombreArchivo, rellenarFut
from src.modelos import CAMPOS_OBLIGATORIOS, SolicitudFut
from src.plantillas_prompt import MENSAJE_BIENVENIDA, describirCampo
from src.servicio_ollama import ServicioOllama

_configuracionLog = obtenerConfiguracion()
logging.basicConfig(
    level=logging.DEBUG if _configuracionLog.modoDepuracion else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

#: Turnos consecutivos sin avance a partir de los cuales se sugiere el panel manual.
TURNOS_SIN_AVANCE_PARA_SUGERIR: int = 2


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
def configurarPagina(configuracion: Configuracion) -> None:
    """Define título, icono y disposición general de la página."""
    icono = str(configuracion.rutaLogo) if configuracion.rutaLogo.is_file() else "📄"
    st.set_page_config(
        page_title=configuracion.nombreAplicacion,
        page_icon=icono,
        layout="centered",
        initial_sidebar_state="expanded",
    )


def cargarEstilos(rutaEstilos: Path) -> None:
    """Inyecta la hoja de estilos de la aplicación."""
    if not rutaEstilos.is_file():
        return
    st.markdown(f"<style>{rutaEstilos.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def codificarImagen(ruta: str) -> str:
    """Devuelve una imagen local como data URI para incrustarla en el encabezado."""
    return base64.b64encode(Path(ruta).read_bytes()).decode("ascii")


@st.cache_resource(show_spinner=False)
def obtenerAgente() -> AgenteFut:
    """Instancia única del agente (se reutiliza entre recargas de la interfaz)."""
    return AgenteFut()


@st.cache_data(ttl=60, show_spinner=False)
def verificarOllama() -> tuple[bool, str]:
    """Estado del servidor de Ollama, consultado como máximo una vez por minuto."""
    return ServicioOllama().verificarDisponibilidad()


def inicializarEstado(configuracion: Configuracion) -> None:
    """Crea las claves de ``st.session_state`` la primera vez que se abre la app."""
    if "solicitud" not in st.session_state:
        st.session_state.solicitud = SolicitudFut(ciudad=configuracion.ciudadPredeterminada)
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [{"role": "assistant", "content": MENSAJE_BIENVENIDA}]
    if "documentos" not in st.session_state:
        # indice del mensaje -> {"pdf": bytes, "nombre": str}
        st.session_state.documentos = {}
    if "advertencias" not in st.session_state:
        st.session_state.advertencias = []
    if "turnosSinAvance" not in st.session_state:
        st.session_state.turnosSinAvance = 0
    if "camposEsperados" not in st.session_state:
        st.session_state.camposEsperados = []


def reiniciarConversacion(configuracion: Configuracion) -> None:
    """Vuelve al estado inicial conservando la configuración cargada."""
    st.session_state.solicitud = SolicitudFut(ciudad=configuracion.ciudadPredeterminada)
    st.session_state.mensajes = [{"role": "assistant", "content": MENSAJE_BIENVENIDA}]
    st.session_state.documentos = {}
    st.session_state.advertencias = []
    st.session_state.turnosSinAvance = 0
    st.session_state.camposEsperados = []


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
def renderizarEncabezado(configuracion: Configuracion) -> None:
    """Cabecera con el logo de la FIIS y el nombre de la aplicación."""
    logo = ""
    if configuracion.rutaLogo.is_file():
        logo = f'<img src="data:image/png;base64,{codificarImagen(str(configuracion.rutaLogo))}" alt="Logo FIIS UNFV" />'

    st.markdown(
        f"""
        <div class="encabezado-fiis">
          {logo}
          <div class="encabezado-textos">
            <p class="encabezado-titulo">Trámites FIIS</p>
            <p class="encabezado-subtitulo">Llena tu Formulario Único de Trámite conversando. Universidad Nacional Federico Villarreal.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Panel lateral: expediente en construcción
# ---------------------------------------------------------------------------
def renderizarPanelLateral(configuracion: Configuracion) -> None:
    """Muestra el trámite elegido, el avance del formulario y las acciones manuales."""
    solicitud: SolicitudFut = st.session_state.solicitud

    with st.sidebar:
        st.markdown('<p class="panel-titulo">TRÁMITE</p>', unsafe_allow_html=True)
        renderizarTarjetaTramite(solicitud)
        st.caption(
            "Este asistente no pide ni adjunta una firma digital: el FUT se entrega sin "
            "firmar y la firmas a mano sobre el PDF impreso."
        )

        st.markdown('<p class="panel-titulo">AVANCE DEL FORMULARIO</p>', unsafe_allow_html=True)
        renderizarAvance(solicitud)

        with st.expander("Revisar y corregir datos"):
            renderizarFormularioManual(solicitud, configuracion)

        st.markdown('<p class="panel-titulo">SESIÓN</p>', unsafe_allow_html=True)
        if st.button("Empezar un trámite nuevo", use_container_width=True, type="secondary"):
            reiniciarConversacion(configuracion)
            st.rerun()

        renderizarEstadoDelSistema(configuracion)


def renderizarTarjetaTramite(solicitud: SolicitudFut) -> None:
    """Tarjeta con el nombre, el costo y el código de pago del trámite en curso."""
    tramite = solicitud.tramite
    if tramite is None:
        st.markdown(
            '<div class="tarjeta-vacia">Cuéntale al asistente qué necesitas y aquí '
            "aparecerá el trámite con su costo.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="tarjeta-tramite">
          <div class="nombre">{tramite.nombre}</div>
          <div class="detalle">
            {tramite.montoFormateado} · código {tramite.codigoPago}<br />
            {solicitud.dependencia or tramite.dependencia}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def renderizarAvance(solicitud: SolicitudFut) -> None:
    """Barra de progreso y lista de verificación de los campos obligatorios."""
    faltantes = set(solicitud.camposFaltantes())
    obligatorios = list(CAMPOS_OBLIGATORIOS)
    if solicitud.esCartaPresentacion:
        obligatorios += [
            "empresa.nombreInstitucion",
            "empresa.ruc",
            "empresa.correo",
            "empresa.telefono",
            "empresa.direccion",
            "empresa.destinatario",
        ]

    completos = [c for c in obligatorios if c not in faltantes]
    total = len(obligatorios) or 1
    st.progress(len(completos) / total)
    st.markdown(
        f'<p class="progreso-texto">{len(completos)} de {total} datos completos</p>',
        unsafe_allow_html=True,
    )

    elementos = []
    for campo in obligatorios:
        completo = campo not in faltantes
        clase = "completo" if completo else "pendiente"
        marca = "●" if completo else "○"
        valor = obtenerValorLegible(solicitud, campo) if completo else ""
        detalle = f'<span class="valor">{valor}</span>' if valor else ""
        elementos.append(
            f'<li class="{clase}"><span class="marca">{marca}</span>'
            f"<span>{describirCampo(campo)} {detalle}</span></li>"
        )
    st.markdown(f'<ul class="lista-campos">{"".join(elementos)}</ul>', unsafe_allow_html=True)


def obtenerValorLegible(solicitud: SolicitudFut, campo: str) -> str:
    """Valor corto del campo para mostrarlo junto a la marca de completado."""
    if campo == "tramiteClave":
        return ""
    if campo.startswith("empresa."):
        valor = str(getattr(solicitud.empresa, campo.split(".", 1)[1], ""))
    else:
        valor = str(getattr(solicitud, campo, ""))
    return valor if len(valor) <= 28 else f"{valor[:27]}…"


def renderizarFormularioManual(solicitud: SolicitudFut, configuracion: Configuracion) -> None:
    """Permite corregir a mano cualquier dato y regenerar el FUT sin pasar por el chat."""
    tramites = listarTramites()
    claves = [t.clave for t in tramites]
    indiceTramite = claves.index(solicitud.tramiteClave) if solicitud.tramiteClave in claves else 0

    with st.form("formulario_manual"):
        claveElegida = st.selectbox(
            "Trámite",
            options=claves,
            index=indiceTramite,
            format_func=lambda c: obtenerTramite(c).nombre,
        )
        apellidosNombres = st.text_input("Apellidos y nombres", value=solicitud.apellidosNombres)
        escuela = st.selectbox(
            "Escuela profesional",
            options=list(ESCUELAS_PROFESIONALES),
            index=(
                list(ESCUELAS_PROFESIONALES).index(solicitud.escuelaProfesional)
                if solicitud.escuelaProfesional in ESCUELAS_PROFESIONALES
                else 0
            ),
        )
        codigo = st.text_input("Código de estudiante", value=solicitud.codigoEstudiante)
        documento = st.text_input("DNI / Pasaporte / C. Extranjería", value=solicitud.documentoIdentidad)
        direccion = st.text_input("Dirección domiciliaria", value=solicitud.direccion)
        numeroDepartamento = st.text_input("N° y/o Dpto.", value=solicitud.numeroDepartamento)
        distrito = st.text_input("Distrito", value=solicitud.distrito)
        telefonoFijo = st.text_input("Teléfono fijo", value=solicitud.telefonoFijo)
        celular = st.text_input("Celular", value=solicitud.celular)
        correo = st.text_input("Correo electrónico", value=solicitud.correoElectronico)
        dependencia = st.text_input("Dependencia a quien se dirige", value=solicitud.dependencia)

        datosEmpresa: dict[str, str] = {}
        if claveElegida == "carta_presentacion":
            st.markdown("**Centro de prácticas**")
            datosEmpresa = {
                "nombreInstitucion": st.text_input(
                    "Nombre de la institución o empresa", value=solicitud.empresa.nombreInstitucion
                ),
                "ruc": st.text_input("RUC de la empresa", value=solicitud.empresa.ruc),
                "correo": st.text_input("Correo de la empresa", value=solicitud.empresa.correo),
                "telefono": st.text_input("Teléfono de la empresa", value=solicitud.empresa.telefono),
                "direccion": st.text_input(
                    "Dirección de la institución o empresa", value=solicitud.empresa.direccion
                ),
                "destinatario": st.text_input(
                    "Nombre, apellidos y cargo a quien va dirigido",
                    value=solicitud.empresa.destinatario,
                ),
            }

        enviado = st.form_submit_button("Guardar y generar FUT", use_container_width=True)

    if not enviado:
        return

    cambios: dict[str, object] = {
        "tramiteClave": claveElegida,
        "apellidosNombres": apellidosNombres,
        "escuelaProfesional": escuela,
        "codigoEstudiante": codigo,
        "documentoIdentidad": documento,
        "direccion": direccion,
        "numeroDepartamento": numeroDepartamento,
        "distrito": distrito,
        "telefonoFijo": telefonoFijo,
        "celular": celular,
        "correoElectronico": correo,
        "dependencia": dependencia,
    }
    if datosEmpresa:
        cambios["empresa"] = datosEmpresa

    solicitud.fusionar(cambios)
    solicitud.aplicarValoresDelTramite()
    generarDesdeFormulario(solicitud, configuracion)


def generarDesdeFormulario(solicitud: SolicitudFut, configuracion: Configuracion) -> None:
    """Genera el FUT desde el panel manual y lo publica como mensaje del asistente."""
    errores = solicitud.erroresDeFormato()
    if errores:
        st.error(" ".join(errores.values()))
        return

    faltantes = solicitud.camposFaltantes()
    if faltantes:
        etiquetas = ", ".join(describirCampo(c).lower() for c in faltantes[:4])
        st.warning(f"Todavía faltan datos: {etiquetas}.")
        return

    agente = obtenerAgente()
    if not solicitud.fundamentacion:
        solicitud.fundamentacion = agente.redactarFundamentacion(solicitud)

    try:
        pdf = rellenarFut(solicitud, configuracion.rutaPlantillaFut)
    except ErrorLlenadoFut as error:
        st.error(str(error))
        return
    except Exception as error:  # salvaguarda: un fallo inesperado nunca debe quedar en silencio
        st.error(f"Ocurrió un error inesperado al generar el PDF: {error}")
        return

    nombreArchivo = generarNombreArchivo(solicitud)
    st.session_state.turnosSinAvance = 0
    st.session_state.camposEsperados = []
    registrarMensajeConDocumento(
        "Actualicé tus datos y volví a generar el FUT. Descárgalo o ábrelo para imprimir aquí abajo.",
        pdf,
        nombreArchivo,
    )
    st.rerun()


def renderizarEstadoDelSistema(configuracion: Configuracion) -> None:
    """Indica si Ollama y la plantilla del FUT están disponibles."""
    problemas = configuracion.verificarRutas()
    disponible, detalle = verificarOllama()

    if problemas:
        st.markdown(
            f'<p class="aviso-estado error">{"<br />".join(problemas)}</p>',
            unsafe_allow_html=True,
        )
    clase = "aviso-estado" if disponible else "aviso-estado error"
    st.markdown(f'<p class="{clase}">{detalle}</p>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
def registrarMensajeConDocumento(texto: str, pdf: bytes | None, nombreArchivo: str | None) -> None:
    """Agrega un mensaje del asistente y, si corresponde, adjunta el PDF generado."""
    st.session_state.mensajes.append({"role": "assistant", "content": texto})
    if pdf and nombreArchivo:
        indice = len(st.session_state.mensajes) - 1
        st.session_state.documentos[indice] = {"pdf": pdf, "nombre": nombreArchivo}


def renderizarHistorial() -> None:
    """Dibuja toda la conversación, con el botón de descarga en su mensaje original."""
    for indice, mensaje in enumerate(st.session_state.mensajes):
        with st.chat_message(mensaje["role"]):
            st.markdown(mensaje["content"])
            documento = st.session_state.documentos.get(indice)
            if documento:
                renderizarDescarga(documento, indice)


def renderizarDescarga(documento: dict[str, object], indice: int) -> None:
    """Bloque de descarga e impresión del FUT dentro del propio mensaje del chat.

    La firma se deja siempre en blanco a propósito: es una firma manuscrita la que la
    Secretaría General exige al presentar el trámite en físico, y una imagen adjunta no
    tiene ese valor ni evita que la oficina pida firmar de todos modos. Por eso el
    formulario solo imprime el nombre bajo la línea de firma (el "Post firma") y aquí se
    recuerda con claridad que falta firmarlo a mano, en vez de ofrecer una opción de
    "adjuntar firma" que daría una falsa sensación de trámite terminado.
    """
    nombre = str(documento["nombre"])
    pdfBytes = documento["pdf"]
    pdfBase64 = base64.b64encode(pdfBytes).decode("ascii")

    st.markdown(
        f'<div class="bloque-descarga"><div class="archivo">{nombre}</div></div>',
        unsafe_allow_html=True,
    )

    columnaDescarga, columnaImprimir = st.columns(2)
    with columnaDescarga:
        st.download_button(
            label="⬇️ Descargar PDF",
            data=pdfBytes,
            file_name=nombre,
            mime="application/pdf",
            key=f"descarga_{indice}",
            use_container_width=True,
        )
    with columnaImprimir:
        st.markdown(
            f'<a class="boton-imprimir" href="data:application/pdf;base64,{pdfBase64}" '
            f'target="_blank" rel="noopener">🖨️ Abrir e imprimir</a>',
            unsafe_allow_html=True,
        )

    st.caption(
        "El botón de imprimir abre el PDF en una pestaña nueva; usa el ícono de impresión "
        "del visor de tu navegador (o Ctrl+P). Firma a mano sobre \"Firma y Post Firma del "
        "Solicitante\" antes de presentarlo: no se acepta ni se genera firma digital."
    )


def procesarEntrada(texto: str) -> None:
    """Envía el mensaje del estudiante al agente y publica la respuesta."""
    st.session_state.mensajes.append({"role": "user", "content": texto})

    with st.chat_message("user"):
        st.markdown(texto)

    with st.chat_message("assistant"):
        with st.spinner("Revisando tus datos…"):
            agente = obtenerAgente()
            historial = st.session_state.mensajes[:-1]
            respuesta: RespuestaAgente = agente.procesarMensaje(
                texto,
                st.session_state.solicitud,
                historial,
                camposEsperados=st.session_state.camposEsperados,
            )

    st.session_state.solicitud = respuesta.solicitud
    st.session_state.advertencias = respuesta.advertencias
    st.session_state.camposEsperados = respuesta.camposPreguntados

    if respuesta.formularioListo or respuesta.camposActualizados:
        st.session_state.turnosSinAvance = 0
    else:
        st.session_state.turnosSinAvance += 1

    mensaje = respuesta.mensaje
    if not respuesta.formularioListo and st.session_state.turnosSinAvance >= TURNOS_SIN_AVANCE_PARA_SUGERIR:
        mensaje += (
            "\n\nSi prefieres no seguir conversando, abre \"Revisar y corregir datos\" en el "
            "panel lateral: ahí puedes escribir todos los datos directamente y generar el FUT "
            "sin depender del chat."
        )

    registrarMensajeConDocumento(mensaje, respuesta.pdf, respuesta.nombreArchivo)
    st.rerun()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def principal() -> None:
    """Arranca la aplicación."""
    configuracion = obtenerConfiguracion()
    configurarPagina(configuracion)
    cargarEstilos(configuracion.rutaEstilos)
    inicializarEstado(configuracion)

    renderizarEncabezado(configuracion)
    renderizarPanelLateral(configuracion)
    renderizarHistorial()

    for advertencia in st.session_state.advertencias:
        st.warning(advertencia)

    entrada = st.chat_input("Escribe tu consulta o tus datos…")
    if entrada:
        procesarEntrada(entrada)


if __name__ == "__main__":
    principal()
