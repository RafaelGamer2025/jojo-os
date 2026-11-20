# Análise técnica e roadmap — JoJo-OS

## Resumo do passe de correção

O ZIP original era um protótipo com interface interessante, mas continha falhas de caminhos, dependências e escopo. Este passe corrige os defeitos reproduzíveis de maior prioridade e adiciona testes automatizados. Não equivale a uma auditoria formal de segurança nem a uma certificação de “sem bugs”.

### Corrigido nesta rodada

1. **Banco e login:** caminhos ancorados ao projeto; migração de hash legado para PBKDF2; assinatura HMAC; escrita atômica; rotação de chave curta com fallback temporário para não perder o banco em interrupção; falha de integridade não é mais “reparada” re-assinando conteúdo não confiável; cadastro e login de primeiro uso exercitados em uma pasta temporária.
2. **Calculadora:** removido `eval`; agora interpreta somente AST aritmética permitida, com limite de tamanho, expoente e resultado. O efeito “ZA WARUDO” captura temporariamente apenas a janela-alvo em memória para revelar pixels negativos num círculo; não salva nem transmite screenshot. A antiga cópia `core/calc.txt` virou uma nota de descontinuação.
3. **Debugger:** removido `shell=True`; argumentos são passados em lista, há confirmação antes de executar código, timeout de 10 segundos, saída limitada e executáveis de compilação temporários. O próprio aviso continua dizendo que isso **não é um sandbox**.
4. **Terminal e arquivos:** mantidos no workspace do aplicativo, com rejeição de traversal; remoção exige confirmação. Testes cobrem traversal e nomes inválidos.
5. **IA:** cliente lazy, chave opcional, configuração `.env` ancorada à pasta do projeto, mensagens limitadas a 4.000 caracteres, timeout e erros sem despejar detalhes da requisição. A chamada roda em thread e o resultado volta à UI por fila; importar a janela não exige uma chave nem faz chamada de rede.
6. **Interface:** cores do perfil não alteram classes globais; ícones duplicados removidos; escolha dos Stands agora tem rolagem; navegador só aceita HTTP/HTTPS. A antiga tela demonstrativa de antivírus foi substituída pelo scanner local descrito na atualização posterior.
7. **Mini-jogo principal:** movimento usa delta time, personagem fica dentro da tela, há saída por Esc e a opção Kakyoin usa `kakyoin.png` em vez de um nome inexistente. O código foi colocado em `main()` para que importar `games.main` não abra janela/loop.
8. **Demo experimental de ação:** reorganizada sob `experiments/jojo_action_demo`; seus assets foram extraídos do arquivo aninhado após validação de integridade/caminhos; corrigidos caminho dos sprites, áudio opcional, ataque disparado por evento, salto e animação com delta time, limite horizontal e 60 FPS. O ZIP interno redundante foi mantido fora da cópia corrigida.
9. **Piano:** transformado em `PianoWindow` reutilizável, sem abrir janela nem inicializar áudio na importação; notas param ao fechar e sustain foi testado. O ícone foi adicionado à área de trabalho.
10. **Menu/utilitários:** handlers vazios do menu foram conectados ao app; escolha de batalha ganhou rolagem; posição dos ícones é validada e salva atomicamente; efeitos de áudio não interrompem outros canais.
11. **Dependências e documentação:** corrigida a linha inválida `httx`; criadas dependências principais/opcionais, `.env.example`, regras Git contra segredos/dados, README em português e roadmap de evolução.

## Evidências de validação

- `python -m compileall -q -f .`: passou.
- `ruff check .`: passou sem avisos.
- `python -m unittest discover -s tests -v`: **16 testes passaram**.
- Imports do app feitos a partir de `/tmp`, sem depender do diretório atual: passaram.
- Smoke de janelas em Xvfb: área de trabalho/tema, gerenciador, terminal virtual, IA, batalha e calculadora abriram; o tema do perfil não alterou a classe global.
- Cadastro e login de primeiro uso passaram usando diretório temporário; o banco real não foi escrito no teste.
- Coordenadas de ícones inválidas/extremas foram filtradas em configuração temporária; persistência atômica passou.
- O executor do debugger rodou um script benigno com caminho contendo espaços.
- Mini-jogo abriu e saiu sob drivers dummy com `dio`, `dio_teste`, `jotaro` e `kakyoin`.
- A demo experimental carregou nove frames de caminhada por direção, desenhou e encerrou normalmente sob SDL dummy.
- Testes de importação confirmaram que nenhum dos dois jogos nem o piano cria janela/áudio ao ser importado.
- Piano abriu com driver de áudio dummy; tecla, release, sustain, fechamento e ausência de efeitos colaterais ao importar passaram.
- Adaptador de IA sem chave devolveu mensagem clara e não tentou rede.
- Nenhum identificador, senha, hash ou banco de usuário acompanha o pacote limpo.

Os testes ocorreram em sandbox Linux com Python 3.12 e Xvfb/SDL dummy; **não houve validação em uma instalação real do Windows nem chamada real à API Groq**.

## Riscos e limitações que continuam

