"""Gráficas de fuerza bruta vs. voraz conforme crece el tamaño de la entrada.

Reutiliza las estrategias de kate_mcp.py y el generador de instancias sintéticas
de benchmark.py. Produce una figura con cuatro paneles:

  A) Tiempo de ejecución (escala log): fuerza bruta vs. voraz, con la curva
     teórica c * 2^n como referencia.
  B) Evaluaciones realizadas (escala log): 2^n subconjuntos vs. el voraz.
  C) Brecha del voraz respecto al óptimo (fuerza bruta), en %.
  D) Escalabilidad del voraz solo, hasta n grande (log-log), con la curva
     de referencia n log n.

La fuerza bruta solo corre hasta --max-n-fb (2^n crece demasiado rápido);
el voraz sigue hasta --max-n-voraz.

Uso (desde la raíz del repo):
    python scripts/graficar_fb_vs_voraz.py
    python scripts/graficar_fb_vs_voraz.py --max-n-fb 20 --semillas 5
    python scripts/graficar_fb_vs_voraz.py --mostrar
"""
import argparse
import csv
import math
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import kate_mcp  # noqa: E402
from benchmark import generar_instancia  # noqa: E402
from kate_mcp import horario_fuerza_bruta, horario_voraz  # noqa: E402


def _medir(funcion, clases, plan):
    t0 = time.perf_counter()
    res = funcion(clases, plan=plan)
    return res, time.perf_counter() - t0


def barrido_comparativo(min_n, max_n, semillas, plan):
    """Corre fuerza bruta y voraz sobre las mismas instancias (n pequeño)."""
    filas = []
    for n in range(min_n, max_n + 1):
        for semilla in range(semillas):
            clases = generar_instancia(n, semilla)
            fb, t_fb = _medir(horario_fuerza_bruta, clases, plan)
            vz, t_vz = _medir(horario_voraz, clases, plan)
            brecha = (
                (fb["valor_total"] - vz["valor_total"]) / fb["valor_total"] * 100
                if fb["valor_total"] > 0 else 0.0
            )
            filas.append({
                "n": n, "semilla": semilla,
                "t_fuerza_bruta_s": t_fb, "t_voraz_s": t_vz,
                "evals_fuerza_bruta": fb["evaluaciones"],
                "evals_voraz": vz["evaluaciones"],
                "valor_fuerza_bruta": fb["valor_total"],
                "valor_voraz": vz["valor_total"],
                "brecha_voraz_pct": brecha,
            })
            print(f"[comparativo] n={n:>3} semilla={semilla} "
                  f"fb={t_fb:.4f}s voraz={t_vz:.6f}s brecha={brecha:.2f}%")
    return filas


def barrido_voraz(ns, semillas, plan):
    """Corre solo el voraz con n grande (la fuerza bruta ya no es viable)."""
    filas = []
    for n in ns:
        for semilla in range(semillas):
            clases = generar_instancia(n, semilla)
            vz, t_vz = _medir(horario_voraz, clases, plan)
            filas.append({"n": n, "semilla": semilla, "t_voraz_s": t_vz,
                          "evals_voraz": vz["evaluaciones"]})
        print(f"[voraz solo] n={n:>5} listo")
    return filas


def _agrupar(filas, campo):
    """Devuelve (ns, medianas, minimos, maximos) del campo por cada n."""
    ns = sorted({f["n"] for f in filas})
    med, lo, hi = [], [], []
    for n in ns:
        vals = [f[campo] for f in filas if f["n"] == n]
        med.append(statistics.median(vals))
        lo.append(min(vals))
        hi.append(max(vals))
    return ns, med, lo, hi


