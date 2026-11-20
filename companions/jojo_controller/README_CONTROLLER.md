# JoJo-OS Controller

Este projeto é o app Android companheiro para controlar o **IKEMEN GO no computador**. Não é o APK do jogo nem uma alteração do DroidCast. Tem direcional de oito direções, seis ataques simultâneos A/B/C/X/Y/Z, Start, layout remapeável e tela de conexão USB ou Bluetooth.

## App Android e build

O código foi preparado como app Expo/React Native com um módulo Kotlin local em `modules/jojo-controller/`. **É necessário gerar um build Android no Dashboard do projeto Manus e instalar o APK resultante.** O Expo Go não contém esse módulo. O Preview Web permite testar o layout, mas não envia comandos ao computador e não verifica Bluetooth ou USB físicos.

A configuração mantém os identificadores gerados do projeto. O build deve autolinkar `expo.modules.jojocontroller.JoJoControllerModule`. O APK oficial IKEMEN permanece separado e intacto. Nenhum APK companion compilado deve ser apresentado como pronto antes de um build Android bem-sucedido. Não há teste em telefone/PC Windows real nesta entrega.

## USB: cabo de dados e receptor no Windows

No JoJo-OS atualizado, abra o hub IKEMEN e clique em **CONTROLE PELO CELULAR**. Na janela de controle, configure o caminho do `adb.exe` oficial caso ainda não esteja disponível. As [Platform Tools oficiais](https://developer.android.com/tools/releases/platform-tools) incluem essa ferramenta. Só use fontes oficiais para os drivers e o ADB.

Conecte seu Android com um cabo que transporte dados. Ative **Depuração USB** em Opções do desenvolvedor e autorize apenas o seu computador. No receptor, inicie a sessão USB e copie o código exibido. No app Android, escolha USB, insira o código e toque em conectar. O código muda a cada sessão. Se houver mais de um telefone USB, deixe conectado apenas o desejado.

O receptor ouve somente em `127.0.0.1:8765`. O ADB cria o encaminhamento reverso da mesma porta no telefone. A primeira linha JSON é `{"token":"<32 hex minúsculos>","protocol":1}`; o receptor responde `{"ok":true,"protocol":1}`. Depois o app envia `{"mask":<0..2047>}` com estados completos, ao alterar os botões e em intervalos de aproximadamente 100 ms. Não há Wi-Fi nem serviço cloud no caminho dos comandos USB.

Abra o IKEMEN no PC, mantenha sua janela em primeiro plano e configure as teclas em Input Settings caso sejam diferentes. A ponte converte os botões em entradas de teclado; **não cria um controle XInput virtual**. Padrão sugerido: direções=setas, A=Z, B=X, C=C, X=A, Y=S, Z=D e Start=Enter. O mapa é ajustável no receptor, sem substituir sua configuração do IKEMEN.

Em erro, perda de foco ou desconexão, a ponte libera as teclas. Depois de perder o foco, solte todos os botões antes de retomar o jogo. Feche a sessão no app e no receptor ao terminar; você pode desligar a Depuração USB. Não é necessário executar o jogo ou receptor como administrador. O Windows pode impedir injeção se o jogo estiver elevado e o receptor não estiver.

## Bluetooth: gamepad HID Android

Requer Android 9 ou posterior, perfil HID Device efetivamente suportado pelo fabricante, Bluetooth no computador e pareamento entre telefone e PC. O modo é **Bluetooth clássico HID**, não Bluetooth LE, nem conexão por uma porta serial.

Pareie telefone e computador nos ajustes. No app, selecione Bluetooth, conceda a permissão de conexão Bluetooth quando solicitada, atualize a lista de pareados, escolha seu PC e conecte. Aguarde o estado real **CONECTADO**, que vem do callback Android. Registro HID ou uma chamada bem-sucedida ainda não significa que o computador está conectado.

Configure o controle no IKEMEN em **Options → Input Settings → Joystick Config**. O gamepad anuncia report ID 1 com botões HID 1–6 para A/B/C/X/Y/Z, botão 7 para Start e hat switch de oito posições para o direcional. Neste modo, o receptor USB não participa: o Windows recebe diretamente os reports HID.

O suporte do fabricante e o mapeamento SDL do IKEMEN precisam ser verificados no equipamento real. Se o controle não aparecer, confira primeiro o painel de controles do Windows e só depois o mapeamento no jogo. Mantenha o app em primeiro plano; ao sair dele, a sessão é encerrada por segurança e pelo comportamento da API HID. Volte e toque em conectar novamente. Não há promessa de latência fixa ou suporte universal.

## Proteção contra botões presos

Estados completos neutralizam direções opostas. O app envia neutro ao cancelar os toques, mudar de tela, encerrar ou ir para segundo plano. O módulo nativo possui watchdog para limpar comandos se o JavaScript parar de atualizar o estado. O receptor USB fecha a conexão e libera as teclas se faltar atualização por cerca de 0,5 segundo. Desligar ou travar um aparelho ainda precisa de teste físico para validar o comportamento completo do driver.

## Fontes e continuação

Fontes do app: `app/`, `components/fight-pad.tsx`, `hooks/use-controller.ts`, `lib/controller-*.ts` e `modules/jojo-controller/`. Receptor Windows: fontes Python `core/games/controller_bridge.py` e `controller_window.py` do JoJo-OS, com integração no hub.

Use `pnpm check`, `pnpm lint` e `pnpm test` para checar o JavaScript. `expo-modules-autolinking resolve --platform android` confirma descoberta da ponte local, mas **não compila Kotlin nem prova pareamento HID**. O build nativo e um teste real de partida são a etapa restante antes de considerar o controle pronto para uso final. As [referências técnicas](REFERENCIAS.md) documentam as APIs utilizadas.
