"""
Perfis de coluna por aba da planilha "Controle" — porta fiel do array ABAS
em Preflight_PSM.html. Cada aba do Controle tem colunas em ordem diferente;
sem saber qual aba foi colada, a colagem sem cabeçalho cai nas colunas
erradas (foi um pedido explícito do usuário desde o início do projeto).

`colunas`: lista na mesma ordem das colunas coladas; `None` = coluna a
ignorar (existe na planilha mas não interessa à conferência).
"""

ABAS = [
    {"id": "", "nome": "— selecione a aba —", "colunas": None},
    {"id": "anosIniciais", "nome": "1 | 2 - Anos Iniciais",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "ef69cj", "nome": "3 - EF6 | EF9 - CJ",
     "colunas": ["turno", None, "descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "ef69vse", "nome": "3.1 - EF6 | EF9 - VSE",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "ef69cda", "nome": "4 - EF6 | EF9 - CDA",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "em_cjlourdes", "nome": "5 - EM1 a EM3 | IME ITA - CJ/Lourdes",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "em_vse", "nome": "5.1 - EM1 a EM2 - VSE",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "em_cda", "nome": "6 - EM1 a EM3 - CDA",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "modulo", "nome": "7 - Módulo",
     "colunas": ["descricao", None, "serie", "adaptacoes", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "simulados", "nome": "8 - Simulados | PV - BH_SSA",
     "colunas": [None, None, "descricao", "serie", "disciplina", "frente", "professor", "qDisc", "vDisc", "qObj", "vObj"]},
    {"id": "perifericos", "nome": "9 - Periféricos - BH_SSA",
     "colunas": [None, "descricao", "serie", "disciplina"]},
    {"id": "pab_pbb", "nome": "10 - PAB | PBB - BH_SSA",
     "colunas": ["descricao", "serie", "adaptacoes", "disciplina", "professor", None, "vDisc", "qDisc", "vDisc", "qObj"]},
]

CAMPOS_NUMERICOS = {"qDisc", "vDisc", "qObj", "vObj"}
CAMPOS_TEXTO = {"descricao", "serie", "adaptacoes", "disciplina", "frente", "professor", "turno"}


def _numf(s):
    s = (s or "").strip().replace(",", ".")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_linha(cols, colunas):
    item = {campo: None for campo in CAMPOS_TEXTO | CAMPOS_NUMERICOS}
    for i, campo in enumerate(colunas):
        if campo is None or i >= len(cols):
            continue
        valor = cols[i].strip()
        if campo in CAMPOS_NUMERICOS:
            item[campo] = _numf(valor)
        else:
            item[campo] = valor or None
    return item


def parse_planilha(texto, aba):
    colunas = aba["colunas"] if aba else None
    if not colunas:
        return []
    itens = []
    for linha in texto.strip().splitlines():
        if not linha.strip():
            continue
        cols = linha.split("\t")
        itens.append(parse_linha(cols, colunas))
    return itens


def chave_conteudo_item(it):
    # mesma prova, mudando só a coluna de adaptação (EN.../AD...) não conta
    # como duas provas diferentes — mesma regra do Preflight_PSM.html.
    return (
        (it.get("descricao") or "").strip().lower(), (it.get("serie") or "").strip().upper(),
        (it.get("disciplina") or "").strip().upper(), (it.get("frente") or "").strip().upper(),
        (it.get("professor") or "").strip().lower(), (it.get("turno") or "").strip().lower(),
        it.get("qDisc"), it.get("vDisc"), it.get("qObj"), it.get("vObj"),
    )
