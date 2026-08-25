"""
Leitura de PDF para o Preflight PSM (versão Python/pdfplumber).

Por que reescrever em Python: a versão HTML (pdf.js, no navegador) extrai o
texto por posição de caractere e o agrupamento em linhas/colunas precisa ser
feito manualmente — isso já causou vários bugs reais (número do Valor colado
com a tarja lateral virada, frente por nome não reconhecida) que foram
corrigidos um a um. O pdfplumber já entrega PALAVRAS separadas com posição e
orientação (upright/direction) prontas, o que evita boa parte dessa classe
de erro de largada.
"""
import hashlib
import re
import unicodedata

import pdfplumber


# ---------------------------------------------------------------------------
# normalização de texto (equivalente a norm()/normU() do Preflight_PSM.html)
# ---------------------------------------------------------------------------
def _strip_accents(s):
    # NFKD (não NFD): também decompõe "º"/"ª" (ordinal indicators) em "o"/"a"
    # comum — sem isso "8º Ano" não bate com o regex de série/ano escolar.
    # Faz isso ANTES de mudar caixa: a decomposição de "ª" sempre vira "a"
    # minúsculo, então upper()/lower() têm de vir DEPOIS, senão "3ª Série"
    # normalizado para maiúsculas sobra como "3a SERIE" (a minúsculo) e o
    # regex de série (que espera [AO] maiúsculo) não bate.
    return "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    return _strip_accents(s or "").lower().strip()


def normU(s):
    return _strip_accents(s or "").upper().strip()


# ---------------------------------------------------------------------------
# agrupamento de palavras em linhas
# ---------------------------------------------------------------------------
def extract_lines(page):
    """Retorna (linhas_horizontais, linhas_giradas, largura, altura).

    Cada linha: {"texto", "x0", "x1", "topo", "tam"}.
    """
    words = page.extract_words(extra_attrs=["size", "upright"], use_text_flow=False)
    horiz = [w for w in words if w.get("upright", True)]
    girado = [w for w in words if not w.get("upright", True)]

    def agrupar(ws, key_pos):
        # agrupa por proximidade vertical (linhas horizontais) ou horizontal
        # (texto girado, lido de cima pra baixo) — key_pos dá a "linha" e a
        # "posição ao longo do texto" pra cada palavra.
        itens = sorted(ws, key=lambda w: (key_pos(w)[0], key_pos(w)[1]))
        linhas = []
        bloco = []
        ref = None
        for w in itens:
            v, u = key_pos(w)
            if ref is None or abs(v - ref) <= max(1.5, 0.5 * w["size"]):
                bloco.append(w)
                ref = v if ref is None else ref
            else:
                if bloco:
                    linhas.append(_fechar_bloco(bloco, key_pos))
                bloco = [w]
                ref = v
        if bloco:
            linhas.append(_fechar_bloco(bloco, key_pos))
        return linhas

    def _fechar_bloco(bloco, key_pos):
        bloco = sorted(bloco, key=lambda w: key_pos(w)[1])
        partes = []
        fim = None
        for w in bloco:
            _, u0 = key_pos(w)
            if fim is not None:
                lac = u0 - fim
                if lac > 0.22 * max(w["size"], 1):
                    partes.append("   " if lac > 1.6 * max(w["size"], 1) else " ")
            partes.append(w["text"])
            fim = u0 + (w["x1"] - w["x0"] if "x1" in w else 0)
        texto = "".join(partes).strip()
        xs = [w["x0"] for w in bloco] + [w["x1"] for w in bloco]
        tops = [w["top"] for w in bloco] + [w["bottom"] for w in bloco]
        return {
            "texto": texto,
            "x0": min(xs),
            "x1": max(xs),
            "topo": min(tops),
            "tam": max(w["size"] for w in bloco),
        }

    linhas_h = agrupar(horiz, lambda w: (w["top"], w["x0"]))
    linhas_g = agrupar(girado, lambda w: (w["x0"], w["top"]))
    linhas_h.sort(key=lambda l: (l["topo"], l["x0"]))
    return linhas_h, linhas_g, page.width, page.height


