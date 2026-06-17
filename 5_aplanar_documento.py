"""
5_aplanar_documento.py
────────────────────────
PASO 5 del flujo.

Convierte documento_semantico.json (salida del paso 4, jerárquico)
en una lista PLANA de filas con id / parent_id / order / type,
lista para subir directamente a MongoDB.

Aplanador GENÉRICO Y RECURSIVO:
  - Recorre cualquier dict/list anidado
  - Para listas de strings primitivos crea una fila por cada string
    (ej: semana.contenidos → filas de type "semana_contenido")
  - Para listas de dicts aplana cada dict recursivamente
  - IDs deterministas y secuenciales (reproducible entre ejecuciones)

Cómo se calcula "type"
───────────────────────
  1. Si el nodo (dict) tiene su propia clave "type" → se usa tal cual
  2. Si no → "{contexto}_{singular(clave_contenedora)}"
     (ej: semanas + "contenidos" → semana_contenido)
  3. Si es un string dentro de una lista → "{contexto}_{singular(clave)}"

ENTRADA:  JSONObtenidos/documento_semantico.json
SALIDA:   JSONObtenidos/documento_aplanado.json
"""

import json
from collections import Counter
from pathlib import Path


filas    = []
contador = 0


def nuevo_id() -> int:
    global contador
    contador += 1
    return contador


SINGULARES: dict[str, str] = {
    "kids":                       "kid",
    "children":                   "child",
    "items":                      "item",
    "rows":                       "row",
    "cells":                      "cell",
    "docentes":                   "docente",
    "semanas":                    "semana",
    "emails":                     "email",
    "urls":                       "url",
    "fechas":                     "fecha",
    "evaluacion":                 "evaluacion_item",
    "competencias_genericas":     "competencia_generica",
    "competencias_especificas":   "competencia_especifica",
    "resultados_aprendizaje":     "resultado_aprendizaje",
    "bibliografia":               "bibliografia_item",
    "competencias":               "competencia",
    "contenidos":                 "contenido",
    "resultados":                 "resultado",
    "actividades":                "actividad",
    "elements":                   "element",
}

def singular(clave: str) -> str:
    if clave in SINGULARES:
        return SINGULARES[clave]
    if clave.endswith("s") and len(clave) > 1:
        return clave[:-1]
    return clave


def agregar_fila(tipo: str, parent_id, order: int,
                 source_id=None, **campos) -> int:
    fila = {
        "id":        nuevo_id(),
        "parent_id": parent_id,
        "order":     order,
        "type":      tipo,
        "source_id": source_id,
    }
    fila.update(campos)
    filas.append(fila)
    return fila["id"]


def aplanar(nodo, parent_id, order: int,
            clave: str | None = None, contexto: str | None = None):
    """
    Recorre nodo recursivamente.
    - nodo puede ser: dict, list, o un valor primitivo (str, int, float, bool).
    """

    # ── LISTA ──────────────────────────────────────────────
    if isinstance(nodo, list):
        for i, item in enumerate(nodo):
            aplanar(item, parent_id, i, clave=clave, contexto=contexto)
        return

    # ── DICCIONARIO ────────────────────────────────────────
    if isinstance(nodo, dict):

        tipo_explicito = nodo.get("type")

        if tipo_explicito:
            tipo = tipo_explicito
        elif contexto and clave:
            tipo = f"{contexto}_{singular(clave)}"
        else:
            tipo = clave or "document"

        nuevo_contexto = tipo_explicito or contexto

        # Campos simples (no dict/list, no "type"/"id")
        campos = {
            k: v for k, v in nodo.items()
            if k not in ("type", "id")
            and not isinstance(v, (dict, list))
        }

        nodo_id = agregar_fila(
            tipo, parent_id, order,
            source_id=nodo.get("id"),
            **campos
        )

        # Recorrer hijos (dict o list)
        for k, v in nodo.items():
            if isinstance(v, (dict, list)):
                aplanar(v, nodo_id, 0, clave=k, contexto=nuevo_contexto)
        return

    # ── VALOR PRIMITIVO (str, int, float, bool) ────────────
    # Ocurre cuando una lista contiene strings directos
    # ej: semana.contenidos = ["Unidad 1...", "Unidad 2..."]
    if nodo is not None and str(nodo).strip():
        tipo = f"{contexto}_{singular(clave)}" if contexto and clave else (clave or "valor")
        agregar_fila(tipo, parent_id, order, valor=str(nodo))


# ══════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":

    entrada = Path("JSONObtenidos/documento_semantico.json")
    salida  = Path("JSONObtenidos/documento_aplanado.json")

    with open(entrada, "r", encoding="utf-8") as f:
        documento = json.load(f)

    aplanar(documento, parent_id=None, order=0)

    with open(salida, "w", encoding="utf-8") as f:
        json.dump(filas, f, ensure_ascii=False, indent=4)

    conteo = Counter(f["type"] for f in filas)

    print()
    print("=" * 55)
    print("  documento_aplanado.json generado")
    print("=" * 55)
    print(f"  Total filas: {len(filas)}")
    for tipo, cnt in sorted(conteo.items()):
        print(f"    {tipo:<40} : {cnt}")
    print("=" * 55)
