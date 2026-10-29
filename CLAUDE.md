# Central de Crédito e Cobrança — Distribuidora Aurora

Leia este arquivo inteiro antes de mexer em qualquer coisa. Ele existe para quem abre esta pasta
sem ter visto a conversa em que a Central foi construída (outra pessoa da equipe, ou uma conversa
nova do Claude).

## O que é

Cinco telas no navegador, **num arquivo só (`Central_Aurora.html`)**, que ajudam a equipe financeira da Aurora (distribuidora de alimentos e
bebidas que vende a prazo) a decidir **quem cobrar, como cobrar e quanto vai entrar no caixa**.
Tudo sai de uma única planilha entregue pela empresa, `Base_bruta.xlsx` (clientes, um título por
linha, contatos de cobrança já feitos).

| Tela | Endereço dentro do arquivo | Pergunta que responde |
|---|---|---|
| Hoje | `Central_Aurora.html#/hoje` | Quem eu ligo primeiro? |
| Risco por cliente | `#/risco` (`#/risco/3` abre a ficha do cliente 3) | Onde está o meu dinheiro em risco? |
| Previsão de caixa | `#/previsao` | Quanto entra nas próximas 4 semanas, e em qual semana? |
| Régua de cobrança | `#/regua` (`#/regua/11` abre o cliente 11) | Que texto mando, com que tom? E registro que cobrei. |
| Relatório da semana | `#/relatorio` | Texto corrido de 4 minutos para a diretoria. |

Dados fictícios, criados para um exercício (diz a aba Leia-me). A base atual tem 12 clientes,
754 títulos, de set/2024 a ago/2026.

## Regras que não podem mudar (e por quê)

1. **`Base_bruta.xlsx` nunca é alterada.** É o que veio da empresa. Nenhum script escreve nela;
   `conferencia.py` confere o hash dela. Cobranças registradas na Central vão para
   `registros_cobranca.json`, à parte.
2. **"Hoje" é a data de referência escrita na aba Leia-me da planilha, nunca o relógio do
   computador.** Com o relógio, os números mudariam sozinhos a cada dia e nada mais bateria.
   Vale também para os registros de cobrança: `aurora_calc.agora_na_base()` usa a data de
   referência com a hora real, senão a cobrança nasceria semanas depois da base e a regra das 48 horas
   nunca pegaria.
3. **Valores em centavos, como inteiro**, em todo o código. Só vira "R$" na hora de mostrar.
   Com casa decimal os totais fecham por sorte e um dia deixam de fechar.
4. **Uma conta só por assunto, em `aurora_calc.py`.** Média de atraso, desvio, sazonalidade,
   "mudou de comportamento", escolha do tom, última semana: tudo é calculado ali e as telas só
   leem. Já houve cliente com "mudou de comportamento" no Hoje e "não mudou" no Risco, porque
   cada tela tinha a própria regra. Se uma tela precisar de um número que não existe, ele passa a
   existir em `aurora_calc.py` (e as telas antigas herdam), nunca numa conta paralela dentro do
   script da tela. O Relatório também não calcula: lê os `dados_*.json`.
5. **Sem internet, sem conta, sem chave, sem IA.** Todo texto (frases do Hoje, do Risco, da Régua,
   do Relatório) é montado por regra a partir dos números. A redação está isolada em dois lugares,
   para o dia em que se quiser trocar por um modelo: `gerarTexto()` em `app/redacao.js` e
   `montar_relatorio()` em `redator_relatorio.py`. Não espalhe chamadas de rede.
6. **A Central redige e copia; quem manda o WhatsApp ou o e-mail é a pessoa.** Sem integração com
   nenhum serviço.
7. **Não invente número.** Se faltar histórico para uma conta, a tela diz "histórico insuficiente",
   não estima.
8. **Estimativa não tem centavo; título fechado tem.** Previsão, risco e probabilidades são
   arredondados em reais. Valor de título é valor exato (ver "Pendências" sobre isso).
9. **Quando uma conta muda, diga qual número mudou em qual tela e se a fila de Hoje trocou de
   ordem.** É assim que quem responde pelo projeto confere a mudança.
10. **Quando a conferência falhar, o conserto é no código, nunca em afrouxar a checagem.**

## Como abrir e rodar

