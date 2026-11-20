# Referências técnicas do JoJo-OS Controller

O controle é um companheiro próprio, separado do APK oficial do IKEMEN. O transporte USB usa `adb reverse` para encaminhar o socket do telefone ao receptor local no PC; precisa de Depuração USB e autorização do computador. O receptor não precisa de um servidor público. [1] [2]

No Bluetooth, o módulo nativo usa `BluetoothHidDevice`, disponível desde API 28, para registrar um gamepad HID. Registro não equivale a conexão; a interface só mostra conectado depois do callback Android. Android recente exige a permissão de conectar Bluetooth. O sistema desregistra o HID quando o aplicativo deixa o primeiro plano, por isso a sessão não é mantida em segundo plano. [3] [4]

O módulo Android local fica em `modules/jojo-controller/`; o Expo autolinka módulos locais desse diretório. A UI TypeScript chama o módulo opcional, que não está no Expo Go e não existe na versão Web. O build Android do Dashboard precisa incluir esse módulo; Preview é somente demonstração de interface. [5] [6]

No IKEMEN, os botões Bluetooth devem ser configurados em Options → Input Settings → Joystick Config. A detecção depende do host e pode exigir um mapeamento SDL compatível. Não foi feita uma detecção física de controle neste ambiente. [7]

## Referências
[1]: https://developer.android.com/tools/adb "Android Debug Bridge e Depuração USB"
[2]: https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/master/docs/user/adb.1.md "Manual AOSP do adb reverse"
[3]: https://developer.android.com/reference/android/bluetooth/BluetoothHidDevice "API Android BluetoothHidDevice"
[4]: https://developer.android.com/reference/android/bluetooth/BluetoothHidDevice.Callback "Callbacks de registro e conexão HID"
[5]: https://docs.expo.dev/modules/autolinking/ "Expo Autolinking de módulos locais"
[6]: https://docs.expo.dev/modules/module-api/ "API Expo Modules e lifecycle Android"
[7]: https://github.com/ikemen-engine/Ikemen-GO/issues/2941 "IKEMEN GO e mapeamentos SDL de controle"
