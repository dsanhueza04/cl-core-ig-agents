"""Banco de errores inyectados: cada caso debe aplicarse una sola vez y cambiar el IG (sin Docker)."""
import pytest

from agents.loop import _precheck
from scripts import errores, make_broken, medir_reparacion
from validator.precheck import collect_aliases


@pytest.mark.parametrize("nombre", sorted(errores.CASOS))
def test_cada_caso_se_aplica_y_cambia_el_archivo(nombre, tmp_path):
    caso = errores.CASOS[nombre]
    out = errores.aplicar(caso, tmp_path / "roto")
    original = (errores.GOLD / "input" / "fsh" / caso.archivo).read_text(encoding="utf-8")
    roto = (out / "input" / "fsh" / caso.archivo).read_text(encoding="utf-8")
    assert roto != original
    assert caso.etapa in {"precheck", "sushi", "publisher"}


def test_texto_ambiguo_se_rechaza(tmp_path):
    malo = errores.Caso("x", "x", "sushi", "perfiles.fsh", "*", "?")
    with pytest.raises(ValueError, match="aparece"):
        errores.aplicar(malo, tmp_path / "roto")


def test_los_casos_de_precheck_los_detecta_el_chequeo_previo(tmp_path):
    from tests.test_catalog_precheck import mini_catalog
    cat = mini_catalog()
    for nombre in [n for n, c in errores.CASOS.items() if c.etapa == "precheck"]:
        out = errores.aplicar(errores.CASOS[nombre], tmp_path / nombre)
        files = {p.name: p.read_text(encoding="utf-8") for p in (out / "input" / "fsh").glob("*.fsh")}
        assert _precheck(files, cat, collect_aliases(files["aliases.fsh"]) if "aliases.fsh" in files else {}), nombre


def test_make_broken_sin_caso_inyecta_los_dos_errores_clasicos(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["make_broken", "--out", str(tmp_path / "r")])
    assert make_broken.main() == 0
    prof = (tmp_path / "r/input/fsh/perfiles.fsh").read_text(encoding="utf-8")
    ej = (tmp_path / "r/input/fsh/ejemplos.fsh").read_text(encoding="utf-8")
    assert "cl-core-signo-vitales" in prof and "$CSDNI#01" in ej


def test_resumen_cuenta_convergencias_y_etapas():
    filas = [
        {"caso": "a", "etapa_hipotesis": "sushi", "corrida": 1, "estado": "ok", "convergio": True,
         "etapa_observada": "sushi", "vueltas": 2, "llamadas": 1, "tokens_in": 10, "tokens_out": 5, "segundos": 10.0},
        {"caso": "a", "etapa_hipotesis": "sushi", "corrida": 2, "estado": "sin_progreso", "convergio": False,
         "etapa_observada": "sushi", "vueltas": 3, "llamadas": 3, "tokens_in": 30, "tokens_out": 9, "segundos": 20.0},
    ]
    r = medir_reparacion.resumir(filas)
    assert r["casos"]["a"]["ok"] == 1 and r["casos"]["a"]["n"] == 2
    assert r["casos"]["a"]["estados"] == {"ok": 1, "sin_progreso": 1}
    assert r["total"]["ok"] == 1
    assert "| a |" in medir_reparacion.resumen_md(r, "mock")


def test_hay_20_casos_de_desarrollo_y_7_reservados():
    desarrollo = [c for c in errores.CASOS.values() if not c.reservado]
    reservados = [c for c in errores.CASOS.values() if c.reservado]
    assert (len(desarrollo), len(reservados)) == (20, 7)


def test_los_casos_reservados_no_tienen_regla():
    """Comprobación mínima (mensajes genéricos): las reglas no disparan sobre los casos reservados. No sustituye
    la disciplina de no diseñar reglas mirándolos; la medición real es `--conjunto reservado`."""
    from agents.reglas import aplicar_reglas
    from agents.reparador import Problem
    for c in errores.CASOS.values():
        if not c.reservado:
            continue
        texto = (errores.GOLD / "input" / "fsh" / c.archivo).read_text(encoding="utf-8")
        files = {c.archivo: texto.replace(c.buscar, c.reemplazar, 1)}
        linea = next(i for i, (a, b) in enumerate(zip(files[c.archivo].split("\n"), texto.split("\n")), 1) if a != b)
        for msg in ("Value does not match", "does not exist", "Unknown code", "is not valid"):
            assert aplicar_reglas(files, [Problem("sushi", msg, file=c.archivo, line=linea)])[1] == [], c.nombre
