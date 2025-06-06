from threading import Thread
from bot import main as run_bot
from admin import app

def run_admin():
    app.run(host='0.0.0.0', port=8080, debug=False)  # debug=False для production

if __name__ == "__main__":
    # Запускаем бот и админку в разных потоках
    bot_thread = Thread(target=run_bot)
    admin_thread = Thread(target=run_admin)
    
    bot_thread.start()
    admin_thread.start()
    
    bot_thread.join()
    admin_thread.join()