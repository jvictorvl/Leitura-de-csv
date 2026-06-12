# Análise de Fechamento Diário

Script Python reutilizável para análise de dados de fechamento diário de restaurante/marmitaria.

## Estrutura do Projeto

```
fechamento-analise/
├── data/                    # Coloque seus arquivos CSV aqui
├── output/
│   ├── graficos/            # Gráficos gerados automaticamente
│   ├── dados_limpos_unificados.csv
│   ├── resumo_geral.csv
│   ├── analise_dia_semana.csv
│   ├── analise_por_mes.csv
│   └── anomalias.csv
├── analisar_fechamento.py   # Script principal
├── requirements.txt
└── README.md
```

## Instalação

**Nenhuma dependência externa é necessária!** O script usa apenas a biblioteca padrão do Python 3.8+.

Basta ter Python instalado e executar.

## Como Usar

### 1. Coloque seus CSVs na pasta `data/`

O script aceita arquivos com as seguintes colunas:
- `closing_id` — identificador do fechamento
- `date` — data do registro
- `business_date` — data de negócio
- `weekday` — dia da semana
- `daily_expenses` — despesas do dia (opcional)
- `daily_result` — resultado/receita do dia
- `meals_quantity` — quantidade de refeições
- `restaurant_meals_quantity` — refeições no restaurante
- `large_marmitas_quantity` — marmitas grandes
- `small_marmitas_quantity` — marmitas pequenas
- `notes` — observações/correções

### 2. Execute o script

```bash
# Analisar todos os CSVs da pasta data/
python analisar_fechamento.py

# Especificar outra pasta
python analisar_fechamento.py --pasta meus_dados/

# Analisar um arquivo específico
python analisar_fechamento.py --arquivo data/fechamento-diario-2026-05.csv
```

### 3. Confira os resultados

Os resultados ficam em `output/`:
- **CSVs** com dados limpos, resumos e análises
- **Gráficos** em `output/graficos/`

## Análises Geradas

| Análise | Descrição |
|---------|-----------|
| Resumo Geral | Período, totais, médias, dias com correção |
| Por Dia da Semana | Receita média, refeições, marmitas por dia |
| Por Mês | Comparativo mensal de todos indicadores |
| Tendência | Média móvel de 7 dias da receita |
| Anomalias | Dias com valores fora do padrão (±2 desvios) |
| Margem | Receita - Despesas por dia |

## Gráficos Gerados

1. **receita_diaria_tendencia.png** — Receita diária com média móvel
2. **analise_dia_semana.png** — Receita e refeições por dia da semana
3. **evolucao_marmitas.png** — Marmitas grandes vs pequenas ao longo do tempo
4. **margem_diaria.png** — Margem (receita - despesas) por dia
5. **comparativo_meses.png** — Comparativo entre meses

## Detecção Automática

O script detecta automaticamente:
- Separador do CSV (vírgula ou ponto-e-vírgula)
- Caractere decimal (vírgula ou ponto)
- Dias com correções manuais (pela coluna `notes`)

## Adicionando Novos Meses

Basta colocar o novo arquivo `.csv` na pasta `data/` e rodar o script novamente.
Todos os arquivos serão unificados automaticamente.
