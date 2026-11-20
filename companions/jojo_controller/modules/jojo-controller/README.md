# JoJoController — módulo Expo local Android

Módulo nativo `Name("JoJoController")`, autolinked pela configuração Expo local em `./modules`, apenas para Android. O módulo não habilita permissões em runtime: a aplicação deve pedir `BLUETOOTH_CONNECT` no Android 12+ antes de consultar dispositivos emparelhados ou iniciar HID. Nenhum pareamento, ativação de Bluetooth ou acesso perigoso é iniciado automaticamente.

## API JS

- `capabilities(): Promise<{ androidApi, bluetoothEnabled, hidApiAvailable }>`; se `BLUETOOTH_CONNECT` ainda não foi concedida no API 31+, `bluetoothEnabled` pode ser `false` até a permissão ser dada.
- `listBondedDevices(): Promise<{name,address}[]>`; exige a permissão Android 12+ e lista apenas dispositivos já emparelhados.
- `startBluetooth(address): Promise<void>` valida o endereço MAC e resolve quando o comando foi enfileirado. Os estados `connecting`, `registered` e `connected` são publicados pelo callback HID real via evento `onStatus`; não se declara conectado só por registrar o SDP.
- `connectUsb(token): Promise<void>` exige token hexadecimal minúsculo com 32 caracteres e só resolve depois de estabelecer TCP em `127.0.0.1:8765` e receber `{ "ok": true, "protocol": 1 }` em uma linha NDJSON.
- `setMask(mask): void` é síncrono e aceita inteiros de `0` a `2047`; chamá-lo aproximadamente a cada 100 ms mantém os reports/heartbeat ativos. Após 300 ms sem refresh, o módulo envia uma única máscara neutra e interrompe o heartbeat até novo refresh.
- `disconnect(): Promise<void>` e `openBluetoothSettings(): Promise<void>`.
- `onStatus` envia `{mode:'usb'|'bluetooth'|'none', state:'connecting'|'registered'|'connected'|'disconnected'|'error', message, device?}`.

## Máscara e HID

Bits da máscara: `0 Up`, `1 Down`, `2 Left`, `3 Right`, `4 A`, `5 B`, `6 C`, `7 X`, `8 Y`, `9 Z`, `10 Start`. O descriptor é exclusivamente um gamepad HID em report protocol, Report ID 1: byte 0 = A/B/C/X/Y/Z/Start nos bits 0..6; byte 1 = hat switch nos 4 bits inferiores (0 cima, 1 cima-direita, 2 direita, 3 baixo-direita, 4 baixo, 5 baixo-esquerda, 6 esquerda, 7 cima-esquerda, 8 neutro). Não há reports de teclado nem boot mode. Requisições HID de saída/desconhecidas recebem `reportError`; solicitação de boot protocol libera/desconecta a sessão.

O perfil HID Device requer Android API 28+. App background e destruição do módulo soltam o report, desconectam e removem o registro HID. Callbacks antigos são invalidados por geração de sessão.

## USB/TCP

O app conecta a `127.0.0.1:8765` (por exemplo, encaminhado pelo host com `adb reverse tcp:8765 tcp:8765`). Primeira linha enviada: `{"token":"<32 lowercase hex>","protocol":1}\n`, limitada a 256 bytes; resposta deve ser uma linha JSON versionada com `ok:true`. Em seguida são enviados frames `{"mask":N}\n` em uma única fila serial, a cada 100 ms enquanto o JS mantém o refresh, e imediatamente quando a máscara muda. EOF/falha de escrita encerra e emite status; a thread de leitura é daemon e fecha com o socket.

## Verificação

`python3 tests/check_contract.py` executa verificações estáticas da configuração, permissões e contrato do protocolo. Há testes JVM de `JoJoGamepadReport` em `android/src/test`; o APK nativo, pareamento e conexão física ainda precisam de verificação Android/device. O starter Expo não foi alterado e nenhum APK/release foi construído aqui.
