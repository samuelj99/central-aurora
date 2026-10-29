"""
Calcula a tela "Risco por cliente" a partir de Base_bruta.xlsx (a tela é montada por build_app.py).

Não mexe na fila da tela Hoje. Lê a mesma planilha e usa o comportamento
de pagamento já calculado em aurora_calc.py (média, desvio, sazonalidade,
mudança de comportamento -- o MESMO número usado pela tela Hoje e pela Previsão
de caixa). Aqui só é calculado o que é específico desta tela: atividade de
compra, concentração de faturamento, ocupação de limite e o índice de risco
0-100 com pesos explícitos e justificados.

Também exporta dados_risco.json -- um resumo compacto por cliente (índice de
risco, saldo em aberto, casos especiais) que a tela Previsão de caixa lê, para
não recalcular o índice por conta própria.

Uso:
    python build_risco.py
"""

import json
from pathlib import Path

import pandas as pd

import aurora_calc as ac

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
JSON_EXPORT_PATH = Path(__file__).parent / "dados_risco.json"

# ---------------------------------------------------------------------------
# Parâmetros específicos desta tela (decisões assumidas -- documentadas no relatório)
# ---------------------------------------------------------------------------
JANELA_TRIMESTRES_COMPRA = 2      # trimestres completos p/ comparar ritmo de compra (recente x anterior)

TETO_MEDIA_ATRASO = 35            # dias -- média histórica que já satura o componente "nível" (25 pts)
TETO_DESVIO_ATRASO = 12           # dias -- desvio que já satura o componente "imprevisibilidade" (20 pts)
TETO_SHARE_FATURAMENTO = 25       # % do faturamento 12m que já satura a metade de "exposição"
TETO_OCUPACAO_LIMITE = 100        # % do limite ocupado que já satura a outra metade de "exposição"

PESOS = {"nivel": 25, "imprevisibilidade": 20, "mudanca": 25, "compra": 15, "exposicao": 15}

NOME_MES = ac.NOME_MES


TOM_DO_CASO = {
    "deteriorou": "Piorou de verdade",
    "comprando_menos": "Parou de comprar",
    "falso_positivo_cronico": "Aparece vencido, não é risco",
    "sazonal": "Padrão sazonal",
    "caro_silencioso": "Caro e silencioso",
}
PRIORIDADE_DESCOBERTAS = ["deteriorou", "comprando_menos", "falso_positivo_cronico", "caro_silencioso", "sazonal"]


def nivel_do_indice(indice: int) -> str:
    """Mesmos cortes que a tela já usava para pintar o índice (60 e 30), agora com nome."""
    return "alto" if indice >= 60 else ("medio" if indice >= 30 else "baixo")


def alerta_curto(c: dict) -> str:
    """Uma ou duas frases: o mesmo conteúdo do alerta por extenso (que continua na ficha), só mais curto."""
    casos = c["casos_especiais"]
    if "comprando_menos" in casos:
        return (f"Pedidos caíram {c['queda_compra_pct']:.0f}% e faz {ac.fmt_dias(c['dias_desde_pedido'])} sem pedido. "
                f"Converse antes de cobrar.")
    if "deteriorou" in casos:
        return (f"Pagava em {c['media_antiga']:.0f} dias e agora leva {c['media_recente']:.0f}. "
                f"Ligue antes de liberar novo pedido.")
    if "falso_positivo_cronico" in casos:
        return (f"Paga sempre em {c['media_atraso']:.0f} dias, sem exceção: não é risco. "
                f"Vale ajustar o prazo do contrato ({c['prazo_contratado_dias']} dias).")
    if "caro_silencioso" in casos:
        return "Nunca atrasou, mas paga cada vez mais tarde e pesa muito no faturamento. Contato comercial preventivo."
    if "sazonal" in casos:
        meses = " e ".join(NOME_MES[m] for m in c["meses_sazonais"])
        return f"O atraso sobe todo ano em {meses} e volta ao normal: é o calendário dele, não piora."
    if c["indice_risco"] >= 40 and c["media_atraso"] is not None:
        return "Sem gatilho específico, mas o atraso é alto e pouco previsível. Vale acompanhar de perto."
    return "Sem sinal de risco relevante: atraso e compras dentro do padrão dele."


