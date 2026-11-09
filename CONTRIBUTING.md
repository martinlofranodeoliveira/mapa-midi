# Contribuir com o Mapa MIDI

Abra uma issue com o objetivo, versão de Python, comando e resultado observado. Prefira um MIDI sintético mínimo ou um pequeno gerador em vez de arquivos pessoais ou músicas de terceiros.

Para alterações, instale em ambiente separado, execute `python -m unittest discover -s tests -v` e mantenha o contrato de saída e a documentação consistentes. Inclua um oráculo independente quando mudar relógio, pareamento ou leitura de bytes. Uma conversão de ida e volta, sozinha, não demonstra a semântica das notas.

Não acrescente reprodução, acesso a dispositivos ou consultas de rede à inspeção. Propostas que ampliem o subconjunto SMF precisam demonstrar o comportamento no decoder e no consumidor independente. Preserve as licenças e a autoria das dependências.