```
python servidor.py        # abre http://localhost:8842/Central_Aurora.html (só escuta em 127.0.0.1)
python build_app.py       # só refaz as contas e o arquivo único, sem servidor
```

- `Central_Aurora.html` abre com duplo clique, em qualquer computador, sem internet e sem
  instalar nada (dados, fontes, estilo e script estão dentro dele). **"Registrar cobrança" só
  funciona com o servidor**: sem ele o botão fica desligado e a tela diz por quê (ver "Entrega").
- `build_app.py` roda as contas na ordem certa (`build_central`, `build_risco`, `build_previsao`,
  `build_regua`: Previsão e Régua leem `dados_risco.json`, a Régua lê também `dados_hoje.json`),
  pede o texto ao redator do Relatório e embute tudo no arquivo único. O servidor chama o mesmo
  `build_app` depois de cada registro.
- Endereços antigos (`/Central.html`, `/Risco.html`...) continuam funcionando pelo servidor: ele
  redireciona para a tela certa do arquivo único.
- **O servidor carrega o código na partida.** Depois de mexer em qualquer `.py`, pare e suba de
  novo, senão ele continua rodando a versão antiga (o Relatório mostrou o texto velho por isso).
- Precisa de Python 3 com `pip install pandas numpy openpyxl`. Testado com Python 3.15, pandas 3.0.6,
  numpy 2.5.4, openpyxl 3.1.5 (Windows 11).

## Mapa dos arquivos

| Arquivo | Papel |
|---|---|
| `aurora_calc.py` | Cálculo compartilhado + formatadores (`fmt_reais`, `fmt_dias`, `fmt_atraso`, `fmt_dec`) + escolha do tom + registros + semana passada. **Parâmetros de comportamento no topo** (janela de 90 dias, limiares de piora, sazonalidade). |
| `build_central.py` | Fila do Hoje. Parâmetros no topo (fator por situação do atraso, penalidade de 48h). Também a cor de cada cliente (`severidade`), as linhas curtas do porquê (`motivo_curto`) e as faixas de atraso. Grava `dados_hoje.json` e devolve os dados. |
| `build_risco.py` | Índice de risco 0–100 (pesos e tetos no topo), alertas por extenso e curtos, casos especiais, nível do índice e as "descobertas" do topo do Hoje (`montar_descobertas`). Grava `dados_risco.json`. |
| `build_previsao.py` | Previsão de 4 semanas (probabilidade de entrada no topo) e a semana de maior diferença. Grava `dados_previsao.json`. |
| `build_regua.py` | Candidatos e tom sugerido. Grava `dados_regua.json`. |
| `redator_relatorio.py` | Monta o texto do Relatório a partir dos quatro `dados_*.json`; `numeros_da_semana()` dá o número do topo da tela. |
| `build_app.py` | **Monta `Central_Aurora.html`**: roda as contas acima e embute dados, estilo, script e fontes num arquivo só. Não faz conta de negócio. |
| `app/base.html` | Esqueleto: topo, barra de navegação (as 5 telas), janela da ficha. |
| `app/estilo.css` | Todo o desenho. As cores e o trabalho de cada uma estão no comentário do topo. |
| `app/redacao.js` | Motor de redação das mensagens da Régua (`gerarTexto`) e o formatador `fmtReais` do navegador. |
| `app/app.js` | As cinco telas, busca, filtros, ordenação, "já liguei", ficha, gráficos. Só lê `DATA`, não calcula. |
| `app/fontes/` | Unbounded (números e títulos) e Manrope (texto), licença livre SIL OFL 1.1; vão embutidas no HTML. |
| `Central_Aurora.html` | **GERADO por `build_app.py`: nunca edite à mão** (o próximo build apaga). É também o arquivo que se manda para a equipe. |
| `servidor.py` | Serve `Central_Aurora.html` e grava `registros_cobranca.json` (`POST /api/registrar`); depois de cada registro chama `build_app`. |
| `conferencia.py` | 59 checagens das CONTAS: recalcula da planilha crua e compara com os dados do arquivo; compara tela com tela; confere que o arquivo não depende de internet. **Reprova se `Central_Aurora.html` não existir** (antes, arquivo ausente fazia a checagem ser pulada em silêncio). |
| `auditoria_navegador.py` | 84 verificações da TELA, no Chrome de verdade (precisa `pip install playwright`): a lista do que não pode sumir, nada cortado, primeiro cliente visível no telão, 6 tons reescrevendo o texto, "Registrar" desligado com motivo no arquivo offline, valores do Relatório realçados. Tira fotos de tudo. |
| `dados_hoje.json`, `dados_risco.json`, `dados_previsao.json`, `dados_regua.json` | **Gerados** pelos `build_*.py` (não edite). É o que as outras telas e o Relatório leem em vez de recalcular. |
| `registros_cobranca.json` | Cobranças registradas pela Central. Começa `[]`. |

