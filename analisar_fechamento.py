"""
Script reutilizavel para analise de dados de fechamento diario.
Restaurante / Marmitaria

SEM DEPENDENCIAS EXTERNAS - usa apenas biblioteca padrao do Python.
Para graficos, gera um HTML interativo.

Uso:
    python analisar_fechamento.py
    python analisar_fechamento.py --pasta data/
    python analisar_fechamento.py --arquivo data/fechamento-diario-2026-04.csv

Coloque seus arquivos CSV na pasta data/ e execute o script.
"""

import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean, stdev
from pathlib import Path


# =============================================================================
# CONFIGURACOES
# =============================================================================

PASTA_DADOS = "data"
PASTA_OUTPUT = "output"

ORDEM_DIAS = {
    "segunda-feira": 0, "segunda": 0,
    "terca-feira": 1, "terça-feira": 1, "terca": 1,
    "quarta-feira": 2, "quarta": 2,
    "quinta-feira": 3, "quinta": 3,
    "sexta-feira": 4, "sexta": 4,
    "sabado": 5, "sábado": 5,
    "domingo": 6,
}

DIAS_LABELS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# =============================================================================
# FUNCOES DE UTILIDADE
# =============================================================================

def parse_numero(valor: str) -> float:
    """Converte string para float, tratando virgula como decimal."""
    if not valor or valor.strip() == "":
        return 0.0
    valor = valor.strip()
    # Se tem ponto E virgula, ponto eh milhar e virgula eh decimal
    if "." in valor and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    # Se tem apenas virgula, eh decimal
    elif "," in valor:
        valor = valor.replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return 0.0


def parse_data(valor: str) -> datetime:
    """Converte string para datetime, tentando varios formatos."""
    valor = valor.strip()
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(valor, fmt)
        except ValueError:
            continue
    return None


def formatar_moeda(valor: float) -> str:
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# =============================================================================
# CARREGAMENTO E LIMPEZA DE DADOS
# =============================================================================

def detectar_separador(arquivo: str) -> str:
    """Detecta separador do CSV."""
    with open(arquivo, "r", encoding="utf-8") as f:
        primeira_linha = f.readline()
    if ";" in primeira_linha and primeira_linha.count(";") > primeira_linha.count(","):
        return ";"
    return ","


def carregar_csv(arquivo: str) -> list:
    """Carrega um CSV e retorna lista de dicionarios."""
    separador = detectar_separador(arquivo)

    registros = []
    with open(arquivo, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=separador)
        for row in reader:
            # Normalizar chaves
            registro = {}
            for k, v in row.items():
                if k:
                    registro[k.strip().lower().replace(" ", "_")] = (v or "").strip()
            registros.append(registro)

    return registros


def limpar_registro(reg: dict) -> dict:
    """Limpa e enriquece um registro individual."""
    r = reg.copy()

    # Parsear datas
    for campo_data in ["date", "business_date"]:
        if campo_data in r:
            r[campo_data + "_dt"] = parse_data(r[campo_data])

    # Parsear numericos
    campos_num = [
        "daily_expenses", "daily_result",
        "meals_quantity", "restaurant_meals_quantity",
        "large_marmitas_quantity", "small_marmitas_quantity",
    ]
    for campo in campos_num:
        if campo in r:
            r[campo + "_num"] = parse_numero(r[campo])
        else:
            r[campo + "_num"] = 0.0

    # Dia da semana normalizado
    if "weekday" in r:
        r["weekday_lower"] = r["weekday"].strip().lower()
        r["weekday_num"] = ORDEM_DIAS.get(r["weekday_lower"], -1)

    # Flag de correcao
    notes = r.get("notes", "").lower()
    r["teve_correcao"] = any(p in notes for p in ["corre", "ajust", "manual", "focada"])

    # Calculos derivados
    r["total_marmitas"] = r["large_marmitas_quantity_num"] + r["small_marmitas_quantity_num"]

    receita = r["daily_result_num"]
    despesa = r["daily_expenses_num"]
    r["margem"] = receita - despesa if despesa > 0 else None
    r["margem_pct"] = (r["margem"] / receita * 100) if (r["margem"] is not None and receita > 0) else None

    return r