def guardar_csv(filas, ruta):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def graficar(comp, solo_voraz, salida, mostrar):
    import matplotlib
    if not mostrar:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    (a, b), (c, d) = ax

    # A) Tiempo -------------------------------------------------------------
    ns, t_fb, lo_fb, hi_fb = _agrupar(comp, "t_fuerza_bruta_s")
    _, t_vz, lo_vz, hi_vz = _agrupar(comp, "t_voraz_s")
    a.plot(ns, t_fb, "o-", color="tab:red", label="Fuerza bruta")
    a.fill_between(ns, lo_fb, hi_fb, color="tab:red", alpha=0.15)
    a.plot(ns, t_vz, "s-", color="tab:blue", label="Voraz")
    a.fill_between(ns, lo_vz, hi_vz, color="tab:blue", alpha=0.15)
    k = t_fb[-1] / 2 ** ns[-1]
    a.plot(ns, [k * 2 ** n for n in ns], "--", color="gray", label="c · 2ⁿ (referencia)")
    a.set_yscale("log")
    a.set_xlabel("n (secciones candidatas)")
    a.set_ylabel("Tiempo (s, escala log)")
    a.set_title("A) Tiempo de ejecución")
    a.grid(True, which="both", alpha=0.3)
    a.legend()

    # B) Evaluaciones -------------------------------------------------------
    _, e_fb, _, _ = _agrupar(comp, "evals_fuerza_bruta")
    _, e_vz, _, _ = _agrupar(comp, "evals_voraz")
    b.plot(ns, e_fb, "o-", color="tab:red", label="Fuerza bruta (2ⁿ)")
    b.plot(ns, e_vz, "s-", color="tab:blue", label="Voraz")
    b.set_yscale("log")
    b.set_xlabel("n (secciones candidatas)")
    b.set_ylabel("Evaluaciones (escala log)")
    b.set_title("B) Trabajo realizado")
    b.grid(True, which="both", alpha=0.3)
    b.legend()

    # C) Brecha -------------------------------------------------------------
    _, g_med, _, g_max = _agrupar(comp, "brecha_voraz_pct")
    g_prom = [statistics.mean([f["brecha_voraz_pct"] for f in comp if f["n"] == n])
              for n in ns]
    c.bar(ns, g_prom, color="tab:orange", label="Brecha media")
    c.plot(ns, g_max, "k^--", label="Brecha máxima")
    c.set_xlabel("n (secciones candidatas)")
    c.set_ylabel("(óptimo − voraz) / óptimo  [%]")
    c.set_title("C) Calidad del voraz vs. el óptimo")
    c.grid(True, axis="y", alpha=0.3)
    c.legend()

    # D) Voraz a gran escala -----------------------------------------------
    nv, tv, lo, hi = _agrupar(solo_voraz, "t_voraz_s")
    d.plot(nv, tv, "s-", color="tab:blue", label="Voraz")
    d.fill_between(nv, lo, hi, color="tab:blue", alpha=0.15)
    kk = tv[-1] / (nv[-1] * math.log2(nv[-1]))
    d.plot(nv, [kk * n * math.log2(n) for n in nv], "--", color="gray",
           label="c · n log n (referencia)")
    d.set_xscale("log")
    d.set_yscale("log")
    d.set_xlabel("n (escala log)")
    d.set_ylabel("Tiempo (s, escala log)")
    d.set_title("D) Escalabilidad del voraz")
    d.grid(True, which="both", alpha=0.3)
    d.legend()

    fig.suptitle("K.A.T.E. — Fuerza bruta vs. voraz al crecer la entrada", fontsize=14)
    fig.tight_layout()
    fig.savefig(salida, dpi=150)
    print(f"Gráfica guardada en {salida}")
    if mostrar:
        plt.show()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-n", type=int, default=4)
    p.add_argument("--max-n-fb", type=int, default=18,
                   help="n máxima para la fuerza bruta (2^n; máx. %d)" % kate_mcp.MAX_N_FUERZA_BRUTA)
    p.add_argument("--max-n-voraz", type=int, default=2000,
                   help="n máxima para el panel del voraz solo")
    p.add_argument("--semillas", type=int, default=3)
    p.add_argument("--max-creditos", type=int, default=24)
    p.add_argument("--salida", default=str(RAIZ / "resultados"),
                   help="carpeta donde se guardan el PNG y los CSV")
    p.add_argument("--mostrar", action="store_true",
                   help="abrir la ventana de matplotlib además de guardar el PNG")
    a = p.parse_args()

    if a.max_n_fb > kate_mcp.MAX_N_FUERZA_BRUTA:
        p.error(f"--max-n-fb no puede pasar de {kate_mcp.MAX_N_FUERZA_BRUTA}")

    plan = kate_mcp.validar_restricciones(
        [{"tipo": "max_creditos", "dureza": "dura", "creditos": a.max_creditos}]
    )
    carpeta = Path(a.salida)
    carpeta.mkdir(parents=True, exist_ok=True)

    comp = barrido_comparativo(a.min_n, a.max_n_fb, a.semillas, plan)
    ns_grandes = [n for n in (10, 20, 50, 100, 200, 500, 1000, 2000, 5000)
                  if n <= a.max_n_voraz]
    solo = barrido_voraz(ns_grandes, a.semillas, plan)

    guardar_csv(comp, carpeta / "fb_vs_voraz_comparativo.csv")
    guardar_csv(solo, carpeta / "voraz_escalabilidad.csv")
    graficar(comp, solo, carpeta / "fb_vs_voraz.png", a.mostrar)