Os comentários e docstrings no topo de cada `.py` explicam o raciocínio de cada tela; não foram
copiados para cá. Leia o do arquivo que for mexer.

## Decisões que não estavam no pedido (e foram tomadas por quê)

- **Vencido = vencimento antes da data de referência.** O título que vence **na própria data de
  referência** não está vencido (não entra no Hoje), e na Previsão entra na **semana 1**, que
  começa hoje. Antes ele não caía em nenhuma semana da planilha mas entrava no esperado, e a
  diferença da Previsão (R$ 36.804) era quase toda erro. Regra de ouro: todo título em aberto
  cai em exatamente um lugar (vencido, uma das 4 semanas, ou depois do horizonte) — a conferência
  confere isso.
- **"48 horas" = 2 dias corridos** (`JANELA_CONTATO_DIAS` em `build_central.py`), porque a base só
  guarda a data com a hora do contato e o relógio é o da base.
- **Mudou de comportamento** = a média dos últimos 90 dias (vencimento) subiu pelo menos 8 dias E
  pelo menos 1 desvio do próprio cliente, com 3 títulos pagos em cada lado. Cliente que atrasava
  35 dias e foi para 42 não piorou. Meses de atraso sazonal (repetidos em 2 anos diferentes) são
  descontados antes da comparação.
- **Hoje e Risco ordenam de propósito de jeitos diferentes.** Hoje: valor *vencido* × risco do
  atraso atual × penalidade de contato recente ("quem ligo"). Risco: saldo *em aberto* (vencido +
  a vencer) × índice ("onde está o dinheiro"). A Régua segue **a mesma numeração do Hoje**.
- **Tom da cobrança** é escolhido por `aurora_calc.escolher_tom()` com prioridade fixa: parou de
  comprar > atraso crônico confiável > piora real > atraso inédito de cliente grande (≥10% do
  faturamento) > atraso inédito > padrão. O usuário pode trocar o tom na mão; por isso **cada tom
  só afirma o que os números daquele cliente sustentam** (ex.: "maiores parceiros" só se for ≥10%).
  Ao criar um tom novo, teste-o em **todos** os clientes, não só no sugerido.
- **Previsão:** a diferença do **total** das 4 semanas hoje é ≈ R$ 0 (a planilha acerta o tamanho e
  erra *quando* entra). Por isso o número principal da tela é a **maior diferença semanal**, e o
  total fica em segundo plano. A faixa otimista–conservador só existe no **acumulado** (semana a
  semana os cenários se cruzam, porque atrasar empurra o dinheiro para a semana seguinte).
- **Relatório:** a lista "o que fazer" segue a ordem da fila de Hoje e cada item termina numa ação
  (o tom que a Régua sugere). Termina em decisão, não em gráfico.

## Desenho (refeito em 29/10/2026, direção "Poster luminoso", escolhida pelo dono do projeto)

Feito para telão e para abrir ao lado de sistemas caros: tem de impressionar em três segundos e
deixar claro por onde olhar. O conteúdo e as contas são os mesmos de antes; só a camada visual mudou.

- **Escuro**, degradê de cima a baixo na página inteira; vidro e degradê em todo lugar; **brilho só
  no que é principal** (o número do topo, o botão principal de cada cartão, a tela atual na barra).
- **Cinco cores, um trabalho cada, sempre com texto junto** (nunca só a cor): brasa = crítico;
  âmbar = atenção; menta = dentro do padrão; violeta = ação/foco; ciano = valor em reais citado em
  texto e a série "esperado" nos gráficos. Os chips de filtro funcionam também como legenda.
