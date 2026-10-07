import { NeighborhoodGlyph } from '../ui/icons'
import { DOCUMENTED } from './content'
import type { AboutCopy } from './content'
import { Formula, Strong, Ui } from './primitives'

const decimal = (value: number, digits: number) => value.toFixed(digits).replace('.', ',')

export const aboutPtBR: AboutCopy = {
  kicker: 'Sobre',
  title: 'Simulação de cheias no Vale do Taquari, uma célula de cada vez',
  lede: (
    <>
      O Terranova simula como o rio Taquari se espalha sobre o terreno entre Lajeado e Estrela. Ele usa um{' '}
      <Strong>autômato celular macroscópico</Strong>: o vale vira uma grade de células, e cada célula repassa água aos
      vizinhos por uma regra local simples. O objetivo é um mapa de inundação rápido o bastante para ser recalculado
      muitas vezes, preciso o bastante para inspirar confiança e construído apenas com dados públicos.
    </>
  ),
  credits:
    'Trabalho de Conclusão de Curso (TCC), Engenharia de Software, Univates · Lucca Coutinho Heineck · Orientador: Prof. Me. Edson Moacir Ahlert',
  openSimulator: 'Abrir o simulador',
  howToUse: 'Como usar',
  onThisPage: 'Nesta página',
  nav: {
    'about-problem': 'O problema',
    'about-model': 'O modelo',
    'about-engines': 'Dois motores',
    'about-data': 'Dados',
    'about-usage': 'Como usar',
    'about-limits': 'Limitações',
  },

  problem: [
    <>
      Em setembro de 2023 e novamente em maio de 2024, o Vale do Taquari inundou além do recorde de 1941. Em maio de
      2024, o rio em Lajeado e Estrela subiu de 13,00 m para {decimal(DOCUMENTED.peakStageM, 2)} m em 72 horas.
    </>,
    <>
      Modelos hidrodinâmicos que resolvem as equações completas de águas rasas (o HEC-RAS 2D, por exemplo) são
      precisos, mas lentos e caros de executar. Numa emergência, é preciso perguntar &ldquo;e se o rio chegar a este
      nível?&rdquo; muitas vezes, e rápido. Este projeto investiga se um autômato celular, rodando sobre dados públicos
      de terreno, uso do solo e postos fluviométricos, consegue desenhar uma mancha de inundação útil numa fração desse
      tempo.
    </>,
  ],

  model: {
    intro: (
      <>
        Cada célula guarda dois números: a elevação do terreno <Formula>Z</Formula>, que nunca muda, e a lâmina
        d&rsquo;água <Formula>H</Formula>, que muda. A cada passo, todas as células aplicam a mesma regra ao mesmo
        tempo:
      </>
    ),
    stepLabel: (n) => `Passo ${n}`,
    steps: [
      {
        title: 'Encontrar a superfície da água',
        body: (
          <>
            <Formula>WSE = Z + H</Formula>. A água só escoa morro abaixo sobre essa superfície, de um nível d&rsquo;água
            mais alto para um mais baixo.
          </>
        ),
      },
      {
        title: 'Dividir o escoamento',
        body: (
          <>
            <span className="mb-1.5 flex items-center gap-2 text-ink">
              <NeighborhoodGlyph kind="moore" /> 8 vizinhos (Moore)
            </span>
            Os vizinhos mais baixos recebem uma parcela ponderada pela equação de Manning, <Formula>√S / n</Formula>:
            ganha o mais íngreme e mais liso. As diagonais contam sua distância maior.
          </>
        ),
      },
      {
        title: 'Mover a água',
        body: 'O volume que sai de uma célula é somado aos vizinhos. Nada é criado nem perdido: o volume total só muda pelo que o rio traz e pelo que sai pelo exutório.',
      },
    ],
    outro: (
      <>
        Essa última propriedade, a conservação de massa, é a principal verificação de corretude do modelo. Durante uma
        simulação de maio de 2024, a linha do tempo a mostra ao vivo como o <em>balanço</em>: o volume menos a entrada
        líquida, que fica no nível do erro de arredondamento.
      </>
    ),
  },

  engines: {
    intro:
      'O aplicativo roda o mesmo terreno e a mesma rugosidade em dois motores que respondem a perguntas diferentes. Ambos são avaliados contra a mancha observada da cheia de maio de 2024 na grade de 90 m.',
    csiAtPeak: 'CSI no pico',
    runTime: 'Tempo de execução, 90 m',
    temporal: {
      name: 'AC temporal',
      tagline: 'Como a cheia se desenvolve?',
      body: 'O autômato celular passo a passo descrito acima. Cada passo cobre um intervalo real de tempo derivado do escoamento de Manning, então a simulação acompanha o hidrograma real de maio de 2024 hora a hora e transmite quadros para o mapa à medida que avança.',
    },
    fast: {
      name: 'Modo rápido',
      tagline: 'Até onde a água chega no pico?',
      body: 'Uma única extensão estática na vazão de pico observada, sem passos de tempo: o escoamento é propagado uma vez pelo terreno, do alto para o baixo, e depois espalhado pela planície de inundação com uma curva-chave construída a partir da altura acima do rio. Inspirado em Torres et al. (2022).',
    },
    csi: 'O CSI (Critical Success Index, índice de sucesso crítico) conta as células que a simulação e a observação consideram inundadas, dividido por todas as células que qualquer uma das duas considera inundadas: 1 é uma concordância perfeita, e tanto as omissões quanto os alarmes falsos o reduzem.',
  },

  data: {
    intro:
      'Tudo vem de fontes públicas e é pré-processado offline, então uma simulação lê apenas arquivos locais. A área de estudo é um recorte de cerca de 6 km de lado sobre o rio entre Lajeado e Estrela, com células de 30, 60 ou 90 m.',
    headers: { input: 'Entrada', source: 'Fonte', usedAs: 'Usada como' },
    rows: [
      {
        what: 'Terreno',
        source: 'MDE SRTM de 1 segundo de arco (via OpenTopography), reprojetado para SIRGAS 2000 / UTM 22S e com depressões preenchidas',
        use: 'Elevação Z de cada célula',
      },
      {
        what: 'Uso do solo',
        source: 'MapBiomas Coleção 10, mapa de 2024',
        use: 'Cada classe convertida em um n de Manning: o quanto ela freia a água',
      },
      {
        what: 'Rio',
        source: 'Posto ANA/SGB 86879300, Porto Fluvial de Estrela, de 27 de abril a 10 de maio de 2024',
        use: 'Vazão que entra na grade ao longo do evento real',
      },
      {
        what: 'Cheia observada',
        source: 'Mapa de mancha de inundação do SGB/CPRM para Lajeado na cota de 33,67 m',
        use: 'Referência contra a qual as simulações são avaliadas (CSI)',
      },
    ],
  },

  usage: {
    steps: [
      {
        title: 'Comece pela cheia real',
        body: (
          <>
            Em <Ui>Configurar</Ui>, clique em <Ui>Reproduzir a cheia de maio de 2024</Ui>. Isso roda o cenário
            validado: primeiro o modo rápido (que responde quase na hora), depois o AC temporal até o pico observado,
            na grade de 90 m e lado a lado na visualização <Ui>Comparar</Ui>.
          </>
        ),
      },
      {
        title: 'Ou configure sua própria simulação',
        body: (
          <>
            Escolha um <Strong>motor</Strong> e uma <Strong>grade</Strong>. Para o AC temporal, escolha um cenário:{' '}
            <Ui>Maio/2024</Ui> conduz a simulação com as vazões reais do rio, enquanto <Ui>Poça inicial</Ui>{' '}
            solta uma poça de água e deixa que ela se espalhe. Na poça inicial você define o número de passos e o volume,
            e pode clicar no mapa, dentro do contorno tracejado, para escolher onde a poça começa. <Ui>Ajustes do motor</Ui>{' '}
            reúne a vizinhança, o intervalo de quadros e a fração de escoamento; os padrões são os validados.
          </>
        ),
      },
      {
        title: 'Execute',
        body: (
          <>
            Clique em <Ui>Iniciar simulação</Ui> na barra superior. As configurações ficam bloqueadas durante a
            simulação; <Ui>Parar</Ui> a encerra antes do fim e mantém o que já chegou. O indicador de estado na barra
            superior mostra em que ponto ela está.
          </>
        ),
      },
      {
        title: 'Explore o mapa',
        body: (
          <ul className="mt-1 flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-muted">
            <li>
              <Ui>Temporal</Ui>, <Ui>Rápido</Ui> e <Ui>Comparar</Ui> (no alto, ao centro) alternam entre os resultados; em
              Comparar, os dois mapas se movem e se aproximam juntos. Logo abaixo, <Ui>Lâmina</Ui>, <Ui>Chegada</Ui> e{' '}
              <Ui>Lâmina máx.</Ui> escolhem o que o mapa temporal mostra.
            </li>
            <li>
              A <Strong>linha do tempo</Strong>, sob o mapa temporal, percorre e reproduz os quadros recebidos até agora;{' '}
              <Ui>Ir para o mais recente</Ui> volta a acompanhar a simulação.
            </li>
            <li>
              <Ui>Camadas</Ui> (no alto, à direita) troca o mapa base e a opacidade da sobreposição.{' '}
              <Ui>Cheia observada</Ui> colore cada célula pela concordância com a mancha real de maio de 2024;{' '}
              <Ui>Terreno</Ui> e <Ui>Rugosidade</Ui> mostram as entradas do próprio modelo.
            </li>
            <li>
              <Ui>Exportar</Ui> salva o mapa como está, em PNG, ou a mancha de inundação em GeoJSON.
            </li>
            <li>
              Clique em qualquer célula para ver sua elevação, uso do solo, n de Manning, lâmina d&rsquo;água e como a
              água que sai dela se divide entre os vizinhos.
            </li>
          </ul>
        ),
      },
      {
        title: 'Leia os números',
        body: (
          <>
            <Ui>Resultados</Ui> mostra a área inundada da simulação, o registro fluviométrico de maio de 2024, as
            métricas contra a cheia observada (CSI, taxa de acerto, taxa de alarme falso) e, depois de uma reprodução,
            como os dois motores concordam. <Ui>Registro</Ui> guarda uma linha por quadro recebido: o passo, o tempo
            simulado e o volume, ou a vazão e o tempo do modo rápido.
          </>
        ),
      },
    ],
    tip: 'Dica: o botão de painel, no canto esquerdo da barra superior, oculta o painel lateral e deixa o mapa com a largura toda.',
  },

  limitsTitle: 'Limitações que vale conhecer',
  limits: [
    'A grade de 90 m é a validada, e a única avaliada ao vivo no app. A grade de 60 m foi avaliada fora do app contra o mesmo evento (CSI com correção da lacuna de 0,87 no motor temporal e 0,88 no modo rápido). A grade de 30 m roda o mesmo modelo com mais detalhe, mas seus resultados não são avaliados.',
    'Os resultados validados usam a regra de 8 vizinhos (Moore). A opção de 4 vizinhos (von Neumann) existe para comparação e não é validada.',
    <>
      O mapa observado deixa de fora parte da margem de Estrela, então essas células aparecem como &ldquo;não
      avaliadas&rdquo; e ficam fora do CSI corrigido pela lacuna.
    </>,
    'O modo rápido é verificado só pela extensão da inundação: não há observações de lâmina para validar suas profundidades.',
    'A poça inicial é um teste sintético da mecânica, não um evento real; seu volume é a soma das lâminas das células, em metros.',
  ],

  builtWith:
    'Feito com Python, NumPy, rasterio e FastAPI (com WebSockets) no backend, e React, TypeScript, Vite e Leaflet no frontend, empacotado com Docker Compose.',
}