def carregar_todos_csvs(pasta: str) -> list:
    """Carrega todos CSVs de uma pasta."""
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.csv")))

    if not arquivos:
        print(f"\n[ERRO] Nenhum arquivo CSV encontrado em '{pasta}/'")
        print(f"       Coloque seus arquivos .csv na pasta '{pasta}/' e execute novamente.")
        sys.exit(1)

    print(f"Encontrados {len(arquivos)} arquivo(s) CSV:")
    todos = []
    for arq in arquivos:
        registros = carregar_csv(arq)
        for r in registros:
            r["arquivo_origem"] = os.path.basename(arq)
        todos.extend(registros)
        print(f"  - {arq} ({len(registros)} registros)")

    print(f"\nTotal de registros carregados: {len(todos)}")
    return todos


# =============================================================================
# FUNCOES DE ANALISE
# =============================================================================

def resumo_geral(dados: list) -> dict:
    """Gera resumo geral."""
    datas = [r["business_date_dt"] for r in dados if r.get("business_date_dt")]
    receitas = [r["daily_result_num"] for r in dados if r["daily_result_num"] > 0]
    refeicoes = [r["meals_quantity_num"] for r in dados]
    marmitas_g = [r["large_marmitas_quantity_num"] for r in dados]
    marmitas_p = [r["small_marmitas_quantity_num"] for r in dados]
    despesas = [r["daily_expenses_num"] for r in dados if r["daily_expenses_num"] > 0]
    margens = [r["margem"] for r in dados if r["margem"] is not None]
    correcoes = sum(1 for r in dados if r["teve_correcao"])

    resumo = {
        "periodo_inicio": min(datas).strftime("%d/%m/%Y") if datas else "N/A",
        "periodo_fim": max(datas).strftime("%d/%m/%Y") if datas else "N/A",
        "total_dias": len(dados),
        "receita_total": sum(receitas),
        "receita_media": mean(receitas) if receitas else 0,
        "receita_max": max(receitas) if receitas else 0,
        "receita_min": min(receitas) if receitas else 0,
        "total_refeicoes": sum(refeicoes),
        "media_refeicoes_dia": mean(refeicoes) if refeicoes else 0,
        "total_marmitas_grandes": sum(marmitas_g),
        "total_marmitas_pequenas": sum(marmitas_p),
        "despesa_total": sum(despesas),
        "despesa_media": mean(despesas) if despesas else 0,
        "margem_media": mean(margens) if margens else 0,
        "margem_pct_media": mean([r["margem_pct"] for r in dados if r["margem_pct"] is not None]),
        "dias_com_correcao": correcoes,
    }
    return resumo


def analise_por_dia_semana(dados: list) -> list:
    """Agrupa metricas por dia da semana."""
    grupos = defaultdict(list)
    for r in dados:
        dia_num = r.get("weekday_num", -1)
        if dia_num >= 0:
            grupos[dia_num].append(r)

    resultado = []
    for dia_num in sorted(grupos.keys()):
        registros = grupos[dia_num]
        receitas = [r["daily_result_num"] for r in registros]
        refeicoes = [r["meals_quantity_num"] for r in registros]
        marm_g = [r["large_marmitas_quantity_num"] for r in registros]
        marm_p = [r["small_marmitas_quantity_num"] for r in registros]

        resultado.append({
            "dia": DIAS_LABELS[dia_num] if dia_num < len(DIAS_LABELS) else "?",
            "dia_num": dia_num,
            "qtd_dias": len(registros),
            "receita_media": mean(receitas) if receitas else 0,
            "receita_total": sum(receitas),
            "refeicoes_media": mean(refeicoes) if refeicoes else 0,
            "marmitas_g_media": mean(marm_g) if marm_g else 0,
            "marmitas_p_media": mean(marm_p) if marm_p else 0,
        })

    return resultado


def analise_por_mes(dados: list) -> list:
    """Agrupa metricas por mes."""
    grupos = defaultdict(list)
    for r in dados:
        dt = r.get("business_date_dt")
        if dt:
            chave = dt.strftime("%Y-%m")
            grupos[chave].append(r)

    resultado = []
    for mes in sorted(grupos.keys()):
        registros = grupos[mes]
        receitas = [r["daily_result_num"] for r in registros]
        refeicoes = [r["meals_quantity_num"] for r in registros]
        despesas = [r["daily_expenses_num"] for r in registros if r["daily_expenses_num"] > 0]

        resultado.append({
            "mes": mes,
            "dias": len(registros),
            "receita_total": sum(receitas),
            "receita_media": mean(receitas) if receitas else 0,
            "refeicoes_total": sum(refeicoes),
            "refeicoes_media": mean(refeicoes) if refeicoes else 0,
            "despesa_total": sum(despesas),
            "despesa_media": mean(despesas) if despesas else 0,
            "marmitas_g_total": sum(r["large_marmitas_quantity_num"] for r in registros),
            "marmitas_p_total": sum(r["small_marmitas_quantity_num"] for r in registros),
        })

    return resultado