- **Não é um sistema operacional:** é um app Tkinter com módulos temáticos. Evite apresentá-lo como substituto ou produto de segurança de desktop.
- **Debugger não isolado:** qualquer linguagem executada ainda pode acessar arquivos e recursos do usuário. Para publicação, a opção mais segura é desabilitar a execução arbitrária ou executar em uma VM/container descartável com limites de CPU, memória, rede e filesystem; subprocess + timeout, sozinho, não cria sandbox.
- **Segurança local limitada:** HMAC não criptografa o banco, e a chave fica no mesmo diretório. O sistema ajuda a detectar corrupção acidental, mas não resiste a um atacante com acesso de escrita/leitura à conta do usuário. `data/key_secret.json` também é uma credencial local em texto claro na cópia de desenvolvimento; ela não será incluída no pacote limpo.
- **Propriedade intelectual:** nomes, personagens, logotipos, imagens e áudio de JoJo aparecem no projeto. As licenças dos arquivos não foram auditadas nesta revisão. Não publicar/vender até confirmar direitos ou substituir por conteúdo original/licenciado.
- **SoundFont local:** o arquivo `GeneralUser_GS_v1.471.sf2` não é referenciado pelo código atual; foi excluído do ZIP limpo por tamanho e porque sua licença não foi verificada. O piano distribuído sintetiza os tons com NumPy.
- **IA depende de terceiros:** precisa de chave, internet, conta e modelo habilitado. Não foi testada uma solicitação real. Não envie segredos ou dados pessoais ao provedor.
- **Produto/jogo incompleto:** a batalha é simples e o mini-jogo ainda é uma demo de andar; faltam gameplay de luta integrado, objetivos/progressão, tutorial, save/settings centralizados, áudio mixado, UX de erros e testes de usuário.
- **IKEMEN GO:** o desktop consulta a última release estável oficial quando o motor não existe, verifica SHA-256 e extrai sem sobrescrever arquivos locais. O engine não acompanha o ZIP do JoJo-OS; arquivos de personagens são de terceiros e não são baixados. A validação desta rodada usou um ZIP oficial em pasta temporária, sem iniciar o executável e sem teste nativo em Windows.
- **Persistência — diagnóstico anterior:** os arquivos JSON descritos nesta análise foram migrados para SQLite na atualização de 01/11/2026, registrada abaixo. A revisão inclui testes de migração e backup em diretórios temporários; isso não substitui um teste de recuperação com os dados reais de cada instalação.

## Sugestões para a próxima versão

### Prioridade 1 — reduzir risco e tornar o projeto compartilhável

1. Desabilitar o debugger por padrão em builds públicas; se mantido, movê-lo para um runner isolado real e adicionar teste de tentativa de acesso fora do workspace.
2. Implementar assistente de primeiro uso para gerar chaves locais, não distribuir `key_secret.json`, limitar tentativas de login e oferecer backup/restauração testados.
3. Inventariar cada imagem, som, fonte e código com autor, licença, origem e comprovante; trocar conteúdo de JoJo por IP própria caso o objetivo seja concurso, loja ou distribuição pública.
4. Criar build Windows instalável/testada em máquina limpa, logging rotativo, versionamento e procedimento de atualização/rollback.

### Prioridade 2 — evoluir de protótipo para produto

1. **Concluído em 01/11/2026:** estado da aplicação no SQLite com migração validada de JSON legado. Continua recomendada uma exportação/restauração guiada do banco e da chave HMAC como conjunto consistente.
2. Adicionar uma camada de serviços e testes de integração sem GUI; reduzir lógica de negócio dentro de widgets Tkinter.
3. Fazer o game hub listar apenas executáveis realmente instalados e separar “demo Pygame” de “jogo completo”.
4. Transformar o mini-jogo em um loop jogável: arena, estados de luta, hitboxes, ataques, defesa, cooldowns, vitória/derrota, rematch e dificuldade. Usar spritesheets com licença documentada.
5. Criar configurações de volume/áudio, controles, resolução, idioma, acessibilidade e salvar preferências por usuário.

### Prioridade 3 — acabamento visual e usabilidade

1. Fazer layout responsivo em diferentes resoluções/DPI; adicionar navegação por teclado, foco visível e contraste/accessibilidade.
2. Substituir emojis/ícones inconsistentes por um conjunto de ícones original; adicionar estados vazios, carregamento e mensagens de erro consistentes.
3. Medir startup, memória do piano e uso de CPU; cachear sons conforme necessário e liberar recursos ao fechar janelas.
4. Automatizar `ruff`, `unittest`, varredura de segredos e build em CI, com teste em Windows e Linux em cada release.


## Atualização — 01/11/2026: SQLite e scanner local

Esta atualização substitui as recomendações antigas de “migrar para SQLite” e “antivírus apenas demonstrativo”. Contas, posições de ícones, estado administrativo e histórico de varreduras agora usam `data/jojo_os.db`; arquivos JSON antigos são migrados de forma validada e preservados como backup. A chave HMAC continua separada, pois armazená-la dentro do próprio banco enfraqueceria a verificação de integridade. A migração e a recuperação a partir de backup foram exercitadas em diretórios temporários.

