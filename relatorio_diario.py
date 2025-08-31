import os
import requests
import json
from datetime import datetime, timezone, timedelta

# --- 1. CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'

# --- 2. FUNÇÃO DE ENVIO PARA O TELEGRAM ---
def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Secrets do Telegram não encontrados."); return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais: mensagem = mensagem.replace(char, f'\\{char}')
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("\n✅ Relatório diário enviado com sucesso para o Telegram!")
        else:
            print(f"\n❌ ERRO ao enviar relatório para o Telegram: {response.text}")
    except Exception as e:
        print(f"\n❌ ERRO de conexão com o Telegram: {e}")

# --- 3. LÓGICA PRINCIPAL DO RELATÓRIO ---
def gerar_relatorio_diario():
    print("--- 📊 Iniciando geração do Relatório Diário de Performance... ---")
    
    # Carrega o histórico de todas as apostas já concluídas
    try:
        with open(ARQUIVO_HISTORICO_APOSTAS, 'r', encoding='utf-8') as f:
            historico = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Arquivo 'historico_de_apostas.json' não encontrado ou vazio. Nenhum relatório a ser gerado.")
        return

    # Define o período de 24 horas atrás a partir de agora
    agora = datetime.now(timezone.utc)
    vinte_e_quatro_horas_atras = agora - timedelta(days=1)
    
    # Filtra apenas as apostas concluídas nas últimas 24 horas
    apostas_do_dia = []
    for aposta in historico:
        data_conclusao = datetime.fromisoformat(aposta['data_conclusao'])
        if data_conclusao >= vinte_e_quatro_horas_atras:
            apostas_do_dia.append(aposta)

    if not apostas_do_dia:
        print("Nenhuma aposta foi concluída nas últimas 24 horas.")
        # Opcional: Enviar uma mensagem mesmo que não haja resultados
        mensagem = "📊 *Relatório Diário de Performance*\n\nNenhuma aposta foi concluída nas últimas 24 horas."
        enviar_alerta_telegram(mensagem)
        return

    # Calcula as estatísticas
    greens = 0
    reds = 0
    for aposta in apostas_do_dia:
        if aposta['resultado'] == 'GREEN':
            greens += 1
        elif aposta['resultado'] == 'RED':
            reds += 1
    
    total_apostas = greens + reds
    # Calcula a taxa de acerto (evita divisão por zero)
    taxa_acerto = (greens / total_apostas * 100) if total_apostas > 0 else 0
    
    print(f"Resultados do dia: {greens} GREENs, {reds} REDs.")
    
    # Monta a mensagem final para o Telegram
    data_hoje_str = agora.strftime('%d/%m/%Y')
    mensagem = (
        f"📊 *Relatório Diário de Performance - {data_hoje_str}*\n\n"
        f"Resumo das apostas concluídas nas últimas 24 horas:\n"
        f"====================\n"
        f"✅ *GREENs:* {greens}\n"
        f"🔴 *REDs:* {reds}\n"
        f"📈 *Total de Entradas:* {total_apostas}\n"
        f"🎯 *Taxa de Acerto (Winrate):* {taxa_acerto:.2f}%\n"
        f"===================="
    )

    # Envia o relatório
    enviar_alerta_telegram(mensagem)

if __name__ == "__main__":
    gerar_relatorio_diario()
