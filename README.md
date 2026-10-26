# ss-zapret2 для Podkop

![Zapret2 Version](https://img.shields.io/badge/zapret2-v1.0.6-red)

Минимальный форк [vernette/ss-zapret2](https://github.com/vernette/ss-zapret2) для локального использования на OpenWrt NanoPi R76S вместе с Podkop. Образ остаётся универсальным Linux-контейнером: пути и настройки конкретного роутера в него не зашиты.

Основные отличия от upstream:

- наружу публикуется только SOCKS5 на loopback хоста, по умолчанию `127.0.0.1:1081`, TCP и UDP;
- внутренний Shadowsocks-сервер слушает только loopback контейнера и не публикуется;
- `shadowsocks-rust` берётся из стабильного Alpine 3.21 `community` вместо `shadowsocks-libev` из `edge/testing`;
- версия zapret2 задаётся build arg `ZAPRET_TAG`, а не требует изменения `Dockerfile`;
- GHCR CI собирает `linux/amd64` и `linux/arm64`.

## Архитектура

```text
Podkop / sing-box
      │  SOCKS5 TCP + UDP
      ▼
127.0.0.1:1081 на OpenWrt
      │  Docker publish только на host loopback
      ▼
sslocal ── Shadowsocks по loopback контейнера ──► ssserver
                                                     │
                                                     ▼
                                             zapret2 / nfqws2
                                                     │
                                                     ▼
                                                  Интернет
```

Порт `1081` не конфликтует с текущим ByeDPI на `127.0.0.1:1080`. У контейнера отдельное сетевое пространство имён, поэтому его правила `nftables`/`iptables` не должны менять сеть хоста или контейнер ByeDPI.

### Почему `shadowsocks-rust`

Решение основано не на недоказанном обещании большей скорости, а на воспроизводимости и поддержке:

- Alpine 3.21 содержит `shadowsocks-rust` 1.21.2 для `x86_64` и `aarch64` в стабильном `community`;
- upstream-контейнер устанавливает `shadowsocks-libev` из меняющегося `edge/testing`;
- официальный `shadowsocks-rust` поддерживает SOCKS5, `-U@@ (TCP+UDP) и `--dns@@;
- CLI используется напрямую, без генерации JSON и связанных с ней проблем экранирования.

Цена решения — примерно 10 МБ установленных бинарников `sslocal`/`ssserver` вместо более компактного libev runtime. Нагрузочное преимущество не заявляется без отдельного теста на NanoPi; совместимость подтверждается multi-arch сборкой и проверками TCP/UDP/DNS.

> [!CAUTION]
> В режиме `nfqws` контейнер работает только на Linux из-за отсутствия `nfqueue` на других ОС

## Содержание

- [Быстрый старт](#быстрый-старт)
  - [Предварительные требования](#предварительные-требования)
  - [Установка и запуск](#установка-и-запуск)
- [Изменение конфигурации](#изменение-конфигурации)
- [Расширенные возможности](#расширенные-возможности)
  - [Поиск стратегий](#поиск-стратегий)
  - [Custom.d скрипты](#customd-скрипты)
  - [Lua](#lua)
  - [Fake-файлы](#fake-файлы)
  - [Проверка работы стратегий](#проверка-работы-стратегий)
  - [Интеграция с прокси-клиентами](#интеграция-с-прокси-клиентами)
- [Обновление и откат](#обновление-и-откат)
- [Синхронизация с upstream](#синхронизация-с-upstream)
- [Работа Instagram в браузере](#работа-instagram-в-браузере)
- [Сценарии использования](#сценарии-использования)
- [Разработка](#разработка)
- [Вклад в разработку](#вклад-в-разработку)
- [Предупреждение про Shadowsocks и SOCKS5](#предупреждение-про-shadowsocks-и-socks5)
- [Благодарности](#благодарности)

## Быстрый старт

### Предварительные требования

1. Установка git:

```bash
# Ubuntu/Debian
sudo apt install git

# Fedora
sudo dnf install git

# Arch Linux
sudo pacman -S git
```

2. Установка Docker Engine и Compose plugin. Для OpenWrt используйте пакеты своей прошивки; не запускайте установочный скрипт для обычного Linux на OpenWrt.

Для обычного Linux:

```bash
bash <(wget -qO- https://get.docker.com)
```

### Установка и запуск

1. Клонируйте репозиторий:

```bash
git clone https://github.com/rsnorlax/ss-zapret2
cd ss-zapret2
```

2. Скопируйте стандартный конфиг zapret2:

```bash
cp config.default config
```

3. Cоздайте `.env` файл. За основу можно взять `.env.example`:

```bash
cp .env.example .env
nano .env
```

Пример содержимого `.env`:

```env
ZAPRET_TAG=v1.0.6                           # Build arg, Dockerfile менять не нужно
SS_PORT=8388                                # Внутренний порт Shadowsocks
SOCKS_PORT=1081                             # Loopback-порт SOCKS5 для Podkop
SS_PASSWORD=change-me-before-use            # Внутренний ключ sslocal <-> ssserver
SS_ENCRYPT_METHOD=chacha20-ietf-poly1305    # Метод шифрования
SS_TIMEOUT=300                              # Таймаут подключения
SS_VERBOSE=0                                # 1 включает подробные логи
DNS_SERVER=1.1.1.1                          # DNS для удалённого резолвинга ssserver
```

> [!NOTE]
> `SS_PORT` не публикуется на хост. Он нужен только для связи двух процессов внутри контейнера. Пустой `DNS_SERVER` включает системный resolver контейнера.

Список переменных окружения в `docker-compose.yml`:

| Переменная                                  | Compose / `.env.example` | Назначение |
| ------------------------------------------- | --------------------- | ---------- |
| `ZAPRET_TAG`                                | `v1.0.6`              | Release tag zapret2 для сборки |
| `SS_PORT`                                   | `8388`                | Внутренний порт Shadowsocks |
| `SOCKS_PORT`                                | `1081`                | SOCKS5 для Podkop; TCP и UDP |
| `SS_PASSWORD`                               | обязательна           | Внутренний ключ Shadowsocks |
| `SS_ENCRYPT_METHOD`                         | `chacha20-ietf-poly1305` | Метод Shadowsocks |
| `SS_TIMEOUT`                                | `300`                 | Таймаут в секундах |
| `SS_VERBOSE`                                | `0`                   | `1` включает подробные логи |
| `DNS_SERVER`                                | пусто / `1.1.1.1`       | DNS resolver для `ssserver` |

4. Соберите и запустите контейнер:

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

На хосте должны появиться только `127.0.0.1:1081/tcp` и `127.0.0.1:1081/udp`. Фиксированного `container_name` нет, поэтому отдельный Compose project можно поднять параллельно для теста.

## Изменение конфигурации

Для внесения изменений в конфиг открываем его в текстовом редакторе:

```bash
nano config
```

Стратегия меняется в переменной `NFQWS2_OPT`, например:

```
NFQWS2_OPT="
--filter-tcp=80 --filter-l7=http --payload http_req --lua-desync=http_methodeol --new
--filter-tcp=443 --filter-l7=tls --payload=tls_client_hello --hostlist-domains=youtube.com,googlevideo.com,youtubei.googleapis.com --lua-desync=multisplit:pos=10:seqovl=1 --new
--filter-tcp=443 --filter-l7=tls --payload=tls_client_hello --lua-desync=multidisorder:pos=2 --new
--filter-udp=443 --filter-l7=quic --payload=quic_initial --lua-desync=fake:blob=fake_default_quic:repeats=6
"
```

- `--filter-tcp=80` - стратегия для всего HTTP трафика
- `--filter-tcp=443 ... --hostlist-domains=youtube.com,googlevideo.com,youtubei.googleapis.com` - стратегия для HTTPS для определенных доменов
- `--filter-tcp=443` - стратегия для всего остального HTTPS трафика
- `--filter-udp=443` - стратегия для всего HTTP3 (QUIC) трафика

После внесения изменений не забудьте перезапустить контейнер:

```bash
docker compose restart
```

## Расширенные возможности

### Поиск стратегий

Перед поиском стратегий нужно обязательно остановить zapret2 командой, чтобы поиск шёл без модификации трафика:

```bash
docker compose exec ss-zapret2 sh /opt/zapret2/init.d/sysv/zapret2 stop
```

Как и в оригинальном проекте, поиск стратегий осуществляется скриптом `blockcheck2.sh`. Этот скрипт подбирает оптимальные стратегии для вашего домашнего/хостинг провайдера:

```bash
docker compose exec ss-zapret2 sh /opt/zapret2/blockcheck2.sh
```

> [!TIP]
> К скрипту поиска можно применять дополнительные параметры. Более подробно в [оригинальном репозитории](https://github.com/bol-van/zapret?tab=readme-ov-file#%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0-%D0%BF%D1%80%D0%BE%D0%B2%D0%B0%D0%B9%D0%B4%D0%B5%D1%80%D0%B0)

Пример запуска с параметрами:

```bash
docker compose exec ss-zapret2 sh -c 'REPEATS=8 DOMAINS="amnezia.org discord.com" /opt/zapret2/blockcheck2.sh'
```

#### Поиск стратегий для HTTP, HTTPS TLS 1.2, без HTTPS TLS 1.3 и HTTP3 (QUIC). Подходит для сайтов, которые не поддерживают TLS 1.3 (таких мало, но они есть)

```bash
docker compose exec ss-zapret2 sh -c 'SKIP_DNSCHECK=1 SECURE_DNS=0 IPVS=4 ENABLE_HTTP=1 ENABLE_HTTPS_TLS12=1 ENABLE_HTTPS_TLS13=0 ENABLE_HTTP3=0 REPEATS=8 PARALLEL=1 SCANLEVEL=standard BATCH=1 DOMAINS="amnezia.org discord.com" /opt/zapret2/blockcheck2.sh'
```

#### Поиск стратегий для HTTPS TLS 1.3, без HTTP, HTTPS TLS 1.2 и HTTP3 (QUIC). Подходит для большинства сайтов и серверов YouTube

```bash
docker compose exec ss-zapret2 sh -c 'SKIP_DNSCHECK=1 SECURE_DNS=0 IPVS=4 ENABLE_HTTP=0 ENABLE_HTTPS_TLS12=0 ENABLE_HTTPS_TLS13=1 ENABLE_HTTP3=0 REPEATS=8 PARALLEL=1 SCANLEVEL=standard BATCH=1 DOMAINS="xxxxxx.googlevideo.com" /opt/zapret2/blockcheck2.sh'
```

Вместо `xxxxxx.googlevideo.com` можно указать адрес ближайшего GGC сервера, который можно найти командой (требуется установленный `curl` и `jq`):

```bash
curl "https://www.youtube.com/youtubei/v1/player" \
  --silent \
  --request POST \
  --json '{"videoId":"dQw4w9WgXcQ","context":{"client":{"clientName":"ANDROID","clientVersion":"21.02.35","androidSdkVersion":30,"userAgent":"com.google.android.youtube/21.02.35(Linux;U;Android11)gzip","osName":"Android","osVersion":"11"}}}' \
  --proxy socks5h://127.0.0.1:1081 |
  jq -r ".streamingData.serverAbrStreamingUrl" |
  awk -F'/' '{print $3}'
```

> [!NOTE]
> Обратите внимание, что запрос мы делаем через локальный прокси контейнера

После завершения поиска стратегий запустите zapret2 командой:

```bash
docker compose exec ss-zapret2 sh /opt/zapret2/init.d/sysv/zapret2 start
```

Либо перезапустите контейнер:

```bash
docker compose restart
```

#### blockcheckw

В контейнер интегрирован [blockcheckw](https://github.com/rcd27/blockcheckw). Это форк `blockcheck2` от [rcd27](https://github.com/rcd27), написанный на Rust.

Для его работы в конфиге необходимо переключить `FWTYPE` на `nftables`:

```bash
FWTYPE=nftables
```

Пример запуска:

```bash
docker compose exec ss-zapret2 sh -c "blockcheckw -w 32 scan -d rutracker.org | blockcheckw check -d rutracker.org --take 10"
```

Более подробная документация описана в оригинальном репозитории.

### Custom.d скрипты

После первого запуска контейнера в директории проекта будет создана директория `scripts`:

```
scripts
├── custom.d
└── examples
    ├── 10-keenetic-udp-fix
    ├── 20-fw-extra
    ├── 40-webserver
    ├── 50-dht4all
    ├── 50-discord-media
    ├── 50-nfqws-ipset
    ├── 50-quic4all
    ├── 50-stun4all
    └── 50-wg4all
```

Для того, чтобы использовать эти скрипты, необходимо скопировать их из директории `examples` в директорию `custom.d`. Например, скопируем скрипты для Discord и Stun (Telegram, WhatsApp):

```bash
cp scripts/examples/{50-discord-media,50-stun4all} scripts/custom.d
```

После чего необходимо перезапустить контейнер, чтобы скрипты применились:

```bash
docker compose restart
```

### Lua

После первого запуска контейнера в директории проекта будет создана директория `lua`:

```
lua/
├── zapret-antidpi.lua
├── zapret-auto.lua
├── zapret-lib.lua
├── zapret-pcap.lua
├── zapret-tests.lua
└── zapret-wgobfs.lua
```

Помимо стандартных скриптов, вы можете добавлять собственные lua-файлы для расширения функциональности.

### Fake-файлы

После первого запуска контейнера в директории проекта будет создана директория `fakes` со встроенными в zapret2 фейк-файлами:

```
fakes
├── tls_clienthello_rutracker_org_kyber.bin
├── tls_clienthello_sberbank_ru.bin
├── tls_clienthello_vk_com.bin
├── tls_clienthello_vk_com_kyber.bin
├── tls_clienthello_www_google_com.bin
...
```

Вы можете добавлять в эту директорию собственные fake-файлы и использовать их в стратегиях.

### Проверка работы стратегий

Сначала дождитесь `healthy`: healthcheck выполняет настоящее SOCKS5-приветствие на endpoint, а не проверяет внутренний Shadowsocks-порт.

```bash
docker compose ps
```

TCP и удалённое DNS-разрешение через SOCKS:

```bash
curl --fail --show-error --socks5-hostname 127.0.0.1:1081 https://example.com/ -o /dev/null
```

Ключ `--socks5-hostname` принципиален: имя отправляется proxy-серверу, поэтому успех подтверждает TCP и DNS на стороне `ssserver`. Он ещё не доказывает UDP.

UDP ASSOCIATE и DNS-запрос по UDP проверяет автономный probe без сторонних Python-пакетов:

```bash
python3 tests/check_socks_udp_dns.py --host 127.0.0.1 --port 1081 --domain example.com
```

Успешный результат заканчивается строкой `PASS`. После этого отдельно проверяйте нужные домены/приложения: probe доказывает транспорт SOCKS5 TCP+UDP и DNS, но не эффективность выбранной стратегии zapret2 против конкретного DPI.

### Интеграция с прокси-клиентами

В Podkop добавьте SOCKS5 outbound без аутентификации:

- адрес: `127.0.0.1`;
- порт: `1081`;
- UDP: включён.

Это верно, когда Podkop работает на самом OpenWrt-хосте. Для Podkop в другом контейнере `127.0.0.1` укажет на тот контейнер, поэтому понадобится общая Docker network и обращение по имени сервиса; публиковать SOCKS на `0.0.0.0` ради этого не следует.

Примеры интеграции с sing-box, Xray и в существующий проект: [INTEGRATION.md](https://github.com/vernette/ss-zapret/blob/master/INTEGRATION.md)

## Работа Instagram в браузере

Чаще всего IP Instagram будет заблокирован и будет работать только в мобильном приложении.

Чтобы решить эту проблему, нам нужно найти незаблокированный IP и прописать его в `docker-compose.yml` на сервере:

```yaml
ss-zapret2:
  ...
  extra_hosts:
    instagram.com: "незаблокированный_ip"
    www.instagram.com: "незаблокированный_ip"
```

> Например instagram.com: "11.22.33.44"

После чего перезапустить compose, чтобы он прописал изменения в файл `/etc/hosts` контейнера:

```bash
docker compose down && docker compose up -d
```

## Сценарии использования

- **Локальное использование**: Запуск контейнера на домашнем сервере для изолированной работы zapret2 без модификации основной сети
- **Серверное использование**: Развертывание на удалённом VPS как единая точка подключения

## Разработка

Сборка образа с другой версией zapret2 не требует изменения `Dockerfile`:

```bash
docker build --build-arg ZAPRET_TAG=v1.0.6 -t ss-zapret2:v1.0.6 .
```

Для Compose достаточно изменить `ZAPRET_TAG` в локальном `.env` и пересобрать:

```bash
docker compose build --pull
docker compose up -d
```

CI принимает тот же `zapret_tag` при ручном запуске и публикует GHCR-теги `latest`, `vX.Y.Z` и неизменяемый для конкретного коммита `sha-<git-sha>`. На pull request выполняется multi-arch сборка без публикации. После первого push сделайте GHCR package публичным, если образ должен скачиваться на роутер без `docker login`.

## Обновление и откат

Перед обновлением сохраните рабочий `config` и текущий идентификатор образа:

```bash
cp config config.before-update
docker inspect --format '{{.Image}}' "$(docker compose ps -q ss-zapret2)"
```

Локальная сборка новой версии:

```bash
sed -i 's/^ZAPRET_TAG=.*/ZAPRET_TAG=v1.0.6/' .env
docker compose build --pull
docker compose up -d
docker compose ps
```

Для опубликованного образа задайте, например, `SS_ZAPRET2_IMAGE=ghcr.io/rsnorlax/ss-zapret2:sha-<git-sha>` в `.env`, затем:

```bash
docker compose pull ss-zapret2
docker compose up -d --no-build ss-zapret2
```

Откат выполняется той же командой после возврата `SS_ZAPRET2_IMAGE` на предыдущий `sha-...` tag и, если нужно, восстановления `config.before-update`. Не используйте только `latest` как точку отката.

## Синхронизация с upstream

В локальном клоне `upstream` должен указывать на `vernette/ss-zapret2`, а `origin` — на ваш GitHub fork:

```bash
git remote add upstream https://github.com/vernette/ss-zapret2.git
git fetch upstream
git log --oneline --left-right master...upstream/master
git merge upstream/master
```

После merge повторите проверки из раздела выше и multi-arch CI. Обычный merge не переписывает опубликованную историю. Rebase имеет смысл только для ещё не опубликованных локальных коммитов.

## Вклад в разработку

Проблемы базового контейнера сначала сверяйте с [upstream issues](https://github.com/vernette/ss-zapret2/issues). Podkop-профиль этого форка старайтесь сохранять отдельными небольшими коммитами поверх upstream.

## Предупреждение про Shadowsocks и SOCKS5

> [!IMPORTANT]
> Compose публикует SOCKS5 только на `127.0.0.1`. Не меняйте bind на `0.0.0.0` и не открывайте порт в WAN. Внутренний Shadowsocks-порт вообще не публикуется.

## Благодарности

- [bol-van](https://github.com/bol-van) - За zapret2
- [ampetelin](https://github.com/ampetelin) - За [изначальный](https://github.com/ampetelin/ss-zapret) проект
- [rcd27](https://github.com/rcd27) - За blockcheckw
