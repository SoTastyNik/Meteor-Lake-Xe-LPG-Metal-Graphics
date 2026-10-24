Графика Meteor Lake для HUAWEI MateBook 14 (FLMH-XX, Core Ultra 5 125H, Intel Arc 8086:7D55)
Порт проекта VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics (Dell Latitude 5350, 8086:7D45).
Экспериментальная сборка. На этом ноутбуке пока НЕ проверялась.

Что адаптировано под MateBook:
- ID видеокарты 7D55 и подсистема HUAWEI 19E5:3E71 во всех проверках: ядро NMXGPU (i915),
  LatitudePanelClaim, LatitudeMTLFB, Metal-плагин, Mesa ANV, утилиты (huawei-port/apply_identity.py).
- EDID панели EDO142 (OLED 2880x1920, 300x200 мм) вместо панели BOE от Dell.
- Минимум яркости PWM 6/255 по VBT ноутбука (у Dell 15/255).
- Свой установщик для чистой системы (у Dell он обновлял только их машину).

Требования:
- macOS Sequoia 15 (у автора проверена 15.8.1 / 24H32), загрузка через графический EFI:
  csr-active-config 0x0A43, AMFIPass, LatitudePanelClaim.kext в EFI.
- Резервная копия важных данных. Драйвер ставится в Auxiliary Kernel Collection.

Установка (в macOS, из папки пакета):
  sudo /bin/bash install.sh
Скрипт проверит ноутбук, соберёт и проверит Aux KC, сделает резервную копию и включит ОДНУ
загрузку с ускорением. Ничего не перезагружает сам.
Затем перезагрузиться через ту же флешку (без сброса NVRAM).

После загрузки (удачной или нет):
  sudo /bin/bash collect.sh --test
и прислать папку reports/collect-*.

Если экран не загрузился: выключить ноутбук кнопкой и включить снова через флешку.
Одноразовые флаги уже израсходованы, поэтому macOS запустится с обычным экраном прошивки.
Откат установки: sudo /bin/bash uninstall.sh