def montar_descobertas(clientes: list) -> list:
    """Até três achados, um por tipo de caso, na ordem de prioridade; dentro do tipo, o maior valor em risco.
    É só uma seleção do que a tela Risco já conclui -- nenhuma conta nova."""
    achados = []
    for tipo in PRIORIDADE_DESCOBERTAS:
        candidatos = [c for c in clientes if tipo in c["casos_especiais"]]
        if not candidatos:
            continue
        c = max(candidatos, key=lambda x: x["valor_em_risco_centavos"])
        if tipo == "deteriorou":
            chave, rotulo = f"{c['media_antiga']:.0f} → {c['media_recente']:.0f} dias", "atraso médio, antes e agora"
            frase = f"{c['nome']}: ligar antes de liberar novo pedido."
        elif tipo == "comprando_menos":
            chave, rotulo = ac.fmt_dias(c["dias_desde_pedido"]), "sem fazer pedido"
            frase = f"{c['nome']}: conversar antes de cobrar."
        elif tipo == "falso_positivo_cronico":
            chave, rotulo = f"{c['media_atraso']:.0f} dias", f"prazo real; o contrato diz {c['prazo_contratado_dias']}"
            frase = f"{c['nome']}: ajustar o prazo do contrato em vez de cobrar."
        elif tipo == "caro_silencioso":
            chave, rotulo = f"{ac.fmt_dec(c['share_faturamento_12m'])}%", "do faturamento, pagando mais tarde"
            frase = f"{c['nome']}: contato comercial preventivo."
        else:
            chave, rotulo = " e ".join(NOME_MES[m] for m in c["meses_sazonais"]), "meses em que atrasa todo ano"
            frase = f"{c['nome']}: é o calendário dele, não piora."
        achados.append({"tipo": tipo, "tipo_rotulo": TOM_DO_CASO[tipo], "codigo": c["codigo"], "nome": c["nome"],
                        "frase": frase, "chave": chave, "chave_rotulo": rotulo})
        if len(achados) == 3:
            break
    return achados


