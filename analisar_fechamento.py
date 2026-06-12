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
    """Gera dashboard HTML com graficos e filtros interativos usando Chart.js."""

    # Preparar dados para graficos — cada registro vira um objeto JSON
    dados_ord = sorted(dados, key=lambda x: x.get("business_date_dt") or datetime.min)

    # Montar array de objetos com todos os campos necessarios
    registros_json = []
    for r in dados_ord:
        if not r.get("business_date_dt"):
            continue
        registros_json.append({
            "data": r["business_date_dt"].strftime("%d/%m"),
            "data_full": r["business_date_dt"].strftime("%Y-%m-%d"),
            "mes": r["business_date_dt"].strftime("%Y-%m"),
            "weekday": r.get("weekday_lower", ""),
            "weekday_num": r.get("weekday_num", -1),
            "receita": round(r["daily_result_num"], 2),
            "despesa": round(r["daily_expenses_num"], 2),
            "refeicoes": round(r["meals_quantity_num"], 0),
            "refeicoes_salao": round(r["restaurant_meals_quantity_num"], 0),
            "marmitas_g": round(r["large_marmitas_quantity_num"], 0),
            "marmitas_p": round(r["small_marmitas_quantity_num"], 0),
            "total_marmitas": round(r.get("total_marmitas", 0), 0),
            "margem": round(r["margem"], 2) if r["margem"] is not None else 0,
        })

    # Lista de meses unicos
    meses_unicos = sorted(set(r["mes"] for r in registros_json))

    # Tabela anomalias
    anomalias_html = ""
    if anomalias:
        anomalias_html = "<h3>Anomalias Detectadas</h3><table><tr><th>Data</th><th>Dia</th><th>Valor</th><th>Tipo</th><th>Desvio</th><th>Notas</th></tr>"
        for a in anomalias:
            cor = "#c62828" if a["tipo"] == "ABAIXO" else "#2e7d32"
            anomalias_html += f'<tr><td>{a["data"]}</td><td>{a["dia_semana"]}</td><td>{formatar_moeda(a["valor"])}</td><td style="color:{cor};font-weight:bold">{a["tipo"]}</td><td>{formatar_moeda(a["desvio_media"])}</td><td>{a["notas"][:60]}</td></tr>'
        anomalias_html += "</table>"

    # Gerar opcoes de meses para filtro
    meses_options = "".join(f'<option value="{m}">{m}</option>' for m in meses_unicos)

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
        .header {{ text-align: center; margin-bottom: 20px; }}
        .header h1 {{ color: #333; font-size: 24px; }}
        .header p {{ color: #666; margin-top: 5px; }}

        /* FILTROS */
        .filtros {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .filtros h3 {{ margin-bottom: 12px; color: #333; font-size: 16px; }}
        .filtros-grid {{ display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-end; }}
        .filtro-grupo {{ display: flex; flex-direction: column; gap: 5px; }}
        .filtro-grupo label {{ font-size: 12px; font-weight: 600; color: #555; text-transform: uppercase; }}
        .filtro-grupo select {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; background: white; cursor: pointer; min-width: 160px; }}
        .filtro-grupo select:focus {{ outline: none; border-color: #1976D2; box-shadow: 0 0 0 2px rgba(25,118,210,0.2); }}
        .btn-limpar {{ padding: 8px 16px; background: #f44336; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; align-self: flex-end; }}
        .btn-limpar:hover {{ background: #d32f2f; }}

        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px; }}
        .card {{ background: white; padding: 18px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
        .card .valor {{ font-size: 22px; font-weight: bold; color: #1976D2; }}
        .card .label {{ font-size: 11px; color: #666; margin-top: 5px; text-transform: uppercase; }}
        .chart-container {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .chart-container h3 {{ margin-bottom: 15px; color: #333; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f0f7ff; }}
        .filtro-ativo {{ background: #e3f2fd !important; border-color: #1976D2 !important; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Dashboard de Fechamento Diario</h1>
        <p id="headerPeriodo">{resumo['periodo_inicio']} a {resumo['periodo_fim']} | {resumo['total_dias']} dias</p>
    </div>

    <!-- FILTROS -->
    <div class="filtros">
        <h3>Filtros</h3>
        <div class="filtros-grid">
            <div class="filtro-grupo">
                <label>Tipo de Refeicao</label>
                <select id="filtroTipo">
                    <option value="todas">Todas</option>
                    <option value="salao">Somente Salao</option>
                    <option value="marmitas_g">Somente Marmitas Grandes</option>
                    <option value="marmitas_p">Somente Marmitas Pequenas</option>
                    <option value="marmitas_todas">Todas as Marmitas (G+P)</option>
                </select>
            </div>
            <div class="filtro-grupo">
                <label>Mes</label>
                <select id="filtroMes">
                    <option value="todos">Todos os meses</option>
                    {meses_options}
                </select>
            </div>
            <div class="filtro-grupo">
                <label>Dia da Semana</label>
                <select id="filtroDia">
                    <option value="todos">Todos os dias</option>
                    <option value="0">Segunda</option>
                    <option value="1">Terca</option>
                    <option value="2">Quarta</option>
                    <option value="3">Quinta</option>
                    <option value="4">Sexta</option>
                    <option value="5">Sabado</option>
                    <option value="6">Domingo</option>
                </select>
            </div>
            <button class="btn-limpar" onclick="limparFiltros()">Limpar Filtros</button>
        </div>
    </div>

    <!-- CARDS RESUMO -->
    <div class="cards">
        <div class="card"><div class="valor" id="cardReceita">-</div><div class="label">Receita Total</div></div>
        <div class="card"><div class="valor" id="cardReceitaMedia">-</div><div class="label">Receita Media/Dia</div></div>
        <div class="card"><div class="valor" id="cardRefeicoes">-</div><div class="label">Total Refeicoes</div></div>
        <div class="card"><div class="valor" id="cardSalao">-</div><div class="label">Refeicoes Salao</div></div>
        <div class="card"><div class="valor" id="cardMarmitas">-</div><div class="label">Marmitas G / P</div></div>
        <div class="card"><div class="valor" id="cardMargem">-</div><div class="label">Margem Media/Dia</div></div>
    </div>

    <!-- GRAFICOS -->
    <div class="chart-container">
        <h3 id="tituloGraficoPrincipal">Receita Diaria + Media Movel (7 dias)</h3>
        <canvas id="chartPrincipal"></canvas>
    </div>

    <div class="grid-2">
        <div class="chart-container">
            <h3>Por Dia da Semana</h3>
            <canvas id="chartDiaSemana"></canvas>
        </div>
        <div class="chart-container">
            <h3 id="tituloQuantidades">Quantidades por Dia</h3>
            <canvas id="chartQuantidades"></canvas>
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
        // === DADOS COMPLETOS ===
        const DADOS = {json.dumps(registros_json)};
        const DIAS_LABELS = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo'];

        // === REFERENCIAS DOS GRAFICOS ===
        let chartPrincipal = null;
        let chartDiaSemana = null;
        let chartQuantidades = null;
        let chartMarmitas = null;
        let chartMargem = null;

        // === FUNCOES UTILITARIAS ===
        function formatarMoeda(valor) {{
            return 'R$ ' + valor.toFixed(2).replace('.', ',').replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, '.');
        }}

        function calcularMediaMovel(valores, janela) {{
            return valores.map((_, i) => {{
                const inicio = Math.max(0, i - janela + 1);
                const slice = valores.slice(inicio, i + 1);
                return slice.reduce((a, b) => a + b, 0) / slice.length;
            }});
        }}

        // === FUNCAO DE FILTRO ===
        function filtrarDados() {{
            const tipoFiltro = document.getElementById('filtroTipo').value;
            const mesFiltro = document.getElementById('filtroMes').value;
            const diaFiltro = document.getElementById('filtroDia').value;

            let filtrados = DADOS;

            // Filtro por mes
            if (mesFiltro !== 'todos') {{
                filtrados = filtrados.filter(r => r.mes === mesFiltro);
            }}

            // Filtro por dia da semana
            if (diaFiltro !== 'todos') {{
                filtrados = filtrados.filter(r => r.weekday_num === parseInt(diaFiltro));
            }}

            return {{ filtrados, tipoFiltro }};
        }}

        // === FUNCAO PARA OBTER VALORES POR TIPO ===
        function getValoresPorTipo(registros, tipo) {{
            switch(tipo) {{
                case 'salao':
                    return registros.map(r => r.refeicoes_salao);
                case 'marmitas_g':
                    return registros.map(r => r.marmitas_g);
                case 'marmitas_p':
                    return registros.map(r => r.marmitas_p);
                case 'marmitas_todas':
                    return registros.map(r => r.total_marmitas);
                default:
                    return registros.map(r => r.refeicoes);
            }}
        }}

        function getTituloTipo(tipo) {{
            switch(tipo) {{
                case 'salao': return 'Refeicoes do Salao';
                case 'marmitas_g': return 'Marmitas Grandes';
                case 'marmitas_p': return 'Marmitas Pequenas';
                case 'marmitas_todas': return 'Total Marmitas (G+P)';
                default: return 'Total Refeicoes';
            }}
        }}

        // === ATUALIZAR DASHBOARD ===
        function atualizarDashboard() {{
            const {{ filtrados, tipoFiltro }} = filtrarDados();

            if (filtrados.length === 0) {{
                document.getElementById('headerPeriodo').textContent = 'Nenhum dado encontrado para os filtros selecionados';
                return;
            }}

            // Atualizar periodo
            const primeiro = filtrados[0];
            const ultimo = filtrados[filtrados.length - 1];
            document.getElementById('headerPeriodo').textContent =
                `${{primeiro.data}} a ${{ultimo.data}} | ${{filtrados.length}} dias (filtrado)`;

            // Atualizar cards
            const receitas = filtrados.map(r => r.receita);
            const receitaTotal = receitas.reduce((a, b) => a + b, 0);
            const receitaMedia = receitaTotal / filtrados.length;
            const refeicoes = filtrados.map(r => r.refeicoes).reduce((a, b) => a + b, 0);
            const salao = filtrados.map(r => r.refeicoes_salao).reduce((a, b) => a + b, 0);
            const marmG = filtrados.map(r => r.marmitas_g).reduce((a, b) => a + b, 0);
            const marmP = filtrados.map(r => r.marmitas_p).reduce((a, b) => a + b, 0);
            const margens = filtrados.map(r => r.margem);
            const margemMedia = margens.reduce((a, b) => a + b, 0) / filtrados.length;

            document.getElementById('cardReceita').textContent = formatarMoeda(receitaTotal);
            document.getElementById('cardReceitaMedia').textContent = formatarMoeda(receitaMedia);
            document.getElementById('cardRefeicoes').textContent = Math.round(refeicoes);
            document.getElementById('cardSalao').textContent = Math.round(salao);
            document.getElementById('cardMarmitas').textContent = `${{Math.round(marmG)}} / ${{Math.round(marmP)}}`;
            document.getElementById('cardMargem').textContent = formatarMoeda(margemMedia);

            // === GRAFICOS ===
            const labels = filtrados.map(r => r.data);
            const valoresReceita = filtrados.map(r => r.receita);
            const mm7 = calcularMediaMovel(valoresReceita, 7);

            // Grafico Principal - muda conforme tipo
            if (chartPrincipal) chartPrincipal.destroy();
            const valoresQuantidade = getValoresPorTipo(filtrados, tipoFiltro);
            const tituloTipo = getTituloTipo(tipoFiltro);

            if (tipoFiltro === 'todas') {{
                document.getElementById('tituloGraficoPrincipal').textContent = 'Receita Diaria + Media Movel (7 dias)';
                chartPrincipal = new Chart(document.getElementById('chartPrincipal'), {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: [
                            {{ label: 'Receita', data: valoresReceita, backgroundColor: 'rgba(33,150,243,0.3)', borderColor: 'rgba(33,150,243,1)', borderWidth: 1 }},
                            {{ label: 'Media Movel 7d', data: mm7, type: 'line', borderColor: '#1565C0', borderWidth: 2, pointRadius: 0, fill: false }}
                        ]
                    }},
                    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }} }}
                }});
            }} else {{
                document.getElementById('tituloGraficoPrincipal').textContent = tituloTipo + ' por Dia';
                const mm7q = calcularMediaMovel(valoresQuantidade, 7);
                chartPrincipal = new Chart(document.getElementById('chartPrincipal'), {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: [
                            {{ label: tituloTipo, data: valoresQuantidade, backgroundColor: 'rgba(76,175,80,0.4)', borderColor: 'rgba(76,175,80,1)', borderWidth: 1 }},
                            {{ label: 'Media Movel 7d', data: mm7q, type: 'line', borderColor: '#2E7D32', borderWidth: 2, pointRadius: 0, fill: false }}
                        ]
                    }},
                    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }} }}
                }});
            }}

            // Grafico por Dia da Semana
            if (chartDiaSemana) chartDiaSemana.destroy();
            const porDia = {{}};
            filtrados.forEach(r => {{
                if (!porDia[r.weekday_num]) porDia[r.weekday_num] = [];
                porDia[r.weekday_num].push(tipoFiltro === 'todas' ? r.receita : getValoresPorTipo([r], tipoFiltro)[0]);
            }});
            const diasComDados = Object.keys(porDia).sort((a, b) => a - b);
            const diasLabels = diasComDados.map(d => DIAS_LABELS[d]);
            const diasMedias = diasComDados.map(d => porDia[d].reduce((a, b) => a + b, 0) / porDia[d].length);

            chartDiaSemana = new Chart(document.getElementById('chartDiaSemana'), {{
                type: 'bar',
                data: {{
                    labels: diasLabels,
                    datasets: [{{ label: tipoFiltro === 'todas' ? 'Receita Media (R$)' : tituloTipo + ' (media)', data: diasMedias.map(v => Math.round(v * 100) / 100), backgroundColor: 'rgba(33,150,243,0.6)' }}]
                }},
                options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
            }});

            // Grafico Quantidades
            if (chartQuantidades) chartQuantidades.destroy();
            document.getElementById('tituloQuantidades').textContent = tipoFiltro === 'todas' ? 'Quantidades por Dia' : tituloTipo + ' por Dia';
            chartQuantidades = new Chart(document.getElementById('chartQuantidades'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{ label: tituloTipo, data: valoresQuantidade, backgroundColor: 'rgba(255,152,0,0.5)', borderColor: 'rgba(255,152,0,1)', borderWidth: 1 }}]
                }},
                options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
            }});

            // Marmitas
            if (chartMarmitas) chartMarmitas.destroy();
            chartMarmitas = new Chart(document.getElementById('chartMarmitas'), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [
                        {{ label: 'Grandes', data: filtrados.map(r => r.marmitas_g), borderColor: '#2196F3', backgroundColor: 'rgba(33,150,243,0.1)', fill: true }},
                        {{ label: 'Pequenas', data: filtrados.map(r => r.marmitas_p), borderColor: '#FFC107', backgroundColor: 'rgba(255,193,7,0.1)', fill: true }}
                    ]
                }},
                options: {{ responsive: true }}
            }});

            // Margem
            if (chartMargem) chartMargem.destroy();
            chartMargem = new Chart(document.getElementById('chartMargem'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'Margem (R$)',
                        data: margens,
                        backgroundColor: margens.map(v => v >= 0 ? 'rgba(76,175,80,0.6)' : 'rgba(244,67,54,0.6)')
                    }}]
                }},
                options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
            }});
        }}

        // === EVENTOS DE FILTRO ===
        document.getElementById('filtroTipo').addEventListener('change', atualizarDashboard);
        document.getElementById('filtroMes').addEventListener('change', atualizarDashboard);
        document.getElementById('filtroDia').addEventListener('change', atualizarDashboard);

        function limparFiltros() {{
            document.getElementById('filtroTipo').value = 'todas';
            document.getElementById('filtroMes').value = 'todos';
            document.getElementById('filtroDia').value = 'todos';
            atualizarDashboard();
        }}

        // Inicializar
        atualizarDashboard();
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
