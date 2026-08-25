"""
Motor de regras — mesma filosofia do Preflight_PSM.html, fase 1 (2026-08-21):
só bloqueia (GRAVE) nestas 4 famílias, o resto é aviso e volta numa fase 2:

  1. Conteúdo de outra série/tipo (cabeçalho x nome do arquivo x planilha,
     inclusive no MEIO do PDF).
  2. Página ou arquivo idêntico a outro do lote, mas que deveria ser diferente.
  3. Tipo de prova errado no meio do lote (recuperação numa 2ª chamada, etc).
  4. Conteúdo faltando (menos questões, ou valor errado, do que a planilha diz).
"""
import re
from collections import defaultdict

from pdf_read import norm, normU

NOME_NAT = {
    "2a_chamada": "2ª Chamada", "recuperacao": "Recuperação",
    "simulado": "Simulado", "admissao": "Admissão", "regular": "Regular",
}

# --- ajustes pedidos em 2026-08 -------------------------------------------
# arquivo adaptado: nome com "AD<n>" ou "N<n>" (ex.: ..._AD1_..., ..._N2_...)
ADAPT_RE = re.compile(r"(?:^|[_\-.\s])(AD|N)\d{1,3}(?=[_\-.\s]|$)", re.IGNORECASE)
TABELA_PERIODICA_RE = re.compile(r"TABELA\s*PERI[OÓ]DICA")
INFINITO = "∞"  # ∞


def eh_adaptado(nome):
    return bool(ADAPT_RE.search(nome or ""))


def eh_quimica(cab, do_nome):
    disc = (cab.get("disciplina") if cab else None) or (do_nome or {}).get("disciplina")
    if disc == "Química":
        return True
    if disc == "Ciências":
        frente = normU((cab or {}).get("frente") or "")
        if "QUIM" in frente:
            return True
    return False


def numero_serie(txt):
    m = re.search(r"\b([0-9]{1,2})\s*[AO]\b", normU(txt or ""))
    return int(m.group(1)) if m else None


def serie_bate(a, b):
    if a is None or b is None or a == "" or b == "":
        return False
    na, nb = numero_serie(a), numero_serie(b)
    if na is not None and nb is not None:
        return na == nb
    return normU(str(a)) == normU(str(b))


def bate_campo(campo, x, y):
    if campo == "serie":
        return serie_bate(x, y)
    return normU(str(x)) == normU(str(y))


def chave_conteudo(item):
    return "|".join(str(x) for x in [
        norm(item.get("descricao")), normU(item.get("serie")), normU(item.get("disciplina")),
        normU(item.get("frente")), norm(item.get("professor")),
        item.get("qDisc"), item.get("vDisc"), item.get("qObj"), item.get("vObj"),
    ])


def _texto_contem(texto_norm, alvo):
    if not alvo:
        return False
    return norm(alvo) in texto_norm


def pontuar(item, pdf):
    """Pontuação de compatibilidade item-da-planilha x PDF (quanto maior,
    melhor o par). Retorna dict com pt e sinalizadores usados no relatório."""
    c = pdf.get("cab") or {}
    bernoulli = pdf.get("origem") == "bernoulli"
    pt = 0
    conflito = False

    disc_cab = bool(item.get("disciplina") and c.get("disciplina") and normU(item["disciplina"]) == normU(c["disciplina"]))
    disc_txt = bool(item.get("disciplina") and _texto_contem(norm(pdf.get("texto", "")), item["disciplina"]))
    disc = disc_cab or disc_txt
    if item.get("disciplina") and not disc:
        conflito = True
    if disc_cab:
        pt += 4
    elif disc_txt:
        pt += 2

    fr_cab = bool(item.get("frente") and c.get("frente") and normU(item["frente"]) == normU(c["frente"]))
    fr_txt = bool(item.get("frente") and _texto_contem(norm(pdf.get("texto", "")), item["frente"]))
    fr = fr_cab or fr_txt
    if item.get("frente") and bernoulli and not fr:
        conflito = True
    if fr_cab:
        pt += 3
    elif fr_txt:
        pt += 1

    prof_cab = bool(item.get("professor") and c.get("professor") and norm(item["professor"]) in norm(c["professor"]))
    prof_exato = bool(item.get("professor") and _texto_contem(norm(pdf.get("texto", "")), item["professor"]))
    if prof_cab:
        pt += 3
    elif prof_exato:
        pt += 1

    if item.get("serie") and c.get("serie") and serie_bate(item["serie"], c["serie"]):
        pt += 2

    if conflito:
        pt = 0

    return {
        "pt": pt, "bernoulli": bernoulli, "disc": disc, "disc_cab": disc_cab,
        "fr": fr, "fr_cab": fr_cab, "prof_cab": prof_cab, "prof_exato": prof_exato,
        "conflito": conflito,
    }