# ---------------------------------------------------------------------------
# parser do cabeçalho — equivalente a analisarCabecalho() do HTML
# ---------------------------------------------------------------------------
RE_ETAPA = re.compile(r"\b([1-4])\s*[AO]?\s*ETAPA\b")
RE_ETAPA_FOLGADA = re.compile(r"\b([1-4])\s*[AO]\b[\s\S]{0,40}?ETAPA\b")
RE_SERIE = re.compile(r"\b([1-9])\s*[AO]?\s*SERIE\b")
RE_ANO_ESC = re.compile(r"\b([1-9])\s*[AO]?\s*ANO\b")
RE_FRENTE_LETRA = re.compile(r"\bFRENTE\s*:?\s*(UNICA|[A-D])(?![A-Z])")
RE_ROTULO_VALOR = re.compile(r"\bVALOR\b")
RE_VALOR = re.compile(r"\bVALOR\s*:?\s*([0-9]{1,2}\s*[,.]\s*[0-9]{1,2})\b")
RE_SO_NUM = re.compile(r"^\(?\s*([0-9]{1,2}\s*[,.]\s*[0-9]{1,2})\s*\)?$")
RE_NUM_FIM = re.compile(r"([0-9]{1,2}\s*[,.]\s*[0-9]{1,2})\s*$")
RE_NUM_QQ = re.compile(r"\b([0-9]{1,2}\s*[,.]\s*[0-9]{1,2})(?!\d)")
RE_ANO = re.compile(r"\b(20[0-9]{2})\b")
RE_CODIGO = re.compile(r"(?<![A-Z0-9])(A\s?[1-9]|U\s?[1-9]|SA\s?\d{1,2}|SE\s?\d{1,2}|PAB|PBB|AD\s?[1-4])(?![A-Z0-9])")

NOME_NAT = {
    "2a_chamada": "2ª Chamada",
    "recuperacao": "Recuperação",
    "simulado": "Simulado",
    "admissao": "Admissão",
    "regular": "Regular",
}
NATUREZAS = [
    ("2a_chamada", ["2 CHAMADA", "2A CHAMADA", "SEGUNDA CHAMADA"]),
    ("recuperacao", ["RECUPERACAO", "RECUPERAÇÃO".upper()]),
    ("simulado", ["SIMULADO"]),
    ("admissao", ["ADMISSAO", "PAB", "PBB"]),
]

DISCIPLINAS_PADRAO = [
    "Português", "Matemática", "História", "Geografia", "Física", "Química",
    "Biologia", "Inglês", "Espanhol", "Filosofia", "Sociologia", "Arte",
    "Educação Física", "Redação", "Literatura", "Gramática", "Ciências",
]


def _achar_disciplina(txtU, disciplinas):
    achados = []
    for d in sorted(disciplinas, key=len, reverse=True):
        dn = normU(d)
        if re.search(r"\b" + re.escape(dn), txtU):
            achados.append(d)
    return achados[0] if achados else None


def _valor_perto(zona, i):
    base = zona[i]
    for j in range(i + 1, min(i + 8, len(zona))):
        o = zona[j]
        if o["topo"] - base["topo"] > 6 * max(base["tam"], 6):
            break
        if o["x1"] < base["x0"] - 12 or o["x0"] > base["x1"] + 40:
            continue
        t = o["texto"].strip()
        m = RE_SO_NUM.match(t)
        if m:
            return m.group(1)
        m2 = RE_NUM_FIM.search(t)
        if m2 and o["x1"] >= base["x0"] - 12:
            return m2.group(1)
        m3 = RE_NUM_QQ.search(t)
        if m3 and o["x1"] >= base["x0"] - 12:
            return m3.group(1)
    return None


