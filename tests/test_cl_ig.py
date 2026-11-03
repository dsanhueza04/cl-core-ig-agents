"""El comando único cl_ig.py: diagnóstico, mensajes claros y flujo sin Docker (modelo simulado)."""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import cl_ig

REAL = Path("build/catalog/catalog.json")


def runner_ok(cmd, **kw):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def runner_sin_docker(cmd, **kw):
    return SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect to the Docker daemon")


def hechos(filas):
    return {nombre: ok for nombre, ok, _, _ in filas}


def test_diagnostico_todo_listo(tmp_path):
    (tmp_path / "build/catalog").mkdir(parents=True)
    (tmp_path / "build/catalog/catalog.json").write_text("{}")
    (tmp_path / "reference/clcore-1.9.3/site").mkdir(parents=True)
    (tmp_path / "reference/clcore-1.9.3/site/package.tgz").write_text("x")
    filas = cl_ig.diagnostico(env={}, runner=runner_ok, raiz=tmp_path)
    assert all(ok for _, ok, _, obligatorio in filas if obligatorio)
    assert any("simulado" in n for n, *_ in filas)


def test_diagnostico_sin_docker_dice_como_arreglarlo(tmp_path):
    filas = cl_ig.diagnostico(env={}, runner=runner_sin_docker, raiz=tmp_path)
    h = hechos(filas)
    assert h["Docker está encendido"] is False and h["Imagen con SUSHI e IG Publisher"] is False
    assert any("cl_ig.py imagen" in ayuda for _, ok, ayuda, _ in filas if not ok)
    assert any("cl_ig.py catalogo" in ayuda for _, ok, ayuda, _ in filas if not ok)


def test_diagnostico_con_ollama_revisa_el_modelo(tmp_path):
    def con_modelo(url, timeout=5):
        return io.StringIO(json.dumps({"models": [{"name": "qwen2.5:7b"}]}))

    def sin_modelo(url, timeout=5):
        return io.StringIO(json.dumps({"models": [{"name": "llama3:8b"}]}))

    def caido(url, timeout=5):
        raise OSError("sin conexión")

    env = {"LLM_BACKEND": "local", "LLM_MODEL": "qwen2.5:7b"}
    assert hechos(cl_ig.diagnostico(env, runner_ok, con_modelo, tmp_path))["Ollama responde y tiene el modelo qwen2.5:7b"]
    assert not hechos(cl_ig.diagnostico(env, runner_ok, sin_modelo, tmp_path))["Ollama responde y tiene el modelo qwen2.5:7b"]
    assert hechos(cl_ig.diagnostico(env, runner_ok, caido, tmp_path))["Ollama responde"] is False


def test_generar_una_especificacion_sin_modelo_explica_que_hacer(monkeypatch, capsys):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    codigo = cl_ig.main(["generar", "examples/demo/spec.md"])
    err = capsys.readouterr().err
    assert codigo == 2 and "--local" in err and "spec.json" in err


def test_generar_archivo_inexistente_apunta_a_los_ejemplos(capsys):
    assert cl_ig.main(["generar", "no-existe.md"]) == 2
    assert "ejemplos" in capsys.readouterr().err


def test_ejemplos_lista_los_casos(capsys):
    assert cl_ig.main(["ejemplos"]) == 0
    salida = capsys.readouterr().out
    assert "examples/demo/spec.md" in salida and "peso-talla" in salida


def test_reparar_carpeta_invalida(capsys, tmp_path):
    assert cl_ig.main(["reparar", str(tmp_path)]) == 2
    assert "sushi-config.yaml" in capsys.readouterr().err


@pytest.mark.skipif(not REAL.is_file(), reason="sin build/catalog (make catalog)")
def test_generar_desde_ficha_sin_docker_deja_un_informe_legible(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    codigo = cl_ig.main(["generar", "examples/demo/spec.json", "--sin-docker", "--runs", str(tmp_path)])
    informes = list(tmp_path.glob("*/informe.md"))
    assert codigo == 0 and len(informes) == 1
    md = informes[0].read_text(encoding="utf-8")
    assert "Qué hizo el sistema" in md and "borrador" in md
    assert "Informe completo" in capsys.readouterr().out


def test_la_consola_de_windows_no_rompe_el_comando(monkeypatch, capsys):
    """cmd usa cp850/cp1252: las flechas y los emojis se reemplazan en vez de lanzar UnicodeEncodeError."""
    import io
    import sys
    crudo = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(crudo, encoding="cp1252", errors="strict"))
    monkeypatch.setattr(cl_ig, "diagnostico", lambda **k: [("Algo", False, "Haz esto → y esto ✅", True)])
    assert cl_ig.main(["diagnostico"]) == 1
    sys.stdout.flush()
    assert b"Haz esto" in crudo.getvalue()


def test_imagen_y_catalogo_no_necesitan_make(tmp_path, monkeypatch, capsys):
    llamadas = []
    monkeypatch.setattr(cl_ig.shutil, "which", lambda x: "docker")
    monkeypatch.setattr(cl_ig.subprocess, "run", lambda cmd, **k: llamadas.append(cmd) or type("R", (), {"returncode": 0})())
    assert cl_ig.main(["imagen"]) == 0
    assert llamadas[0][:3] == ["docker", "build", "-t"] and llamadas[0][3] == cl_ig.IMAGEN
    # sin paquete: explica dónde ponerlo y no ejecuta nada
    llamadas.clear()
    assert cl_ig.main(["catalogo", "--package", str(tmp_path / "no-esta.tgz")]) == 2
    assert not llamadas and "reference/clcore-1.9.3/site/package.tgz" in capsys.readouterr().err
    assert cl_ig.main(["catalogo", "--package", str(tmp_path)]) == 0
    assert llamadas[0][1].endswith("extract_catalog.py")


def test_sin_docker_la_imagen_explica_que_falta(monkeypatch, capsys):
    monkeypatch.setattr(cl_ig.shutil, "which", lambda x: None)
    assert cl_ig.main(["imagen"]) == 2 and "Docker Desktop" in capsys.readouterr().err


def test_diagnostico_usa_texto_simple_si_la_consola_no_muestra_simbolos(monkeypatch, capsys):
    import io
    import sys
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict"))
    assert cl_ig._simbolos() == ("[OK]", "[FALTA]", "[ ]", "->")
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    assert cl_ig._simbolos()[0] == "✓"


@pytest.mark.skipif(not (Path(__file__).resolve().parent.parent / "build" / "catalog" / "catalog.json").is_file(), reason="necesita build/catalog (cl_ig.py catalogo)")
def test_construir_se_detiene_antes_de_docker_si_el_chequeo_previo_falla(tmp_path, monkeypatch, capsys):
    import validator.precheck as pc
    from agents import run
    libro = tmp_path / "demo.xlsx"
    assert cl_ig.main(["plantilla", str(libro), "--ejemplo"]) == 0
    monkeypatch.setattr(pc, "precheck_path", lambda ruta, cat: {"perfiles.fsh": [pc.RefIssue("name", 3, "Parent: X", "'X' no existe en CL Core ni está definido localmente")]})
    monkeypatch.setattr(run, "main", lambda argv: pytest.fail("no debe llegar a Docker ni al modelo"))
    assert cl_ig.main(["construir", str(libro), "--runs", str(tmp_path / "runs")]) == 1
    err = capsys.readouterr().err
    assert "Corrígelo en el libro" in err and "perfiles.fsh:3" in err