def _lote_esperado(itens, declarado):
    """natureza esperada do lote: o que a planilha declarar (maioria), ou o
    que vier explicitamente 'declarado' (recorte colado no passo 1)."""
    if declarado and declarado.get("natureza"):
        return declarado["natureza"]
    contagem = defaultdict(int)
    for it in itens:
        n = it.get("origem_natureza")
        if n:
            contagem[n] += 1
    if not contagem:
        return None
    return max(contagem, key=contagem.get)


def conferir_cabecalhos(pdfs, esperado_natureza=None):
    """R04 (cabeçalho x nome do arquivo) e R05 (natureza errada no meio do
    lote) + R19 (página no meio com série/tipo diferente) + R20 (página
    idêntica em outro arquivo)."""
    resultados = {pdf["nome"]: {"pdf": pdf, "graves": [], "avisos": []} for pdf in pdfs}

    for pdf in pdfs:
        r = resultados[pdf["nome"]]
        c = pdf.get("cab") or {}
        if not c or not c.get("linhas"):
            r["avisos"].append({"cod": "R01", "msg": "Cabeçalho não pôde ser lido", "det": pdf.get("erro") or "1ª página sem texto."})
            continue

        # R04 — cabeçalho x nome do arquivo
        do_nome = pdf.get("do_nome", {})
        for campo in sorted(do_nome.keys()):
            vn, vc = do_nome.get(campo), c.get(campo)
            if vc is None or vn is None:
                continue
            if not bate_campo(campo, vc, vn):
                r["graves"].append({
                    "cod": "R04", "msg": f"Cabeçalho e nome do arquivo discordam em {campo}",
                    "det": f'cabeçalho diz "{vc}", nome do arquivo diz "{vn}".',
                })

        # R05 — natureza errada no meio do lote (o caso original do projeto)
        if esperado_natureza and c.get("natureza") and c["natureza"] != esperado_natureza:
            r["graves"].append({
                "cod": "R05",
                "msg": f"Prova de {NOME_NAT.get(c['natureza'], c['natureza']).upper()} no meio de um lote de {NOME_NAT.get(esperado_natureza, esperado_natureza).upper()}",
                "det": f'o cabeçalho diz "{c.get("titulo") or ""}".',
            })

        # R19 — página no meio do arquivo é de outra série/tipo
        divergentes = [
            o for o in pdf.get("outros_cab", [])
            if (o.get("natureza") and c.get("natureza") and o["natureza"] != c["natureza"])
            or (o.get("serie") and c.get("serie") and not serie_bate(o["serie"], c["serie"]))
            or (o.get("etapa") is not None and c.get("etapa") is not None and o["etapa"] != c["etapa"])
        ]
        if divergentes:
            paginas = ", ".join(str(o["pagina"]) for o in divergentes)
            desc = "; ".join(
                " ".join(filter(None, [NOME_NAT.get(o.get("natureza"), o.get("natureza")), o.get("serie")])) or "?"
                for o in divergentes
            )
            r["graves"].append({
                "cod": "R19", "msg": "Página no meio do arquivo é de outra série/tipo de prova",
                "det": f"pág. {paginas}: {desc}.",
            })
        resto = [o for o in pdf.get("outros_cab", []) if o not in divergentes]
        if resto:
            r["avisos"].append({
                "cod": "R10", "msg": "Arquivo tem cabeçalho de prova em outra página",
                "det": "páginas: " + ", ".join(str(o["pagina"]) for o in resto) + ".",
            })

        # R21 — página de início de prova tem que ser ÍMPAR (nunca no verso
        # da anterior), exceto provas adaptadas (AD/N), que saem só frente.
        if not eh_adaptado(pdf["nome"]):
            paginas_inicio = [1] + [o["pagina"] for o in pdf.get("outros_cab", [])]
            pares = sorted(set(p for p in paginas_inicio if p % 2 == 0))
            if pares:
                r["graves"].append({
                    "cod": "R21", "msg": "Prova começando no verso (página par) — precisa iniciar em página ímpar",
                    "det": "pág. " + ", ".join(str(p) for p in pares) + ".",
                })

        # R22 — Química (ou Ciências com frente de Química) precisa ter a
        # tabela periódica ao final do arquivo.
        if eh_quimica(c, pdf.get("do_nome")):
            if not TABELA_PERIODICA_RE.search(normU(pdf.get("texto", ""))):
                r["graves"].append({
                    "cod": "R22", "msg": "Falta a tabela periódica ao final da prova de Química",
                    "det": "",
                })

        # R23 — prova adaptada (AD/N no nome do arquivo) precisa ter o
        # símbolo ∞ do Bernoulli em algum lugar do cabeçalho.
        if eh_adaptado(pdf["nome"]):
            if INFINITO not in (pdf.get("texto") or ""):
                r["graves"].append({
                    "cod": "R23", "msg": "Prova adaptada sem o símbolo ∞ (infinito) de identificação",
                    "det": "",
                })

        # R24 — soma dos pontos de cada questão tem que bater com o valor
        # declarado no cabeçalho (não só o valor declarado x planilha).
        valores_q = pdf.get("valores_q") or []
        if valores_q and c.get("valor") is not None:
            soma = round(sum(valores_q), 2)
            if abs(soma - c["valor"]) > 0.011:
                r["graves"].append({
                    "cod": "R24", "msg": f"Soma dos pontos das questões ({soma}) não bate com o Valor do cabeçalho ({c['valor']})",
                    "det": "",
                })

    # R20 — página idêntica em outro arquivo do lote
    por_fp = defaultdict(list)
    for pdf in pdfs:
        for pg in pdf.get("paginas_fp", []):
            por_fp[pg["fp"]].append((pdf, pg["pagina"]))
    for grupo in por_fp.values():
        por_arquivo = defaultdict(list)
        for pdf, pagina in grupo:
            por_arquivo[pdf["nome"]].append((pdf, pagina))
        if len(por_arquivo) < 2:
            continue
        for nome, entradas in por_arquivo.items():
            pdf = entradas[0][0]
            paginas = sorted(p for _, p in entradas)
            outros = "; ".join(
                f'{on} (pág. {", ".join(str(p) for _, p in oe)})'
                for on, oe in por_arquivo.items() if on != nome
            )
            resultados[nome]["graves"].append({
                "cod": "R20", "msg": "Página idêntica à de outro arquivo do lote",
                "det": f"pág. {', '.join(str(p) for p in paginas)} = mesmo texto de {outros}.",
            })

    return resultados