- **Cada tela tem uma coisa que domina o topo**: Hoje, o vencido; Risco, o valor em risco; Previsão,
  a maior diferença semanal; Régua, quantas mensagens prontas; Relatório, quanto entrou na semana.
  O número grande se ajusta à largura e nunca é cortado.
- **Hoje no telão (1920×1080)**: número grande, as 3 descobertas, a fila e o **primeiro cliente
  inteiro sem rolar** (a auditoria confere). Fila em **uma coluna, todos os cartões com a mesma
  cara**; o 1º tem só um contorno discreto.
- **Texto curto à vista, detalhe atrás de um clique**: cada cliente mostra 2–3 linhas (`motivo`);
  a frase completa, os títulos e os 5 fatores ficam na dobra; os blocos de método ficam fechados.
  Nada foi tirado: a lista do que não pode sumir está em `auditoria_navegador.py`
  (`lista_nao_pode_sumir`) e é conferida a cada rodada.
- **Operar a tela**: busca, filtros (com contagem), ordenação, "já liguei" e um botão principal por
  cartão (sempre o último, no mesmo lugar). Régua em **lista de um lado e texto de um cliente do
  outro**.
- **Gráficos só onde explicam mais rápido que texto**: faixas de atraso no topo do Hoje (onde o
  vencido está parado); linha de atraso mês a mês em cada cliente do Risco (mostra a piora do Vila
  Nova de longe); colunas planilha × esperado por semana na Previsão (é a tese da tela: o erro é
  *quando* entra); o acumulado com a faixa otimista–conservador e o gráfico da ficha já existiam.
  Régua e Relatório ficaram sem gráfico de propósito. As cores dos gráficos passaram no
  validador (distinguíveis para daltônicos); "planilha" é cinza de propósito (é a referência).
- **Animação**: só a contagem do número do topo e o brilho que respira. O número final está no HTML
  desde o início; sem animação (ou com "reduzir movimento" no sistema), ele aparece direto.
- **"Já liguei"** é uma marcação **só deste navegador** (guardada no próprio navegador, por data de
  referência). Não muda a fila nem registra cobrança: para isso existe "Registrar cobrança".

## Entrega: o arquivo único para a equipe

`Central_Aurora.html` é o arquivo a mandar: a pessoa recebe, dá dois cliques e abre no navegador
(Chrome ou Edge), sem instalar nada, sem internet e sem extrair nada. O que muda em relação a
abrir pelo servidor, e a tela diz isso no selo do topo e onde importa:

- **"Registrar cobrança" fica desligado**, com o motivo escrito ao lado (o arquivo não tem onde
  gravar). Copiar o texto, trocar tom e canal funcionam.
- **O Relatório é o do momento em que o arquivo foi gerado**; o botão "Atualizar com os registros
  de hoje" só aparece com o servidor.
- **"Já liguei" fica só no navegador de quem marcou**; não chega à equipe nem ao servidor.
- Os números são os da data de referência da planilha (12/08/2026) até alguém gerar um arquivo novo.

## O que parece defeito e não é

- **Dona Zica com queda de compra de exatamente 50%**: é real (de 14 para 7 pedidos em dois
  trimestres).
- **Empório Frescor com "histórico de compra curto demais"**: é real, é cliente desde 10/2025.
- **Hortifrúti Terra Boa com R$ 0 em risco e 0% do limite**: o saldo dele é zero. (Prazo "à vista"
  = 0 dias; o texto escreve "à vista", não "0 dias".)
- **Ninguém aparece como "caro e silencioso"**: o mais próximo é a Polo Norte, com 8,9% do
  faturamento, e o corte é 10%.
- **Dona Zica com "Atraso inédito" no Hoje e tom "Comercial, antes do financeiro" na Régua**:
  intencional, parar de comprar vence atraso inédito na escolha do tom.
- **Adega Boa Vista "cobrada há 2 dias"** vem da aba Cobranças da planilha (10/08), não de um
  registro da Central. Conta como contato recente (2 dias corridos).
- **Vila Nova com 6 dias numa tela e 8 em outra**: são medidas diferentes (média *antes* da piora
  contra média do histórico inteiro). Os textos já dizem qual é qual.
- **Total da Previsão quase igual ao da planilha**: ver acima, é o resultado, não conta que não
  rodou. O que mexe é a distribuição por semana.