O scanner é uma interface para mecanismos instalados no computador: Microsoft Defender no Windows, via `MpCmdRun.exe`, ou ClamAV quando disponível. A pessoa escolhe arquivo/pasta e confirma antes de começar; o aplicativo não remove nem coloca itens em quarentena, mostra saída/status e guarda um histórico local. Ele não instala mecanismos, não atualiza assinaturas e não substitui proteção em tempo real. O ambiente Linux desta revisão não foi usado para executar uma varredura real; a chamada ao motor deve ser testada na máquina-alvo. As regras de execução e status do Defender e do ClamAV são documentadas em [1], [2] e [3].

Nesta rodada, `compileall`, Ruff e **28 testes unitários** passaram; um smoke de interface em Xvfb confirmou que a janela abre sem disparar uma varredura e que `system_state.json` migra para SQLite e pode ser removido por confirmação. Isso não equivale a homologação em Windows nem a um teste de detecção com arquivo de teste.

### Próximas funcionalidades recomendadas

1. **Backup/restauração guiados:** exportar banco e chave HMAC como um conjunto consistente, com opção de cifrar o arquivo usando uma senha que só a pessoa conhece; validar restauração em cópia temporária antes de substituir dados.
2. **Relatórios de varredura:** busca por período, filtros de detecções/erros, exportação TXT/CSV e botão para abrir o destino no Explorer — sem enviar caminhos a serviços externos.
3. **Agendamento opt-in:** escolher pasta e horário, exibir notificação de início/fim e permitir cancelamento; usar apenas o mecanismo instalado, sem serviço residente escondido.
4. **Quarentena manual e reversível:** somente com escolha e confirmação explícitas, histórico de origem/destino e opção de restauração; nunca apagar automaticamente.
5. **Painel de saúde do mecanismo:** mostrar versão das assinaturas, proteção em tempo real e última atualização sem prometer que o computador está “100% seguro”.
6. **Migração da chave de cadastro administrativa:** guardar somente hash lento e salt no banco, oferecer troca/recuperação e continuar excluindo chaves e `.env` dos pacotes compartilhados.

### Referências do scanner

[1]: https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus "Microsoft Defender — MpCmdRun"
[2]: https://learn.microsoft.com/en-us/powershell/module/defender/get-mpcomputerstatus?view=windowsserver2025-ps "Get-MpComputerStatus"
[3]: https://docs.clamav.net/manual/Usage/Scanning.html "ClamAV — Scanning"

## Atualização — 01/11/2026: fala da IA, navegador com guias e grade

- **Fala da IA:** desativada por padrão. `JOJO_TTS_PROVIDER=auto` usa Fish Audio quando existe `FISH_AUDIO_API_KEY`, com o modelo DIO indicado pelo usuário; sem chave, usa `pyttsx3` local. Ao ativar fala online, o texto da resposta é enviado à API. O segredo fica no `.env`, não no pacote; erros de chave, cota, rede e reprodução são exibidos sem imprimir credenciais. O worker de áudio continua fora da thread Tk. Os testes simulam a API; uma chamada real e áudio audível dependem da chave, da conta e de uma máquina com saída de áudio.
- **Navegador:** Chromium via QtWebEngine opcional, em subprocesso separado do Tkinter. Tem barra de endereço, voltar/avançar, recarregar, início e guias que podem ser abertas, fechadas e movidas. A navegação é limitada a HTTP/HTTPS e cookies/cache não são persistidos. É uma interface própria com convenções comuns de navegadores com guias, não uma cópia de marca ou produto Opera.
- **Grade da área de trabalho:** além de reservar posições distintas, agora a célula considera a largura/altura solicitadas pelos frames Tk com uma margem e reorganiza os ícones depois de desenhá-los. O smoke geométrico encontrou e corrigiu uma colisão entre “Games” e “Internet” que os testes anteriores de coordenadas não detectavam. No Xvfb, os retângulos reais dos 11 ícones JOJO e 10 do tema Hacker não se sobrepõem no tamanho mínimo de 700×700.
- **Pesquisa de vozes abertas:** modelos comunitários de DIO, Diego Brando e Jotaro encontrados são majoritariamente RVC, isto é, conversão de áudio-base e não TTS direto. O código do RVC ser MIT ou o repositório declarar uma licença não confirma os direitos dos pesos/voz de personagem. Não foi encontrado modelo verificável de Johnny Joestar; as fontes e limites estão em `PESQUISA_VOZES_OPEN_SOURCE.md`.
- **Validação desta rodada:** compilação Python, Ruff e **54 testes unitários** passaram na fonte; a API Fish foi testada com mocks, sem chave real ou chamada externa. Um smoke com Chromium carregou uma página HTTP local, confirmou título, criação/fechamento de guias e proteção da última guia. O encerramento sem aviso foi confirmado fechando a janela dentro do loop de eventos Qt; fechar fora dele no harness offscreen não reproduz o ciclo de vida do app.
- **Limites:** não houve chamada real à Fish Audio nem confirmação de áudio audível; o sandbox não tem chave Fish nem voz de sistema instalada. A interface Tk e o Chromium ainda precisam de uma rodada nativa no Windows; o smoke do navegador usou página local e não certifica compatibilidade com todos os sites.

### Próximas melhorias recomendadas

1. Validar a API Fish com uma chave própria e saída de áudio no Windows; avaliar seletor de provedor/voz e verificar direitos do modelo antes de redistribuir o aplicativo.
2. Acrescentar favoritos, atalhos de teclado e restauração de sessão do navegador somente se ativados, preservando o padrão sem cookies/histórico persistentes.
3. Testar grade e fontes em resoluções/DPI diferentes e adicionar navegação por teclado/foco visível.
4. Fazer teste de recuperação guiada do SQLite com a chave correspondente e automatizar a suíte em Windows e Linux.