def parse_header(page, altura_cabecalho=0.30, disciplinas=None):
    disciplinas = disciplinas or DISCIPLINAS_PADRAO
    linhas_h, linhas_g, largura, altura = extract_lines(page)
    lim = altura * altura_cabecalho
    zona = [l for l in linhas_h if l["topo"] <= lim] or linhas_h[:12]

    cab = {
        "natureza": None, "codigo": None, "disciplina": None, "etapa": None,
        "serie": None, "frente": None, "valor": None, "ano": None,
        "professor": None, "tarja": None, "titulo": None, "linhas": [l["texto"] for l in zona],
    }

    tU = normU("\n".join(l["texto"] for l in zona))

    if zona:
        maior = max(l["tam"] for l in zona)
        titulo_linhas = [l for l in zona if l["tam"] >= maior - 0.6 and not re.match(r"^[\s_/\d.:()-]+$", l["texto"])]
        cab["titulo"] = " ".join(l["texto"].strip() for l in titulo_linhas) if titulo_linhas else None
    titU = normU(cab["titulo"] or "")

    for nome, tokens in NATUREZAS:
        if any(t in titU or t in tU for t in tokens):
            cab["natureza"] = nome
            break
    mc = RE_CODIGO.search(titU) or RE_CODIGO.search(tU)
    if mc:
        cab["codigo"] = mc.group(1).replace(" ", "")
        if not cab["natureza"]:
            cab["natureza"] = "regular"

    # tarja: texto girado nas margens laterais. Dependendo da rotação da
    # fonte, o texto pode sair invertido ("ACIMÍUQ" em vez de "QUÍMICA") —
    # por isso tenta casar tanto o texto normal quanto o texto ao contrário.
    beira = sorted(
        [l for l in linhas_g if l["x0"] >= 0.82 * largura or l["x1"] <= 0.18 * largura],
        key=lambda l: -len(l["texto"]),
    )
    tarja_disc = None
    for l in beira:
        txt = l["texto"]
        d = _achar_disciplina(normU(txt), disciplinas) or _achar_disciplina(normU(txt[::-1]), disciplinas)
        if d:
            tarja_disc = d
            cab["tarja"] = d
            break
        if cab["tarja"] is None and len(txt.strip()) <= 40:
            cab["tarja"] = txt.strip()

    # turno (Manhã/Tarde/Noite) — em alguns templates (EF Anos Finais) vem
    # na MESMA tarja lateral da disciplina, junto, tipo "HISTÓRIA   MANHÃ"
    # (às vezes espelhado, "ÃHNAM   AIRÓTSIH"). Confere os dois sentidos.
    _TURNOS = {"MANHA": "Manhã", "TARDE": "Tarde", "NOITE": "Noite", "INTEGRAL": "Integral"}
    cab["turno"] = None
    for l in linhas_g:
        for cand in (normU(l["texto"]), normU(l["texto"])[::-1]):
            m = re.search(r"\b(MANHA|TARDE|NOITE|INTEGRAL)\b", cand)
            if m:
                cab["turno"] = _TURNOS[m.group(1)]
                break
        if cab["turno"]:
            break

    # a TARJA lateral tem prioridade: é o campo pensado pra dizer só a
    # disciplina, sem ambiguidade. O título/corpo do cabeçalho é usado como
    # reforço, mas pode enganar de dois jeitos vistos em arquivos reais:
    # (1) título colado sem espaço ("DEQUÍMICA"/"DEPORTUGUÊS") faz o \b do
    # regex falhar; (2) quando isso acontece, a busca cai pro texto da zona
    # inteira, que também contém a linha "Frente Literatura/Redação/
    # Gramática" — e como esses nomes de frente TAMBÉM são disciplinas
    # válidas (existem sozinhas em Anos Iniciais), a frente errada acaba
    # sendo lida como se fosse a disciplina da prova.
    cab["disciplina"] = tarja_disc or _achar_disciplina(titU, disciplinas) or _achar_disciplina(tU, disciplinas)

    m = RE_ETAPA.search(titU) or RE_ETAPA.search(tU) or RE_ETAPA_FOLGADA.search(titU) or RE_ETAPA_FOLGADA.search(tU)
    if m:
        cab["etapa"] = int(m.group(1))
    m = RE_SERIE.search(tU)
    if m:
        cab["serie"] = f"{m.group(1)}ª Série"
    else:
        m = RE_ANO_ESC.search(tU)
        if m:
            cab["serie"] = f"{m.group(1)}º Ano"

    m = RE_FRENTE_LETRA.search(tU)
    if m:
        cab["frente"] = m.group(1).replace(" ", "")
    if not cab["frente"]:
        for l in zona:
            mf = re.search(r"FRENTE\s*:?\s*", l["texto"], re.IGNORECASE)
            if not mf:
                continue
            resto = l["texto"][mf.end():]
            resto = re.split(r"\s{2,}|_{2,}|\d{1,2}\s*[/,.]\s*\d|\|", resto)[0]
            resto = re.sub(r"[:\-\s]+$", "", resto).strip()
            if resto and re.search(r"[A-Za-zÀ-ÿ]{3,}", resto):
                cab["frente"] = resto
                break

    # valor
    rotulo_valor_em = -1
    for i, l in enumerate(zona):
        lU = normU(l["texto"])
        mv = RE_VALOR.search(lU)
        if mv:
            cab["valor"] = float(mv.group(1).replace(" ", "").replace(",", "."))
            break
        if RE_ROTULO_VALOR.search(lU):
            if rotulo_valor_em < 0:
                rotulo_valor_em = i
            v = _valor_perto(zona, i)
            if v:
                cab["valor"] = float(v.replace(" ", "").replace(",", "."))
                break
    if cab["valor"] is None and rotulo_valor_em >= 0:
        base_rot = zona[rotulo_valor_em]
        if base_rot["x0"] >= 0.5 * largura:
            melhor, melhor_dist = None, float("inf")
            for j, o in enumerate(zona):
                if j == rotulo_valor_em or o["x0"] < 0.5 * largura:
                    continue
                t = o["texto"].strip()
                m2 = RE_SO_NUM.match(t) or RE_NUM_FIM.search(t)
                if not m2:
                    continue
                dist = abs(o["topo"] - base_rot["topo"])
                if dist < melhor_dist:
                    melhor_dist, melhor = dist, m2.group(1)
            if melhor:
                cab["valor"] = float(melhor.replace(" ", "").replace(",", "."))

    m = RE_ANO.search(tU)
    if m:
        cab["ano"] = int(m.group(1))

    for l in zona:
        if "PROFESSOR" in normU(l["texto"]):
            resto = re.split(r"[Pp]rofessor\(?a?\)?\s*:?", l["texto"])
            resto = resto[1] if len(resto) > 1 else ""
            resto = re.split(r"\s{2,}|Valor|Nota|Frente", resto)[0]
            resto = resto.replace("_", " ").strip().strip(".:- ")
            if len(resto) >= 3 and re.search(r"[A-Za-zÀ-ÿ]{3}", resto):
                cab["professor"] = resto
            break

    blocos = {
        "professor": "PROFESSOR" in tU, "aluno": "ALUNO" in tU,
        "numero": bool(re.search(r"\bN[O0]?\s*:", tU)) or "NUMERO" in tU,
        "turma": "TURMA" in tU, "nota": "NOTA" in tU, "valor": "VALOR" in tU,
        "data": bool(re.search(r"/\s*20[0-9]{2}", tU)) or "DATA" in tU,
    }
    cab["blocos"] = blocos
    return cab