- **Índice de risco inteiro, componentes com uma casa decimal**: o índice é a soma arredondada
  (5,5 + 10,9 + 21,1 + 0 + 8,8 = 46,3 → 46).
- **Console do navegador com um 404**: é o pedido do ícone da aba (favicon). Ignorar.
- **R$ 278.550 / 15 títulos vencidos**: número de uma leitura exploratória que usou 11/08 como
  "hoje". Está errado; o certo para 12/08 é R$ 302.680 em 16 títulos. Se aparecer em algum lugar,
  é resto de texto antigo.
- **Desconfie do que vier redondo demais** (0%, 100%, dias idênticos, total exato, categoria
  vazia): quase sempre é conta que não rodou. Os casos acima foram investigados e são reais.

## Armadilhas conhecidas

- **O caminho da planilha está escrito em 7 arquivos**: `build_central.py`, `build_risco.py`,
  `build_previsao.py`, `build_regua.py`, `redator_relatorio.py`, `servidor.py`, `conferencia.py`
  (constante `XLSX_PATH = C:\Users\samue\Downloads\Base_bruta.xlsx`). Em outra máquina ou usuário,
  troque nos sete; esquecer um deixa uma tela lendo outra planilha.
- **`fmtReais` existe em dois lugares**: `app/redacao.js` (navegador) e `aurora_calc.fmt_reais`
  (Python, usado no Relatório). Os dois arredondam ao real mais próximo; mudou um, mude o outro
  (a conferência cobre o de Python; a auditoria compara os números da tela com os do Python).
- **Tela nova** = uma função `telaX()` em `app/app.js`, uma entrada em `TELAS` no mesmo arquivo, um
  link na barra em `app/base.html` e os itens dela em `lista_nao_pode_sumir` da auditoria.
- **Nome de classe CSS com dois trabalhos quebra a tela em silêncio.** Aconteceu duas vezes: `brand`
  (marca e menu) e `din` (realce de dinheiro, que proíbe quebrar linha, e tom do topo da tela), que
  fez parágrafos inteiros vazarem para a coluna ao lado. Uma classe, um trabalho.
- **O número grande é medido com o valor final**, não com o que a contagem animada está mostrando
  (medir no meio da animação deixava o último dígito fora da caixa, invisível por causa do degradê).
- **Ao mudar um `.py`, reinicie o servidor** (ver acima).
- **A planilha precisa manter o formato**: abas `Leia-me`, `Clientes`, `Títulos`, `Cobranças` e as
  colunas com os nomes exatos que `aurora_calc.carregar_base()` lê (ex.: "Código do cliente",
  "Valor do título", "Data de vencimento", "Data de pagamento", "Prazo em dias", "Limite de crédito",
  "Data e hora do contato", "Valor cobrado"). A data de referência é lida da célula ao lado de
  "DATA DE REFERÊNCIA" na aba Leia-me, no formato "12 de agosto de 2026". Título sem data de
  pagamento é título em aberto.
- **A aba Leia-me cita um `Base_analisada.xlsx` ("para conferir o seu resultado")**: esse arquivo
  não existe aqui. Não conte com ele.

## Pendências e tensões conhecidas (decisões que ainda são do dono do projeto)

1. **"Sem instalar pacote nenhum" vale para abrir `Central_Aurora.html`**, não para gerar.
   `python servidor.py`, `build_app.py` e os `build_*.py` precisam de pandas, numpy e openpyxl
   (o comentário do `servidor.py` já diz isso). Resolver exigiria reescrever o cálculo sem pandas.
2. **Título com centavo:** a base atual não tem nenhum (conferido: 0 de 754), mas todos os
   formatadores arredondam ao real. Se a base nova trouxer centavos, o valor de **título**
   (lista da Régua, mensagens) aparecerá arredondado, contra a regra 8. Antes de usar uma base
   com centavos, crie um formatador com centavos para títulos.
3. **Registros acumulam entre meses** (decisão tomada). Risco: se a base nova trouxer na aba
   Cobranças um contato que a Central também registrou, ele aparece duas vezes no histórico. A
   conferência avisa (mesmo cliente, dia e valor); ver passo 6 abaixo.