## Atualização — 02/11/2026: efeitos visuais, arraste e app opcional

- **Calculadora:** clique longo (400 ms) ativa por 7 segundos uma captura em memória só da janela da calculadora; o círculo negativo nasce no centro, cresce até os cantos em 3,5 segundos e mantém a tela congelada pelo restante. Fechar a janela encerra o overlay e seus timers; os cálculos não mudam.
- **Desktop / Za Warudo:** a conta `the world`/`za warudo` também recebe a onda negativa central ao entrar (4 segundos: 3 de expansão e 1 com a área inteira negativa), usando o mesmo componente e cobrindo a área cliente do desktop.
- **Terminal virtual:** `/za_warudo` e `/psychedelic` ativam por 7 segundos uma paleta psicodélica legível e anéis no rodapé. Texto e comandos continuam intactos; a execução permanece restrita ao workspace e nenhum shell externo foi adicionado.
- **Grid e arraste:** o ícone segue o ponteiro em coordenadas do canvas e fica limitado à área visível. Durante movimento real, só o símbolo aparece: labels somem e o fundo/borda do botão se misturam ao desktop; no drop o ícone completo é restaurado. O snap escolhe slot livre, persiste posição e não dispara a abertura do app.
- **Restaurante do Tonio Trussardi:** adicionado como app opcional em Aplicativos → Catálogo. O estado de instalação usa a chave SQLite `optional_apps`, vazia por padrão. O cardápio é fictício/local; instalação/desinstalação não apaga preferências de outros apps.
- **Validação desta rodada:** `compileall`, Ruff e **75 testes unitários** passaram. Smokes Xvfb confirmaram a captura temporária da própria janela, inversão dentro da máscara central até os cantos, restauração automática na calculadora e no desktop Za Warudo. Eventos Tk sintéticos moveram o ícone de uma região ocupada para um slot livre, salvaram no SQLite temporário, não abriram o app e mostraram apenas o símbolo sem retângulo preto; os smokes anteriores de terminal, catálogo e não sobreposição dos temas continuam válidos.
- **Limites:** os smokes gráficos ocorreram em sandbox Linux com Xvfb; não houve teste nativo no Windows. Captura de tela, escala DPI/múltiplos monitores, arraste com mouse físico, fontes e áudio ainda precisam de verificação nativa no Windows.


## Histórico — 07/11/2026: IKEMEN GO como jogo principal

O ícone de jogos do desktop agora abre o hub IKEMEN GO em vez de iniciar a demo de caminhada. O hub não bloqueia a interface: se o executável estiver faltando, consulta `releases/latest` do GitHub oficial, seleciona o pacote estável da plataforma, exige SHA-256 publicado, limita o tamanho, valida os caminhos do ZIP e só então instala em `games/ikemen_go/`. Uma instalação incompleta é reparada copiando apenas arquivos ausentes, sem sobrescrever `chars/` ou `data/select.def`. Instalações antigas em `core/games/jojo_ikemen/` continuam sendo reconhecidas.

O `setup_ikemen_sbr.py` trabalha a partir de seu próprio diretório (ou `--game-dir`), cria as pastas Johnny/Gyro/Diego/Funny Valentine, evita `.def` falsos e registra somente pastas com `.def` e `.sff`. Ele não baixa esses personagens de Steel Ball Run. Em outra etapa, o launcher passou a incluir Naruto e Yuji e instalá-los automaticamente; os arquivos de fã não têm licença explícita de redistribuição e seus créditos ficam registrados.

Validação daquele marco inicial: `compileall` e Ruff passaram; **81 testes unitários** passaram, incluindo checksum simulado, preservação de `select.def`, idempotência e bloqueio de Zip Slip. O ZIP oficial Windows v1.0.0 foi conferido e extraído em pasta temporária; o executável não foi iniciado. Os resultados atuais estão na atualização final no fim deste documento; a validação nativa em Windows continua pendente.


Teste adicional de ponta a ponta: a implementação consultou a API oficial ao vivo, recebeu `v1.0.0` e o SHA-256 publicado, baixou e extraiu o ZIP Windows em `TemporaryDirectory`, copiou o script e criou as quatro pastas de personagens sem inserir entradas falsas. O CLI do `.py` foi executado duas vezes a partir de outro diretório e permaneceu idempotente; o fluxo assíncrono do botão foi verificado em Xvfb com processo simulado. Nenhum executável de jogo foi iniciado.


## Histórico inicial — 07/11/2026: importação local para Naruto e Jujutsu Kaisen

O hub IKEMEN GO agora tem botões para importar pastas locais de Naruto e Jujutsu Kaisen. O importador exige confirmação de uso, valida um `.def` e um `.sff`, rejeita links simbólicos, limita o pacote a 1 GiB e 50 mil arquivos, copia para uma pasta com prefixo da série sem sobrescrever destinos e registra um caminho `.def` explícito em `[Characters]`, preservando um backup `.bak` do `select.def` existente. O recurso não baixa conteúdo nem cria personagens falsos.

