"""
Calcula a tela "Régua de cobrança" a partir de Base_bruta.xlsx (a tela é montada por build_app.py).

Candidatos: todo cliente com título vencido hoje (mesmo conjunto da tela Hoje)
MAIS todo cliente marcado em Risco por cliente como "comprando_menos" ou
"caro_silencioso" (mesmo sem título vencido -- esses merecem contato comercial,
não financeiro).

Esta tela não calcula nada de novo sobre o cliente: lê aurora_calc.py (mesmo
comportamento de Hoje/Risco/Previsão) e dados_risco.json (mesmo índice e
atividade de compra da tela Risco). A única coisa nova aqui é a escolha do
tom (aurora_calc.escolher_tom, determinística) e a montagem do texto, que
acontece em JavaScript no navegador -- para o usuário poder trocar o tom na
mão e ver o texto reescrito na hora, sem precisar gerar a tela de novo.

Uso:
    python build_risco.py     (gera dados_risco.json, se ainda não existir)
    python build_regua.py
"""

import json
from pathlib import Path

import pandas as pd

import aurora_calc as ac
from build_central import severidade

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
RISCO_JSON_PATH = Path(__file__).parent / "dados_risco.json"
HOJE_JSON_PATH = Path(__file__).parent / "dados_hoje.json"
JSON_EXPORT_PATH = Path(__file__).parent / "dados_regua.json"
REGISTROS_PATH = Path(__file__).parent / "registros_cobranca.json"


def primeiro_nome(nome_completo: str) -> str:
    return (nome_completo or "").strip().split(" ")[0] if nome_completo else "tudo bem"