# ---------------------------------------------------------------------------
# nome do arquivo — equivalente a lerNome()
# ---------------------------------------------------------------------------
_ABREV_DISC = {
    "GEO": "Geografia", "HIS": "História", "HIST": "História", "MAT": "Matemática",
    "FIS": "Física", "QUI": "Química", "BIO": "Biologia", "POR": "Português",
    "RED": "Redação", "LIT": "Literatura", "GRA": "Gramática", "ING": "Inglês",
    "ESP": "Espanhol", "FIL": "Filosofia", "SOC": "Sociologia", "ART": "Arte",
    "EDF": "Educação Física", "CIE": "Ciências",
}


def parse_filename(nome, disciplinas=None):
    disciplinas = disciplinas or DISCIPLINAS_PADRAO
    t = normU(re.sub(r"\.pdf$", "", nome, flags=re.I))
    t = re.sub(r"[_\-.]+", " ", t)
    out = {}
    for n, rx in [
        ("2a_chamada", r"\b(2\s*A?\s*CH(AMADA)?|SEGUNDA\s*CHAMADA|2CH?|SC)\b"),
        ("recuperacao", r"\b(REC|RECUP|RECUPERACAO)\b"),
        ("simulado", r"\b(SIM|SIMULADO)\b"),
        ("admissao", r"\b(PAB|PBB|ADMISSAO)\b"),
    ]:
        if re.search(rx, t):
            out["natureza"] = n
            break
    mc = RE_CODIGO.search(t)
    if mc:
        out["codigo"] = mc.group(1).replace(" ", "")
        out.setdefault("natureza", "regular")
    d = _achar_disciplina(t, disciplinas)
    if not d:
        for k, v in _ABREV_DISC.items():
            if re.search(r"\b" + k + r"\b", t):
                d = v
                break
    if d:
        out["disciplina"] = d
    m = RE_ETAPA.search(t) or re.search(r"\b([1-4])\s*A?\s*ET\b", t) or re.search(r"\bET\s*([1-4])\b", t)
    if m:
        out["etapa"] = int(m.group(1))
    m = RE_SERIE.search(t) or re.search(r"\b([1-3])\s*[AO]?\s*S\b", t)
    if m:
        out["serie"] = f"{m.group(1)}ª Série"
    else:
        m = RE_ANO_ESC.search(t) or re.search(r"\b([6-9])\s*A(NO)?\b", t)
        if m:
            out["serie"] = f"{m.group(1)}º Ano"
    m = RE_FRENTE_LETRA.search(t) or re.search(r"\bFR\s*([A-D])\b", t) or re.search(r"\bF([A-D])\b", t)
    if m:
        out["frente"] = m.group(1)
    m = RE_ANO.search(t)
    if m:
        out["ano"] = int(m.group(1))
    m = re.search(r"\b(MANHA|TARDE|NOITE|INTEGRAL)\b", t)
    if m:
        out["turno"] = {"MANHA": "Manhã", "TARDE": "Tarde", "NOITE": "Noite", "INTEGRAL": "Integral"}[m.group(1)]
    return out


