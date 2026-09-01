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


# --- ajuste pedido em 2026-09: trava lógica de "aba errada" ---------------
# Pelo nome do arquivo/série colada dá pra saber se o lote é de EM, EF Anos
# Finais, EF Anos Iniciais, Simulado, PAB/PBB ou Módulo — mesmo sem entender
# ainda a regra fina de cada um. Isso evita o caso real reportado: colar
# planilha de "1ª Série" (EM) numa aba de "EF6|EF9" e o preflight não avisar
# nada porque a aba errada só muda a ORDEM das colunas, não valida o
# conteúdo contra a aba escolhida.
GRUPO_ESPERADO_ABA = {
    "anosIniciais": {"EFAI"},
    "ef69cj": {"EFAF"}, "ef69vse": {"EFAF"}, "ef69cda": {"EFAF"},
    "em_cjlourdes": {"EM"}, "em_vse": {"EM"}, "em_cda": {"EM"},
    "modulo": None, "simulados": None, "perifericos": None, "pab_pbb": None,
}
# abas que são só do Bernoulli (origem do PDF, ver ler_pdf) vs. só do Módulo
ORIGEM_ESPERADA_ABA = {
    "anosIniciais": "bernoulli", "ef69cj": "bernoulli", "ef69vse": "bernoulli",
    "ef69cda": "bernoulli", "em_cjlourdes": "bernoulli", "em_vse": "bernoulli",
    "em_cda": "bernoulli", "modulo": "modulo",
    "simulados": None, "perifericos": None, "pab_pbb": None,
}


def grupo_da_serie(txt):
    """'1ª Série'/'1a serie' -> EM; '6º a 9º Ano' -> EFAF; '1º a 5º Ano' -> EFAI."""
    tU = normU(txt or "")
    if re.search(r"\bSERIE\b", tU):
        return "EM"
    m = re.search(r"\b([0-9]{1,2})\s*O?\s*ANO\b", tU)
    if m:
        return "EFAF" if int(m.group(1)) >= 6 else "EFAI"
    return None


def checar_aba(aba_id, itens=None, pdfs=None):
    """Trava lógica: a aba do Controle escolhida bate com o CONTEÚDO colado/
    enviado? Não substitui as 4 famílias graves — é um aviso à parte, mostrado
    antes delas, porque se a aba está errada o resto da conferência também
    fica sem sentido (colunas na ordem errada)."""
    itens, pdfs = itens or [], pdfs or []
    alertas = []
    grupos_esperados = GRUPO_ESPERADO_ABA.get(aba_id)
    if grupos_esperados:
        achados = set()
        for it in itens:
            g = grupo_da_serie(it.get("serie"))
            if g:
                achados.add(g)
        for pdf in pdfs:
            serie_pdf = (pdf.get("cab") or {}).get("serie") or (pdf.get("do_nome") or {}).get("serie")
            g = grupo_da_serie(serie_pdf)
            if g:
                achados.add(g)
        estranhos = achados - grupos_esperados
        if estranhos:
            alertas.append({
                "msg": (
                    f"Aba do Controle pode estar errada: pelo conteúdo, isso parece ser de "
                    f"{'/'.join(sorted(estranhos))}, mas a aba escolhida é de "
                    f"{'/'.join(sorted(grupos_esperados))}."
                ),
                "det": "Confira a Série: '1ª/2ª/3ª Série' é Ensino Médio; '6º a 9º Ano' é EF Anos Finais; '1º a 5º Ano' é Anos Iniciais.",
            })
    origem_esperada = ORIGEM_ESPERADA_ABA.get(aba_id)
    if origem_esperada:
        for pdf in pdfs:
            og = pdf.get("origem")
            if og and og not in ("indefinida", origem_esperada):
                alertas.append({
                    "msg": (
                        f"Aba do Controle pode estar errada: o arquivo {pdf.get('nome')} parece ser do "
                        f"{'Módulo' if og == 'modulo' else 'Bernoulli'}, mas a aba escolhida é do "
                        f"{'Módulo' if origem_esperada == 'modulo' else 'Bernoulli'}."
                    ),
                    "det": pdf.get("origem_como") or "",
                })
    if aba_id and aba_id != "simulados":
        for it in itens:
            texto = normU(" ".join(str(it.get(c) or "") for c in ("descricao", "serie", "adaptacoes")))
            if re.search(r"\bSIMULADO\b", texto):
                alertas.append({
                    "msg": "Aba do Controle pode estar errada: uma linha da planilha parece ser de Simulado, mas a aba escolhida não é a 8 - Simulados.",
                    "det": None,
                })
                break
    if aba_id and aba_id != "pab_pbb":
        for it in itens:
            texto = normU(" ".join(str(it.get(c) or "") for c in ("descricao", "adaptacoes")))
            if re.search(r"\b(PAB|PBB)\b", texto):
                alertas.append({
                    "msg": "Aba do Controle pode estar errada: uma linha da planilha parece ser de PAB/PBB, mas a aba escolhida não é a 10 - PAB | PBB.",
                    "det": None,
                })
                break
    return alertas


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


