NOTIFICATIONS_BOT — TELEGRAM-БОТ (AIOGRAM 3) + SQLITE + ПЛАНИРОВЩИК

Кратко:
Бот на aiogram 3 с ролями: пользователь и админ.
Новые пользователи при /start попадают в «заявки». Админ одобряет и ОБЯЗАТЕЛЬНО вводит имя.
Планировщик отправляет 3 типа уведомлений:
• за 3 дня до окончания (в 11:00),
• в день окончания (в 11:00),
• один раз в течение часа после окончания.

Хранение данных: SQLite (через SQLAlchemy async).
Рекомендуемый запуск: через Docker (docker-compose).

ВАЖНО:
Папка data/ и файл .env НЕ лежат в репозитории. Их создаёшь на сервере вручную.
База данных хранится на хосте в ./data и монтируется в контейнер как /data/bot.db.

===============================================================================
СТРУКТУРА ПРОЕКТА

notifications_bot/
app/
handlers/
admin.py ← админские хэндлеры (заявки, approve с вводом имени, дашборд, уведомления)
user.py ← пользовательские хэндлеры
bot.py ← сборка Bot/Dispatcher, подключение роутеров, запуск polling и планировщика
db.py ← модели/функции БД (SQLAlchemy async); путь к БД из env DB_PATH или /data/bot.db
keyboards.py ← генераторы Inline-клавиатур
scheduler.py ← планировщик (aioschedule): hourly job, логика 3 уведомлений
states.py ← FSM-состояния
config.py ← переменные окружения и валидация (BOT_TOKEN, ADMIN_ID, TZ, DB_PATH)
main.py ← ТОЧКА ВХОДА (asyncio.run(run()))
requirements.txt ← зависимости Python
Dockerfile ← сборка Docker-образа
docker-compose.yml ← запуск контейнера (маунты, env, лимиты, безопасность)
.dockerignore ← что НЕ попадёт в образ
.gitignore ← что НЕ попадёт в git (включая data/, .env)

Примечание: папка data/ появится после развёртывания на сервере (см. ниже).

===============================================================================
БЫСТРЫЙ СТАРТ (UBUNTU, DOCKER)

Установи Docker и Compose (однократно)
см. официальную инструкцию или команды:

sudo apt update && sudo apt -y upgrade
sudo apt -y install ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/$(
. /etc/os-release; echo "$ID")/gpg |
sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg]
https://download.docker.com/linux/$(
. /etc/os-release; echo "$ID") $(lsb_release -cs) stable" |
sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
(необязательно) дать доступ без sudo:
sudo usermod -aG docker $USER
newgrp docker

Клонируй репозиторий на сервер
cd ~
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> notifications_bot
cd ~/notifications_bot

Создай папку данных и права (контейнер будет писать сюда)
mkdir -p data
chown $(id -u):$(id -g) data
chmod 770 data
Пояснение «фокуса с data»: контейнер запущен с read_only файловой системой для безопасности,
а каталог /data смонтирован отдельно и доступен на запись, чтобы SQLite мог создавать журналы WAL/SHM.

Создай файл .env (СЕКРЕТЫ; НЕ коммити!)
umask 077
nano .env
Вставь строки (БЕЗ кавычек и БЕЗ $(id -u) — только числа):
BOT_TOKEN=1234567890:AA... # токен от @BotFather
ADMIN_ID=123456789 # ваш numeric Telegram ID
TZ=Europe/Berlin
UID=1000 # выведи через: id -u
GID=1000 # выведи через: id -g
COMPOSE_PROJECT_NAME=notifications_bot
DB_PATH=/data/bot.db
Сохрани файл и выставь права:
chmod 600 .env

Собери и запусти контейнер
docker compose build
docker compose up -d
docker compose logs -f
Всё ок, если видишь, что aiogram начал polling.
Контейнер будет называться примерно: notifications_bot-bot-1.

===============================================================================
ОБНОВЛЕНИЕ ВЕРСИИ

cd ~/notifications_bot
git pull
docker compose build --no-cache
docker compose up -d
docker compose logs -f

Данные в ./data сохраняются.

===============================================================================
РЕЗЕРВНЫЕ КОПИИ БАЗЫ (ГОРЯЧИЙ БЭКАП, БЕЗ ОСТАНОВКИ)

Установи sqlite3 (однократно):
sudo apt -y install sqlite3

Сделай бэкап:
cd ~/notifications_bot
mkdir -p backups
sqlite3 data/bot.db ".backup 'backups/bot-$(date +%F_%H-%M-%S).db'"

Проверка целостности (ожидаем 'ok'):
sqlite3 backups/bot-*.db "PRAGMA integrity_check;"

Сжатие (опционально):
gzip -9 backups/bot-*.db

Восстановление:
docker compose down
gunzip -c backups/bot-YYYY-MM-DD_HH-MM-SS.db.gz > data/bot.db (или копируй .db без gz)
chown 1000:1000 data/bot.db # подставь свои UID:GID
chmod 660 data/bot.db
docker compose up -d

===============================================================================
ЗАПУСК БЕЗ DOCKER (ДЛЯ ОТЛАДКИ, НЕ РЕКОМЕНДУЕТСЯ ДЛЯ PROD)

cd ~/notifications_bot
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data
export DB_PATH="$(pwd)/data/bot.db"
export BOT_TOKEN="1234567890:AA..."
export ADMIN_ID="123456789"
export TZ="Europe/Berlin"
python main.py

===============================================================================
РОЛИ И ПОВЕДЕНИЕ

Админ (по ADMIN_ID в .env) видит админ-меню.

Любой новый пользователь при /start попадает в «заявки».

Админ одобряет заявку → бот просит имя → сохраняет пользователя → выдаёт доступ.

Админка: список пользователей и заявок, установка дат окончания, дашборд, глобальные тумблеры уведомлений
(за 3 дня / в день / после).

===============================================================================
ПОЛЕЗНЫЕ КОМАНДЫ DOCKER

docker compose ps # статус контейнеров в проекте
docker compose logs -f # логи (follow)
docker compose restart # перезапуск
docker compose down # стоп + удалить контейнеры/сеть (данные в ./data сохраняются)
docker exec -it notifications_bot-bot-1 sh # войти внутрь контейнера

Диагностика прав на data:
ls -ld data
stat -c '%u:%g %a %n' data

Проверка переменных:
grep -E '^(UID|GID|BOT_TOKEN|ADMIN_ID|DB_PATH)=' .env

===============================================================================
ЧАСТЫЕ ОШИБКИ

sqlite3.OperationalError: unable to open database file
• Проверь, что монтируется ИМЕННО каталог ./data на /data (а не отдельный файл).
• Проверь права каталога data: владелец UID:GID из .env, режим не строже 770.

Контейнер не стартует из-за user: "${UID}:${GID}"
• В .env должны быть числа (например, UID=1000, GID=1000), а не строки вида $(id -u).

.env отсутствует или неверные права
• Создай .env и выставь chmod 600. Никогда не коммить .env в git.

===============================================================================
БЕЗОПАСНОСТЬ ПО УМОЛЧАНИЮ
Корневая ФС контейнера read_only: true.
Запись разрешена только в /data и системные tmpfs.
cap_drop: ALL, no-new-privileges: true.
Порты наружу не открываются (бот сам ходит к Telegram по long-poll).
Секреты только в .env (права 600), не в репозитории.