## Como mexer nas telas ou acrescentar coisa

1. Desenho e comportamento: `app/` (nunca o `Central_Aurora.html`). Conta: o `build_*.py` da tela,
   e conta nova vai para `aurora_calc.py`. O `app.js` não calcula nada de negócio.
2. Rode `python build_app.py` e `python conferencia.py` (tem de dar "Todas as 59 checagens
   passaram", ou o novo total: toda tela ou número novo ganha a sua checagem, **recalculada da
   planilha crua**). Se a conferência acusar erro porque a tela mudou de forma, arrume a
   conferência no mesmo movimento; **nunca a desligue nem deixe ela "pular"**.
3. Rode `python auditoria_navegador.py` (tem de dar 0 falhas) e **olhe as fotos** que ela tira:
   ela pega o que some e o que é cortado, mas não pega coisa feia ou fora do lugar.
4. **A conferência sozinha não basta.** Ela passou 40 checagens com o título que vence hoje fora
   de qualquer semana, porque repetia a mesma regra do código. Abra as telas **no navegador de
   verdade**, em largura de computador (~1440) e de celular (390), no modo claro e no escuro:
   - procure texto cortado, número fora do quadro, rótulo sobre rótulo, botão quebrado, rolagem
     para o lado;
   - procure frases quebradas: "(s)", "1 dias", "-0%", "em -3 dias", "--", ponto decimal em vez de
     vírgula, "undefined", "NaN";
   - **compare o mesmo cliente entre telas** (valor vencido, índice, média de atraso, valor em
     risco, atraso recente): tem de ser o mesmo número em todo lugar;
   - **refaça as contas por um caminho diferente** (leia a planilha com `openpyxl` puro, sem
     importar nada da Central) e compare com o que está na tela.
   Para automatizar o navegador usou-se o Playwright (`pip install playwright`, canal `chrome`).
   Ele **não é exigido** para rodar a Central, só para auditar.
5. Para testar o registro de cobrança (só com o servidor): registre, confira nas telas, e **desfaça**
   (restaure `registros_cobranca.json` a como estava e rode `build_app.py`). Nunca deixe registro
   de teste na pasta.
6. Apague `__pycache__` ao terminar.

## Passo a passo: trocar a planilha pela do mês seguinte

Pré-requisito: o novo `Base_bruta.xlsx` entregue pela empresa, sem ter sido aberto e salvo (o
hash dele é conferido).

1. **Guarde a base antiga** com a data de referência no nome (ex.: `Base_bruta_2026-08-12.xlsx`),
   para poder reproduzir os números de hoje. Guarde também uma cópia da pasta inteira.
2. **Coloque a base nova no caminho de `XLSX_PATH`** (ou troque o caminho nos 7 arquivos, ver
   Armadilhas).
3. **Confira a estrutura** (abas e colunas, ver Armadilhas) e **a data de referência** na aba
   Leia-me: tem de ser mais nova que a anterior. Conferências rápidas que a Central não faz por
   você:
   - nenhum título com pagamento ou emissão **depois** da data de referência;
   - valores com centavos? (se sim, ver Pendência 2);
   - cliente novo, ou cliente sem nenhum título pago (a Central trata, mas olhe o que a tela diz);
   - o formato de data e o nome das colunas não mudaram.
4. **Atualize o hash** em `conferencia.py` (`HASH_XLSX_ESPERADO`). Calcule com:
   `python -c "import hashlib;print(hashlib.sha256(open(r'CAMINHO','rb').read()).hexdigest())"`.
   Só faça isto com o arquivo exatamente como a empresa entregou.
5. **Refaça a Central**: `python build_app.py` (roda as quatro contas na ordem e gera o
   arquivo único; imprime "OK --" a cada etapa).
6. **Registros de cobrança** (decisão: acumulam). Deixe `registros_cobranca.json` como está. Se a
   aba Cobranças nova já trouxer um contato que a Central registrou, a conferência (passo 7)
   imprime um `AVISO` com o id: tire esse registro do JSON (faça cópia antes; o próximo id usa o
   maior existente, então apagar é seguro) e rode `build_app.py` de novo.
7. **Rode `python conferencia.py`.** Tem de passar tudo. Se algo falhar, **leia a falha antes de
   mexer**: ou a base nova quebrou uma suposição (ex.: uma aba mudou de nome), ou há defeito no
   código. Não afrouxe a checagem para passar.
