import os
import requests
import json
from datetime import datetime, timezone, timedelta

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_RESULTADOS_DIA = 'resultados_do_dia.json'

# O dia da semana para enviar o relatório (0=Segunda, ..., 6=Domingo)
DIA_DO_RELATORIO_SEMANAL = 6 

# --- FUNÇÕES DE SUPORTE (Copiadas do main.py) ---
def carregar_json(caminho_arquivo):
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais: mensagem = mensagem.replace(char, f'\\{char}')
    url, payload = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200: print("  > Mensagem enviada com sucesso para o Telegram!")
        else: print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e: print(f"  > ERRO de conexão com o Telegram: {e}")

# --- FUNÇÃO PRINCIPAL DO SCRIPT ---
def gerar_e_enviar_resumo_semanal():
    print("--- 🗓️ Verificando se é dia de enviar o resumo semanal... ---")
    fuso_horario = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_horario)

    if hoje.weekday() != DIA_DO_RELATORIO_SEMANAL:
        print(f"Hoje não é domingo. O script será encerrado.")
        return

    nome_arquivo_flag = f"relatorio_semanal_{hoje.strftime('%Y-%m-%d')}.flag"
    if os.path.exists(nome_arquivo_flag):
        print("O relatório semanal para hoje já foi enviado. O script será encerrado.")
        return
        
    print("-> ✅ Hoje é dia de relatório! Compilando os dados da semana...")

    apostas_totais = carregar_json(ARQUIVO_HISTORICO_APOSTAS) + carregar_json(ARQUIVO_RESULTADOS_DIA)
    if not apostas_totais:
        print("Nenhum dado histórico para gerar o resumo semanal.")
        return

    sete_dias_atras = hoje - timedelta(days=7)
    apostas_da_semana = [
        aposta for aposta in apostas_totais 
        if datetime.fromtimestamp(aposta.get('timestamp', 0)).astimezone(fuso_horario) >= sete_dias_atras
    ]

    if not apostas_da_semana:
        print("Nenhuma aposta encontrada na última semana.")
        with open(nome_arquivo_flag, 'w') as f: f.write(str(hoje))
        return

    greens = len([r for r in apostas_da_semana if r.get('resultado') == 'GREEN'])
    reds = len([r for r in apostas_da_semana if r.get('resultado') == 'RED'])
    total = len(apostas_da_semana)
    assertividade = (greens / total * 100) if total > 0 else 0
    
    placar_estrategias = {}
    for res in apostas_da_semana:
        estrategia = res.get('estrategia', 'Desconhecida')
        placar_estrategias.setdefault(estrategia, {'GREEN': 0, 'RED': 0})
        if res.get('resultado') == 'GREEN': placar_estrategias[estrategia]['GREEN'] += 1
        elif res.get('resultado') == 'RED': placar_estrategias[estrategia]['RED'] += 1

    texto_detalhado = ""
    estrategias_ordenadas = sorted(placar_estrategias.items(), key=lambda item: item[1]['GREEN'], reverse=True)
    for estrategia, placar in estrategias_ordenadas:
        g, r = placar['GREEN'], placar['RED']
        texto_detalhado += f"*{estrategia}:* {g} ✅ / {r} 🔴\n"

    data_inicio_str = sete_dias_atras.strftime('%d/%m/%Y')
    data_fim_str = hoje.strftime('%d/%m/%Y')
    resumo_msg = (
        f"📊 *Resumo Semanal de Desempenho* 📊\n\n"
        f"*🗓️ Período:* {data_inicio_str} a {data_fim_str}\n\n"
        f"*Placar Geral da Semana:*\n"
        f"✅ *GREENs:* {greens}\n"
        f"🔴 *REDs:* {reds}\n"
        f"📈 *Assertividade:* {assertividade:.2f}%\n"
        f"💰 *Total de Entradas:* {total}\n\n"
        f"--------------------------\n"
        f"*Desempenho por Estratégia na Semana:*\n"
        f"{texto_detalhado}"
    )
    enviar_alerta_telegram(resumo_msg)

    with open(nome_arquivo_flag, 'w') as f: f.write(str(hoje))
    print(f"✅ Relatório semanal enviado! Ficheiro de controlo '{nome_arquivo_flag}' criado.")

if __name__ == "__main__":
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Segredos do Telegram não configurados.")
    else:
        gerar_e_enviar_resumo_semanal()