# ---------------------------------------------------------------------------
# contagem de questões — equivalente a contarQuestoes()
# ---------------------------------------------------------------------------
def contar_questoes(texto, linhas):
    t = norm(texto or "")
    conjuntos = []
    for padrao in [r"quest[ãa]o\s*0*(\d{1,2})", r"\bq\s*0*(\d{1,2})\s*[).:-]"]:
        s = set(int(m.group(1)) for m in re.finditer(padrao, t))
        conjuntos.append(s)
    inicio = set()
    for l in linhas or []:
        # exige DOIS dígitos ("01.", "02.") — é o padrão real de numeração
        # de questão do gabarito Bernoulli/Módulo. Um único dígito sem zero
        # à esquerda ("5.") é ambíguo demais: já causou falso positivo com
        # referência bibliográfica no meio do texto ("5. ed. Porto Alegre...").
        m = re.match(r"^\s*(\d{2})\s*[.)]\s*\S", l)
        if m:
            inicio.add(int(m.group(1)))
    conjuntos.append(inicio)
    melhor = max(conjuntos, key=len, default=set())
    return {"qtd": len(melhor), "numeros": sorted(melhor)}


# ---------------------------------------------------------------------------
# hash de arquivo e de página (equivalente a hashDe()/fpPagina())
# ---------------------------------------------------------------------------
def hash_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def fp_pagina(textos_linha):
    partes = []
    for s in textos_linha:
        if not s:
            continue
        if re.match(r"^\s*\d{1,3}\s*$", s):
            continue
        if re.search(r"bernoulli\s*educa[cç][aã]o", s, re.IGNORECASE):
            continue
        partes.append(re.sub(r"\s+", " ", norm(s)).strip())
    t = "|".join(p for p in partes if p)
    if len(t) < 60:
        return None
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# leitura completa de um PDF — equivalente a lerPdf()
# ---------------------------------------------------------------------------
QVALOR_RE = re.compile(r"\(\s*([0-9]{1,2}[,.][0-9]{1,2})\s*\)")