def hash_dup(itens_casados):
    """PL-HASHDUP: o mesmo arquivo (hash) casado com duas linhas de planilha
    de conteúdo diferente — provável arquivo errado reaproveitado."""
    por_hash = defaultdict(list)
    for r in itens_casados:
        if r.get("pdf") and r["pdf"].get("hash"):
            por_hash[r["pdf"]["hash"]].append(r)
    achados = []
    for grupo in por_hash.values():
        if len(grupo) < 2:
            continue
        chaves = set(chave_conteudo(r["item"]) for r in grupo)
        if len(chaves) < 2:
            continue
        for r in grupo:
            outros = "; ".join(
                f'{o["item"].get("serie") or "série?"} · {o["item"].get("disciplina") or ""}'.strip()
                for o in grupo if o is not r
            )
            achados.append({
                "item": r["item"], "pdf": r["pdf"], "cod": "PL-HASHDUP",
                "msg": "Arquivo idêntico usado em outra prova",
                "det": f'{r["pdf"]["nome"]} é idêntico a outro arquivo já usado para: {outros}.',
            })
    return achados


def conferir_planilha(itens, pdfs, contar_questoes_fn):
    """Casa cada item da planilha com o melhor PDF e roda PL-QTD/PL-VALOR/
    PL-SEMPDF (agora aviso, não bloqueia)."""
    resultados = []
    for item in itens:
        melhor, melhor_pt = None, 0
        for pdf in pdfs:
            s = pontuar(item, pdf)
            if s["pt"] > melhor_pt:
                melhor, melhor_pt = {**s, "pdf": pdf}, s["pt"]
        if not melhor or melhor_pt < 3:
            resultados.append({
                "item": item, "pdf": None, "graves": [], "avisos": [
                    {"cod": "PL-SEMPDF", "msg": "Nenhum PDF corresponde a este item", "det": ""}
                ],
            })
            continue
        pdf = melhor["pdf"]
        graves, avisos = [], []
        esperado = (item.get("qDisc") or 0) + (item.get("qObj") or 0)
        if esperado:
            q = contar_questoes_fn(pdf)
            if q["qtd"] == esperado:
                pass
            elif q["qtd"] == 0:
                avisos.append({"cod": "PL-QTD", "msg": f"Não consegui contar as questões (a planilha diz {esperado})", "det": ""})
            else:
                graves.append({"cod": "PL-QTD", "msg": f"Contei {q['qtd']} questões, a planilha diz {esperado}", "det": ""})
        total = (item.get("vDisc") or 0) + (item.get("vObj") or 0)
        c = pdf.get("cab") or {}
        if total and c.get("valor") is not None and abs(c["valor"] - total) > 0.011:
            graves.append({"cod": "PL-VALOR", "msg": f"Valor deveria ser {total}, cabeçalho diz {c['valor']}", "det": ""})
        resultados.append({"item": item, "pdf": pdf, "graves": graves, "avisos": avisos})

    resultados.extend(
        {"item": h["item"], "pdf": h["pdf"], "graves": [h], "avisos": []}
        for h in hash_dup([r for r in resultados if r["pdf"]])
    )
    return resultados