def main():
    if not RISCO_JSON_PATH.exists():
        raise SystemExit(f"Não encontrei {RISCO_JSON_PATH}. Rode 'python build_risco.py' primeiro.")
    dados_risco = json.loads(RISCO_JSON_PATH.read_text(encoding="utf-8"))["clientes"]

    data_base = ac.ler_data_referencia(XLSX_PATH)
    clientes, titulos, cobrancas = ac.carregar_base(XLSX_PATH)
    comportamento = ac.calcular_comportamento_clientes(clientes, titulos, data_base)
    registros = ac.carregar_registros(REGISTROS_PATH)
    contatos_tabela = ac.combinar_cobrancas(cobrancas, registros)

    aberto = titulos[titulos["Data de pagamento"].isna()].copy()
    aberto["dias_vencido"] = (data_base - aberto["Data de vencimento"]).dt.days
    vencidos = aberto[aberto["Data de vencimento"] < data_base]

    nomes = clientes.set_index("Código do cliente")["Nome do cliente"].to_dict()
    categorias = clientes.set_index("Código do cliente")["Categoria"].to_dict()
    regioes = clientes.set_index("Código do cliente")["Região"].to_dict()
    contatos_nome = clientes.set_index("Código do cliente")["Contato"].to_dict()
    telefones = clientes.set_index("Código do cliente")["Telefone"].to_dict()

    cod_com_vencido = set(int(c) for c in vencidos["Código do cliente"].unique())
    cod_comercial = {
        int(cod) for cod, c in dados_risco.items()
        if set(c["casos_especiais"]) & {"comprando_menos", "caro_silencioso"}
    }
    candidatos = sorted(cod_com_vencido | cod_comercial)

    clientes_out = []
    for cod in candidatos:
        rc = dados_risco[str(cod)]
        comp = comportamento[cod]
        venc_cli = vencidos[vencidos["Código do cliente"] == cod]
        valor_vencido = int(venc_cli["valor_centavos"].sum())
        dias_vencido_max = int(venc_cli["dias_vencido"].max()) if len(venc_cli) else 0

        tier = ac.calcular_tier(dias_vencido_max if len(venc_cli) else -1, comp["media_atraso"], comp["max_atraso"])
        tom_id, justificativa = ac.escolher_tom(tier, comp["mudou_forte"], rc["casos_especiais"], rc["share_faturamento_12m"])

        hist_cliente = contatos_tabela[contatos_tabela["codigo_cliente"] == cod].sort_values("data_hora", ascending=False)
        historico = []
        for _, h in hist_cliente.iterrows():
            historico.append({
                "data_hora": h["data_hora"].strftime("%d/%m/%Y %H:%M"),
                "canal": h["canal"],
                "tom_label": h["tom_label"],
                "valor_cobrado_centavos": int(h["valor_cobrado_centavos"]) if pd.notna(h["valor_cobrado_centavos"]) else None,
                "origem": h["origem"],
                "texto": h["texto"] if isinstance(h["texto"], str) else None,
            })
        ultimo = historico[0] if historico else None
        dias_desde_ultimo_contato = None
        if ultimo:
            dt = hist_cliente.iloc[0]["data_hora"]
            dias_desde_ultimo_contato = int((data_base.normalize() - dt.normalize()).days)

        clientes_out.append({
            "codigo": cod, "nome": nomes[cod], "categoria": categorias[cod], "regiao": regioes[cod],
            "contato_nome": contatos_nome[cod], "contato_primeiro_nome": primeiro_nome(contatos_nome[cod]),
            "telefone": telefones[cod], "prazo_contratado_dias": rc["prazo_contratado_dias"],
            "titulos_vencidos": [
                {"numero": r["Número do título"], "valor_centavos": int(r["valor_centavos"]),
                 "vencimento": r["Data de vencimento"].strftime("%d/%m/%Y"), "dias_vencido": int(r["dias_vencido"])}
                for _, r in venc_cli.sort_values("dias_vencido", ascending=False).iterrows()
            ],
            "valor_vencido_centavos": valor_vencido,
            "tier": tier,
            "media_atraso": comp["media_atraso"], "desvio_atraso": comp["desvio_atraso"],
            "min_atraso": comp["min_atraso"], "max_atraso": comp["max_atraso"],
            "mudou_forte": comp["mudou_forte"], "media_antiga": comp["media_antiga"], "media_recente": comp["media_recente"],
            "indice_risco": rc["indice_risco"], "share_faturamento_12m": rc["share_faturamento_12m"],
            "dias_desde_pedido": rc["dias_desde_pedido"], "gap_tipico_dias": rc["gap_tipico_dias"],
            "queda_compra_pct": rc["queda_compra_pct"], "ultimo_pedido": rc["ultimo_pedido"],
            "casos_especiais": rc["casos_especiais"],
            "tom_sugerido": tom_id, "justificativa_tom": justificativa,
            "severidade": severidade(tier, comp["mudou_forte"]),
            "dias_desde_ultimo_contato": dias_desde_ultimo_contato,
            "historico_contatos": historico,
        })

    # Mesma ordem (e mesmo número) da fila da tela Hoje -- antes a Régua
    # ordenava por valor vencido e o "3" de uma tela era outro cliente na outra.
    # Quem está aqui só por motivo comercial (sem vencido) vem depois da fila.
    fila_hoje = json.loads(HOJE_JSON_PATH.read_text(encoding="utf-8"))["fila"]
    posicao_hoje = {r["codigo"]: r["posicao"] for r in fila_hoje}
    clientes_out.sort(key=lambda c: (posicao_hoje.get(c["codigo"], 10_000), -c["valor_vencido_centavos"]))
    for i, c in enumerate(clientes_out, start=1):
        c["posicao"] = i

    payload = {
        "data_base": data_base.strftime("%d/%m/%Y"),
        "tons": ac.TONS,
        "clientes": clientes_out,
    }


    # Exporta o tom sugerido de cada cliente para o Relatório da semana dizer
    # "o que fazer" com a MESMA decisão que a Régua mostra (não escolher de novo).
    export = {str(c["codigo"]): {"nome": c["nome"], "posicao": c["posicao"], "tom_sugerido": c["tom_sugerido"],
                                 "tom_label": ac.TONS[c["tom_sugerido"]]} for c in clientes_out}
    JSON_EXPORT_PATH.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -- {JSON_EXPORT_PATH.name} gerado. {len(clientes_out)} cliente(s) na régua.")
    for c in clientes_out:
        print(f"  {c['posicao']}. {c['nome']:30} tom sugerido: {ac.TONS[c['tom_sugerido']]}")
    return payload


if __name__ == "__main__":
    main()
