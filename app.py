import tempfile
from pathlib import Path

import streamlit as st

from engine.pdf_read import ler_pdf, contar_questoes, DISCIPLINAS_PADRAO
from engine.rules import conferir_cabecalhos, conferir_planilha, NOME_NAT

st.set_page_config(page_title="Preflight PSM", page_icon="🔎", layout="wide")

st.title("🔎 Preflight PSM")
st.caption(
    "Conferência de provas antes do envio — versão Python (protótipo). "
    "Fase 1: só bloqueia em 4 famílias de erro grave, o resto é aviso."
)

with st.expander("Como funciona", expanded=False):
    st.markdown(
        "**Passo 1** — cole (opcional) o recorte da planilha, uma linha por prova, "
        "colunas separadas por TAB (copiado direto do Excel/Sheets): "
        "`Descrição  Série  Disciplina  Frente  Professor  QtdDiscursivas  ValorDiscursivas  QtdObjetivas  ValorObjetivas`\n\n"
        "**Passo 2** — envie os PDFs.\n\n"
        "**Passo 3** — resultado: só aparece o que está ERRADO nas 4 famílias "
        "graves (série/tipo de outro conteúdo, arquivo/página reaproveitado, "
        "tipo de prova errado no lote, conteúdo faltando). O resto é aviso."
    )

st.subheader("Passo 1 — planilha (opcional)")
texto_planilha = st.text_area(
    "Cole aqui as linhas da planilha (com TAB entre colunas)", height=120,
    placeholder="A2\t1º Ano\tMatemática\t\tFulano de Tal\t2\t3,0\t\t",
)


def parse_planilha(texto):
    itens = []
    for linha in texto.strip().splitlines():
        if not linha.strip():
            continue
        cols = linha.split("\t")
        cols += [""] * (9 - len(cols))
        descricao, serie, disciplina, frente, professor, qdisc, vdisc, qobj, vobj = cols[:9]

        def numf(s):
            s = (s or "").strip().replace(",", ".")
            try:
                return float(s) if s else None
            except ValueError:
                return None

        itens.append({
            "descricao": descricao.strip(), "serie": serie.strip() or None,
            "disciplina": disciplina.strip() or None, "frente": frente.strip() or None,
            "professor": professor.strip() or None,
            "qDisc": numf(qdisc), "vDisc": numf(vdisc), "qObj": numf(qobj), "vObj": numf(vobj),
        })
    return itens


itens = parse_planilha(texto_planilha)
if itens:
    st.caption(f"{len(itens)} linha(s) reconhecida(s) da planilha.")

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
        n_graves += sum(len(r["avisos"]) for r in sem_pdf if False)  # PL-SEMPDF é aviso, não conta

        if n_graves:
            st.error(f"❌ NÃO ENVIE. {n_graves} problema(s) grave(s) neste lote.")
        elif any(avisos_por_pdf.values()) or sem_pdf:
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
        if not algum_grave:
            st.caption("Nenhum erro grave encontrado.")

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

        if sem_pdf:
            st.markdown("#### Linhas da planilha sem PDF correspondente (aviso)")
            for r in sem_pdf:
                st.markdown(f"- {r['item'].get('disciplina') or '?'} · {r['item'].get('serie') or '?'}")

        with st.expander("Ver cabeçalho lido de cada arquivo"):
            for pdf in pdfs:
                st.markdown(f"**{pdf['nome']}**")
                st.json(pdf.get("cab") or {})
else:
    st.info("Envie um ou mais PDFs para começar.")