def analise_tendencia(dados: list, janela: int = 7) -> list:
    """Calcula media movel."""
    dados_ord = sorted(dados, key=lambda x: x.get("business_date_dt") or datetime.min)
    receitas = [r["daily_result_num"] for r in dados_ord]

    medias_moveis = []
    for i in range(len(receitas)):
        inicio = max(0, i - janela + 1)
        janela_vals = receitas[inicio:i + 1]
        medias_moveis.append(mean(janela_vals))

    for i, r in enumerate(dados_ord):
        r["receita_mm7"] = medias_moveis[i]

    return dados_ord


def identificar_anomalias(dados: list, coluna: str = "daily_result_num", desvios: float = 2.0) -> list:
    """Identifica dias com valores fora do padrao."""
    valores = [r[coluna] for r in dados if r[coluna] > 0]
    if len(valores) < 3:
        return []

    m = mean(valores)
    s = stdev(valores)
    limite_inf = m - desvios * s
    limite_sup = m + desvios * s

    anomalias = []
    for r in dados:
        v = r[coluna]
        if v > 0 and (v < limite_inf or v > limite_sup):
            anomalias.append({
                "data": r.get("business_date", ""),
                "dia_semana": r.get("weekday", ""),
                "valor": v,
                "tipo": "ABAIXO" if v < limite_inf else "ACIMA",
                "desvio_media": v - m,
                "notas": r.get("notes", ""),
            })

    return anomalias


# =============================================================================
# SAIDA: RELATORIOS E GRAFICOS HTML
# =============================================================================

def imprimir_resumo(resumo: dict):
    """Imprime resumo formatado."""
    print("\n" + "=" * 50)
    print("  RESUMO GERAL")
    print("=" * 50)
    print(f"  Periodo: {resumo['periodo_inicio']} a {resumo['periodo_fim']}")
    print(f"  Total de dias: {resumo['total_dias']}")
    print(f"  Receita total: {formatar_moeda(resumo['receita_total'])}")
    print(f"  Receita media/dia: {formatar_moeda(resumo['receita_media'])}")
    print(f"  Receita max: {formatar_moeda(resumo['receita_max'])}")
    print(f"  Receita min: {formatar_moeda(resumo['receita_min'])}")
    print(f"  Total refeicoes: {resumo['total_refeicoes']:.0f}")
    print(f"  Media refeicoes/dia: {resumo['media_refeicoes_dia']:.0f}")
    print(f"  Marmitas grandes: {resumo['total_marmitas_grandes']:.0f}")
    print(f"  Marmitas pequenas: {resumo['total_marmitas_pequenas']:.0f}")
    if resumo['despesa_total'] > 0:
        print(f"  Despesa total: {formatar_moeda(resumo['despesa_total'])}")
        print(f"  Despesa media/dia: {formatar_moeda(resumo['despesa_media'])}")
        print(f"  Margem media/dia: {formatar_moeda(resumo['margem_media'])}")
        print(f"  Margem media (%): {resumo['margem_pct_media']:.1f}%")
    print(f"  Dias com correcao manual: {resumo['dias_com_correcao']}")


def imprimir_dia_semana(analise: list):
    """Imprime analise por dia da semana."""
    print("\n" + "=" * 50)
    print("  ANALISE POR DIA DA SEMANA")
    print("=" * 50)
    print(f"  {'Dia':<12} {'Dias':>5} {'Receita Med':>12} {'Refeicoes':>10} {'Marm G':>7} {'Marm P':>7}")
    print("  " + "-" * 55)
    for item in analise:
        print(f"  {item['dia']:<12} {item['qtd_dias']:>5} {formatar_moeda(item['receita_media']):>12} {item['refeicoes_media']:>10.0f} {item['marmitas_g_media']:>7.0f} {item['marmitas_p_media']:>7.0f}")