Naquele checkpoint, o ZIP ainda não continha personagens reais. Isso foi superado pela atualização final abaixo: Naruto Uzumaki e Yuji Itadori agora estão incluídos com créditos e instalação automática. As fontes e limites continuam em `ANIME_ASSET_SOURCES.md`.

Validação daquele checkpoint: `compileall` e Ruff passaram; **88 testes unitários** passaram. O hub abriu em Xvfb e o fluxo simulado importou uma pasta local. A validação atualizada, com 89 testes e cópia temporária dos dois personagens reais, está documentada na seção seguinte; o motor ainda não foi iniciado e segue pendente a validação nativa em Windows.


## Registro anterior — 07/11/2026: Naruto e Yuji incluídos (superado pela atualização abaixo)

O pacote-fonte agora contém Naruto Uzumaki (edição/pacote de InSeph, com base creditada a BabyDesu) e Yuji Itadori (edição de ScalzerBR, com base creditada a Viniciusonico). Os `.def` tiveram suas referências a `.sff`, `.air`, `.cmd`, `.cns` e `.snd` conferidas, e os arquivos de créditos registram as páginas de origem e SHA-256 dos arquivos recebidos.

No primeiro clique em **JOGAR**, o launcher obtém a release oficial do IKEMEN GO, instala esses dois pacotes em `chars/` e atualiza `data/select.def`. A segunda instalação é idempotente e não sobrescreve pastas existentes. As pastas de Steel Ball Run continuam apenas como preparação até que pacotes reais/autorizados sejam escolhidos; o Gojo não foi incluído porque o host gratuito exigia CAPTCHA.

Validação desta rodada: compilação e Ruff passaram; **89 testes unitários** passaram. Um smoke instalou Naruto e Yuji numa pasta temporária, verificou todos os caminhos referenciados e comprovou que `select.def` não duplica as entradas. O hub abriu no Tk/Xvfb em 800×700. O IKEMEN GO e os personagens não foram iniciados, portanto ainda falta teste nativo no Windows.

As fontes, hashes, créditos e ressalvas de redistribuição estão em [ANIME_ASSET_SOURCES.md](ANIME_ASSET_SOURCES.md). Não foi encontrada licença explícita para redistribuição pública/comercial dos pacotes de fã; esta cópia é para uso local e não deve ser republicada sem autorização.

## Histórico — versão anterior do hub (07/11/2026; superada pela atualização abaixo)

A interface agora tem **INSTALAR SBR** e, logo abaixo, **BAIXAR JUJUTSU** (esquerda) e **BAIXAR NARUTO** (direita). Cada botão de anime configura somente o personagem escolhido, cria/usa `chars/` e atualiza `data/select.def` idempotentemente; o motor IKEMEN é obtido e validado automaticamente quando necessário. Não há seletor de arquivo, etapa de extração nem configuração manual.

Limite importante: os arquivos de Naruto e Yuji são instalados a partir dos pacotes que acompanham esta cópia do JoJo-OS; os botões não fazem um novo download online das páginas MediaFire. A API oficial de link direto exige sessão autenticada e o uso automatizado fora das rotas autorizadas não foi implementado. A pessoa usuária não precisa procurar ou extrair os pacotes incluídos, mas um downloader externo em runtime exigiria uma fonte que permita explicitamente esse fluxo ou integração MediaFire autenticada.

Validação desta alteração: `compileall` e Ruff passaram; **91 testes unitários** passaram. Testes de pacote confirmaram instalação seletiva/idempotente e atualização de `select.def`. Smoke Tk/Xvfb confirmou a ordem visual dos botões e seus callbacks com respostas simuladas, sem executar o IKEMEN GO. O teste nativo do executável Windows continua pendente.


## Histórico — 07/11/2026: botões IKEMEN GO e SBR separados (superado pelo seletor fullscreen)

O botão superior **INSTALAR IKEMEN GO** consulta a release oficial, verifica o SHA-256 e abre o motor sem criar a estrutura SBR. O botão **INSTALAR SBR** chama explicitamente o setup, cria `chars/`, `data/` e as quatro pastas SBR, e só registra `.def`/`.sff` reais. Os personagens Johnny, Gyro, Diego e Funny Valentine ainda não estão instalados nem baixados; o clique informa o que falta. Os botões atuais de Naruto/Jujutsu instalam os pacotes locais já incluídos e não fazem transferência online. Dragon Ball Z e One Piece não foram adicionados como botões funcionais porque as fontes verificadas não forneceram um endpoint de download estável e validado; a pesquisa e os links estão em `ANIME_ASSET_SOURCES.md`.

**Validação desta atualização:** `compileall`, Ruff e **93 testes unitários** passaram. Um smoke Tk/Xvfb confirmou que o botão de cima chama `prepare_jojo_ikemen` sem setup SBR e que o inferior solicita `setup_sbr=True`; os callbacks foram simulados, sem iniciar IKEMEN GO. Um download público de Gyro foi tentado apenas para análise, mas expirou duas vezes antes de completar; não foi usado nem incluído qualquer arquivo parcial. A validação nativa do motor/personagens no Windows permanece pendente.


## Atualização — 07/11/2026: seletor fullscreen e download por personagem

