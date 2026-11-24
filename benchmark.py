"""Benchmark de las estrategias de armado de horario de K.A.T.E.

Genera instancias sintéticas, mide tiempo y valor de cada estrategia y
calcula la brecha del voraz contra el óptimo (fuerza bruta).

Uso:
    python benchmark.py                  # n = 8..20, 5 semillas, guarda resultados.csv
    python benchmark.py --max-n 22 --semillas 3
"""
import argparse
import csv
import random
import statistics
import time

import kate_mcp
from kate_mcp import horario_fuerza_bruta, horario_voraz

DIAS = ["L", "M", "J", "V", "S"]


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def generar_instancia(n: int, semilla: int, n_materias: int | None = None) -> list[dict]:
    """Genera n secciones sintéticas.

    Hay menos materias que secciones, así que varias secciones comparten clave
    (conflicto de misma materia). Los horarios se concentran entre 7:00 y 20:00
    para forzar traslapes.
    """
    rng = random.Random(semilla)
    n_materias = n_materias or max(3, (2 * n) // 3)
    profesores = [f"Prof. {i}" for i in range(max(3, n // 2))]
    for p in profesores:
        # Calificación inventada y reproducible por semilla.
        kate_mcp.ESTRELLAS_STUB.setdefault(p, round(rng.uniform(1.5, 5.0), 1))

    clases = []
    for i in range(n):
        inicio = rng.choice(range(7 * 60, 19 * 60, 60))
        duracion = rng.choice([60, 120])
        clases.append(
            {
                "ciclo": "SINT",
                "nrc": f"{100000 + i}",
                "clave": f"MAT{rng.randrange(n_materias):02d}",
                "materia": f"Materia {i}",
                "seccion": f"D{i:02d}",
                "creditos": rng.choice([4, 6, 8, 10]),
                "cupo": 40,
                "disponibles": rng.choice([0, 5, 10, 20]),
                "dias": sorted(rng.sample(DIAS, rng.choice([2, 3, 4]))),
                "hora": f"{_hhmm(inicio)}-{_hhmm(inicio + duracion)}",
                "profesor": rng.choice(profesores),
            }
        )
    return clases


def _medir(funcion, clases, plan):
    t0 = time.perf_counter()
    res = funcion(clases, plan=plan)
    return res, time.perf_counter() - t0


def correr(min_n: int, max_n: int, paso: int, semillas: int,
           max_creditos: int, max_n_fb: int) -> list[dict]:
    filas = []
    plan = kate_mcp.validar_restricciones(
        [{"tipo": "max_creditos", "dureza": "dura", "creditos": max_creditos}]
    )
    for n in range(min_n, max_n + 1, paso):
        for semilla in range(semillas):
            clases = generar_instancia(n, semilla)
            voraz, t_voraz = _medir(horario_voraz, clases, plan)

            if n <= max_n_fb:
                fb, t_fb = _medir(horario_fuerza_bruta, clases, plan)
                brecha = (
                    (fb["valor_total"] - voraz["valor_total"]) / fb["valor_total"] * 100
                    if fb["valor_total"] > 0 else 0.0
                )
            else:
                fb, t_fb, brecha = None, None, None

            filas.append(
                {
                    "n": n,
                    "semilla": semilla,
                    "t_fuerza_bruta_s": t_fb,
                    "t_voraz_s": t_voraz,
                    "valor_fuerza_bruta": fb["valor_total"] if fb else None,
                    "valor_voraz": voraz["valor_total"],
                    "brecha_voraz_pct": brecha,
                    "evals_fuerza_bruta": fb["evaluaciones"] if fb else None,
                    "evals_voraz": voraz["evaluaciones"],
                }
            )
            print(f"n={n:>2} semilla={semilla} "
                  f"fb={t_fb if t_fb is None else round(t_fb, 4)}s "
                  f"voraz={round(t_voraz, 6)}s brecha={brecha}")
    return filas


def guardar_csv(filas: list[dict], ruta: str) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def resumen(filas: list[dict]) -> None:
    print("\n n | t_fb (s) | t_voraz (s) | brecha media % | brecha máx %")
    for n in sorted({f["n"] for f in filas}):
        grupo = [f for f in filas if f["n"] == n]
        tfb = [f["t_fuerza_bruta_s"] for f in grupo if f["t_fuerza_bruta_s"] is not None]
        tv = [f["t_voraz_s"] for f in grupo]
        br = [f["brecha_voraz_pct"] for f in grupo if f["brecha_voraz_pct"] is not None]
        print(f"{n:>2} | "
              f"{statistics.mean(tfb):9.4f} | " if tfb else f"{n:>2} |         - | ",
              end="")
        print(f"{statistics.mean(tv):11.6f} | "
              f"{statistics.mean(br):14.2f} | {max(br):12.2f}" if br
              else f"{statistics.mean(tv):11.6f} |              - |            -")


def graficar(filas: list[dict]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado; se omiten las gráficas.")
        return
    ns = sorted({f["n"] for f in filas})

    def media(campo):
        out = []
        for n in ns:
            vals = [f[campo] for f in filas if f["n"] == n and f[campo] is not None]
            out.append(statistics.mean(vals) if vals else None)
        return out

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for campo, etiqueta in (("t_fuerza_bruta_s", "Fuerza bruta"), ("t_voraz_s", "Voraz")):
        ys = media(campo)
        xs = [n for n, y in zip(ns, ys) if y is not None]
        ax[0].plot(xs, [y for y in ys if y is not None], marker="o", label=etiqueta)
    ax[0].set_yscale("log")
    ax[0].set_xlabel("n (secciones candidatas)")
    ax[0].set_ylabel("Tiempo (s, escala log)")
    ax[0].set_title("Tiempo de ejecución")
    ax[0].legend()

    ys = media("brecha_voraz_pct")
    xs = [n for n, y in zip(ns, ys) if y is not None]
    ax[1].bar(xs, [y for y in ys if y is not None])
    ax[1].set_xlabel("n (secciones candidatas)")
    ax[1].set_ylabel("Brecha del voraz (%)")
    ax[1].set_title("Voraz vs. óptimo")

    fig.tight_layout()
    fig.savefig("resultados.png", dpi=150)
    print("Gráfica guardada en resultados.png")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min-n", type=int, default=8)
    p.add_argument("--max-n", type=int, default=20)
    p.add_argument("--paso", type=int, default=2)
    p.add_argument("--semillas", type=int, default=5)
    p.add_argument("--max-creditos", type=int, default=24)
    p.add_argument("--max-n-fb", type=int, default=20,
                   help="n máxima para correr la fuerza bruta")
    a = p.parse_args()

    datos = correr(a.min_n, a.max_n, a.paso, a.semillas, a.max_creditos, a.max_n_fb)
    guardar_csv(datos, "resultados.csv")
    resumen(datos)
    graficar(datos)
