from main import run_cli


def test_cli_keeps_session_handles_known_errors_and_exits():
    instructions = iter(
        (
            "CARGAR()",
            "EVENTO(PC1,T)",
            "SALUD(PC1)",
            "OPERATIVO(PC999)",
            "SALIR",
        )
    )
    output: list[str] = []

    run_cli(lambda _: next(instructions), output.append)

    assert "LoadSummary(device_count=7, connection_count=6)" in output
    assert any("HealthState.WARNING" in line for line in output)
    assert any(line.startswith("Error: Device 'PC999'") for line in output)
    assert output[-1] == "Hasta luego."