O hub do JoJo-OS agora abre em tela cheia e reúne uma caixa de seleção única para Naruto/Yuji já incluídos, os personagens JoJo disponíveis na árvore GitHub pinada e as opções Goku e Luffy. O botão do personagem prepara o IKEMEN GO se estiver faltando, baixa/instala somente o escolhido, verifica `.def`/`.sff`, rejeita caminhos inseguros e executáveis embutidos, e registra o caminho em `data/select.def`. Repetir a seleção reutiliza o personagem local e repara o registro sem baixar outra cópia. `F11` alterna entre fullscreen e janela; `Esc` sai do fullscreen. **INSTALAR SBR** permanece separado, abaixo do seletor, e só prepara a estrutura SBR.

O Goku usa o fluxo público gratuito do criador Nozywolf no itch.io. O Luffy usa o jogo MUGEN completo de One Piece (455 MB) anunciado pelo criador no itch.io; o código tenta extrair apenas a pasta de Luffy para a instalação existente. A página declara fan game não comercial; o download sob demanda não transfere nem concede direitos autorais, e os arquivos remotos não são embutidos no ZIP do JoJo-OS. Os downloads reais de Goku/Luffy **não foram concluídos nesta sessão**: itch.io respondeu HTTP 429; portanto não se afirma que esses pacotes passaram por CRC/conteúdo reais. A implementação de rede, extração, seleção, tratamento de 429 e registro do `select.def` foi validada com fixtures offline, e a interface foi testada em Xvfb com o downloader simulado.

Primeira execução de validação: `compileall`, Ruff e **102 testes unitários** passaram. O smoke de interface confirmou fullscreen, F11/Esc, presença de Goku/Luffy, posição do botão SBR e encaminhamento da escolha correta. A contagem foi atualizada após acrescentar a regressão anti-rate-limit, registrada abaixo.


Contagem final, após adicionar o teste que assegura respeito ao HTTP 429: `compileall`, Ruff e **103 testes unitários** passaram. O smoke Tk/Xvfb confirmou a lista atualizada com Goku e Luffy e o fluxo simulado de instalação seletiva. A tentativa real de itch.io continuou sem arquivo por rate limit; não houve execução do motor ou de personagens.


## Atualização — bundles de personagens do ZIP enviado (08/11/2026)

O JoJo-OS agora instala seletivamente cinco pacotes que vieram no arquivo fornecido pela usuária: Diego Brando e Funny Valentine (também pelo botão `INSTALAR SBR`), Jotaro M-ISM, Wonder of U e Roronoa Zoro. O restante do jogo completo não foi embutido; o setup cria as pastas canônicas, verifica `.def`/`.sff` e registra os caminhos explícitos no `data/select.def`, sem duplicar numa segunda seleção. Cada pasta mantém um recibo `JOJO_OS_ORIGEM.txt` com autor declarado, origem, SHA-256 e aviso de licença.

O conteúdo chamado `johnny` no pacote enviado credita `salami` e data 2002; não foi identificado como Johnny Joestar. O personagem `zeppeli` dentro da distribuição completa credita Elecbyte e também data 2002; não foi identificado como Gyro. Por isso, `INSTALAR SBR` registra Diego/Funny e informa que Johnny/Gyro continuam pendentes, sem substituí-los por personagens de nome parecido. O Jotaro M-ISM traz uma referência `stcommon=common1.cns` fora do bundle; o motor real ainda precisa ser iniciado para confirmar a resolução dessa dependência.

**Validação desta atualização:** a instalação seletiva dos cinco arquivos reais foi testada em diretórios IKEMEN temporários, com `.def` único no seletor e segunda chamada idempotente; a integração SBR registrou Diego/Funny e manteve Johnny/Gyro pendentes. `compileall`, Ruff e **106 testes unitários** passaram. Smoke Tk/Xvfb confirmou os cinco novos rótulos `INSTALAR`, o botão SBR e as 26 opções disponíveis. Nenhum executável do IKEMEN ou de personagens foi iniciado. Os downloads remotos Goku/Luffy seguem sem confirmação de rede real devido a HTTP 429 no itch.io. A licença formal de redistribuição dos pacotes de fã não foi fornecida/verificada; a integração é para esta cópia local, não uma autorização de republicação.


## Atualização — 08/11/2026: lote de personagens e versão para celular

O hub mantém tela cheia e agora apresenta **BAIXAR TUDO** ao lado da instalação individual: pede confirmação, processa os 26 itens do catálogo em sequência (7 pacotes locais e 19 remotos), reutiliza arquivos já válidos e continua após falhas individuais. A árvore da fonte GitHub é consultada uma vez por lote e só é passada aos personagens dessa fonte. A mensagem final informa itens prontos e falhas; limites externos como HTTP 429 são respeitados, sem scraping alternativo ou instalação de arquivos incompletos.

O botão **BAIXAR VERSÃO PARA CELULAR** consulta a release oficial estável, verifica o SHA-256 publicado, valida o ZIP e o APK e salva o APK Android ARM64 em Downloads para transferência manual ao telefone. A release `v1.0.0` foi baixada temporariamente: ZIP 65.588.398 bytes, SHA-256 `915ee0c8ce96e860e0aab71c505e9ddd2940fe3e1c339e3f30ab4bd69880d47c`; APK 57.615.327 bytes com `AndroidManifest.xml` e bibliotecas nativas arm64 embutidas. Arquivos externos de build não são necessários para o sideload e não são copiados. O APK não foi instalado em aparelho físico nem executado.