def imprimir_por_mes(analise: list):
    """Imprime analise por mes."""
    print("\n" + "=" * 50)
    print("  ANALISE POR MES")
    print("=" * 50)
    print(f"  {'Mes':<10} {'Dias':>5} {'Receita Total':>14} {'Receita Med':>12} {'Refeicoes':>10}")
    print("  " + "-" * 55)
    for item in analise:
        print(f"  {item['mes']:<10} {item['dias']:>5} {formatar_moeda(item['receita_total']):>14} {formatar_moeda(item['receita_media']):>12} {item['refeicoes_total']:>10.0f}")


def salvar_csv_resultado(dados: list, arquivo: str, campos: list):
    """Salva uma lista de dicts como CSV."""
    with open(arquivo, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dados)


def gerar_html_dashboard(dados: list, resumo: dict, dia_semana: list, por_mes: list, anomalias: list, pasta_saida: str):
    """Gera dashboard HTML com graficos usando Chart.js (via CDN ou inline)."""

    # Preparar dados para graficos
    dados_ord = sorted(dados, key=lambda x: x.get("business_date_dt") or datetime.min)

    # Datas e receitas para grafico de linha
    datas_labels = [r["business_date_dt"].strftime("%d/%m") for r in dados_ord if r.get("business_date_dt")]
    receitas = [r["daily_result_num"] for r in dados_ord if r.get("business_date_dt")]

    # Media movel
    mm7 = []
    for i in range(len(receitas)):
        inicio = max(0, i - 6)
        mm7.append(round(mean(receitas[inicio:i+1]), 2))

    # Dia da semana
    dias_labels_chart = [d["dia"] for d in dia_semana]
    dias_receita = [round(d["receita_media"], 2) for d in dia_semana]
    dias_refeicoes = [round(d["refeicoes_media"], 1) for d in dia_semana]

    # Marmitas
    marmitas_g = [r["large_marmitas_quantity_num"] for r in dados_ord if r.get("business_date_dt")]
    marmitas_p = [r["small_marmitas_quantity_num"] for r in dados_ord if r.get("business_date_dt")]

    # Margem
    margens = [round(r["margem"], 2) if r["margem"] is not None else 0 for r in dados_ord if r.get("business_date_dt")]
    margem_cores = ["'rgba(76,175,80,0.6)'" if m >= 0 else "'rgba(244,67,54,0.6)'" for m in margens]

    # Tabela anomalias
    anomalias_html = ""
    if anomalias:
        anomalias_html = "<h3>Anomalias Detectadas</h3><table><tr><th>Data</th><th>Dia</th><th>Valor</th><th>Tipo</th><th>Desvio</th><th>Notas</th></tr>"
        for a in anomalias:
            cor = "#c62828" if a["tipo"] == "ABAIXO" else "#2e7d32"
            anomalias_html += f'<tr><td>{a["data"]}</td><td>{a["dia_semana"]}</td><td>{formatar_moeda(a["valor"])}</td><td style="color:{cor};font-weight:bold">{a["tipo"]}</td><td>{formatar_moeda(a["desvio_media"])}</td><td>{a["notas"][:60]}</td></tr>'
        anomalias_html += "</table>"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Fechamento Diario</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ color: #333; font-size: 24px; }}
        .header p {{ color: #666; margin-top: 5px; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
        .card .valor {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
        .card .label {{ font-size: 12px; color: #666; margin-top: 5px; text-transform: uppercase; }}
        .chart-container {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .chart-container h3 {{ margin-bottom: 15px; color: #333; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f0f7ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Dashboard de Fechamento Diario</h1>
        <p>{resumo['periodo_inicio']} a {resumo['periodo_fim']} | {resumo['total_dias']} dias</p>
    </div>

    <div class="cards">
        <div class="card"><div class="valor">{formatar_moeda(resumo['receita_total'])}</div><div class="label">Receita Total</div></div>
        <div class="card"><div class="valor">{formatar_moeda(resumo['receita_media'])}</div><div class="label">Receita Media/Dia</div></div>
        <div class="card"><div class="valor">{resumo['total_refeicoes']:.0f}</div><div class="label">Total Refeicoes</div></div>
        <div class="card"><div class="valor">{resumo['total_marmitas_grandes']:.0f} / {resumo['total_marmitas_pequenas']:.0f}</div><div class="label">Marmitas G / P</div></div>
        <div class="card"><div class="valor">{formatar_moeda(resumo['margem_media'])}</div><div class="label">Margem Media/Dia</div></div>
        <div class="card"><div class="valor">{resumo['dias_com_correcao']}</div><div class="label">Dias com Correcao</div></div>
    </div>

    <div class="chart-container">
        <h3>Receita Diaria + Media Movel (7 dias)</h3>
        <canvas id="chartReceita"></canvas>
    </div>

    <div class="grid-2">
        <div class="chart-container">
            <h3>Receita Media por Dia da Semana</h3>
            <canvas id="chartDiaSemana"></canvas>
        </div>
        <div class="chart-container">
            <h3>Refeicoes por Dia da Semana</h3>
            <canvas id="chartRefeicoesDia"></canvas>
        </div>
    </div>

    <div class="chart-container">
        <h3>Evolucao de Marmitas (Grandes vs Pequenas)</h3>
        <canvas id="chartMarmitas"></canvas>
    </div>

    <div class="chart-container">
        <h3>Margem Diaria (Receita - Despesas)</h3>
        <canvas id="chartMargem"></canvas>
    </div>

    <div class="chart-container">
        {anomalias_html}
    </div>

    <script>
        const datas = {json.dumps(datas_labels)};
        const receitas = {json.dumps(receitas)};
        const mm7 = {json.dumps(mm7)};
        const diasLabels = {json.dumps(dias_labels_chart)};
        const diasReceita = {json.dumps(dias_receita)};
        const diasRefeicoes = {json.dumps(dias_refeicoes)};
        const marmitasG = {json.dumps(marmitas_g)};
        const marmitasP = {json.dumps(marmitas_p)};
        const margens = {json.dumps(margens)};

        // Grafico Receita Diaria
        new Chart(document.getElementById('chartReceita'), {{
            type: 'bar',
            data: {{
                labels: datas,
                datasets: [
                    {{ label: 'Receita', data: receitas, backgroundColor: 'rgba(33,150,243,0.3)', borderColor: 'rgba(33,150,243,1)', borderWidth: 1 }},
                    {{ label: 'Media Movel 7d', data: mm7, type: 'line', borderColor: '#1565C0', borderWidth: 2, pointRadius: 0, fill: false }}
                ]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }} }}
        }});

        // Dia da Semana - Receita
        new Chart(document.getElementById('chartDiaSemana'), {{
            type: 'bar',
            data: {{
                labels: diasLabels,
                datasets: [{{ label: 'Receita Media (R$)', data: diasReceita, backgroundColor: 'rgba(33,150,243,0.6)' }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Dia da Semana - Refeicoes
        new Chart(document.getElementById('chartRefeicoesDia'), {{
            type: 'bar',
            data: {{
                labels: diasLabels,
                datasets: [{{ label: 'Refeicoes Media', data: diasRefeicoes, backgroundColor: 'rgba(76,175,80,0.6)' }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Marmitas
        new Chart(document.getElementById('chartMarmitas'), {{
            type: 'line',
            data: {{
                labels: datas,
                datasets: [
                    {{ label: 'Grandes', data: marmitasG, borderColor: '#2196F3', backgroundColor: 'rgba(33,150,243,0.1)', fill: true }},
                    {{ label: 'Pequenas', data: marmitasP, borderColor: '#FFC107', backgroundColor: 'rgba(255,193,7,0.1)', fill: true }}
                ]
            }},
            options: {{ responsive: true }}
        }});

        // Margem
        new Chart(document.getElementById('chartMargem'), {{
            type: 'bar',
            data: {{
                labels: datas,
                datasets: [{{
                    label: 'Margem (R$)',
                    data: margens,
                    backgroundColor: margens.map(v => v >= 0 ? 'rgba(76,175,80,0.6)' : 'rgba(244,67,54,0.6)')
                }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
</body>
</html>"""

    caminho = os.path.join(pasta_saida, "dashboard.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Dashboard HTML salvo: {caminho}")
    return caminho


# =============================================================================
# FUNCAO PRINCIPAL
# =============================================================================

def executar_analise(pasta_dados: str = PASTA_DADOS, arquivo_unico: str = None):
    """Executa toda a pipeline de analise."""

    print("\n" + "=" * 60)
    print("  ANALISE DE FECHAMENTO DIARIO")
    print("  Script Reutilizavel - Python (sem dependencias externas)")
    print("=" * 60)

    # --- 1. Carregar dados ---
    print("\n[1/5] Carregando dados...")
    if arquivo_unico:
        registros_raw = carregar_csv(arquivo_unico)
        for r in registros_raw:
            r["arquivo_origem"] = os.path.basename(arquivo_unico)
        print(f"  Carregado: {arquivo_unico} ({len(registros_raw)} registros)")
    else:
        registros_raw = carregar_todos_csvs(pasta_dados)

    # --- 2. Limpar dados ---
    print("\n[2/5] Limpando e tratando dados...")
    dados = [limpar_registro(r) for r in registros_raw]
    # Filtrar registros sem data
    dados = [r for r in dados if r.get("business_date_dt")]
    dados.sort(key=lambda x: x["business_date_dt"])
    print(f"  Registros validos (com data): {len(dados)}")

    # Garantir pasta de saida
    os.makedirs(PASTA_OUTPUT, exist_ok=True)

    # --- 3. Analises ---
    print("\n[3/5] Gerando analises...")
    resumo = resumo_geral(dados)
    imprimir_resumo(resumo)

    dia_semana = analise_por_dia_semana(dados)
    imprimir_dia_semana(dia_semana)

    por_mes = analise_por_mes(dados)
    imprimir_por_mes(por_mes)

    dados_tend = analise_tendencia(dados)

    anomalias = identificar_anomalias(dados)
    if anomalias:
        print(f"\n  ANOMALIAS DETECTADAS: {len(anomalias)}")
        for a in anomalias:
            print(f"    {a['data']} ({a['dia_semana']}): {formatar_moeda(a['valor'])} [{a['tipo']}]")
    else:
        print("\n  Nenhuma anomalia detectada.")

    # --- 4. Salvar CSVs ---
    print("\n[4/5] Salvando resultados CSV...")
    campos_saida = [
        "closing_id", "date", "business_date", "weekday",
        "daily_expenses_num", "daily_result_num", "meals_quantity_num",
        "restaurant_meals_quantity_num", "large_marmitas_quantity_num",
        "small_marmitas_quantity_num", "total_marmitas", "margem", "margem_pct",
        "teve_correcao", "notes", "arquivo_origem",
    ]
    salvar_csv_resultado(dados, os.path.join(PASTA_OUTPUT, "dados_limpos.csv"), campos_saida)
    salvar_csv_resultado(dia_semana, os.path.join(PASTA_OUTPUT, "analise_dia_semana.csv"),
                         ["dia", "qtd_dias", "receita_media", "receita_total", "refeicoes_media", "marmitas_g_media", "marmitas_p_media"])
    salvar_csv_resultado(por_mes, os.path.join(PASTA_OUTPUT, "analise_por_mes.csv"),
                         ["mes", "dias", "receita_total", "receita_media", "refeicoes_total", "refeicoes_media", "despesa_total", "despesa_media", "marmitas_g_total", "marmitas_p_total"])
    if anomalias:
        salvar_csv_resultado(anomalias, os.path.join(PASTA_OUTPUT, "anomalias.csv"),
                             ["data", "dia_semana", "valor", "tipo", "desvio_media", "notas"])
    print("  CSVs salvos em output/")

    # --- 5. Dashboard HTML ---
    print("\n[5/5] Gerando dashboard HTML com graficos...")
    caminho_html = gerar_html_dashboard(dados, resumo, dia_semana, por_mes, anomalias, PASTA_OUTPUT)

    print("\n" + "=" * 60)
    print("  ANALISE CONCLUIDA!")
    print(f"  Resultados em: {PASTA_OUTPUT}/")
    print(f"  Dashboard:     {caminho_html}")
    print(f"  (Abra o arquivo HTML no navegador para ver os graficos)")
    print("=" * 60 + "\n")

    return dados


# =============================================================================
# EXECUCAO
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analise de fechamento diario - sem dependencias externas")
    parser.add_argument("--pasta", default=PASTA_DADOS, help="Pasta com arquivos CSV (default: data/)")
    parser.add_argument("--arquivo", default=None, help="Arquivo CSV unico para analisar")
    args = parser.parse_args()

    executar_analise(pasta_dados=args.pasta, arquivo_unico=args.arquivo)