8. **Refaça por fora os totais** (sem usar nada da Central) e compare com as telas. Ajuste `REF`
   para a data de referência nova:

   ```python
   import openpyxl
   from datetime import datetime
   REF = datetime(2026, 8, 12)          # <- data de referência da aba Leia-me
   wb = openpyxl.load_workbook(r"CAMINHO", read_only=True, data_only=True)
   linhas = [r for r in wb["Títulos"].iter_rows(values_only=True)][1:]
   # colunas: 0 número, 1 cód. cliente, 2 nome, 3 emissão, 4 valor, 5 vencimento, 6 pagamento
   aberto = [r for r in linhas if r[0] and r[6] is None]
   venc, avenc = [r for r in aberto if r[5] < REF], [r for r in aberto if r[5] >= REF]
   cent = lambda rs: sum(round(r[4] * 100) for r in rs)
   print(len(linhas), len(venc), cent(venc) / 100, len(avenc), cent(avenc) / 100)
   ```
   Com a base de 12/08/2026 isto imprime `754 16 302680.0 24 679220.0`: são os números da tela Hoje
   (R$ 302.680 em 16 vencidos, R$ 679.220 em 24 a vencer, 754 títulos na base).
9. **Rode `python auditoria_navegador.py`** e olhe as fotos; depois abra (`python servidor.py`) e
   percorra as 5 telas. Compare o mesmo cliente entre telas.
9b. **Mande o arquivo novo** (`Central_Aurora.html`) para quem usa a versão sem servidor: o
   arquivo antigo que está com eles continua mostrando o mês anterior.
10. **Registre o que mudou de número de um mês para o outro** (fila de Hoje trocou de ordem? quem
    entrou ou saiu? o total em risco subiu quanto?). Mudança esperada: títulos e clientes novos,
    mês novo na série, fila reordenada. Mudança inesperada: número de cliente antigo mudar sem
    motivo na base.
11. **Atualize a tabela "Números de referência" abaixo** com a data nova e os totais novos, e
    apague `__pycache__`.

## Números de referência (base de 12/08/2026 — para saber se algo quebrou)

Se a base de 12/08/2026 (`Base_bruta_2026-08-12.xlsx`, guardada no passo 1) for colocada de volta e
`registros_cobranca.json` estiver `[]`, a Central tem de mostrar exatamente isto:

- Hash da planilha: `af5d278c22234d4a83a9db7086b3d05a72928d09fc166ce7f74967f8bf669511`
- **Hoje:** R$ 302.680 em 16 títulos vencidos, 7 clientes na fila, R$ 679.220 em 24 a vencer, 754
  títulos. Ordem: 1 Supermercado Vila Nova (R$ 126.780), 2 Atacado São Jorge (R$ 60.130),
  3 Casa de Carnes Bom Corte (R$ 21.280), 4 Empório Frescor (R$ 31.000), 5 Adega Serra Azul
  (R$ 30.800), 6 Mercearia Dona Zica (R$ 12.170), 7 Adega e Empório Boa Vista (R$ 20.520, desce por
  ter sido cobrada há 2 dias).
- **Risco:** valor em risco total R$ 270.795; saldo em aberto R$ 981.900; Vila Nova índice 46.
- **Previsão:** planilha R$ 595.710, esperado R$ 595.504 nas 4 semanas (diferença de R$ 206);
  maior diferença semanal: semana 4, R$ 131.509.
- **Régua:** 7 clientes, mesma numeração do Hoje; tom sugerido para o 1º, "Conversa, não ameaça".
- **Hoje, topo**: faixas de atraso 1–7 dias R$ 76.570 (3), 8–30 R$ 128.140 (8), 31–60 R$ 81.410
  (2), mais de 60 R$ 16.560 (3); descobertas: Vila Nova (6 → 26 dias), Dona Zica (93 dias sem
  pedido), Serra Azul (18 dias, prazo real).
- **Relatório, topo**: entrou R$ 279.390 de 05/08 a 11/08.
- `python conferencia.py` → "Todas as 59 checagens passaram."; `python auditoria_navegador.py` →
  "84 verificações OK, 0 falharam"