Uma troca inválida agora falha antes de substituir um APK Android anterior válido. `compileall`, Ruff e **110 testes unitários** passaram; os novos testes cobrem o lote parcial, a seleção/reutilização do APK e a preservação diante de arquivo inválido. Smoke real de Tk/Xvfb conferiu os três botões principais, o resultado do lote simulado, a restauração dos controles e a mensagem de APK pronto. A tentativa real de Goku/Luffy continua sujeita à resposta HTTP 429 do itch.io; não foi contornado o limite e nenhuma execução do IKEMEN/personagens foi feita.


## Atualização — 08/11/2026: APK oficial + pacote de dados Android separado

A solução móvel agora conserva o APK oficial IKEMEN GO `v1.0.0` separado de `JoJo_OS_Android_DataPack.zip`. O APK tem 57.615.327 bytes e SHA-256 `f3b7d07937cfc9ed9452b9138d0a2b3feba09bfa68faa6450f01cc01c72fc7c9`; contém manifesto Android e dez bibliotecas ARM64, e passou CRC. O arquivo de dados tem 903.007.508 bytes e SHA-256 `2e422b8fbcb4c535e031302d8843141052b8c72538365b278d9c727cb190ff48`. O motor não foi modificado, resignado, instalado ou executado.

O pacote contém 44 personagens já disponíveis: 37 pastas selecionáveis do RAR do jogo presente no ZIP enviado e sete bundles locais já existentes no projeto, totalizando 41 JoJo, um Naruto, um Yuji e um Zoro. Não são 60 e não houve pesquisa/download de personagens novos nesta etapa. A grade base oficial tem 80 células; o pacote mescla as entradas na seção Characters, usa `stages/kfm.def` já presente no APK e inclui `data/common1.cns` do arquivo enviado. Os 1.375 arquivos de payload e o ZIP completo passaram verificação CRC, validação do manifesto e correspondência exata de caixa nas dependências obrigatórias.

A auditoria encontrou e corrigiu três referências do DEF de Narancia que tinham caixa incompatível com os nomes no Android; 16 storyboards opcionais sem arquivos foram desativados. Três ZIP/RAR auxiliares que o motor não carrega diretamente e seis metadados de sistema/nomes com controles foram omitidos e registrados no manifesto. Nenhum executável, stage personalizado sem seus assets ou jogo completo foi incluído. As licenças de redistribuição dos personagens de fã continuam não confirmadas.

O código do wrapper Android confirma que o primeiro início pede uma pasta via seletor do sistema, extrai ali os assets base e usa essa pasta no motor. Por isso, o procedimento entregue é instalar o APK, abrir uma vez e escolher uma pasta pública, fechar o app, extrair o ZIP de dados nessa pasta e reabrir. Uma atualização que reextraia os assets pode exigir reaplicar `data/select.def`. A cópia de 903.007.508 bytes passou pelo copiador de produção, que verifica SHA-256, estrutura/roster e grava atomicamente. `compileall`, Ruff e **119 testes unitários** passaram. Smoke Xvfb verificou o rótulo e mensagem do fluxo Android com evento simulado; a integração não foi testada em aparelho físico.

## 10/11/2026 — JoJo-OS Controller para IKEMEN no PC

A usuária escolheu um app companion próprio para USB + Bluetooth, separado do DroidCast. O projeto móvel Expo/React Native está em `companions/jojo_controller/` na distribuição; o módulo local Kotlin usa TCP por USB/ADB e BluetoothHidDevice como gamepad HID. O APK oficial IKEMEN e o pacote de 44 personagens não foram alterados nesta etapa.

Foram acrescentados `controller_bridge.py`, `controller_window.py` e o botão CONTROLE PELO CELULAR no hub. O receptor Windows usa SendInput apenas com o IKEMEN em foco, códigos de sessão regenerados, loopback, mensagens limitadas, estado completo e timeout. O encaminhamento reverso ADB é removido apenas se pertencente à sessão; o servidor ADB não é encerrado. `INICIAR_CONTROLE_USB.bat` abre o receptor standalone sem abrir o jogo.

O layout móvel tem multitouch, diagonais, seis ataques, Start, separação demo/offline, ajuste de posições dos ataques, atualização de dispositivos pareados e estados oriundos dos callbacks. A revisão identificou `setMask` síncrono no Kotlin versus Promise no JavaScript: a interface passou a importar o contrato local e o envio usa adaptador assíncrono que captura erros síncronos. Foram adicionados três testes de regressão.

Evidência: Ruff/compileall e 139 testes Python passaram usando `/tmp/jojo-os-venv`; 20 são da ponte. Smoke Tk/Xvfb verificou o botão e abertura/fechamento do receptor. No móvel, checagem TypeScript, lint e 33 testes JavaScript passaram; um teste de logout do starter foi ignorado. A exportação Web passou e autolinking Android encontrou `expo.modules.jojocontroller.JoJoControllerModule`. A configuração Expo foi introspectada, com ícone original e permissões necessárias declaradas. Quatro checks estáticos do módulo Kotlin passaram; os testes JVM fornecidos não foram executados, pois o compilador não está disponível. Nada disso equivale a teste de Bluetooth ou USB físicos.

