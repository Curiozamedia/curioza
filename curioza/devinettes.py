"""Devinettes de calcul pour les Reels — générées ET vérifiées par le programme.

Principe (comme le Reel « La réponse n'est pas 16 » d'Opulancia, 744 000 vues) :
une opération simple avec un piège de priorité des opérations. La plupart des gens
calculent de gauche à droite et tombent dans le piège -> ils commentent -> l'algorithme pousse.
Chaque devinette a une seule bonne réponse, calculée par Python.
"""
from __future__ import annotations

import random
from fractions import Fraction

MODELES = [
    "{a} + {b} × {c} − {d}",
    "{a} − {b} ÷ {c} + {d}",
    "{a} + {a} × {a} − {a}",
    "{a} × {b} − {c} ÷ {d}",
    "{a} + {b} ÷ {c} × {d}",
    "{a} − {b} × {c} + {d} × {e}",
]

ACCROCHES_BANDEAU = [
    "Beaucoup de gens se *trompent* sur [celle-là]",
    "Niveau *CM2*… et pourtant c'est un [piège]",
    "Prends *5 secondes* avant de [répondre]",
    "Les commentaires ne sont *jamais* [d'accord]",
    "Ton calcul de tête est-il *vraiment* [au point] ?",
]

DECORS = [
    "a blank white sheet of notebook paper lying on a wooden desk, top-down view, a pen next to it",
    "an empty green chalkboard in a French school classroom, soft daylight",
    "a clean empty whiteboard on an office wall, slightly angled",
    "a blank kraft paper sign held in front of a blurred café terrace",
    "an empty beige sticky note board on a kitchen fridge",
]


def _eval_priorite(expr: str) -> Fraction:
    e = expr.replace("×", "*").replace("÷", "/").replace("−", "-")
    # évaluation exacte en fractions (aucun code utilisateur : expression construite ici)
    jetons = []
    i = 0
    while i < len(e):
        c = e[i]
        if c.isdigit():
            j = i
            while j < len(e) and e[j].isdigit():
                j += 1
            jetons.append(f"Fraction({e[i:j]})")
            i = j
        else:
            if c != " ":
                jetons.append(c)
            i += 1
    return eval("".join(jetons), {"Fraction": Fraction, "__builtins__": {}})


def _eval_gauche_droite(expr: str) -> Fraction | None:
    """Le piège : calcul de gauche à droite, sans priorité (ignore les expressions à parenthèses)."""
    if "(" in expr:
        # piège classique : on oublie les parenthèses et on fait gauche->droite
        expr = expr.replace("(", "").replace(")", "")
    e = expr.replace("×", "*").replace("÷", "/").replace("−", "-").split()
    total = Fraction(int(e[0]))
    for op, n in zip(e[1::2], e[2::2]):
        n = Fraction(int(n))
        if op == "+": total += n
        elif op == "-": total -= n
        elif op == "*": total *= n
        elif op == "/":
            if n == 0:
                return None
            total /= n
    return total


def generer(graine: str) -> dict:
    rnd = random.Random(graine)
    for _ in range(500):
        modele = rnd.choice(MODELES)
        valeurs = {k: rnd.randint(2, 12) for k in "abcde"}
        expr = modele.format(**valeurs)
        try:
            juste = _eval_priorite(expr)
            piege = _eval_gauche_droite(expr)
        except ZeroDivisionError:
            continue
        if piege is None or juste.denominator != 1 or piege.denominator != 1:
            continue
        juste, piege = int(juste), int(piege)
        if juste == piege or juste < 0 or piege < 0 or juste > 200 or piege > 200:
            continue
        return {
            "expression": f"{expr} = ?",
            "reponse": juste,
            "piege": piege,
            "bandeau": rnd.choice(ACCROCHES_BANDEAU),
            "decor": rnd.choice(DECORS),
            "accroche_legende": f"La réponse n'est pas {piege} ! 🥴",
        }
    raise RuntimeError("Aucune devinette valide trouvée")


if __name__ == "__main__":
    for i in range(8):
        d = generer(str(i))
        print(d["expression"], "->", d["reponse"], "(piège :", d["piege"], ")")
