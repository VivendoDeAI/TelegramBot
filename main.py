import logging
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import asyncio
from datetime import datetime

# Configurações do OpenAI e Telegram
openai.api_key = os.getenv('OPENAI_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Configuração do logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Buffer local para armazenar as últimas mensagens e respostas
user_buffers = {}
response_buffers = {}
message_buffers = {}
message_timers = {}
MESSAGE_TIMEOUT = 5  # Tempo de espera em segundos antes de consolidar as mensagens

# Função para gerar resposta do OpenAI usando o modelo gpt-4-turbo
async def generate_chat_response(user_id: str, combined_message: str) -> str:
    # Definir o contexto do sistema
    system_message = {
        "role": "system",
        "content": "Alice é uma jovem modelo de 23 anos que vive em São Paulo,Seu trabalho é vender o curso do Matheus Itolog, dono da CRO! você deve ser gentil e amigavel e vender o curso de maneira sutil guiando o usuario para a conversa. Começou sua carreira de modelo na adolescência e, com o tempo, percebeu a importância de construir uma presença digital forte para monetizar sua imagem e alcançar seus sonhos, como financiar suas viagens pelo mundo. Extrovertida, carismática e cheia de energia, Alice sempre soube como cativar as pessoas ao seu redor, usando seu charme natural e sua habilidade em se conectar genuinamente com os outros.Recentemente, Alice se tornou afiliada da CRO, uma comunidade que ensina como viver do digital, fundada por Matheus Itolog. Essa comunidade ajuda pessoas a transformarem suas paixões e habilidades em negócios digitais lucrativos, oferecendo cursos, mentorias e uma rede de apoio sólida. Alice encontrou na CRO uma oportunidade perfeita para expandir ainda mais sua carreira, aprendendo novas estratégias e técnicas para dominar o mercado digital. Sempre buscando crescer e aprender, Alice aproveita os conhecimentos da CRO para compartilhar dicas e insights sobre como construir uma marca pessoal forte e lucrativa. Ela está sempre disposta a ajudar quem também deseja trilhar esse caminho e alcançar a independência financeira. Com uma abordagem envolvente e cativante, Alice não só compartilha sua jornada, mas também inspira outros a seguirem seus próprios sonhos no mundo digital. Ela acredita que todos têm o potencial de transformar suas vidas através do poder do marketing digital, e está sempre aberta a conversar sobre isso com quem estiver interessado. Se você deseja aprender mais sobre como viver do digital e transformar sua paixão em um negócio rentável, Alice está pronta para te guiar nessa jornada. Entre em contato e descubra como a CRO pode te ajudar a alcançar seus objetivos!"
    }

    # Recuperar o contexto das últimas mensagens e respostas
    recent_user_messages = user_buffers.get(user_id, [])
    recent_responses = response_buffers.get(user_id, [])

    # Limitar o número de mensagens armazenadas
    if len(recent_user_messages) > 5:
        recent_user_messages = recent_user_messages[-5:]
    if len(recent_responses) > 5:
        recent_responses = recent_responses[-5:]

    # Criar o histórico das mensagens
    messages = [system_message]
    for msg in recent_user_messages:
        messages.append({"role": "user", "content": msg})
    for res in recent_responses:
        messages.append({"role": "assistant", "content": res})
    messages.append({"role": "user", "content": combined_message})

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=1.2,
        max_tokens=150
    )

    return response.choices[0].message['content'].strip()

# Função para registrar as conversas em um arquivo de log
def log_conversation(user_id: str, username: str, user_message: str, bot_response: str):
    # Criar a pasta logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Definir o nome do arquivo de log usando o nome do usuário e o ID
    filename = f"logs/{username} - {user_id}.txt"

    # Obter o horário atual
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Registrar a mensagem e a resposta no arquivo de log
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {username}: {user_message}\n")
        f.write(f"[{timestamp}] Alice: {bot_response}\n\n")

# Função para lidar com mensagens de texto
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username or update.message.from_user.first_name
    user_message = update.message.text

    # Inicializar buffers se necessário
    if user_id not in user_buffers:
        user_buffers[user_id] = []
        response_buffers[user_id] = []
        message_buffers[user_id] = []

    # Adicionar a nova mensagem ao buffer temporário
    if user_id in message_buffers:
        message_buffers[user_id].append(user_message)
    else:
        message_buffers[user_id] = [user_message]

    # Cancelar o timer existente
    if user_id in message_timers:
        message_timers[user_id].cancel()

    # Definir um novo timer para processar as mensagens
    timer = asyncio.create_task(process_messages(user_id, username, context))
    message_timers[user_id] = timer

# Função para processar e enviar mensagens após um tempo de espera
async def process_messages(user_id: str, username: str, context: CallbackContext) -> None:
    await asyncio.sleep(MESSAGE_TIMEOUT)

    if user_id in message_buffers:
        # Recuperar todas as mensagens acumuladas e combinar
        combined_message = ' '.join(message_buffers[user_id])

        # Limitar o tamanho do histórico para evitar exceder o limite de tokens
        if len(user_buffers.get(user_id, [])) > 10:
            user_buffers[user_id] = user_buffers[user_id][-10:]
        if len(response_buffers.get(user_id, [])) > 10:
            response_buffers[user_id] = response_buffers[user_id][-10:]

        # Adicionar a nova mensagem combinada ao histórico
        user_buffers.setdefault(user_id, []).append(combined_message)

        # Gerar a resposta do bot
        if combined_message:
            response = await generate_chat_response(user_id, combined_message)
            # Adicionar a resposta do bot ao histórico
            response_buffers.setdefault(user_id, []).append(response)
            # Registrar a conversa no log
            log_conversation(user_id, username, combined_message, response)
            # Enviar resposta
            await context.bot.send_message(chat_id=user_id, text=response)

        # Limpar o buffer de mensagens
        message_buffers[user_id] = []

# Função para iniciar o bot
async def start(update: Update, context: CallbackContext) -> None:
    start_message = "Olá! Como posso te ajudar hoje?"
    await update.message.reply_text(start_message)

def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Adiciona handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Inicia o bot
    application.run_polling()

if __name__ == "__main__":
    main()
