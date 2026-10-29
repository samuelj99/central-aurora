# Central de Crédito e Cobrança — Distribuidora Aurora

Projeto feito a partir de um exercício (dados fictícios) da Hashtag: cinco telas de
gestão de crédito e cobrança para uma distribuidora de alimentos e bebidas que vende a
prazo, geradas a partir de uma única planilha e embutidas num **único arquivo HTML**,
sem backend obrigatório e sem internet.

## Telas

| Tela | Pergunta que responde |
|---|---|
| Hoje | Quem eu ligo primeiro? |
| Risco por cliente | Onde está o meu dinheiro em risco? |
| Previsão de caixa | Quanto entra nas próximas 4 semanas, e em qual semana? |
| Régua de cobrança | Que texto mando, com que tom? |
| Relatório da semana | Texto corrido para a diretoria |

## Como rodar

```bash
pip install pandas numpy openpyxl
python servidor.py        # abre http://localhost:8842/Central_Aurora.html
```

Ou apenas abra `Central_Aurora.html` direto no navegador (duplo clique) — funciona
offline, só sem o botão "Registrar cobrança", que precisa do servidor para gravar.

## Como foi feito

Todas as contas (atraso, risco, previsão, tom de cobrança) ficam centralizadas em
`aurora_calc.py` e nos scripts `build_*.py`; as telas (`app/`) só leem os dados já
calculados. `build_app.py` monta o arquivo único final. Mais detalhes de arquitetura,
decisões de negócio e checagens de qualidade (`conferencia.py`,
`auditoria_navegador.py`) em [CLAUDE.md](CLAUDE.md).

Dados fictícios, criados para fins de exercício.
