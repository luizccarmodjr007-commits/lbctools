# lbctools
Little Big City 1 Modding Tools [Android]
Ferramentas Python — Little Big City 1 (Gameloft J2ME, pacote 800×480)

Três scripts Python para extrair, editar e reimportar os atlas gráficos dos arquivos "s05", "s06" e "s10".

Requisitos: Python 3 e Pillow.

pip install pillow

Os scripts preservam o arquivo original e geram um novo arquivo durante a importação, evitando alterações diretas no recurso de entrada.

1. Visão geral

Script| Arquivo compatível| Origem| Observações
"s06tool.py"| "s06"| Script original| Localiza blocos por heurística. Decodifica 22 dos 24 blocos; os blocos 21 e 22 não são decodificados.
"s05tool.py"| "s05", "s10"| Adaptado de "s08tool.py"| Usa assinatura de 6 bytes e validação compatível com os dois arquivos.
"s10tool.py"| "s10", "s05"| Adaptado de "s05tool.py"| Mesmo mecanismo do "s05tool.py", com aviso específico para paletas que já possuem 255 cores.

Os scripts "s05tool.py" e "s10tool.py" compartilham o mesmo mecanismo de processamento, com diferenças no nome, no cabeçalho e nos avisos específicos.

Recomendação: utilize "s05tool.py" para trabalhar com "s05" e "s10tool.py" para trabalhar com "s10". Para o arquivo "s06", utilize exclusivamente "s06tool.py".

2. Estrutura dos arquivos

Formato binário identificado:

Arquivo:
  u16 N
  u32 1
  u32 offsets[N+1]

Bloco:
  PRE (bytes opacos preservados)
  44 44 02 56 01 01
  u8 npal
  u16 pal[npal]       (ARGB4444 little-endian)
  u16 W
  u16 H
  u32 W*H
  W*H bytes de índices (8 bpp)

Características dos arquivos:

- "s05": 45 blocos.
- "s10": 5 blocos.
- Cada bloco representa um atlas gráfico com vários sprites e sua própria paleta de cores.
- A primeira entrada da paleta é "0F0F", usada como transparente.

Integridade confirmada: nos arquivos testados, exportar, reconstruir sem alterações e comparar o resultado produziu arquivos idênticos byte a byte.

A hipótese de que a seção "PRE" armazena retângulos de sprites, pontos de tiles e frames ainda não foi confirmada.

3. Como utilizar "s05tool.py" e "s10tool.py"

Nos exemplos abaixo, substitua o nome do script e do arquivo conforme o recurso que deseja editar.

Consultar a estrutura

python3 -I s05tool.py info s05

Exibe os blocos, offsets, tamanhos e paletas identificados.

Verificar a integridade

python3 -I s05tool.py verify s05

Verifica a leitura e a reconstrução dos dados, além dos índices de pixels em relação à paleta.

Exportar os atlas gráficos

python3 -I s05tool.py export s05 pasta/

Exporta os seguintes arquivos:

- "bNN.png": atlas em RGBA.
- "bNN_indexed.png": atlas indexado, preservando os índices de cores.
- "manifest.json": informações dos atlas exportados.

Testar a reconstrução

python3 -I s05tool.py roundtrip s05 trabalho/

Exporta e reconstrói o arquivo para comparar os bytes com o original. Código de saída "0" indica que os arquivos são idênticos.

Substituir um atlas inteiro

python3 -I s05tool.py import s05 3 pasta/b03.png s05_novo

O PNG deve manter as dimensões originais do atlas.

Substituir somente uma região

python3 -I s05tool.py import s05 3 sprite.png s05_novo --rect X Y W H

Substitua "X", "Y", "W" e "H" pelas coordenadas e dimensões do recorte desejado.

Reconstruir o arquivo com os atlas editados

python3 -I s05tool.py build s05 pasta/ s05_novo

Aplica as imagens "bNN.png" encontradas na pasta e gera um novo arquivo.

Comparar o original com o arquivo editado

python3 -I s05tool.py diff s05 s05_novo

Mostra as diferenças encontradas em cada bloco, incluindo a seção "PRE", a paleta, as dimensões e os pixels.

4. Opções de importação

- "--rect X Y W H": altera somente a região especificada do atlas.
- "--extend-palette": adiciona cores à paleta existente, quando possível. Pode modificar o tamanho do bloco e do arquivo, exigindo o recálculo dos offsets.
- "--force": permite sobrescrever um arquivo de saída já existente. A saída não pode ser o arquivo original.

Como as cores são convertidas

1. Cores idênticas às da paleta existente mantêm seus índices.
2. Pixels com alfa inferior a 128 são convertidos para o índice transparente "0".
3. Cores novas, sem "--extend-palette", são aproximadas para a cor existente mais próxima.
4. Com "--extend-palette", cores novas são acrescentadas à paleta, respeitando o limite de 255 entradas.

Se o PNG for indexado e possuir uma paleta idêntica à do bloco, os índices originais poderão ser utilizados diretamente, evitando perdas desnecessárias.

5. Procedimento seguro para substituir um sprite

1. Faça uma cópia de segurança do arquivo original:
   
   cp s05 s05.orig

2. Verifique a integridade:
   
   python3 -I s05tool.py verify s05

3. Exporte os atlas gráficos e abra o PNG correspondente no editor de imagens.

4. Preserve as dimensões do atlas e a transparência. Sempre que possível, utilize as cores da paleta original.

5. Importe a imagem editada para um novo arquivo.

6. Compare os arquivos com "diff" e confirme que somente o bloco esperado foi alterado.

7. Execute "verify" no arquivo reconstruído.

8. Teste o resultado no jogo ou em um emulador compatível. A validação dentro do jogo ainda precisa ser realizada.

Atenção: se utilizar "--extend-palette", o tamanho do arquivo poderá mudar. Caso outros recursos ou o código do jogo dependam do tamanho ou dos offsets do arquivo, será necessário verificar essas dependências. Blocos com 255 cores já utilizadas, como o bloco 4 de "s10", não possuem espaço para adicionar novas cores.

6. Uso de "s06tool.py"

O script "s06tool.py" utiliza um método diferente dos outros dois. Ele localiza a paleta por heurística e não consegue decodificar os blocos 21 e 22 do arquivo "s06".

Verificar os blocos

python3 -I s06tool.py verify s06

Lista os blocos como "ok" ou "não decodificado".

Exportar os atlas

python3 -I s06tool.py export s06 saida/

Gera os arquivos PNG correspondentes aos atlas que podem ser decodificados.

Substituir um atlas inteiro

python3 -I s06tool.py import s06 BLOCO nova.png novo_s06

Substitua "BLOCO" pelo número do atlas e "nova.png" pela imagem editada, mantendo as dimensões originais.

Substituir somente um recorte

python3 -I s06tool.py import s06 BLOCO nova.png novo_s06 X Y W H

Os valores "X", "Y", "W" e "H" definem a região a ser substituída.

Limitações do "s06tool.py"

- Não verifica a reconstrução byte a byte.
- Utiliza heurística para localizar a paleta.
- Não permite ampliar a paleta; cores novas são aproximadas para as existentes.
- Não impede a sobrescrita do arquivo original caso o mesmo caminho seja informado como saída.
- Não decodifica os blocos 21 e 22.

Conclusão: utilize "s05tool.py" e "s10tool.py" para editar os respectivos recursos gráficos e "s06tool.py" para o arquivo "s06", sempre mantendo cópias de segurança e validando os arquivos reconstruídos antes de testá-los no jogo.

AVISO: Force o app a rodar em 800x480 caso contrário use o App Cloner