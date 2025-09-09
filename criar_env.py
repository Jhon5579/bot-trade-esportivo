print("--- Assistente de Configuração de Chaves ---")

# Usamos strip() para remover quaisquer espaços acidentais no início ou fim
token = input("1/3 - Cole aqui o seu TELEGRAM_TOKEN e aperte Enter: ").strip()
chat_id = input("2/3 - Cole aqui o seu TELEGRAM_CHAT_ID e aperte Enter: ").strip()
api_key = input("3/3 - Cole aqui a sua API_KEY_ODDS e aperte Enter: ").strip()

conteudo_env = f"""TELEGRAM_TOKEN={token}
TELEGRAM_CHAT_ID={chat_id}
API_KEY_ODDS={api_key}
"""

try:
    with open('.env', 'w') as f:
        f.write(conteudo_env)
    print("\n✅ SUCESSO! O arquivo .env foi criado/sobrescrito com suas chaves.")
    print("O arquivo de configuração está 100% correto.")
except Exception as e:
    print(f"\n❌ ERRO: Não foi possível escrever no arquivo .env: {e}")