def main():
    data_base = ac.ler_data_referencia(XLSX_PATH)
    clientes, titulos, _cobrancas = ac.carregar_base(XLSX_PATH)
    comportamento = ac.calcular_comportamento_clientes(clientes, titulos, data_base)

    nomes = clientes.set_index("Código do cliente")["Nome do cliente"].to_dict()
    categorias = clientes.set_index("Código do cliente")["Categoria"].to_dict()
    regioes = clientes.set_index("Código do cliente")["Região"].to_dict()
    prazos_contratados = clientes.set_index("Código do cliente")["Prazo em dias"].to_dict()
    limites = clientes.set_index("Código do cliente")["limite_centavos"].to_dict()
    desde = clientes.set_index("Código do cliente")["Cliente desde"].to_dict()

    aberto = titulos[titulos["Data de pagamento"].isna()].copy()
    aberto["dias_vencido"] = (data_base - aberto["Data de vencimento"]).dt.days

    ult12m = titulos[titulos["Data de emissão"] >= data_base - pd.Timedelta(days=365)]
    faturamento_total_12m = int(ult12m["valor_centavos"].sum())

    # Para o gráfico de compras: só considera trimestres fechados (não o corrente, parcial)
    inicio_trimestre_atual = pd.Timestamp(data_base.year, ((data_base.month - 1) // 3) * 3 + 1, 1)

    clientes_out = []
    for cod in sorted(clientes["Código do cliente"].unique()):
        nome = nomes[cod]
        comp = comportamento[cod]
        n_pagos = comp["n_titulos_pagos"]
        n_pagos_uteis = comp["n_titulos_pagos_uteis"]
        media_atraso = comp["media_atraso"]
        desvio_atraso = comp["desvio_atraso"]
        min_atraso = comp["min_atraso"]
        max_atraso = comp["max_atraso"]
        meses_sazonais = comp["meses_sazonais"]
        mudou_forte = comp["mudou_forte"]
        media_antiga = comp["media_antiga"]
        media_recente = comp["media_recente"]
        delta_forte = comp["delta_forte"]
        leve_delta = comp["leve_delta"]
        leve_n_meses = comp["leve_n_meses"]

        # --- atividade de compra ---
        t_cli = titulos[titulos["Código do cliente"] == cod].sort_values("Data de emissão")
        ultimo_pedido = t_cli["Data de emissão"].max()
        dias_desde_pedido = int((data_base - ultimo_pedido).days)
        gaps = t_cli["Data de emissão"].diff().dt.days.dropna()
        gap_tipico = float(gaps.mean()) if len(gaps) >= 3 else None

        t_fechados = t_cli[t_cli["Data de emissão"] < inicio_trimestre_atual].copy()
        t_fechados["trimestre"] = t_fechados["Data de emissão"].dt.to_period("Q")
        qtd_por_tri = t_fechados.groupby("trimestre").size()
        queda_compra_pct = None
        if len(qtd_por_tri) >= JANELA_TRIMESTRES_COMPRA * 2:
            recentes = qtd_por_tri.iloc[-JANELA_TRIMESTRES_COMPRA:].sum()
            anteriores = qtd_por_tri.iloc[-JANELA_TRIMESTRES_COMPRA * 2:-JANELA_TRIMESTRES_COMPRA].sum()
            if anteriores > 0:
                queda_compra_pct = (1 - recentes / anteriores) * 100

        # --- exposição ---
        valor_12m = int(ult12m[ult12m["Código do cliente"] == cod]["valor_centavos"].sum())
        share_faturamento = (valor_12m / faturamento_total_12m * 100) if faturamento_total_12m else 0.0
        saldo_aberto = int(aberto[aberto["Código do cliente"] == cod]["valor_centavos"].sum())
        limite = int(limites[cod])
        ocupacao_limite = (saldo_aberto / limite * 100) if limite else None

        venc_cli = aberto[(aberto["Código do cliente"] == cod) & (aberto["Data de vencimento"] < data_base)]
        valor_vencido_hoje = int(venc_cli["valor_centavos"].sum())

        # ===================== ÍNDICE DE RISCO (0-100), por componente =====================
        componentes = []

        if media_atraso is None:
            pts_nivel = 0.0
            just_nivel = "Sem título pago suficiente na base para calcular o nível de atraso."
        else:
            pts_nivel = min(PESOS["nivel"], max(0.0, media_atraso) / TETO_MEDIA_ATRASO * PESOS["nivel"])
            prazo = int(prazos_contratados[cod])
            just_nivel = (
                f"Paga em média {ac.fmt_atraso(round(media_atraso))} "
                f"(prazo contratado: {'à vista' if prazo == 0 else ac.fmt_dias(prazo)})."
            )
        componentes.append({"chave": "nivel", "rotulo": "Nível de atraso", "peso": PESOS["nivel"],
                             "pontos": round(pts_nivel, 1), "frase": just_nivel})

        if desvio_atraso is None:
            pts_imprev = PESOS["imprevisibilidade"] * 0.4 if n_pagos_uteis <= 1 else 0.0
            just_imprev = "Histórico pago insuficiente para medir a dispersão do atraso com confiança."
        else:
            pts_imprev = min(PESOS["imprevisibilidade"], max(0.0, desvio_atraso) / TETO_DESVIO_ATRASO * PESOS["imprevisibilidade"])
            if desvio_atraso < 3:
                rotulo_previs = "é muito previsível — praticamente sempre no mesmo dia."
            elif desvio_atraso < 7:
                rotulo_previs = "tem previsibilidade moderada."
            else:
                rotulo_previs = "tem baixa previsibilidade — difícil saber em que dia o dinheiro cai."
            just_imprev = (
                f"O atraso varia cerca de {ac.fmt_dec(desvio_atraso)} dias para mais ou para menos da média "
                f"(o pagamento mais rápido foi {ac.fmt_atraso(min_atraso)}; o mais lento, "
                f"{ac.fmt_atraso(max_atraso)}) — {rotulo_previs}"
            )
        componentes.append({"chave": "imprevisibilidade", "rotulo": "Previsibilidade", "peso": PESOS["imprevisibilidade"],
                             "pontos": round(pts_imprev, 1), "frase": just_imprev})

        if mudou_forte:
            pts_mudanca = min(PESOS["mudanca"], 15 + max(0.0, (delta_forte - ac.LIMIAR_ABS_FORTE) * 0.5))
            just_mudanca = (
                f"Mudança real de comportamento: pagava em média {media_antiga:.0f} dias e passou a pagar em "
                f"{media_recente:.0f} dias nos títulos mais recentes — piora de {delta_forte:.0f} dias, "
                f"grande mesmo para o padrão de variação deste cliente."
            )
        elif leve_delta is not None and leve_delta > 1.0:
            pts_mudanca = min(10.0, leve_delta * 4)
            just_mudanca = (
                f"Sinal leve, não um alarme: comparando mês a mês com o mesmo mês do ano anterior "
                f"({leve_n_meses} meses comparáveis), o atraso médio subiu {ac.fmt_dec(leve_delta)} {'dia' if abs(leve_delta) < 2 else 'dias'} — "
                f"pequeno demais para disparar alerta, mas consistente."
            )
        else:
            pts_mudanca = 0.0
            if delta_forte is not None:
                just_mudanca = (
                    f"Sem mudança relevante: pagava em média {ac.fmt_atraso(round(media_antiga))} e, nos títulos "
                    f"dos últimos {ac.JANELA_TENDENCIA_DIAS} dias, {ac.fmt_atraso(round(media_recente))} — "
                    f"dentro da variação normal dele."
                )
            elif leve_delta is not None:
                just_mudanca = (
                    f"Sem mudança relevante ano a ano: comparando cada mês com o mesmo mês do ano anterior, o "
                    f"atraso médio mudou {ac.fmt_dec(leve_delta)} dia, em média."
                )
            else:
                just_mudanca = "Histórico insuficiente para avaliar tendência com confiança."
        if meses_sazonais:
            nomes_meses = ", ".join(NOME_MES[m] for m in meses_sazonais)
            just_mudanca += f" (meses de {nomes_meses} descontados da conta: é padrão sazonal dele, se repete todo ano.)"
        componentes.append({"chave": "mudanca", "rotulo": "Mudança de comportamento", "peso": PESOS["mudanca"],
                             "pontos": round(pts_mudanca, 1), "frase": just_mudanca})

        pts_compra = 0.0
        frases_compra = []
        if gap_tipico and gap_tipico > 0:
            razao_gap = dias_desde_pedido / gap_tipico
            if razao_gap > 1:
                pts_compra += min(9.0, max(0.0, razao_gap - 1) * 4.5)
            frases_compra.append(
                f"Último pedido há {ac.fmt_dias(dias_desde_pedido)} (intervalo típico dele: {ac.fmt_dias(round(gap_tipico))})."
            )
        else:
            frases_compra.append(f"Último pedido há {ac.fmt_dias(dias_desde_pedido)}.")
        if queda_compra_pct is not None:
            if queda_compra_pct > 0:
                pts_compra += min(6.0, max(0.0, queda_compra_pct) / 50 * 6)
            frases_compra.append(
                f"Nos últimos {JANELA_TRIMESTRES_COMPRA} trimestres fechados, o número de pedidos "
                + (f"caiu {queda_compra_pct:.0f}% frente aos {JANELA_TRIMESTRES_COMPRA} trimestres anteriores."
                   if round(queda_compra_pct) > 0 else
                   f"subiu {-queda_compra_pct:.0f}% frente aos {JANELA_TRIMESTRES_COMPRA} trimestres anteriores."
                   if round(queda_compra_pct) < 0 else
                   f"ficou igual ao dos {JANELA_TRIMESTRES_COMPRA} trimestres anteriores.")
            )
        else:
            frases_compra.append("Histórico de compra curto demais para comparar trimestres.")
        pts_compra = min(PESOS["compra"], pts_compra)
        componentes.append({"chave": "compra", "rotulo": "Atividade de compra", "peso": PESOS["compra"],
                             "pontos": round(pts_compra, 1), "frase": " ".join(frases_compra)})

        pts_exp = min(TETO_SHARE_FATURAMENTO and PESOS["exposicao"] / 2, share_faturamento / TETO_SHARE_FATURAMENTO * (PESOS["exposicao"] / 2))
        if ocupacao_limite is not None:
            pts_exp += min(PESOS["exposicao"] / 2, ocupacao_limite / TETO_OCUPACAO_LIMITE * (PESOS["exposicao"] / 2))
        pts_exp = min(PESOS["exposicao"], pts_exp)
        just_exp = (
            f"Representa {ac.fmt_dec(share_faturamento)}% do faturamento dos últimos 12 meses da Aurora"
            + (f" e já ocupa {ocupacao_limite:.0f}% do limite de crédito dele." if ocupacao_limite is not None else ".")
        )
        componentes.append({"chave": "exposicao", "rotulo": "Exposição", "peso": PESOS["exposicao"],
                             "pontos": round(pts_exp, 1), "frase": just_exp})

        indice = round(sum(c["pontos"] for c in componentes))
        indice = max(0, min(100, indice))

        valor_em_risco = round(saldo_aberto * indice / 100)

        # ===================== classificação / alerta por extenso =====================
        casos_especiais = []
        alerta_partes = []
        if (not mudou_forte) and desvio_atraso is not None and desvio_atraso <= 2.5 and media_atraso and media_atraso >= 10 and valor_vencido_hoje > 0:
            casos_especiais.append("falso_positivo_cronico")
            alerta_partes.append(
                f"Esse cliente aparece como vencido com frequência, mas não é risco: ele paga sempre com o mesmo "
                f"atraso, há muito tempo, sem exceção (desvio de só {ac.fmt_dec(desvio_atraso)} dia em {n_pagos_uteis} títulos). "
                f"O prazo contratado é de {prazos_contratados[cod]} dias, mas na prática ele paga "
                f"{ac.fmt_atraso(round(media_atraso))} — ele não está piorando nem falhando, só tem um prazo real diferente do "
                f"contrato. Não vale a pena gastar cobrança aqui; se quiser, ajuste o prazo contratado para refletir "
                f"a realidade."
            )
        if mudou_forte:
            casos_especiais.append("deteriorou")
            alerta_partes.append(
                f"Piora real e recente: pagava em média {media_antiga:.0f} dias e foi para {media_recente:.0f} dias "
                f"nos títulos mais novos. Ligar para entender o motivo antes de renovar limite ou liberar novo pedido."
            )
        if meses_sazonais:
            casos_especiais.append("sazonal")
            nomes_meses = " e ".join(NOME_MES[m] for m in meses_sazonais)
            alerta_partes.append(
                f"O atraso dele sobe todo ano em {nomes_meses} e volta ao normal depois — isso se repetiu em anos "
                f"diferentes, então é o calendário do negócio dele, não deterioração. Foi descontado da conta de "
                f"tendência acima."
            )
        if queda_compra_pct is not None and queda_compra_pct >= 50:
            casos_especiais.append("comprando_menos")
            alerta_partes.append(
                f"Alerta de atividade: pedidos caindo forte ({queda_compra_pct:.0f}% nos últimos "
                f"{JANELA_TRIMESTRES_COMPRA} trimestres) e último pedido há {dias_desde_pedido} dias, bem acima do "
                f"intervalo típico dele ({gap_tipico:.0f} dias). Antes de cobrar, vale um contato comercial para "
                f"entender se ele ainda está comprando da Aurora."
            )
        if (not mudou_forte) and valor_vencido_hoje == 0 and leve_delta is not None and leve_delta > 1.0 and share_faturamento >= 10:
            casos_especiais.append("caro_silencioso")
            alerta_partes.append(
                f"Esse cliente nunca deixou de pagar e não tem nenhum título vencido hoje, então não aparece em "
                f"lista nenhuma de cobrança. Mas é {ac.fmt_dec(share_faturamento)}% do faturamento da Aurora nos últimos 12 "
                f"meses (um dos maiores clientes da carteira) e, olhando mês a mês contra o mesmo mês do ano "
                f"passado, está pagando em média {ac.fmt_dec(leve_delta)} dia mais devagar — sinal pequeno demais para "
                f"disparar alarme sozinho, mas caro pelo tamanho do cliente. Vale um contato comercial preventivo, "
                f"não de cobrança."
            )
        if not alerta_partes:
            if indice >= 40 and media_atraso is not None:
                alerta_partes.append(
                    f"Nenhum padrão específico disparou alerta (não piorou, não é sazonal, compra normal), mas o "
                    f"índice é alto porque o atraso dele já é estruturalmente alto e pouco previsível: em média "
                    f"{media_atraso:.0f} dias, variando {desvio_atraso:.0f} dias para mais ou para menos. Vale "
                    f"acompanhar de perto mesmo sem um gatilho específico — é um cliente que naturalmente consome "
                    f"mais caixa e dá menos previsibilidade de quando o dinheiro entra."
                )
            else:
                alerta_partes.append(
                    "Sem sinal de risco relevante: atraso e ritmo de compra dentro do padrão dele, exposição controlada."
                )

        titulos_vencidos_detalhe = [
            {"numero": r["Número do título"], "valor_centavos": int(r["valor_centavos"]),
             "vencimento": r["Data de vencimento"].strftime("%d/%m/%Y"), "dias_vencido": int(r["dias_vencido"])}
            for _, r in venc_cli.sort_values("dias_vencido", ascending=False).iterrows()
        ]

        clientes_out.append({
            "codigo": int(cod), "nome": nome, "categoria": categorias[cod], "regiao": regioes[cod],
            "cliente_desde": desde[cod].strftime("%m/%Y"), "prazo_contratado_dias": int(prazos_contratados[cod]),
            "n_titulos_pagos": n_pagos, "n_titulos_pagos_uteis": n_pagos_uteis,
            "media_atraso": round(media_atraso, 1) if media_atraso is not None else None,
            "desvio_atraso": round(desvio_atraso, 1) if desvio_atraso is not None else None,
            "min_atraso": min_atraso, "max_atraso": max_atraso,
            "meses_sazonais": meses_sazonais,
            "mudou_forte": mudou_forte,
            "media_antiga": round(media_antiga, 1) if media_antiga is not None else None,
            "media_recente": round(media_recente, 1) if media_recente is not None else None,
            "leve_delta": round(leve_delta, 1) if leve_delta is not None else None,
            "ultimo_pedido": ultimo_pedido.strftime("%d/%m/%Y"),
            "dias_desde_pedido": dias_desde_pedido,
            "gap_tipico_dias": round(gap_tipico, 1) if gap_tipico is not None else None,
            "queda_compra_pct": round(queda_compra_pct, 1) if queda_compra_pct is not None else None,
            "share_faturamento_12m": round(share_faturamento, 1),
            "valor_12m_centavos": valor_12m,
            "saldo_aberto_centavos": saldo_aberto,
            "valor_vencido_hoje_centavos": valor_vencido_hoje,
            "limite_centavos": limite,
            "ocupacao_limite_pct": round(ocupacao_limite, 1) if ocupacao_limite is not None else None,
            "componentes": componentes,
            "indice_risco": indice,
            "valor_em_risco_centavos": valor_em_risco,
            "casos_especiais": casos_especiais,
            "alerta": " ".join(alerta_partes),
            "serie_mensal": comp["serie_mensal"],
        })

    clientes_out.sort(key=lambda c: c["valor_em_risco_centavos"], reverse=True)
    for i, c in enumerate(clientes_out, start=1):
        c["posicao"] = i
        c["nivel"] = nivel_do_indice(c["indice_risco"])
        c["alerta_curto"] = alerta_curto(c)

    resumo = {
        "data_base": data_base.strftime("%d/%m/%Y"),
        "total_clientes": len(clientes_out),
        "faturamento_total_12m_centavos": faturamento_total_12m,
        "saldo_aberto_total_centavos": int(aberto["valor_centavos"].sum()),
        "valor_em_risco_total_centavos": sum(c["valor_em_risco_centavos"] for c in clientes_out),
    }

    payload = {"resumo": resumo, "pesos": PESOS, "clientes": clientes_out, "descobertas": montar_descobertas(clientes_out)}

    # Exporta os fatos por cliente para as outras telas lerem (nunca recalcular):
    # Previsão de caixa usa índice_risco e saldo_aberto; Régua de cobrança e o
    # Relatório usam o resto (atividade de compra, exposição, casos especiais).
    _CAMPOS_EXPORTADOS = [
        "nome", "categoria", "regiao", "cliente_desde", "prazo_contratado_dias",
        "media_atraso", "desvio_atraso", "min_atraso", "max_atraso",
        "mudou_forte", "media_antiga", "media_recente",
        "ultimo_pedido", "dias_desde_pedido", "gap_tipico_dias", "queda_compra_pct",
        "share_faturamento_12m", "saldo_aberto_centavos", "valor_vencido_hoje_centavos",
        "limite_centavos", "ocupacao_limite_pct",
        "indice_risco", "valor_em_risco_centavos", "casos_especiais",
    ]
    export = {
        "data_base": resumo["data_base"],
        "resumo": resumo,
        "clientes": {
            str(c["codigo"]): {campo: c[campo] for campo in _CAMPOS_EXPORTADOS}
            for c in clientes_out
        },
    }
    JSON_EXPORT_PATH.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK -- {len(clientes_out)} clientes calculados (Risco).")
    print(f"OK -- {JSON_EXPORT_PATH} exportado para as outras telas.")
    for c in clientes_out:
        print(f"  {c['posicao']}. {c['nome']:30} índice={c['indice_risco']:3d}  valor_em_risco=R$ {c['valor_em_risco_centavos']/100:,.0f}  casos={c['casos_especiais']}")
    return payload


if __name__ == "__main__":
    main()
