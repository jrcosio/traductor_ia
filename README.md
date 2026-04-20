# Traductor IA

Base del proyecto para un traductor de voz local en tiempo real o casi real.

## Sprint 0

Este sprint deja preparada la base del repositorio:

- paquete Python en `src/`
- configuración centralizada
- catálogo cerrado de idiomas del MVP
- utilidades de métricas
- benchmark offline base
- tests mínimos de humo y configuración

## Uso rápido

Mostrar la configuración base:

```bash
python main.py info
```

Ejecutar benchmark base:

```bash
python benchmarks/benchmark_base.py --sample samples/base_silence.wav
```

Ejecutar tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
