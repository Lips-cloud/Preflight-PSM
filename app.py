import tempfile
from pathlib import Path

import streamlit as st

from pdf_read import ler_pdf, contar_questoes, DISCIPLINAS_PADRAO
from rules import conferir_cabecalhos, conferir_planilha, NOME_NAT, eh_quimica, eh_adaptado, TABELA_PERIODICA_RE, INFINITO, normU, checar_aba, tem_tabela_periodica_final
from abas import ABAS, parse_planilha, chave_conteudo_item

st.set_page_config(page_title="Preflight PSM", page_icon="🔎", layout="wide")

st.title("🔎 Preflight PSM")
st.caption(
    "Conferência de provas antes do envio — versão Python (protótipo). "
    "Fase 1: só bloqueia em 4 famílias de erro grave, o resto é aviso."
)

with st.expander("Como funciona", expanded=False):
    st.markdown(
        "**Passo 1** — cole (opcional) o recorte da planilha, uma linha por prova, "
        "colunas separadas por TAB (copiado direto do Excel/Sheets), na mesma ordem "
        "da planilha Controle: `Descrição · Série · ID Adaptações Colégio · Disciplina · "
        "Frente · Professor · Qtd. Discursivas · Valor Discursivas · Qtd. Objetivas · "
        "Valor Objetivas`. Linhas duplicadas só por causa da coluna de adaptação "
        "(código EN/AD) são reconhecidas como a mesma prova, não contam em dobro.\n\n"
        "**Passo 2** — envie os PDFs.\n\n"
        "**Passo 3** — resultado: só aparece o que está ERRADO nas 4 famílias "
        "graves (série/tipo de outro conteúdo, arquivo/página reaproveitado, "
        "tipo de prova errado no lote, conteúdo faltando). O resto é aviso."
    )

st.subheader("Passo 1 — qual aba do Controle e a planilha (opcional)")
st.caption(
    "Cada aba do Controle tem as colunas em ORDEM DIFERENTE — escolha a aba antes "
    "de colar, senão a colagem sem cabeçalho cai nas colunas erradas."
)
nome_aba = st.selectbox("Aba do Controle", [a["nome"] for a in ABAS], index=0)
aba = next(a for a in ABAS if a["nome"] == nome_aba)

texto_planilha = st.text_area(
    "Cole aqui as linhas da planilha (com TAB entre colunas, igual copiado do Excel/Sheets)",
    height=120,
    disabled=not aba["colunas"],
    placeholder="(selecione a aba acima primeiro)" if not aba["colunas"] else "",
)
if aba["colunas"]:
    rotulos = {
        "descricao": "Descrição", "serie": "Série", "adaptacoes": "ID Adaptações",
        "disciplina": "Disciplina", "frente": "Frente", "professor": "Professor",
        "qDisc": "Qtd. Discursivas", "vDisc": "Valor Discursivas",
        "qObj": "Qtd. Objetivas", "vObj": "Valor Objetivas", "turno": "Turno",
    }
    ordem = " · ".join(rotulos.get(c, "(ignorar)") for c in aba["colunas"])
    st.caption(f"Ordem de colunas desta aba: {ordem}")

itens_brutos = parse_planilha(texto_planilha, aba) if aba["colunas"] else []
vistos = set()
itens = []
duplicadas = 0
for it in itens_brutos:
    k = chave_conteudo_item(it)
    if k in vistos:
        duplicadas += 1
        continue
    vistos.add(k)
    itens.append(it)

if itens_brutos:
    msg = f"{len(itens_brutos)} linha(s) coladas, {len(itens)} prova(s) única(s) reconhecida(s)."
    if duplicadas:
        msg += f" ({duplicadas} linha(s) descartada(s) por serem cópia da mesma prova — código de adaptação EN/AD.)"
    st.caption(msg)

alertas_aba_planilha = checar_aba(aba.get("id"), itens=itens) if itens else []
for al in alertas_aba_planilha:
    st.error(f"🚫 {al['msg']}")
    if al.get("det"):
        st.caption(al["det"])

st.subheader("Passo 2 — PDFs")
arquivos = st.file_uploader("Arraste os PDFs aqui", type=["pdf"], accept_multiple_files=True)