Pendências explícitas: gerar APK nativo pelo Dashboard Android, compilar/validar Kotlin no build real, testar um telefone Android com suporte HID e Windows/IKEMEN em partida. Não foi executado APK, IKEMEN ou binário de personagens. Não existe promessa de latência fixa ou compatibilidade com todo fabricante. Bluetooth precisa Android9+ e suporte HID Device; USB requer ADB e autorização de Depuração USB. Veja o manual do companion para configuração e segurança.

A revisão nativa final apontou duas correções adicionais: a atualização `setMask` agora só acessa a classe Bluetooth HID se API >= 28 e a sessão for Bluetooth, preservando a rota USB em Android anteriores ao HID; o retorno da função termina em `Unit`, alinhado ao contrato TypeScript `void`. Foram adicionadas duas regressões estáticas, totalizando **seis checks nativos aprovados**. A checagem TypeScript e os 33 testes JavaScript foram reexecutados e passaram. Compilação Kotlin/testes JVM/pareamento físico continuam pendentes no build Android real.


## 10/11/2026 — Cleiton OS, Cleiton Store e envio de arquivo GitHub

A skin verde/preta antes chamada incorretamente de “CLEITAN-OS” agora é o perfil **CLEITON OS**. A alternância atualiza título, botão e entrada de Store no menu. A antiga Store JoJo do Restaurante Trussardi segue separada; a Cleiton Store, seu ícone, catálogo de 20 apps e janelas de ferramentas só são acessíveis no perfil CLEITON. Ao trocar para JOJO, janelas Cleiton abertas são ocultadas, instalações e dados locais preservados; as ferramentas não são pré-instaladas.

Catálogo acrescentado: Painel do Sistema; Processos Ativos em somente leitura; Notas Rápidas; Lista de Tarefas; Conversor de Unidades; Gerador de Senhas; Verificador SHA-256; Analisador de Armazenamento; Rede Local; Formatador JSON; Codificador Base64; Analisador de Texto; Calendário Mensal; Conversor de Cores; Calculadora de Porcentagem; Filtro de Linhas por glob; Conversor de Data/Hora; Analisador CSV; Codificador URL; Gerador de UUID. Operações são locais e usam whitelist. A lista de processos não encerra processos e a ferramenta de rede não faz varredura. Notas e tarefas guardam texto no SQLite local.

O `ENVIAR_ARQUIVO_GITHUB.bat` aceita caminho como argumento ou drag-and-drop, requer clone Git em branch normal com origin GitHub, recusa stage não vazio e caminho de pasta/fora do repositório, prepara apenas o arquivo escolhido, cria commit e faz push sem force. Não inclui credenciais e valida o domínio remoto sem imprimir URL. Seus testes são estáticos em Linux; a execução real do BAT precisa de teste em Windows e de uma instalação Git/Git Credential Manager autenticada.

Evidências: compileall e Ruff passaram; **149 testes Python** passaram, sendo seis testes Cleiton e quatro testes estáticos do BAT; smoke Tk/Xvfb confirmou Store de 20 cards, instalar/abrir, título/menu específico por perfil, ícone Cleiton ausente em JoJo e janelas ocultadas ao trocar. Verificadores estáticos e smoke não equivalem a teste de arquivo enviado a um GitHub real.


## Atualização — 14/11/2026: despertar de Stand no cadastro

O primeiro cadastro e cada novo fluxo **CADASTRAR** agora começam numa janela Tk em tela cheia com as escolhas **Sim**, **Não** e **Quero ser um hacker**. Sim sorteia um cartão entre 33 Stands, executa uma animação de virar a carta e mostra o nome e um símbolo vetorial desenhado no Canvas; Não continua sem Stand; a escolha hacker grava o perfil visual `CLEITON` para o usuário e não concede papel administrativo ou capacidades de invasão. O caminho administrativo de chave Requiem permanece separado.

O catálogo está em `core/stand_awakening.py`: 22 Stands associados aos Arcanos do Tarô, nove Stands egípcios e dois adicionais de Stardust Crusaders (Cream e Tenore Sax). Inclui Star Platinum e The World como Stands separados; a descrição de Star Platinum observa sua técnica “Star Platinum: The World”, sem duplicá-lo como personagem. Cada conta nova guarda `stand`, cores de tema e `os_profile`; a janela principal recebe esses campos no login, restaura Cleiton OS quando escolhido e continua aceitando contas antigas (JOJO, sem Stand salvo). O sistema de batalha e a lista de escolha aceitam todos os 33 novos nomes além dos cinco perfis de combate já existentes.

**Evidência:** 160 testes unitários passaram, incluindo 6 do catálogo, 3 de cadastro/login e 2 da batalha; Ruff e `compileall` da árvore inteira também passaram. Smoke Xvfb testou o tamanho real da janela, os três botões, o fluxo de cadastro, e animações para Silver Chariot (Arcano do Carro) e Geb (deuses egípcios), além da troca de perfil CLEITON/JOJO. Nenhum jogo foi iniciado. A ilustração é simbólica vetorial original, não artwork oficial. O teste ocorreu no sandbox Linux; compatibilidade visual, teclado e DPI no Windows real ainda precisa ser conferida.