def ler_pdf(caminho, nome=None, disciplinas=None, max_paginas=40):
    """Lê um PDF que pode conter MAIS DE UMA prova dentro (lote com várias
    frentes/professores concatenados — comum em arquivos de "2ª chamada",
    onde cada frente vira um PDF só). Por isso, além dos campos "de todo o
    arquivo" (texto, valores_q, cab da 1ª página — mantidos por
    compatibilidade), também monta `segmentos`: um por cabeçalho de prova
    encontrado, com seu próprio texto/linhas/valores/cab — usado para não
    misturar a contagem de questões e o valor de uma frente com o de outra
    dentro do mesmo arquivo."""
    nome = nome or caminho.split("/")[-1]
    out = {
        "nome": nome, "texto": "", "paginas": None, "erro": None, "cab": None,
        "do_nome": parse_filename(nome, disciplinas), "linhas": [], "outros_cab": [],
        "valores_q": [], "paginas_fp": [], "origem": "indefinida", "origem_como": "",
        "segmentos": [],
    }
    out["hash"] = hash_arquivo(caminho)
    try:
        with pdfplumber.open(caminho) as pdf:
            out["paginas"] = len(pdf.pages)
            limite = min(len(pdf.pages), max_paginas)
            partes = []
            paginas_textos = []
            paginas_linhas = []
            cabecalhos = []  # {"pagina": 1-based, "cab": dict} — todo cabeçalho de prova achado
            for p in range(limite):
                page = pdf.pages[p]
                cab_pag = parse_header(page, disciplinas=disciplinas)
                linhas_h, linhas_g, _, _ = extract_lines(page)
                # página inteira rotacionada (ex.: tabela periódica impressa
                # de cabeça pra baixo) sai inteira como texto "girado", e sem
                # isso ficava de fora do texto do arquivo — nunca detectada.
                textos = [l["texto"] for l in linhas_h] + [
                    l["texto"] for l in linhas_g if len(l["texto"].strip()) > 3
                ]
                paginas_textos.append(textos)
                paginas_linhas.append(textos)
                partes.append(" ".join(textos))
                out["linhas"].extend(textos)
                for m in QVALOR_RE.finditer(" ".join(textos)):
                    try:
                        out["valores_q"].append(float(m.group(1).replace(",", ".")))
                    except ValueError:
                        pass
                fp = fp_pagina(textos)
                if fp:
                    out["paginas_fp"].append({"pagina": p + 1, "fp": fp})
                if p == 0:
                    out["cab"] = cab_pag
                    cabecalhos.append({"pagina": 1, "cab": cab_pag})
                    if not linhas_h:
                        out["erro"] = "PDF sem texto na 1ª página (parece digitalizado — precisaria de OCR)"
                else:
                    marcados = sum(1 for k in ("professor", "aluno", "nota", "valor") if cab_pag["blocos"].get(k))
                    # sinal de "página com cabeçalho de prova nova": ou tem
                    # natureza/código reconhecido junto com 2+ blocos, ou tem
                    # 3+ dos 4 blocos estruturais (professor/aluno/nota/valor)
                    # sozinho — isso cobre o caso real de arquivos com várias
                    # frentes concatenadas cujo título vem sem espaço entre
                    # palavras ("2ªCHAMADA DEQUÍMICA") e por isso não bate com
                    # nenhum token de natureza, mas o cabeçalho (caixas de
                    # professor/aluno/valor/nota) claramente recomeça ali.
                    eh_novo_cabecalho = (
                        ((cab_pag["natureza"] or cab_pag["codigo"]) and marcados >= 2)
                        or marcados >= 3
                    )
                    if eh_novo_cabecalho:
                        cabecalhos.append({"pagina": p + 1, "cab": cab_pag})
                        if p < 7:
                            out["outros_cab"].append({
                                "pagina": p + 1, "titulo": cab_pag["titulo"], "natureza": cab_pag["natureza"],
                                "disciplina": cab_pag["disciplina"], "etapa": cab_pag["etapa"], "serie": cab_pag["serie"],
                            })
            out["texto"] = "\n".join(partes)

            # monta os segmentos: um por cabeçalho encontrado, cobrindo até a
            # página anterior ao próximo cabeçalho (ou o fim do arquivo).
            for i, h in enumerate(cabecalhos):
                ini = h["pagina"]
                fim = cabecalhos[i + 1]["pagina"] - 1 if i + 1 < len(cabecalhos) else limite
                idxs = range(ini - 1, fim)
                seg_linhas = [t for i2 in idxs for t in paginas_linhas[i2]]
                seg_texto = "\n".join(" ".join(paginas_textos[i2]) for i2 in idxs)
                seg_valores = []
                for i2 in idxs:
                    for m in QVALOR_RE.finditer(" ".join(paginas_textos[i2])):
                        try:
                            seg_valores.append(float(m.group(1).replace(",", ".")))
                        except ValueError:
                            pass
                out["segmentos"].append({
                    "pagina_ini": ini, "pagina_fim": fim, "cab": h["cab"],
                    "texto": seg_texto, "linhas": seg_linhas, "valores_q": seg_valores,
                })
    except Exception as e:  # noqa: BLE001
        out["erro"] = f"falha ao abrir: {e}"

    if not out["erro"] and not out["texto"].strip():
        out["erro"] = "PDF sem texto (parece digitalizado — precisaria de OCR)"

    tU = normU(out["texto"])
    tem_bern = bool(re.search(r"BERNOULLI\s*EDUCA[CÇ][AÃ]O", tU))
    tem_mod = bool(re.search(r"\bMODULO\b", tU))
    if tem_bern and not tem_mod:
        out["origem"], out["origem_como"] = "bernoulli", "rodapé Bernoulli encontrado no texto"
    elif tem_mod and not tem_bern:
        out["origem"], out["origem_como"] = "modulo", "a palavra Módulo aparece no texto"
    elif tem_bern and tem_mod:
        out["origem"], out["origem_como"] = "bernoulli", "rodapé Bernoulli encontrado no texto"
    else:
        out["origem"], out["origem_como"] = "indefinida", "não achei nem o rodapé Bernoulli nem a palavra Módulo no texto"

    return out
