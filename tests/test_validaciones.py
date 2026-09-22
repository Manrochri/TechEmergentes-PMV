"""Pruebas de las validaciones de datos peruanos."""

from __future__ import annotations

from datetime import date

import pytest

from src import validaciones as val


@pytest.mark.parametrize("valor", ["74125896", "12345678"])
def testDniValido(valor: str) -> None:
    assert val.esDniValido(valor)


@pytest.mark.parametrize("valor", ["7412589", "741258961", "", "ABCDEFGH"])
def testDniInvalido(valor: str) -> None:
    assert not val.esDniValido(valor)


@pytest.mark.parametrize("valor", ["20131312955", "20512345671"])
def testRucValido(valor: str) -> None:
    assert val.esRucValido(valor)


@pytest.mark.parametrize("valor", ["20131312954", "12345678901", "2013131295", ""])
def testRucInvalido(valor: str) -> None:
    assert not val.esRucValido(valor)


@pytest.mark.parametrize("valor", ["alumno@unfv.edu.pe", "practicas.rrhh@empresa.com.pe"])
def testCorreoValido(valor: str) -> None:
    assert val.esCorreoValido(valor)


@pytest.mark.parametrize("valor", ["alumno@", "@unfv.edu.pe", "alumno unfv.edu.pe", ""])
def testCorreoInvalido(valor: str) -> None:
    assert not val.esCorreoValido(valor)


def testNormalizarCelularQuitaPrefijoPais() -> None:
    assert val.normalizarCelular("+51 987 654 321") == "987654321"


def testConstruirLugarYFecha() -> None:
    assert val.construirLugarYFecha("Lima", date(2026, 3, 12)) == "Lima, 12 de marzo de 2026"


def testNormalizarClaveQuitaTildes() -> None:
    assert val.normalizarClave("  Práctica  Pre Profesional ") == "practica pre profesional"
