from agents.informe import ESTADOS, informe_md

BASE = {"run_id": "r1", "status": "ok", "llm": {"calls": 0, "total_cost_usd": 0.0},
        "generacion": {"modo": "estructurado", "meta": {"title": "Peso y talla", "id": "ig.cl.pesotalla"},
                       "validacion_y_reparacion": {"segundos": 120.0}, "advertencias": []},
        "pasos": [{"iteration": 0, "stage": "ok", "problems": 0, "applied": 0, "failures": [], "reglas": []}],
        "pendientes": []}


def test_informe_ok_explica_que_es_un_borrador():
    md = informe_md(BASE)
    assert "✅" in md and "borrador" in md and "Peso y talla" in md
    assert "Usó una ficha ya hecha" in md and "No hubo cambios automáticos" in md


def test_informe_lista_cambios_de_reglas_con_su_nota_para_revision():
    r = {**BASE, "pasos": [
        {"iteration": 0, "stage": "sushi", "problems": 1, "applied": 1, "failures": [],
         "reglas": [{"regla": "valor_sin_unidad", "archivo": "ejemplos.fsh:29", "antes": "* x = 128",
                     "despues": "* x = 128 'mm[Hg]'", "nota": "se asumió la unidad del perfil"}]},
        {"iteration": 1, "stage": "ok", "problems": 0, "applied": 0, "failures": [], "reglas": []}]}
    md = informe_md(r)
    assert "Se corrigieron por regla" in md and "valor_sin_unidad" in md and "se asumió la unidad del perfil" in md
    assert "No hubo cambios automáticos" not in md


def test_informe_de_error_muestra_pendientes_y_que_hacer():
    r = {**BASE, "status": "sin_progreso", "pendientes": [
        {"source": "sushi", "file": "ejemplos.fsh", "line": 29, "message": "Cannot assign kPa"}],
        "pasos": [{"iteration": 0, "stage": "sushi", "problems": 1, "applied": 1, "failures": ["parche inválido"], "reglas": []}]}
    md = informe_md(r)
    assert "⚠️" in md and "ejemplos.fsh:29" in md and "Parche rechazado: parche inválido" in md
    assert "El modelo propuso y se aplicaron 1 parche" in md


def test_informe_de_ficha_invalida_lista_los_problemas():
    r = {**BASE, "status": "ficha_invalida", "pasos": [],
         "generacion": {"modo": "estructurado", "analista": {"intentos": 3, "problemas": ["falta codigo_loinc"],
                                                              "autocompletado_por_codigo": ["a", "b"]}}}
    md = informe_md(r)
    assert "falta codigo_loinc" in md and "3 intento(s)" in md and "2 detalle(s)" in md


def test_informe_tolera_el_formato_de_agents_run_y_estados_desconocidos():
    r = {"run_id": "r2", "status": "raro", "steps": [{"iteration": 0, "stage": "infra", "problems": 0}], "llm": {}}
    md = informe_md(r)
    assert "reintentó sin llamar al modelo" in md and "raro" in md


def test_todos_los_estados_del_bucle_tienen_explicacion():
    for estado in ("ok", "ficha_invalida", "sin_progreso", "max_iteraciones", "presupuesto", "modelo_no_responde", "infraestructura"):
        assert estado in ESTADOS


def test_informe_sin_docker_no_afirma_que_paso_el_publisher():
    r = {**BASE, "generacion": {**BASE["generacion"], "sin_docker": True}}
    md = informe_md(r)
    assert "NO se ejecutaron" in md and "Solo hizo el chequeo previo" in md
    assert "✅" not in md and "pasó SUSHI" not in md


def test_informe_de_una_guia_que_viene_de_un_libro_no_habla_de_loinc_ni_de_la_ficha():
    md = informe_md({"run_id": "x", "status": "ok", "generacion": {}, "pasos": []})
    assert "Partió de una guía ya escrita" in md and "LOINC" not in md and "spec.json" not in md
    assert "bindings y cardinalidades del libro" in md
