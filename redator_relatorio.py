"""
Motor de redação do Relatório da semana -- único ponto que transforma os
números já calculados (nunca recalculados aqui) em texto corrido para a
diretoria. No dia de trocar a redação por um modelo de IA, é esta função,
montar_relatorio(), o único lugar a trocar.

Lê exclusivamente os exports já prontos de cada tela (dados_hoje.json,
dados_risco.json, dados_previsao.json) e o registro de cobranças. A única
conta feita aqui que não mora em nenhuma tela ainda é "o que entrou/não
entrou na última semana" -- e ela não é calculada aqui: está em
aurora_calc.calcular_semana_passada(), o lugar combinado onde esse tipo de
número mora, só chamada daqui.
"""

import json
from pathlib import Path

import aurora_calc as ac

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")


def _ler(pasta: Path, nome: str) -> dict:
    caminho = pasta / nome
    if not caminho.exists():
        raise FileNotFoundError(
            f"{nome} não existe ainda -- rode as telas (build_central.py, build_risco.py, "
            f"build_previsao.py, build_regua.py) antes de gerar o relatório."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def numeros_da_semana() -> dict:
    """Os números da última semana (os mesmos que o texto usa), para a tela mostrar em destaque
    sem refazer a conta: quem calcula é aurora_calc.calcular_semana_passada()."""
    data_base = ac.ler_data_referencia(XLSX_PATH)
    _clientes, titulos, _cobrancas = ac.carregar_base(XLSX_PATH)
    semana = ac.calcular_semana_passada(titulos, data_base)
    return {
        "inicio": semana["inicio"].strftime("%d/%m"), "fim": semana["fim"].strftime("%d/%m"),
        "entrou_centavos": semana["entrou_centavos"], "previsto_centavos": semana["previsto_centavos"],
        "nao_entrou_do_previsto_centavos": semana["nao_entrou_do_previsto_centavos"],
        "qtd_previsto": semana["qtd_previsto"], "qtd_pago": semana["qtd_pago"],
    }


def montar_relatorio(pasta: Path) -> str:
    hoje = _ler(pasta, "dados_hoje.json")
    risco = _ler(pasta, "dados_risco.json")
    previsao = _ler(pasta, "dados_previsao.json")
    regua = _ler(pasta, "dados_regua.json")

    data_base = ac.ler_data_referencia(XLSX_PATH)
    _clientes, titulos, _cobrancas = ac.carregar_base(XLSX_PATH)
    semana = ac.calcular_semana_passada(titulos, data_base)

    def R(centavos):
        return "R$ " + ac.fmt_reais(centavos)

    linhas = []
    linhas.append(f"RELATÓRIO DA SEMANA — DISTRIBUIDORA AURORA")
    linhas.append(f"Dados de referência: {hoje['resumo']['data_base']}.")
    linhas.append("")

    # ---- última semana: o que entrou, o que não ----
    if semana["qtd_previsto"] > 0:
        linhas.append(
            f"Na última semana (de {semana['inicio'].strftime('%d/%m')} a {semana['fim'].strftime('%d/%m')}), "
            f"entrou {R(semana['entrou_centavos'])} no caixa, somando pagamento de título novo e de título mais "
            f"antigo. Dos {R(semana['previsto_centavos'])} que venceram justamente nessa janela, "
            f"{R(semana['nao_entrou_do_previsto_centavos'])} ainda não foram pagos."
        )
    else:
        linhas.append("Não havia título vencendo na última semana para comparar entrada contra previsto.")
    linhas.append("")

    # ---- situação hoje ----
    rh = hoje["resumo"]
    linhas.append(
        f"Hoje, {R(rh['total_vencido_centavos'])} estão vencidos "
        f"em {rh['qtd_titulos_vencidos']} títulos, espalhados por {rh['clientes_na_fila']} dos "
        f"{rh['total_clientes_base']} clientes da carteira. Outros {R(rh['total_a_vencer_centavos'])} ainda "
        f"não venceram."
    )
    linhas.append("")

    # ---- onde está o risco ----
    clientes_risco = sorted(risco["clientes"].items(), key=lambda kv: kv[1]["valor_em_risco_centavos"], reverse=True)
    top_risco = [c for _, c in clientes_risco if c["valor_em_risco_centavos"] > 0][:3]
    if top_risco:
        partes = []
        for c in top_risco:
            motivo = ""
            if "deteriorou" in c["casos_especiais"]:
                motivo = "piorou de comportamento recentemente"
            elif "comprando_menos" in c["casos_especiais"]:
                motivo = "parou de comprar"
            elif "falso_positivo_cronico" in c["casos_especiais"]:
                motivo = "atraso crônico, mas de baixo risco real"
            else:
                motivo = f"índice de risco {c['indice_risco']}"
            partes.append(f"{c['nome']} ({R(c['valor_em_risco_centavos'])}, {motivo})")
        linhas.append(
            f"Em risco (saldo em aberto ponderado pelo índice de cada cliente), soma "
            f"{R(risco['resumo']['valor_em_risco_total_centavos'])} na carteira toda. Concentrado em: "
            + "; ".join(partes) + "."
        )
    else:
        linhas.append("Nenhum cliente com valor em risco relevante esta semana.")
    linhas.append("")

    # ---- próximas semanas ----
    rp = previsao["resumo"]
    primeira = previsao["semanas"][0]
    if abs(rp["diferenca_pct"] or 0) < 1:
        # mesmo critério da tela Previsão: no total quase empata, o erro está no QUANDO
        pior = max(previsao["semanas"], key=lambda s_: abs(s_["diferenca_centavos"]))
        if pior["diferenca_centavos"] >= 0:
            erro = f"promete {R(pior['diferenca_centavos'])} a mais do que deve entrar"
        else:
            erro = f"deixa de contar {R(-pior['diferenca_centavos'])} que deve entrar"
        linhas.append(
            f"Para as próximas 4 semanas (até {rp['horizonte_fim']}), a leitura do comportamento de cada cliente "
            f"projeta {R(rp['esperado_centavos'])} de entrada, praticamente o mesmo que uma soma simples por "
            f"vencimento mostraria ({R(rp['planilha_centavos'])}). O erro da soma simples está em quando o dinheiro "
            f"entra: na semana de {pior['inicio']} a {pior['fim']} ela {erro}. Olhando só a primeira semana "
            f"({primeira['inicio']} a {primeira['fim']}), o esperado é {R(primeira['esperado_centavos'])}."
        )
    else:
        sinal = "a menos" if rp["diferenca_centavos"] >= 0 else "a mais"
        linhas.append(
            f"Para as próximas 4 semanas (até {rp['horizonte_fim']}), a leitura do comportamento de cada cliente "
            f"projeta {R(rp['esperado_centavos'])} de entrada — {R(abs(rp['diferenca_centavos']))} {sinal} do que uma "
            f"soma simples por vencimento mostraria ({R(rp['planilha_centavos'])}). Olhando só a primeira semana "
            f"({primeira['inicio']} a {primeira['fim']}), o esperado é {R(primeira['esperado_centavos'])}."
        )
    linhas.append("")

    # ---- decisão: o que fazer esta semana ----
    # Mesma ordem e mesmo número da fila da tela Hoje (valor vencido pesado pelo
    # risco), para a diretoria e a equipe falarem do "1" e do "2" sem confusão.
    # A ação é o tom que a Régua já sugeriu para o cliente -- não é escolhida de novo aqui.
    linhas.append("O QUE FAZER ESTA SEMANA, NA ORDEM DA FILA DE HOJE (VALOR VENCIDO PESADO PELO RISCO):")
    fila = hoje["fila"][:5]
    motivo_tier = {
        "inedito": "atraso que esse cliente nunca teve",
        "acima_normal": "atraso acima do normal dele",
        "dentro_padrao": "atraso dentro do padrão dele",
        "sem_historico": "sem histórico de pagamento para comparar",
    }
    if fila:
        for c in fila:
            motivo = motivo_tier[c["tier"]]
            if c["mudou_comportamento"]:
                motivo += "; o jeito de pagar dele mudou de verdade nos últimos meses"
            if c["contato_recente_48h"]:
                quando = "hoje" if c["dias_desde_contato"] == 0 else f"há {ac.fmt_dias(c['dias_desde_contato'])}"
                motivo += f"; já foi cobrado {quando}"
            acao = regua.get(str(c["codigo"]), {}).get("tom_label")
            linhas.append(
                f"{c['posicao']}. {c['nome']}: {R(c['valor_vencido_centavos'])} vencidos em "
                f"{c['qtd_vencidos']} {ac.plural(c['qtd_vencidos'], 'título', 'títulos')}, o mais antigo com "
                f"{ac.fmt_dias(c['dias_vencido_max'])} de atraso ({motivo})."
                + (f" Ação: contato com o tom \"{acao}\", já redigido na Régua de cobrança." if acao else "")
            )
    else:
        linhas.append("Nenhum cliente com título vencido hoje.")

    linhas.append("")
    linhas.append(
        "Este relatório não refaz nenhuma conta: lê os mesmos números das telas Hoje, Risco por cliente e "
        "Previsão de caixa, congelados na data de referência acima."
    )

    return "\n".join(linhas)