def _disciplina_base(s):
    # "Português (Conj.)" -> "Português" — a planilha usa esse sufixo pra
    # indicar que a disciplina é composta (Redação/Gramática dentro de
    # Português), mas o cabeçalho da prova só imprime o nome base.
    return re.sub(r"\s*\([^)]*\)\s*$", "", s or "").strip()


def _texto_contem(texto_norm, alvo):
    if not alvo:
        return False
    return norm(alvo) in texto_norm


def _segmentos_de(pdf):
    """Um PDF pode trazer mais de uma prova dentro (várias frentes/
    professores concatenados no mesmo arquivo — comum em 2ª chamada). Usa os
    segmentos detectados em ler_pdf(); se por algum motivo não houver nenhum
    (ex.: PDF ilegível), cai de volta para tratar o arquivo inteiro como um
    segmento único, igual ao comportamento antigo."""
    segs = pdf.get("segmentos")
    if segs:
        return segs
    return [{
        "pagina_ini": 1, "pagina_fim": pdf.get("paginas") or 1,
        "cab": pdf.get("cab") or {}, "texto": pdf.get("texto", ""),
        "linhas": pdf.get("linhas", []), "valores_q": pdf.get("valores_q", []),
    }]


def pontuar_segmento(item, seg, bernoulli):
    """Pontuação de compatibilidade item-da-planilha x SEGMENTO de um PDF
    (um PDF pode ter vários segmentos — uma prova por frente/professor).
    Quanto maior o pt, melhor o par. Comparações de texto usam só o texto
    DESSE segmento, não do arquivo inteiro, pra não vazar dado de uma frente
    pra outra dentro do mesmo arquivo."""
    c = seg.get("cab") or {}
    pt = 0
    conflito = False

    item_disc_base = _disciplina_base(item.get("disciplina"))
    disc_cab = bool(item_disc_base and c.get("disciplina") and normU(item_disc_base) == normU(c["disciplina"]))
    disc_txt = bool(item_disc_base and _texto_contem(norm(seg.get("texto", "")), item_disc_base))
    disc = disc_cab or disc_txt
    if item.get("disciplina") and not disc:
        conflito = True
    if disc_cab:
        pt += 4
    elif disc_txt:
        pt += 2

    fr_cab = bool(item.get("frente") and c.get("frente") and normU(item["frente"]) == normU(c["frente"]))
    fr_txt = bool(item.get("frente") and _texto_contem(norm(seg.get("texto", "")), item["frente"]))
    fr = fr_cab or fr_txt
    if item.get("frente") and bernoulli and not fr:
        conflito = True
    if fr_cab:
        pt += 3
    elif fr_txt:
        pt += 1

    prof_cab = bool(item.get("professor") and c.get("professor") and norm(item["professor"]) in norm(c["professor"]))
    prof_exato = bool(item.get("professor") and _texto_contem(norm(seg.get("texto", "")), item["professor"]))
    if prof_cab:
        pt += 3
    elif prof_exato:
        pt += 1

    if item.get("serie") and c.get("serie") and serie_bate(item["serie"], c["serie"]):
        pt += 2

    turno_bate = None
    if item.get("turno") and c.get("turno"):
        turno_bate = normU(item["turno"]) == normU(c["turno"])
        if turno_bate:
            pt += 2

    if conflito:
        pt = 0

    return {
        "pt": pt, "bernoulli": bernoulli, "disc": disc, "disc_cab": disc_cab,
        "fr": fr, "fr_cab": fr_cab, "prof_cab": prof_cab, "prof_exato": prof_exato,
        "conflito": conflito, "turno_bate": turno_bate,
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

        # R19B — mesma ideia do R19, mas olhando a TARJA que roda em toda
        # página de conteúdo (ex.: "MATEMÁTICA | 4º Ano" no topo), não só as
        # páginas que parecem um cabeçalho completo novo (caixas de
        # professor/aluno/valor). Pega alteração escondida no meio do
        # miolo que não tem essas caixas.
        ja_flagrado = set(o["pagina"] for o in divergentes) | {1}
        divergentes_tag = []
        for seg in _segmentos_de(pdf):
            seg_c = seg.get("cab") or {}
            for tag in pdf.get("paginas_tag", []):
                if tag["pagina"] in ja_flagrado:
                    continue
                if not (seg["pagina_ini"] <= tag["pagina"] <= seg["pagina_fim"]):
                    continue
                diverge = (
                    (tag.get("disciplina") and seg_c.get("disciplina") and normU(tag["disciplina"]) != normU(seg_c["disciplina"]))
                    or (tag.get("serie") and seg_c.get("serie") and not serie_bate(tag["serie"], seg_c["serie"]))
                )
                if diverge:
                    divergentes_tag.append((tag, seg_c))
                    ja_flagrado.add(tag["pagina"])
        if divergentes_tag:
            desc = "; ".join(
                f'pág. {tag["pagina"]}: {" ".join(filter(None, [tag.get("disciplina"), tag.get("serie")])) or "?"} (esperado {" ".join(filter(None, [seg_c.get("disciplina"), seg_c.get("serie")])) or "?"})'
                for tag, seg_c in divergentes_tag
            )
            r["graves"].append({
                "cod": "R19", "msg": "Página no meio do arquivo é de outra série/disciplina",
                "det": desc + ".",
            })

        # R21 — página de início de prova tem que ser ÍMPAR (nunca no verso
        # da anterior), exceto provas adaptadas (AD/N), que saem só frente.
        if not eh_adaptado(pdf["nome"]):
            paginas_inicio = [seg["pagina_ini"] for seg in _segmentos_de(pdf)] or [1]
            pares = sorted(set(p for p in paginas_inicio if p % 2 == 0))
            if pares:
                r["graves"].append({
                    "cod": "R21", "msg": "Prova começando no verso (página par) — precisa iniciar em página ímpar",
                    "det": "pág. " + ", ".join(str(p) for p in pares) + ".",
                })

        # R22 — Química (ou Ciências com frente de Química) precisa ter a
        # tabela periódica ao final do arquivo. Algumas tabelas periódicas
        # saem com o texto inteiro espelhado (mesmo efeito visto na tarja
        # lateral — rotação de página) — por isso confere os dois sentidos.
        if eh_quimica(c, pdf.get("do_nome")):
            tU_arquivo = normU(pdf.get("texto", ""))
            achou = TABELA_PERIODICA_RE.search(tU_arquivo) or TABELA_PERIODICA_RE.search(tU_arquivo[::-1])
            if not achou:
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
        # Roda POR SEGMENTO (cada frente/prova dentro do arquivo), nunca
        # somando questões de uma frente com o valor do cabeçalho de outra.
        for seg in _segmentos_de(pdf):
            seg_valores = seg.get("valores_q") or []
            seg_c = seg.get("cab") or {}
            if seg_valores and seg_c.get("valor") is not None:
                soma = round(sum(seg_valores), 2)
                if abs(soma - seg_c["valor"]) > 0.011:
                    det = f"pág. {seg['pagina_ini']}-{seg['pagina_fim']}." if len(pdf.get("segmentos") or []) > 1 else ""
                    r["graves"].append({
                        "cod": "R24", "msg": f"Soma dos pontos das questões ({soma}) não bate com o Valor do cabeçalho ({seg_c['valor']})",
                        "det": det,
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
    """PL-HASHDUP: o MESMO TRECHO (arquivo + página inicial do segmento)
    casado com duas linhas de planilha de conteúdo diferente — provável
    arquivo errado reaproveitado. Agrupa por (hash do arquivo, página de
    início do segmento) em vez de só o hash do arquivo — um arquivo com
    várias frentes concatenadas (2ª chamada com Frente A/B/C no mesmo PDF)
    é um caso legítimo de o MESMO arquivo casar com VÁRIAS linhas da
    planilha, contanto que cada linha aponte pra um segmento diferente."""
    por_trecho = defaultdict(list)
    for r in itens_casados:
        pdf = r.get("pdf")
        if pdf and pdf.get("hash"):
            chave = (pdf["hash"], r.get("segmento_pagina_ini", 1))
            por_trecho[chave].append(r)
    achados = []
    for grupo in por_trecho.values():
        if len(grupo) < 2:
            continue
        # duas linhas da planilha podem legitimamente casar com o MESMO
        # trecho quando é um bloco combinado (ex.: "Redação e Gramática"
        # impressas juntas, uma prova só, dividida em duas linhas só pra
        # corrigir com professores diferentes) — nesse caso série e
        # disciplina são as mesmas, só frente/professor mudam. Só é
        # reaproveitamento ERRADO quando SÉRIE ou DISCIPLINA divergem.
        chaves_conteudo = set(
            (normU(r["item"].get("serie")), normU(_disciplina_base(r["item"].get("disciplina"))))
            for r in grupo
        )
        if len(chaves_conteudo) < 2:
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
                "msg": "Mesmo trecho do arquivo usado em outra prova",
                "det": f'{r["pdf"]["nome"]} (pág. {r.get("segmento_pagina_ini","?")}) é idêntico a outro trecho já usado para: {outros}.',
            })
    return achados


def conferir_planilha(itens, pdfs, contar_questoes_fn):
    """Casa cada item da planilha com o melhor SEGMENTO de PDF (um arquivo
    pode trazer várias provas concatenadas — uma por frente/professor) e
    roda PL-QTD/PL-VALOR/PL-SEMPDF (agora aviso, não bloqueia) usando só o
    texto/valor DESSE segmento, nunca do arquivo inteiro.

    Duas ou mais linhas da planilha podem legitimamente casar com o MESMO
    segmento — caso real: "Redação" e "Gramática" saem como um único bloco
    de prova (mesmo cabeçalho, mesmo Valor somado), mas a planilha separa a
    correção em duas linhas por professor. Nesse caso a conferência de
    questões/valor é feita pela SOMA do grupo contra o segmento, não linha
    a linha — senão cada linha sozinha nunca bate com o total do bloco
    inteiro."""
    casados = []  # [{"item", "pdf", "segmento"}] ou {"item","pdf":None} se não achou
    for item in itens:
        melhor, melhor_pt = None, 0
        for pdf in pdfs:
            bernoulli = pdf.get("origem") == "bernoulli"
            for seg in _segmentos_de(pdf):
                s = pontuar_segmento(item, seg, bernoulli)
                if s["pt"] > melhor_pt:
                    melhor, melhor_pt = {**s, "pdf": pdf, "segmento": seg}, s["pt"]
        if not melhor or melhor_pt < 3:
            casados.append({"item": item, "pdf": None, "segmento": None})
        else:
            casados.append({"item": item, "pdf": melhor["pdf"], "segmento": melhor["segmento"]})

    grupos = defaultdict(list)
    for c in casados:
        if c["pdf"]:
            grupos[(c["pdf"]["nome"], c["segmento"]["pagina_ini"])].append(c)

    resultados = []
    for c in casados:
        if not c["pdf"]:
            resultados.append({
                "item": c["item"], "pdf": None, "graves": [], "avisos": [
                    {"cod": "PL-SEMPDF", "msg": "Nenhum PDF corresponde a este item", "det": ""}
                ],
            })
            continue
        item, pdf, seg = c["item"], c["pdf"], c["segmento"]
        grupo = grupos[(pdf["nome"], seg["pagina_ini"])]
        multiplo = len(grupo) > 1
        graves, avisos = [], []

        # turno errado — planilha diz Manhã/Tarde/Noite e o PDF casado é de
        # outro turno (mesma família de "conteúdo de outra série/tipo").
        seg_cab = seg.get("cab") or {}
        if item.get("turno") and seg_cab.get("turno") and normU(item["turno"]) != normU(seg_cab["turno"]):
            graves.append({
                "cod": "PL-TURNO", "msg": f"Planilha diz turno {item['turno']}, mas o PDF casado é do turno {seg_cab['turno']}",
                "det": "",
            })
        esperado_grupo = sum((g["item"].get("qDisc") or 0) + (g["item"].get("qObj") or 0) for g in grupo)
        esperado = (item.get("qDisc") or 0) + (item.get("qObj") or 0)
        if esperado_grupo:
            q = contar_questoes_fn(seg)
            sufixo = " (somando as linhas que dividem essa mesma prova)" if multiplo else ""
            if q["qtd"] == esperado_grupo:
                pass
            elif q["qtd"] == 0:
                avisos.append({"cod": "PL-QTD", "msg": f"Não consegui contar as questões (a planilha diz {esperado}{sufixo})", "det": ""})
            else:
                graves.append({"cod": "PL-QTD", "msg": f"Contei {q['qtd']} questões, a planilha diz {esperado_grupo}{sufixo}", "det": ""})
        total_grupo = sum((g["item"].get("vDisc") or 0) + (g["item"].get("vObj") or 0) for g in grupo)
        total = (item.get("vDisc") or 0) + (item.get("vObj") or 0)
        c_seg = seg.get("cab") or {}
        if total_grupo and c_seg.get("valor") is not None and abs(c_seg["valor"] - total_grupo) > 0.011:
            sufixo = " (somando as linhas que dividem essa mesma prova)" if multiplo else ""
            graves.append({"cod": "PL-VALOR", "msg": f"Valor deveria ser {total_grupo}{sufixo}, cabeçalho diz {c_seg['valor']}", "det": ""})
        resultados.append({
            "item": item, "pdf": pdf, "graves": graves, "avisos": avisos,
            "segmento_pagina_ini": seg["pagina_ini"],
        })

    resultados.extend(
        {"item": h["item"], "pdf": h["pdf"], "graves": [h], "avisos": []}
        for h in hash_dup([r for r in resultados if r["pdf"]])
    )
    return resultados