if arquivos:
    with tempfile.TemporaryDirectory() as tmp:
        pdfs = []
        with st.spinner("Lendo PDFs..."):
            for up in arquivos:
                caminho = Path(tmp) / up.name
                caminho.write_bytes(up.getbuffer())
                pdfs.append(ler_pdf(str(caminho), nome=up.name, disciplinas=DISCIPLINAS_PADRAO))

        st.subheader("Passo 3 — o que está errado")

        alertas_aba_pdf = checar_aba(aba.get("id"), pdfs=pdfs)

        cab_res = conferir_cabecalhos(pdfs)
        graves_por_pdf = {nome: r["graves"] for nome, r in cab_res.items()}
        avisos_por_pdf = {nome: r["avisos"] for nome, r in cab_res.items()}

        plan_res = []
        if itens:
            plan_res = conferir_planilha(itens, pdfs, lambda pdf: contar_questoes(pdf["texto"], pdf["linhas"]))
            for r in plan_res:
                if r["pdf"]:
                    graves_por_pdf.setdefault(r["pdf"]["nome"], []).extend(r["graves"])
                    avisos_por_pdf.setdefault(r["pdf"]["nome"], []).extend(r["avisos"])

        n_graves = sum(len(g) for g in graves_por_pdf.values())
        sem_pdf = [r for r in plan_res if not r["pdf"]]
        n_graves += sum(len(r["graves"]) for r in sem_pdf)  # PL-SEMPDF: prova faltando no lote, é grave
        n_graves += len(alertas_aba_planilha) + len(alertas_aba_pdf)

        if alertas_aba_planilha or alertas_aba_pdf:
            st.markdown("#### Aba do Controle")
            for al in alertas_aba_planilha + alertas_aba_pdf:
                st.markdown(f"- 🚫 **{al['msg']}**")
                if al.get("det"):
                    st.caption(al["det"])

        if n_graves:
            st.error(f"❌ NÃO ENVIE. {n_graves} problema(s) grave(s) neste lote.")
        elif any(avisos_por_pdf.values()):
            st.warning("⚠️ Nada grave. Só pontos a confirmar.")
        else:
            st.success("✅ Pode enviar. Tudo confere.")

        st.markdown("#### Erros graves")
        algum_grave = False
        for pdf in pdfs:
            graves = graves_por_pdf.get(pdf["nome"], [])
            if not graves:
                continue
            algum_grave = True
            with st.container(border=True):
                st.markdown(f"**{pdf['nome']}** `{pdf.get('origem','indefinida')}`")
                for g in graves:
                    st.markdown(f"- 🔴 **{g['msg']}**")
                    if g.get("det"):
                        st.caption(g["det"])
        if sem_pdf:
            algum_grave = True
            with st.container(border=True):
                st.markdown("**Linhas da planilha sem PDF correspondente**")
                for r in sem_pdf:
                    it = r["item"]
                    desc = " · ".join(str(x) for x in [it.get("disciplina") or "?", it.get("serie") or "?", it.get("frente") or "", it.get("professor") or ""] if x)
                    for g in r["graves"]:
                        st.markdown(f"- 🔴 **{g['msg']}** — {desc}")
        if not algum_grave:
            st.caption("Nenhum erro grave encontrado.")

        st.markdown("#### Itens extras verificados")
        algum_check = False
        for pdf in pdfs:
            checks = []
            c = pdf.get("cab") or {}
            if eh_quimica(c, pdf.get("do_nome")):
                achou = tem_tabela_periodica_final(pdf)
                checks.append(("Tabela periódica (últimas páginas)", achou))
            if eh_adaptado(pdf["nome"]):
                achou = INFINITO in (pdf.get("texto") or "")
                checks.append(("Símbolo ∞ de prova adaptada", achou))
            if not checks:
                continue
            algum_check = True
            with st.container(border=True):
                st.markdown(f"**{pdf['nome']}**")
                for label, ok in checks:
                    st.markdown(f"- {'✅' if ok else '🔴'} {label}: {'encontrado' if ok else 'NÃO encontrado'}")
        if not algum_check:
            st.caption("Nenhum item extra a verificar neste lote (sem Química nem prova adaptada).")

        st.markdown("#### Confira antes de enviar (avisos)")
        algum_aviso = False
        for pdf in pdfs:
            avisos = avisos_por_pdf.get(pdf["nome"], [])
            if not avisos:
                continue
            algum_aviso = True
            with st.container(border=True):
                st.markdown(f"**{pdf['nome']}**")
                for a in avisos:
                    st.markdown(f"- 🟡 {a['msg']}")
                    if a.get("det"):
                        st.caption(a["det"])
        if not algum_aviso:
            st.caption("Nenhum aviso.")

        with st.expander("Ver cabeçalho lido de cada arquivo"):
            for pdf in pdfs:
                st.markdown(f"**{pdf['nome']}**")
                st.json(pdf.get("cab") or {})
else:
    st.info("Envie um ou mais PDFs para começar.")
