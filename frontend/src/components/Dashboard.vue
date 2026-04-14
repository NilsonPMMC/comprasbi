<script setup>
/**
 * Painel de Inteligência de Compras — GovTech (Mogi das Cruzes).
 * Catálogo master, histórico de preços, gráfico e tabela com economia unificada.
 */
import {
  ref,
  computed,
  onMounted,
  onUnmounted,
  watch,
  nextTick,
} from 'vue'
import VueApexCharts from 'vue3-apexcharts'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import {
  getCatalogo,
  getHistoricoPrecos,
  getComprasPorAno,
  getItensCompra,
  getMatrizCatalogo,
} from '../services/api.js'

// ---------------------------------------------------------------------------
// Componente de gráfico (import local; não depende de registro global no main)
// ---------------------------------------------------------------------------
const Apexchart = VueApexCharts

/** Máximo de caracteres nos rótulos do catálogo (lista + botão); título mostra o texto completo. */
const ROTULO_CATALOGO_MAX = 72

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
/** Lista de produtos do catálogo master (GET /catalogo). */
const produtos = ref([])

/** ID do produto selecionado no <select> (string para v-model). */
const produtoSelecionado = ref('')

/** Combobox: painel aberto, termo de busca e refs. */
const catalogoAberto = ref(false)
const buscaCatalogo = ref('')
const wrapperCatalogoEl = ref(null)
const inputBuscaCatalogoEl = ref(null)

/** Linhas retornadas por GET /catalogo/{id}/historico-precos. */
const historicoBruto = ref([])

/** Indica carregamento do catálogo (mount) ou do histórico (troca de produto). */
const carregando = ref(false)
const periodoInicio = ref('')
const periodoFim = ref('')
const anoCompra = ref(String(new Date().getFullYear()))
const comprasAno = ref([])
const compraSelecionada = ref('')
const buscaCompra = ref('')
const itensCompraBruto = ref([])
const carregandoCompras = ref(false)
const carregandoItensCompra = ref(false)
const abaAtiva = ref('produto')
const itemCompraSelecionado = ref(null)
const historicoItemCompra = ref([])
const carregandoHistoricoItemCompra = ref(false)
const modoEvolucaoItemCompra = ref('semantica_master')
const modoEvolucaoProdutoMaster = ref('semantica')
const matrizBusca = ref('')
const matrizItens = ref([])
const carregandoMatriz = ref(false)
const selecionadosMatriz = ref([])
const itemMatrizSelecionado = ref(null)
const historicoItemMatriz = ref([])
const carregandoHistoricoItemMatriz = ref(false)
const modoEvolucaoMatriz = ref('semantica')
const mostrarLogoPrefeitura = ref(true)
const exportandoRelatorioCompra = ref(false)

// ---------------------------------------------------------------------------
// Formatação e parsing (valores monetários da API em string pt/en)
// ---------------------------------------------------------------------------
const fmtBRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})

function parseMoney(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number.parseFloat(String(value).replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

function formatarData(iso) {
  if (!iso) return '—'
  const d = String(iso).slice(0, 10)
  const [y, m, day] = d.split('-')
  if (!y || !m || !day) return String(iso)
  return `${day}/${m}/${y}`
}

function dataIsoNormalizada(iso) {
  if (!iso) return ''
  return String(iso).slice(0, 10)
}

/** Rótulo do eixo X: data DD/MM/AAAA ou ano/sequencial. */
function rotuloGrafico(row) {
  const br = formatarData(row.data_publicacao)
  if (br !== '—') return br
  return `${row.ano}/${row.sequencial}`
}

function truncarRotuloCatalogo(texto) {
  const s = String(texto ?? '').trim()
  if (!s) return '—'
  if (s.length <= ROTULO_CATALOGO_MAX) return s
  return `${s.slice(0, ROTULO_CATALOGO_MAX - 1)}…`
}

function truncarTexto(texto, limite = 110) {
  const s = String(texto ?? '').trim()
  if (!s) return '—'
  if (s.length <= limite) return s
  return `${s.slice(0, limite - 1)}…`
}

function rotuloCompra(c) {
  const data = formatarData(c.data_publicacao)
  const objeto = truncarTexto(c.objeto || 'Sem objeto')
  return `${c.ano}/${c.sequencial} · ${data} · ${objeto}`
}

function formatarProcessoData(ano, sequencial, data) {
  if (!ano || !sequencial) return '—'
  return `${ano}/${sequencial} · ${formatarData(data)}`
}

/** Campos nulos quando não há vínculo com catálogo ou histórico vazio. */
const consolidadoPrecosVazio = () => ({
  maior_valor: null,
  maior_ano: null,
  maior_sequencial: null,
  maior_data_publicacao: null,
  menor_valor: null,
  menor_ano: null,
  menor_sequencial: null,
  menor_data_publicacao: null,
  ultimo_valor: null,
  ultimo_ano: null,
  ultimo_sequencial: null,
  ultimo_data_publicacao: null,
})

/** Tie-breaks alinhados à matriz no servidor: maior/menor por valor homologado; último por data de publicação. */
function compararMaiorPrecoHistorico(a, b) {
  const va = parseMoney(a.valor_homologado)
  const vb = parseMoney(b.valor_homologado)
  if (va !== vb) return vb - va
  const da = dataIsoNormalizada(a.data_publicacao) || ''
  const db = dataIsoNormalizada(b.data_publicacao) || ''
  if (da !== db) return db.localeCompare(da)
  if (a.ano !== b.ano) return b.ano - a.ano
  return b.sequencial - a.sequencial
}

function compararMenorPrecoHistorico(a, b) {
  const va = parseMoney(a.valor_homologado)
  const vb = parseMoney(b.valor_homologado)
  if (va !== vb) return va - vb
  const da = dataIsoNormalizada(a.data_publicacao) || ''
  const db = dataIsoNormalizada(b.data_publicacao) || ''
  if (da !== db) return db.localeCompare(da)
  if (a.ano !== b.ano) return b.ano - a.ano
  return b.sequencial - a.sequencial
}

function compararUltimoHistorico(a, b) {
  const da = dataIsoNormalizada(a.data_publicacao) || ''
  const db = dataIsoNormalizada(b.data_publicacao) || ''
  if (da !== db) return db.localeCompare(da)
  if (a.ano !== b.ano) return b.ano - a.ano
  return b.sequencial - a.sequencial
}

/** Agrega maior/menor/último a partir da mesma lista que GET historico-precos. */
function consolidarHistoricoMatrizLike(rows) {
  const candidatos = (rows || []).filter((r) => parseMoney(r.valor_homologado) !== null)
  if (candidatos.length === 0) return consolidadoPrecosVazio()

  const maior = [...candidatos].sort(compararMaiorPrecoHistorico)[0]
  const menor = [...candidatos].sort(compararMenorPrecoHistorico)[0]
  const ultimo = [...candidatos].sort(compararUltimoHistorico)[0]

  return {
    maior_valor: maior.valor_homologado,
    maior_ano: maior.ano,
    maior_sequencial: maior.sequencial,
    maior_data_publicacao: maior.data_publicacao,
    menor_valor: menor.valor_homologado,
    menor_ano: menor.ano,
    menor_sequencial: menor.sequencial,
    menor_data_publicacao: menor.data_publicacao,
    ultimo_valor: ultimo.valor_homologado,
    ultimo_ano: ultimo.ano,
    ultimo_sequencial: ultimo.sequencial,
    ultimo_data_publicacao: ultimo.data_publicacao,
  }
}

function normalizarBusca(s) {
  return String(s ?? '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
}

function termoBuscaCompra(c) {
  return normalizarBusca(`${c.ano}/${c.sequencial} ${c.objeto || ''} ${formatarData(c.data_publicacao)}`)
}

const produtoSelecionadoObj = computed(() => {
  const id = produtoSelecionado.value
  if (!id) return null
  return produtos.value.find((p) => String(p.id) === String(id)) ?? null
})

const catalogoFiltrado = computed(() => {
  const q = normalizarBusca(buscaCatalogo.value)
  const lista = produtos.value
  if (!q) return lista
  return lista.filter((p) =>
    normalizarBusca(p.nome_padrao).includes(q),
  )
})

const historicoFiltrado = computed(() => {
  return historicoBruto.value.filter((row) => {
    const data = dataIsoNormalizada(row.data_publicacao)
    if (!data) return false
    if (periodoInicio.value && data < periodoInicio.value) return false
    if (periodoFim.value && data > periodoFim.value) return false
    return true
  })
})

const resumoIndicadores = computed(() => {
  const processos = new Set(
    historicoFiltrado.value.map((r) => `${r.ano}/${r.sequencial}`),
  ).size

  const valores = historicoFiltrado.value
    .map((r) => parseMoney(r.valor_homologado) ?? parseMoney(r.valor_estimado))
    .filter((v) => v !== null)

  const menorPreco = valores.length ? Math.min(...valores) : null
  const maiorPreco = valores.length ? Math.max(...valores) : null

  return {
    processos,
    menorPreco,
    maiorPreco,
  }
})

function fecharCatalogo() {
  catalogoAberto.value = false
  buscaCatalogo.value = ''
}

function alternarCatalogo() {
  if (carregando.value && produtos.value.length === 0) return
  catalogoAberto.value = !catalogoAberto.value
}

function selecionarProdutoCatalogo(p) {
  produtoSelecionado.value = String(p.id)
  fecharCatalogo()
}

function limparProdutoCatalogo() {
  produtoSelecionado.value = ''
  periodoInicio.value = ''
  periodoFim.value = ''
  fecharCatalogo()
}

function limparPeriodo() {
  periodoInicio.value = ''
  periodoFim.value = ''
}

function chaveCompra(c) {
  return `${c.ano}/${c.sequencial}`
}

const compraSelecionadaObj = computed(() => {
  if (!compraSelecionada.value) return null
  return comprasAno.value.find((c) => chaveCompra(c) === compraSelecionada.value) ?? null
})

const comprasAnoFiltradas = computed(() => {
  const q = normalizarBusca(buscaCompra.value)
  if (!q) return comprasAno.value
  return comprasAno.value.filter((c) => termoBuscaCompra(c).includes(q))
})

const resumoCompraSelecionada = computed(() => {
  const totalItens = itensCompraBruto.value.length
  const comHomologado = itensCompraBruto.value.filter(
    (i) => parseMoney(i.valor_unitario_homologado) !== null,
  ).length
  return {
    totalItens,
    comHomologado,
  }
})

const itensCompraTabela = computed(() => {
  return itensCompraBruto.value.map((item, idx) => ({
    chaveLinha: `${item.numero_item}-${idx}`,
    valorEstimadoNum: parseMoney(item.valor_unitario_estimado),
    valorHomologadoNum: parseMoney(item.valor_unitario_homologado),
    numeroItem: item.numero_item,
    descricao: item.descricao || '—',
    valorUnitarioEstimado: parseMoney(item.valor_unitario_estimado),
    valorTotal: parseMoney(item.valor_total),
    valorUnitarioHomologado: parseMoney(item.valor_unitario_homologado),
    nomeVencedor: item.nome_vencedor || '—',
    produtoMasterId: item.produto_master_id,
  })).map((linha) => {
    let variacaoReais = null
    let variacaoPct = null
    if (linha.valorEstimadoNum !== null && linha.valorHomologadoNum !== null) {
      variacaoReais = linha.valorHomologadoNum - linha.valorEstimadoNum
      if (linha.valorEstimadoNum !== 0) {
        variacaoPct = ((linha.valorHomologadoNum - linha.valorEstimadoNum) / linha.valorEstimadoNum) * 100
      }
    }
    let classeVariacao = 'text-slate-600'
    if (variacaoReais !== null) {
      if (variacaoReais > 0) classeVariacao = 'text-red-600 font-semibold'
      else if (variacaoReais < 0) classeVariacao = 'text-green-700 font-semibold'
      else classeVariacao = 'text-slate-700'
    }
    return {
      ...linha,
      variacaoReais,
      variacaoPct,
      classeVariacao,
    }
  })
})

const itemCompraSelecionadoObj = computed(() => {
  if (!itemCompraSelecionado.value) return null
  return itensCompraTabela.value.find((i) => i.chaveLinha === itemCompraSelecionado.value) ?? null
})

const isModoSemantica = (modo) => modo === 'semantica'

function deduplicarHistoricoPorProcesso(rows) {
  const map = new Map()
  for (const row of rows || []) {
    const chave = `${row.ano}/${row.sequencial}`
    if (!map.has(chave)) map.set(chave, row)
  }
  return [...map.values()]
}

const linhasGraficoProdutoMaster = computed(() => {
  if (isModoSemantica(modoEvolucaoProdutoMaster.value)) return historicoFiltrado.value
  return deduplicarHistoricoPorProcesso(historicoFiltrado.value)
})

const grupoSemanticoProdutoMaster = computed(() => {
  if (!produtoSelecionadoObj.value) return null
  const processosRelacionados = deduplicarHistoricoPorProcesso(historicoFiltrado.value)
    .map((r) => ({
      chave: `${r.ano}-${r.sequencial}-${r.data_publicacao || ''}`,
      rotulo: formatarProcessoData(r.ano, r.sequencial, r.data_publicacao),
    }))
  return {
    catalogoId: produtoSelecionadoObj.value.id,
    nomePadrao: produtoSelecionadoObj.value.nome_padrao,
    totalRegistrosHistorico: historicoFiltrado.value.length,
    totalProcessosRelacionados: processosRelacionados.length,
    processosRelacionados,
  }
})

const linhasEvolucaoItemCompra = computed(() => {
  if (modoEvolucaoItemCompra.value === 'semantica_master') return historicoItemCompra.value
  return deduplicarHistoricoPorProcesso(historicoItemCompra.value)
})

const grupoSemanticoItemCompra = computed(() => {
  const item = itemCompraSelecionadoObj.value
  if (!item || !item.produtoMasterId) return null

  const itensRelacionadosCompra = itensCompraTabela.value
    .filter((i) => i.produtoMasterId === item.produtoMasterId)
    .map((i) => ({
      chave: i.chaveLinha,
      numeroItem: i.numeroItem,
      descricao: i.descricao,
    }))
    .sort((a, b) => a.numeroItem - b.numeroItem)

  const processosRelacionados = deduplicarHistoricoPorProcesso(historicoItemCompra.value)
    .map((r) => ({
      chave: `${r.ano}-${r.sequencial}-${r.data_publicacao || ''}`,
      rotulo: formatarProcessoData(r.ano, r.sequencial, r.data_publicacao),
    }))

  return {
    produtoMasterId: item.produtoMasterId,
    totalItensCompraRelacionados: itensRelacionadosCompra.length,
    itensRelacionadosCompra,
    totalProcessosRelacionados: processosRelacionados.length,
    processosRelacionados,
  }
})

const seriesEvolucaoItemCompra = computed(() => {
  const rows = linhasEvolucaoItemCompra.value
  return [
    {
      name: 'Valor estimado',
      data: rows.map((r) => parseMoney(r.valor_estimado)),
    },
    {
      name: 'Valor homologado',
      data: rows.map((r) => parseMoney(r.valor_homologado)),
    },
  ]
})

const optionsEvolucaoItemCompra = computed(() => ({
  ...optionsGrafico.value,
  xaxis: {
    ...optionsGrafico.value.xaxis,
    categories: linhasEvolucaoItemCompra.value.map((r) => rotuloGrafico(r)),
  },
}))

const seriesEvolucaoItemMatriz = computed(() => {
  const rows = isModoSemantica(modoEvolucaoMatriz.value)
    ? historicoItemMatriz.value
    : deduplicarHistoricoPorProcesso(historicoItemMatriz.value)
  return [
    { name: 'Valor estimado', data: rows.map((r) => parseMoney(r.valor_estimado)) },
    { name: 'Valor homologado', data: rows.map((r) => parseMoney(r.valor_homologado)) },
  ]
})

const categoriasEvolucaoMatriz = computed(() => {
  const rows = isModoSemantica(modoEvolucaoMatriz.value)
    ? historicoItemMatriz.value
    : deduplicarHistoricoPorProcesso(historicoItemMatriz.value)
  return rows.map((r) => rotuloGrafico(r))
})

const grupoSemanticoMatriz = computed(() => {
  if (!itemMatrizSelecionado.value) return null
  const processosRelacionados = deduplicarHistoricoPorProcesso(historicoItemMatriz.value)
    .map((r) => ({
      chave: `${r.ano}-${r.sequencial}-${r.data_publicacao || ''}`,
      rotulo: formatarProcessoData(r.ano, r.sequencial, r.data_publicacao),
    }))
  return {
    catalogoId: itemMatrizSelecionado.value.catalogo_id,
    descricao: itemMatrizSelecionado.value.descricao,
    totalRegistrosHistorico: historicoItemMatriz.value.length,
    totalProcessosRelacionados: processosRelacionados.length,
    processosRelacionados,
  }
})

const optionsEvolucaoItemMatriz = computed(() => ({
  ...optionsGrafico.value,
  xaxis: {
    ...optionsGrafico.value.xaxis,
    categories: categoriasEvolucaoMatriz.value,
  },
}))

const matrizSelecionadosRows = computed(() => {
  const ids = new Set(selecionadosMatriz.value)
  return matrizItens.value.filter((r) => ids.has(r.catalogo_id))
})

async function carregarComprasAno() {
  const ano = Number(anoCompra.value)
  if (!Number.isFinite(ano) || ano < 2000 || ano > 2100) {
    comprasAno.value = []
    compraSelecionada.value = ''
    return
  }

  carregandoCompras.value = true
  try {
    const pageSize = 200
    let pagina = 1
    let todos = []
    let totalRegistros = 0
    while (pagina <= 50) {
      const { data } = await getComprasPorAno(ano, pagina, pageSize)
      const lista = Array.isArray(data?.data) ? data.data : []
      totalRegistros = Number(data?.totalRegistros || 0)
      todos = todos.concat(lista)
      if (todos.length >= totalRegistros || lista.length < pageSize) break
      pagina += 1
    }
    comprasAno.value = todos
    if (!comprasAno.value.some((c) => chaveCompra(c) === compraSelecionada.value)) {
      compraSelecionada.value = ''
      itensCompraBruto.value = []
    }
    if (!comprasAnoFiltradas.value.some((c) => chaveCompra(c) === compraSelecionada.value)) {
      buscaCompra.value = ''
    }
  } catch (e) {
    console.error(e)
    comprasAno.value = []
    compraSelecionada.value = ''
    itensCompraBruto.value = []
  } finally {
    carregandoCompras.value = false
  }
}

async function buscarItensCompra() {
  const compra = compraSelecionadaObj.value
  if (!compra) {
    itensCompraBruto.value = []
    itemCompraSelecionado.value = null
    historicoItemCompra.value = []
    return
  }
  carregandoItensCompra.value = true
  try {
    const pageSize = 500
    let pagina = 1
    let todos = []
    let totalRegistros = 0
    while (pagina <= 30) {
      const { data } = await getItensCompra(compra.ano, compra.sequencial, pagina, pageSize)
      const lista = Array.isArray(data?.data) ? data.data : []
      totalRegistros = Number(data?.totalRegistros || 0)
      todos = todos.concat(lista)
      if (todos.length >= totalRegistros || lista.length < pageSize) break
      pagina += 1
    }
    itensCompraBruto.value = todos
    itemCompraSelecionado.value = null
    historicoItemCompra.value = []
  } catch (e) {
    console.error(e)
    itensCompraBruto.value = []
    itemCompraSelecionado.value = null
    historicoItemCompra.value = []
  } finally {
    carregandoItensCompra.value = false
  }
}

async function selecionarItemCompra(linha) {
  itemCompraSelecionado.value = linha.chaveLinha
  historicoItemCompra.value = []

  await carregarHistoricoMasterItemCompra()
}

async function carregarHistoricoMasterItemCompra() {
  const item = itemCompraSelecionadoObj.value
  if (!item || !item.produtoMasterId) {
    historicoItemCompra.value = []
    return
  }
  carregandoHistoricoItemCompra.value = true
  try {
    const { data } = await getHistoricoPrecos(item.produtoMasterId)
    historicoItemCompra.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error(e)
    historicoItemCompra.value = []
  } finally {
    carregandoHistoricoItemCompra.value = false
  }
}

async function carregarMatriz() {
  carregandoMatriz.value = true
  try {
    const pageSize = 500
    let pagina = 1
    let todos = []
    let totalRegistros = 0
    while (pagina <= 30) {
      const { data } = await getMatrizCatalogo(matrizBusca.value, pagina, pageSize)
      const lista = Array.isArray(data?.data) ? data.data : []
      totalRegistros = Number(data?.totalRegistros || 0)
      todos = todos.concat(lista)
      if (todos.length >= totalRegistros || lista.length < pageSize) break
      pagina += 1
    }
    matrizItens.value = todos
    selecionadosMatriz.value = selecionadosMatriz.value.filter((id) =>
      matrizItens.value.some((r) => r.catalogo_id === id),
    )
  } catch (e) {
    console.error(e)
    matrizItens.value = []
    selecionadosMatriz.value = []
  } finally {
    carregandoMatriz.value = false
  }
}

async function verEvolucaoMatriz(row) {
  itemMatrizSelecionado.value = row
  historicoItemMatriz.value = []
  carregandoHistoricoItemMatriz.value = true
  try {
    const { data } = await getHistoricoPrecos(row.catalogo_id)
    historicoItemMatriz.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error(e)
    historicoItemMatriz.value = []
  } finally {
    carregandoHistoricoItemMatriz.value = false
  }
}

function toggleSelecionarTodosMatriz(event) {
  if (event.target.checked) {
    selecionadosMatriz.value = matrizItens.value.map((r) => r.catalogo_id)
    return
  }
  selecionadosMatriz.value = []
}

function exportarRelatorioMatrizSelecionados() {
  if (matrizSelecionadosRows.value.length === 0) return
  const header = [
    'item',
    'descricao',
    'maior_valor',
    'maior_processo_data',
    'menor_valor',
    'menor_processo_data',
    'ultimo_valor',
    'ultimo_processo_data',
  ]
  const rows = matrizSelecionadosRows.value.map((r) => [
    r.catalogo_id,
    `"${String(r.descricao || '').replace(/"/g, '""')}"`,
    r.maior_valor ?? '',
    `"${formatarProcessoData(r.maior_ano, r.maior_sequencial, r.maior_data_publicacao)}"`,
    r.menor_valor ?? '',
    `"${formatarProcessoData(r.menor_ano, r.menor_sequencial, r.menor_data_publicacao)}"`,
    r.ultimo_valor ?? '',
    `"${formatarProcessoData(r.ultimo_ano, r.ultimo_sequencial, r.ultimo_data_publicacao)}"`,
  ])
  const csv = [header.join(','), ...rows.map((r) => r.join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `relatorio_matriz_itens_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function carregarImagemComoDataURL(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('Falha ao criar contexto de imagem'))
        return
      }
      ctx.drawImage(img, 0, 0)
      resolve({
        dataUrl: canvas.toDataURL('image/png'),
        width: img.width,
        height: img.height,
      })
    }
    img.onerror = () => reject(new Error('Falha ao carregar imagem do brasão'))
    img.src = src
  })
}

async function aplicarCabecalhoInstitucionalPDF(doc, titulo, subtitulo) {
  try {
    const logo = await carregarImagemComoDataURL('/branding/Brasao_cor__1.png')
    const maxW = 30
    const maxH = 28
    const escala = Math.min(maxW / logo.width, maxH / logo.height)
    const logoW = logo.width * escala
    const logoH = logo.height * escala
    const logoX = 10 + (maxW - logoW) / 2
    const logoY = 6 + (maxH - logoH) / 2
    doc.addImage(logo.dataUrl, 'PNG', logoX, logoY, logoW, logoH)
  } catch (e) {
    console.warn('Não foi possível carregar o brasão para o PDF:', e)
  }

  doc.setFontSize(16)
  doc.setTextColor(15, 42, 99)
  doc.text(titulo, 44, 14)
  doc.setFontSize(10)
  doc.setTextColor(51, 65, 85)
  doc.text(subtitulo, 44, 20)
  doc.setDrawColor(203, 213, 225)
  doc.line(10, 36, 287, 36)
}

function didDrawPageRodapePMC(doc) {
  const pageCount = doc.getNumberOfPages()
  const pageCurrent = doc.getCurrentPageInfo().pageNumber
  doc.setFontSize(8)
  doc.setTextColor(71, 85, 105)
  doc.text(
    `Prefeitura Municipal de Mogi das Cruzes - Página ${pageCurrent}/${pageCount}`,
    286,
    205,
    { align: 'right' },
  )
}

async function exportarRelatorioMatrizSelecionadosPDF() {
  if (matrizSelecionadosRows.value.length === 0) return

  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
  const dataAtual = new Date().toLocaleString('pt-BR')
  const titulo = 'Relatório Comparativo de Preços'
  const subtitulo = `Gerado em: ${dataAtual}`
  await aplicarCabecalhoInstitucionalPDF(doc, titulo, subtitulo)

  const body = matrizSelecionadosRows.value.map((r) => [
    String(r.catalogo_id),
    truncarTexto(r.descricao, 72),
    `${formatarMoeda(parseMoney(r.maior_valor))}\n${formatarProcessoData(r.maior_ano, r.maior_sequencial, r.maior_data_publicacao)}`,
    `${formatarMoeda(parseMoney(r.menor_valor))}\n${formatarProcessoData(r.menor_ano, r.menor_sequencial, r.menor_data_publicacao)}`,
    `${formatarMoeda(parseMoney(r.ultimo_valor))}\n${formatarProcessoData(r.ultimo_ano, r.ultimo_sequencial, r.ultimo_data_publicacao)}`,
  ])

  autoTable(doc, {
    startY: 40,
    head: [['Item', 'Descrição', 'Maior preço', 'Menor preço', 'Último preço']],
    body,
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [15, 42, 99] },
    columnStyles: {
      0: { cellWidth: 15 },
      1: { cellWidth: 90 },
      2: { cellWidth: 55 },
      3: { cellWidth: 55 },
      4: { cellWidth: 55 },
    },
    didDrawPage: () => didDrawPageRodapePMC(doc),
  })

  doc.save(`relatorio_matriz_itens_${new Date().toISOString().slice(0, 10)}.pdf`)
}

async function montarLinhasRelatorioCompra() {
  const compra = compraSelecionadaObj.value
  if (!compra || itensCompraBruto.value.length === 0) return []

  const idsCatalogo = [
    ...new Set(
      itensCompraBruto.value.map((i) => i.produto_master_id).filter((id) => id != null),
    ),
  ]

  const cache = new Map()
  await Promise.all(
    idsCatalogo.map(async (catalogoId) => {
      try {
        const { data } = await getHistoricoPrecos(catalogoId)
        const rows = Array.isArray(data) ? data : []
        cache.set(catalogoId, consolidarHistoricoMatrizLike(rows))
      } catch (e) {
        console.error(e)
        cache.set(catalogoId, consolidadoPrecosVazio())
      }
    }),
  )

  const ordenados = [...itensCompraBruto.value].sort((a, b) => a.numero_item - b.numero_item)

  return ordenados.map((item) => {
    const cons =
      item.produto_master_id != null
        ? cache.get(item.produto_master_id) ?? consolidadoPrecosVazio()
        : consolidadoPrecosVazio()
    return {
      numero_item: item.numero_item,
      descricao: item.descricao || '',
      ...cons,
    }
  })
}

async function exportarRelatorioCompraCSV() {
  const compra = compraSelecionadaObj.value
  if (!compra || itensCompraBruto.value.length === 0) return

  exportandoRelatorioCompra.value = true
  try {
    const linhas = await montarLinhasRelatorioCompra()
    if (linhas.length === 0) return

    const header = [
      'item',
      'descricao',
      'maior_valor',
      'maior_processo_data',
      'menor_valor',
      'menor_processo_data',
      'ultimo_valor',
      'ultimo_processo_data',
    ]
    const rows = linhas.map((r) => [
      r.numero_item,
      `"${String(r.descricao || '').replace(/"/g, '""')}"`,
      r.maior_valor ?? '',
      `"${formatarProcessoData(r.maior_ano, r.maior_sequencial, r.maior_data_publicacao)}"`,
      r.menor_valor ?? '',
      `"${formatarProcessoData(r.menor_ano, r.menor_sequencial, r.menor_data_publicacao)}"`,
      r.ultimo_valor ?? '',
      `"${formatarProcessoData(r.ultimo_ano, r.ultimo_sequencial, r.ultimo_data_publicacao)}"`,
    ])
    const csv = [header.join(','), ...rows.map((row) => row.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `relatorio_compra_${compra.ano}_${compra.sequencial}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    exportandoRelatorioCompra.value = false
  }
}

async function exportarRelatorioCompraPDF() {
  const compra = compraSelecionadaObj.value
  if (!compra || itensCompraBruto.value.length === 0) return

  exportandoRelatorioCompra.value = true
  try {
    const linhas = await montarLinhasRelatorioCompra()
    if (linhas.length === 0) return

    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
    const dataAtual = new Date().toLocaleString('pt-BR')
    const titulo = 'Relatório de Itens da Compra'
    const subtitulo = `Compra ${compra.ano}/${compra.sequencial} · Gerado em: ${dataAtual}`
    await aplicarCabecalhoInstitucionalPDF(doc, titulo, subtitulo)

    const body = linhas.map((r) => [
      String(r.numero_item),
      truncarTexto(r.descricao, 72),
      `${formatarMoeda(parseMoney(r.maior_valor))}\n${formatarProcessoData(r.maior_ano, r.maior_sequencial, r.maior_data_publicacao)}`,
      `${formatarMoeda(parseMoney(r.menor_valor))}\n${formatarProcessoData(r.menor_ano, r.menor_sequencial, r.menor_data_publicacao)}`,
      `${formatarMoeda(parseMoney(r.ultimo_valor))}\n${formatarProcessoData(r.ultimo_ano, r.ultimo_sequencial, r.ultimo_data_publicacao)}`,
    ])

    autoTable(doc, {
      startY: 40,
      head: [['Item', 'Descrição', 'Maior preço', 'Menor preço', 'Último preço']],
      body,
      styles: { fontSize: 8, cellPadding: 2 },
      headStyles: { fillColor: [15, 42, 99] },
      columnStyles: {
        0: { cellWidth: 15 },
        1: { cellWidth: 90 },
        2: { cellWidth: 55 },
        3: { cellWidth: 55 },
        4: { cellWidth: 55 },
      },
      didDrawPage: () => didDrawPageRodapePMC(doc),
    })

    doc.save(`relatorio_compra_${compra.ano}_${compra.sequencial}_${new Date().toISOString().slice(0, 10)}.pdf`)
  } finally {
    exportandoRelatorioCompra.value = false
  }
}

function onErroLogoPrefeitura() {
  mostrarLogoPrefeitura.value = false
}

function onClickForaCatalogo(ev) {
  const el = wrapperCatalogoEl.value
  if (!el || el.contains(ev.target)) return
  fecharCatalogo()
}

watch(catalogoAberto, async (aberto) => {
  if (!aberto) return
  await nextTick()
  inputBuscaCatalogoEl.value?.focus()
  inputBuscaCatalogoEl.value?.select()
})

// ---------------------------------------------------------------------------
// Ciclo de vida — catálogo
// ---------------------------------------------------------------------------
onMounted(async () => {
  document.addEventListener('click', onClickForaCatalogo)
  carregando.value = true
  try {
    const { data } = await getCatalogo()
    produtos.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error(e)
    produtos.value = []
  } finally {
    carregando.value = false
  }
  await carregarComprasAno()
  await carregarMatriz()
})

onUnmounted(() => {
  document.removeEventListener('click', onClickForaCatalogo)
})

// ---------------------------------------------------------------------------
// Histórico ao mudar o produto
// ---------------------------------------------------------------------------
async function buscarHistorico() {
  const id = produtoSelecionado.value
  if (!id) {
    historicoBruto.value = []
    return
  }
  const num = Number(id)
  if (!Number.isFinite(num)) {
    historicoBruto.value = []
    return
  }

  carregando.value = true
  try {
    const { data } = await getHistoricoPrecos(num)
    historicoBruto.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error(e)
    historicoBruto.value = []
  } finally {
    carregando.value = false
  }
}

watch(produtoSelecionado, () => {
  buscarHistorico()
})

watch(anoCompra, () => {
  buscaCompra.value = ''
  carregarComprasAno()
})

watch(compraSelecionada, () => {
  buscarItensCompra()
})

watch(modoEvolucaoItemCompra, async (modo) => {
  if (!itemCompraSelecionadoObj.value || historicoItemCompra.value.length > 0) return
  await carregarHistoricoMasterItemCompra()
})

// ---------------------------------------------------------------------------
// Tabela: economia em R$ e % + classe de cor (verde economizou, vermelho estourou)
// ---------------------------------------------------------------------------
const dadosTabela = computed(() => {
  return historicoFiltrado.value.map((row) => {
    const estimado = parseMoney(row.valor_estimado)
    const pago = parseMoney(row.valor_homologado)

    let economiaReais = null
    let economiaPct = null
    if (estimado !== null && pago !== null) {
      economiaReais = estimado - pago
      if (estimado !== 0) {
        economiaPct = ((estimado - pago) / estimado) * 100
      }
    }

    // Verde: pagou menos que o estimado (economia positiva em R$)
    // Vermelho: pagou mais que o estimado
    let classeEconomia = 'text-slate-600'
    if (economiaReais !== null) {
      if (economiaReais > 0) classeEconomia = 'text-green-700 font-semibold'
      else if (economiaReais < 0) classeEconomia = 'text-red-600 font-semibold'
      else classeEconomia = 'text-slate-700'
    }

    return {
      dataFormatada: formatarData(row.data_publicacao),
      processo: `${row.ano} / ${row.sequencial}`,
      vencedor: row.fornecedor_vencedor || '—',
      estimado,
      pago,
      economiaReais,
      economiaPct,
      classeEconomia,
    }
  })
})

// ---------------------------------------------------------------------------
// ApexCharts — área; azul = estimado, verde = homologado; sem toolbar
// ---------------------------------------------------------------------------
const CORES = ['#2563eb', '#16a34a'] // blue-600, green-600

const seriesGrafico = computed(() => {
  const rows = linhasGraficoProdutoMaster.value
  return [
    {
      name: 'Valor estimado',
      data: rows.map((r) => parseMoney(r.valor_estimado)),
    },
    {
      name: 'Valor homologado',
      data: rows.map((r) => parseMoney(r.valor_homologado)),
    },
  ]
})

const optionsGrafico = computed(() => ({
  chart: {
    type: 'area',
    toolbar: { show: false },
    zoom: { enabled: false },
    fontFamily:
      'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    foreColor: '#0f172a',
  },
  colors: CORES,
  stroke: { curve: 'smooth', width: 2 },
  dataLabels: { enabled: false },
  fill: {
    type: 'gradient',
    gradient: {
      shadeIntensity: 0.35,
      opacityFrom: 0.4,
      opacityTo: 0.05,
    },
  },
  xaxis: {
    categories: linhasGraficoProdutoMaster.value.map((r) => rotuloGrafico(r)),
    labels: {
      style: { colors: '#64748b', fontSize: '11px' },
      rotate: -35,
      rotateAlways: linhasGraficoProdutoMaster.value.length > 6,
    },
    axisBorder: { color: '#e2e8f0' },
  },
  yaxis: {
    labels: {
      style: { colors: '#64748b' },
      formatter: (v) => (v != null && !Number.isNaN(v) ? fmtBRL.format(v) : ''),
    },
    title: {
      text: 'Valor unitário (R$)',
      style: { color: '#64748b', fontSize: '11px', fontWeight: 600 },
    },
  },
  tooltip: {
    shared: true,
    y: {
      formatter: (v) => (v != null ? fmtBRL.format(v) : '—'),
    },
  },
  legend: {
    position: 'top',
    horizontalAlign: 'right',
    labels: { colors: '#0f172a' },
  },
  grid: { borderColor: '#e2e8f0', strokeDashArray: 4 },
}))

function formatarMoeda(val) {
  if (val === null || val === undefined || Number.isNaN(val)) return '—'
  return fmtBRL.format(val)
}

function formatarEconomiaPct(pct) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return '—'
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(pct)}%`
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <!-- Barra superior institucional -->
    <header class="bg-blue-900 p-4 text-white shadow-md">
      <div class="container mx-auto">
        <div class="flex items-center gap-3">
          <img
            v-if="mostrarLogoPrefeitura"
            src="/branding/brasao_pmmc_azul.png"
            alt="Brasão da Prefeitura"
            class="h-12 w-12 rounded object-contain p-1"
            @error="onErroLogoPrefeitura"
          >
          <h1 class="text-xl font-bold tracking-tight sm:text-2xl">
            Painel BI Compras - Prefeitura de Mogi das Cruzes
          </h1>
        </div>
      </div>
    </header>

    <div class="container mx-auto space-y-6 p-6">
      <section class="rounded-md border border-slate-200 bg-white p-2 shadow-sm">
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <button
            type="button"
            class="rounded-md px-3 py-2 text-sm font-semibold transition"
            :class="abaAtiva === 'produto'
              ? 'bg-blue-900 text-white shadow-sm'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
            @click="abaAtiva = 'produto'"
          >
            Painel Produto Master
          </button>
          <button
            type="button"
            class="rounded-md px-3 py-2 text-sm font-semibold transition"
            :class="abaAtiva === 'compra'
              ? 'bg-blue-900 text-white shadow-sm'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
            @click="abaAtiva = 'compra'"
          >
            Painel Compras
          </button>
          <button
            type="button"
            class="rounded-md px-3 py-2 text-sm font-semibold transition"
            :class="abaAtiva === 'matriz'
              ? 'bg-blue-900 text-white shadow-sm'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
            @click="abaAtiva = 'matriz'"
          >
            Matriz de Itens
          </button>
        </div>
      </section>

      <div
        v-show="abaAtiva === 'produto'"
        class="space-y-6"
      >
      <!-- Filtro: produto master -->
      <section
        class="rounded-md border border-slate-200 bg-white p-4 shadow-sm"
        aria-label="Filtro por produto do catálogo"
      >
        <label
          id="label-catalogo"
          class="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-600"
        >
          Produto master
        </label>
        <div
          ref="wrapperCatalogoEl"
          class="relative w-full max-w-2xl"
        >
          <div class="flex gap-2">
            <button
              type="button"
              class="flex min-h-[42px] flex-1 items-center justify-between gap-2 rounded border border-slate-300 bg-white px-3 py-2 text-left text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="carregando && produtos.length === 0"
              aria-haspopup="listbox"
              :aria-expanded="catalogoAberto"
              aria-controls="lista-catalogo-produtos"
              aria-labelledby="label-catalogo"
              @click.stop="alternarCatalogo"
            >
              <span
                class="min-w-0 flex-1 truncate"
                :title="produtoSelecionadoObj?.nome_padrao || ''"
              >
                <template v-if="produtoSelecionadoObj">
                  {{ truncarRotuloCatalogo(produtoSelecionadoObj.nome_padrao) }}
                </template>
                <template v-else>
                  Selecione ou busque um produto
                </template>
              </span>
              <span
                class="shrink-0 text-slate-400"
                aria-hidden="true"
              >{{ catalogoAberto ? '▲' : '▼' }}</span>
            </button>
            <button
              v-if="produtoSelecionado"
              type="button"
              class="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              title="Limpar seleção"
              @click.stop="limparProdutoCatalogo"
            >
              Limpar
            </button>
          </div>

          <div
            v-show="catalogoAberto"
            id="lista-catalogo-produtos"
            class="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg"
            role="listbox"
            aria-labelledby="label-catalogo"
            @click.stop
          >
            <input
              ref="inputBuscaCatalogoEl"
              v-model="buscaCatalogo"
              type="search"
              autocomplete="off"
              placeholder="Buscar por nome do produto…"
              class="w-full border-b border-slate-200 px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-600"
              aria-controls="lista-catalogo-opcoes"
              @keydown.escape.prevent="fecharCatalogo"
            >
            <ul
              id="lista-catalogo-opcoes"
              class="max-h-64 overflow-y-auto py-1"
              role="presentation"
            >
              <li
                v-if="catalogoFiltrado.length === 0"
                class="px-3 py-3 text-center text-sm text-slate-500"
              >
                Nenhum produto encontrado.
              </li>
              <li
                v-for="p in catalogoFiltrado"
                :key="p.id"
                role="option"
                :aria-selected="String(p.id) === produtoSelecionado"
                class="cursor-pointer px-3 py-2 text-sm text-slate-800 hover:bg-blue-50"
                :class="{
                  'bg-blue-100 font-medium': String(p.id) === produtoSelecionado,
                }"
                :title="p.nome_padrao"
                @click="selecionarProdutoCatalogo(p)"
              >
                {{ truncarRotuloCatalogo(p.nome_padrao) }}
              </li>
            </ul>
          </div>
        </div>
        <p class="mt-1.5 text-xs text-slate-500">
          {{ produtos.length }} produto(s) no catálogo · nomes longos são abreviados
          (até {{ ROTULO_CATALOGO_MAX }} caracteres); passe o mouse para ver o texto completo.
        </p>

        <div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label class="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Início do período
            <input
              v-model="periodoInicio"
              type="date"
              class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              :disabled="!produtoSelecionado"
            >
          </label>
          <label class="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Fim do período
            <input
              v-model="periodoFim"
              type="date"
              class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              :disabled="!produtoSelecionado"
            >
          </label>
          <button
            type="button"
            class="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!periodoInicio && !periodoFim"
            @click="limparPeriodo"
          >
            Limpar período
          </button>
        </div>
      </section>

      <section
        v-if="produtoSelecionado && !carregando"
        class="grid gap-3 sm:grid-cols-3"
        aria-label="Resumo de indicadores do produto"
      >
        <article class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Processos</p>
          <p class="mt-2 text-2xl font-bold text-slate-800">{{ resumoIndicadores.processos }}</p>
        </article>
        <article class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Menor preço</p>
          <p class="mt-2 text-2xl font-bold text-green-700">{{ formatarMoeda(resumoIndicadores.menorPreco) }}</p>
        </article>
        <article class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Maior preço</p>
          <p class="mt-2 text-2xl font-bold text-red-600">{{ formatarMoeda(resumoIndicadores.maiorPreco) }}</p>
        </article>
      </section>

      <!-- Gráfico -->
      <section
        class="rounded-md border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
        aria-label="Gráfico de evolução de preços"
      >
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-800">
            Evolução de preços (unitário)
          </h2>
          <label class="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Modo de análise
            <select
              v-model="modoEvolucaoProdutoMaster"
              class="ml-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 sm:text-sm"
            >
              <option value="semantica">Identificação semântica (consolidado)</option>
              <option value="id_exata">ID exata (uma linha por compra/processo)</option>
            </select>
          </label>
        </div>

        <!-- Estado inicial / vazio -->
        <div
          v-if="!produtoSelecionado"
          class="flex min-h-[280px] items-center justify-center rounded border border-dashed border-slate-200 bg-slate-50 px-4 py-12 text-center text-sm text-slate-600"
        >
          Selecione um produto no filtro acima para carregar o histórico e o
          gráfico.
        </div>

        <div
          v-else-if="carregando"
          class="flex min-h-[280px] flex-col items-center justify-center gap-2 rounded bg-slate-50"
          role="status"
          aria-live="polite"
        >
          <div
            class="h-10 w-10 animate-pulse rounded-full bg-slate-200"
            aria-hidden="true"
          />
          <p class="text-sm font-medium text-slate-600">Carregando dados…</p>
        </div>

        <div
          v-else-if="linhasGraficoProdutoMaster.length === 0"
          class="flex min-h-[280px] items-center justify-center rounded border border-slate-100 bg-slate-50 px-4 text-center text-sm text-slate-600"
        >
          Nenhum registro encontrado para o período selecionado.
        </div>

        <Apexchart
          v-else
          type="area"
          height="360"
          :options="optionsGrafico"
          :series="seriesGrafico"
        />

        <div
          v-if="produtoSelecionado && grupoSemanticoProdutoMaster"
          class="mt-4 rounded-md border border-blue-100 bg-blue-50/60 p-3 text-xs text-slate-700"
        >
          <p class="font-semibold text-blue-900">
            Grupo semântico identificado (informativo)
          </p>
          <p class="mt-1 text-slate-600">
            Produto master {{ grupoSemanticoProdutoMaster.catalogoId }} ·
            {{ truncarTexto(grupoSemanticoProdutoMaster.nomePadrao, 100) }} ·
            {{ grupoSemanticoProdutoMaster.totalRegistrosHistorico }} registro(s) no histórico filtrado ·
            {{ grupoSemanticoProdutoMaster.totalProcessosRelacionados }} processo(s) relacionado(s).
          </p>
          <div class="mt-2">
            <p class="mb-1 font-semibold text-slate-700">Processos relacionados no período</p>
            <ul class="max-h-24 space-y-1 overflow-auto pr-1">
              <li
                v-for="proc in grupoSemanticoProdutoMaster.processosRelacionados"
                :key="`grupo-prod-proc-${proc.chave}`"
                class="rounded bg-white/80 px-2 py-1 text-[11px]"
              >
                {{ proc.rotulo }}
              </li>
              <li
                v-if="grupoSemanticoProdutoMaster.processosRelacionados.length === 0"
                class="rounded bg-white/80 px-2 py-1 text-[11px] text-slate-500"
              >
                Sem processos correlatos para os filtros selecionados.
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- Tabela de transparência -->
      <section
        v-if="produtoSelecionado && !carregando && historicoFiltrado.length > 0"
        class="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm"
        aria-label="Tabela detalhada do histórico"
      >
        <div class="border-b border-slate-200 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-800">
            Detalhamento — transparência
          </h2>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full border-collapse border border-slate-200 text-sm">
            <thead>
              <tr class="bg-slate-100">
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Data
                </th>
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Processo
                </th>
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Vencedor
                </th>
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Estimado
                </th>
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Pago
                </th>
                <th
                  scope="col"
                  class="border border-slate-200 px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Economia
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(linha, i) in dadosTabela"
                :key="i"
                class="odd:bg-white even:bg-slate-50/80"
              >
                <td class="border border-slate-200 px-3 py-2 tabular-nums">
                  {{ linha.dataFormatada }}
                </td>
                <td class="border border-slate-200 px-3 py-2 font-mono text-xs">
                  {{ linha.processo }}
                </td>
                <td
                  class="max-w-[12rem] truncate border border-slate-200 px-3 py-2 sm:max-w-md"
                  :title="linha.vencedor"
                >
                  {{ linha.vencedor }}
                </td>
                <td class="border border-slate-200 px-3 py-2 text-right tabular-nums">
                  {{ formatarMoeda(linha.estimado) }}
                </td>
                <td class="border border-slate-200 px-3 py-2 text-right tabular-nums font-medium">
                  {{ formatarMoeda(linha.pago) }}
                </td>
                <td
                  class="border border-slate-200 px-3 py-2 text-right text-sm tabular-nums"
                  :class="linha.classeEconomia"
                >
                  <template v-if="linha.economiaReais === null">—</template>
                  <template v-else>
                    {{ formatarMoeda(linha.economiaReais) }}
                    <span
                      v-if="linha.economiaPct !== null"
                      class="block text-xs font-normal opacity-90"
                    >
                      ({{ formatarEconomiaPct(linha.economiaPct) }})
                    </span>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      </div>

      <div
        v-show="abaAtiva === 'compra'"
        class="space-y-6"
      >
      <section class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
        <div class="mb-3">
          <h2 class="text-sm font-semibold text-slate-800">
            Painel de Compra - Itens da compra selecionada
          </h2>
          <p class="mt-1 text-xs text-slate-500">
            Selecione ano e compra para listar todos os itens salvos no cache local.
          </p>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-[140px_1fr]">
          <label class="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Ano
            <input
              v-model="anoCompra"
              type="number"
              min="2000"
              max="2100"
              class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
            >
          </label>
          <label class="block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Compra
            <input
              v-model="buscaCompra"
              type="search"
              placeholder="Buscar por número, data ou objeto..."
              class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              :disabled="carregandoCompras || comprasAno.length === 0"
            >
            <select
              v-model="compraSelecionada"
              class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              :disabled="carregandoCompras"
            >
              <option value="">Selecione uma compra</option>
              <option
                v-for="c in comprasAnoFiltradas"
                :key="chaveCompra(c)"
                :value="chaveCompra(c)"
                :title="c.objeto"
              >
                {{ rotuloCompra(c) }}
              </option>
            </select>
            <span class="mt-1 block text-[11px] normal-case tracking-normal text-slate-500">
              {{ comprasAnoFiltradas.length }} de {{ comprasAno.length }} compra(s) no filtro.
            </span>
          </label>
        </div>

        <p class="mt-2 text-xs text-slate-500">
          {{ comprasAno.length }} compra(s) carregada(s) para {{ anoCompra }}.
        </p>
      </section>

      <section
        v-if="compraSelecionada && !carregandoItensCompra"
        class="grid gap-3 sm:grid-cols-2"
        aria-label="Resumo da compra selecionada"
      >
        <article class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Total de itens</p>
          <p class="mt-2 text-2xl font-bold text-slate-800">{{ resumoCompraSelecionada.totalItens }}</p>
        </article>
        <article class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Itens com valor homologado</p>
          <p class="mt-2 text-2xl font-bold text-slate-800">{{ resumoCompraSelecionada.comHomologado }}</p>
        </article>
      </section>

      <section class="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-800">
            Itens da compra
          </h2>
          <div
            v-if="compraSelecionada && !carregandoItensCompra && itensCompraTabela.length > 0"
            class="flex flex-wrap gap-2"
          >
            <button
              type="button"
              class="rounded border border-blue-700 bg-blue-700 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
              :disabled="exportandoRelatorioCompra"
              @click="exportarRelatorioCompraCSV"
            >
              Relatório CSV ({{ itensCompraTabela.length }})
            </button>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-700 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-700 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
              :disabled="exportandoRelatorioCompra"
              @click="exportarRelatorioCompraPDF"
            >
              Relatório PDF
            </button>
          </div>
        </div>

        <div
          v-if="!compraSelecionada"
          class="px-4 py-10 text-center text-sm text-slate-600"
        >
          Selecione uma compra para listar os itens.
        </div>
        <div
          v-else-if="carregandoItensCompra"
          class="px-4 py-10 text-center text-sm text-slate-600"
        >
          Carregando itens da compra...
        </div>
        <div
          v-else-if="itensCompraTabela.length === 0"
          class="px-4 py-10 text-center text-sm text-slate-600"
        >
          Nenhum item encontrado para a compra selecionada.
        </div>
        <div
          v-else
          class="overflow-x-auto"
        >
          <table class="w-full border-collapse border border-slate-200 text-sm">
            <thead>
              <tr class="bg-slate-100">
                <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Item</th>
                <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Descrição</th>
                <th class="border border-slate-200 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">Unit. estimado</th>
                <th class="border border-slate-200 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">Total</th>
                <th class="border border-slate-200 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">Unit. homologado</th>
                <th class="border border-slate-200 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">Variação</th>
                <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Vencedor</th>
                <th class="border border-slate-200 px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-600">Produto master</th>
                <th class="border border-slate-200 px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-600">Evolução</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="linha in itensCompraTabela"
                :key="linha.chaveLinha"
                class="odd:bg-white even:bg-slate-50/80"
                :class="{ 'ring-1 ring-blue-400': linha.chaveLinha === itemCompraSelecionado }"
              >
                <td class="border border-slate-200 px-3 py-2 font-mono text-xs">{{ linha.numeroItem }}</td>
                <td
                  class="max-w-[20rem] truncate border border-slate-200 px-3 py-2"
                  :title="linha.descricao"
                >
                  {{ truncarTexto(linha.descricao, 150) }}
                </td>
                <td class="border border-slate-200 px-3 py-2 text-right tabular-nums">{{ formatarMoeda(linha.valorUnitarioEstimado) }}</td>
                <td class="border border-slate-200 px-3 py-2 text-right tabular-nums">{{ formatarMoeda(linha.valorTotal) }}</td>
                <td class="border border-slate-200 px-3 py-2 text-right tabular-nums">{{ formatarMoeda(linha.valorUnitarioHomologado) }}</td>
                <td
                  class="border border-slate-200 px-3 py-2 text-right text-sm tabular-nums"
                  :class="linha.classeVariacao"
                >
                  <template v-if="linha.variacaoReais === null">—</template>
                  <template v-else>
                    {{ formatarMoeda(linha.variacaoReais) }}
                    <span
                      v-if="linha.variacaoPct !== null"
                      class="block text-xs font-normal opacity-90"
                    >
                      ({{ formatarEconomiaPct(linha.variacaoPct) }})
                    </span>
                  </template>
                </td>
                <td class="max-w-[14rem] truncate border border-slate-200 px-3 py-2" :title="linha.nomeVencedor">{{ linha.nomeVencedor }}</td>
                <td class="border border-slate-200 px-3 py-2 text-center tabular-nums">
                  {{ linha.produtoMasterId ?? '—' }}
                </td>
                <td class="border border-slate-200 px-3 py-2 text-center">
                  <button
                    type="button"
                    class="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
                    @click="selecionarItemCompra(linha)"
                  >
                    Ver evolução
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-slate-800">
            Evolução de preço do item da compra
          </h3>
          <label class="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Modo de análise
            <select
              v-model="modoEvolucaoItemCompra"
              class="ml-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 sm:text-sm"
            >
              <option value="semantica_master">Identificação semântica (produto master)</option>
              <option value="id_exata_item">ID exata (uma linha por compra/processo)</option>
            </select>
          </label>
        </div>

        <div
          v-if="!itemCompraSelecionadoObj"
          class="rounded border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
        >
          Clique em <strong>Ver evolução</strong> em um item da tabela acima.
        </div>
        <div
          v-else-if="modoEvolucaoItemCompra === 'semantica_master' && !itemCompraSelecionadoObj.produtoMasterId"
          class="rounded border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
        >
          Este item ainda não possui produto master vinculado, então não há série histórica comparável.
        </div>
        <div
          v-else-if="modoEvolucaoItemCompra === 'semantica_master' && carregandoHistoricoItemCompra"
          class="rounded bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
        >
          Carregando evolução do item...
        </div>
        <div
          v-else-if="modoEvolucaoItemCompra === 'semantica_master' && historicoItemCompra.length === 0"
          class="rounded border border-slate-100 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
        >
          Nenhum histórico encontrado para este item/produto.
        </div>
        <div v-else>
          <p class="mb-3 text-xs text-slate-500">
            Item {{ itemCompraSelecionadoObj.numeroItem }} · Produto master {{ itemCompraSelecionadoObj.produtoMasterId }}
          </p>
          <div
            v-if="grupoSemanticoItemCompra"
            class="mb-4 rounded-md border border-blue-100 bg-blue-50/60 p-3 text-xs text-slate-700"
          >
            <p class="font-semibold text-blue-900">
              Grupo semântico identificado (informativo)
            </p>
            <p class="mt-1 text-slate-600">
              Produto master {{ grupoSemanticoItemCompra.produtoMasterId }} ·
              {{ grupoSemanticoItemCompra.totalItensCompraRelacionados }} item(ns) relacionado(s) na compra atual ·
              {{ grupoSemanticoItemCompra.totalProcessosRelacionados }} processo(s) relacionado(s) no histórico.
            </p>

            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p class="mb-1 font-semibold text-slate-700">Itens da compra no mesmo grupo</p>
                <ul class="max-h-28 space-y-1 overflow-auto pr-1">
                  <li
                    v-for="i in grupoSemanticoItemCompra.itensRelacionadosCompra"
                    :key="`grupo-item-${i.chave}`"
                    class="rounded bg-white/80 px-2 py-1 text-[11px]"
                  >
                    Item {{ i.numeroItem }} · {{ truncarTexto(i.descricao, 90) }}
                  </li>
                </ul>
              </div>
              <div>
                <p class="mb-1 font-semibold text-slate-700">Processos relacionados no histórico</p>
                <ul class="max-h-28 space-y-1 overflow-auto pr-1">
                  <li
                    v-for="proc in grupoSemanticoItemCompra.processosRelacionados"
                    :key="`grupo-proc-${proc.chave}`"
                    class="rounded bg-white/80 px-2 py-1 text-[11px]"
                  >
                    {{ proc.rotulo }}
                  </li>
                  <li
                    v-if="grupoSemanticoItemCompra.processosRelacionados.length === 0"
                    class="rounded bg-white/80 px-2 py-1 text-[11px] text-slate-500"
                  >
                    Sem processos correlatos carregados para este grupo.
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <Apexchart
            type="area"
            height="300"
            :options="optionsEvolucaoItemCompra"
            :series="seriesEvolucaoItemCompra"
          />
        </div>
      </section>
      </div>

      <div
        v-show="abaAtiva === 'matriz'"
        class="space-y-6"
      >
        <section class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
            <label class="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              Busca semântica
              <input
                v-model="matrizBusca"
                type="search"
                placeholder="Descreva o item, ex.: luva de procedimento, material escolar..."
                class="mt-1 block w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              >
            </label>
            <button
              type="button"
              class="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
              :disabled="carregandoMatriz"
              @click="carregarMatriz"
            >
              Buscar
            </button>
            <button
              type="button"
              class="rounded border border-blue-700 bg-blue-700 px-3 py-2 text-sm text-white shadow-sm hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="matrizSelecionadosRows.length === 0"
              @click="exportarRelatorioMatrizSelecionados"
            >
              Relatório CSV ({{ matrizSelecionadosRows.length }})
            </button>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-700 px-3 py-2 text-sm text-white shadow-sm hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-700 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="matrizSelecionadosRows.length === 0"
              @click="exportarRelatorioMatrizSelecionadosPDF"
            >
              Relatório PDF
            </button>
          </div>
        </section>

        <section class="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
          <div class="border-b border-slate-200 px-4 py-3">
            <h2 class="text-sm font-semibold text-slate-800">
              Matriz consolidada de itens
            </h2>
          </div>
          <div
            v-if="carregandoMatriz"
            class="px-4 py-10 text-center text-sm text-slate-600"
          >
            Carregando matriz de itens...
          </div>
          <div
            v-else-if="matrizItens.length === 0"
            class="px-4 py-10 text-center text-sm text-slate-600"
          >
            Nenhum item encontrado para o filtro informado.
          </div>
          <div
            v-else
            class="max-h-[28rem] overflow-auto"
          >
            <table class="w-full border-collapse border border-slate-200 text-sm">
              <thead>
                <tr class="sticky top-0 z-10 bg-slate-100">
                  <th class="border border-slate-200 px-2 py-2 text-center">
                    <input
                      type="checkbox"
                      :checked="selecionadosMatriz.length > 0 && selecionadosMatriz.length === matrizItens.length"
                      @change="toggleSelecionarTodosMatriz"
                    >
                  </th>
                  <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Item</th>
                  <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Descrição</th>
                  <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Maior preço</th>
                  <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Menor preço</th>
                  <th class="border border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Último preço</th>
                  <th class="border border-slate-200 px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-600">Evolução</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in matrizItens"
                  :key="row.catalogo_id"
                  class="odd:bg-white even:bg-slate-50/80"
                  :class="{ 'ring-1 ring-blue-400': itemMatrizSelecionado?.catalogo_id === row.catalogo_id }"
                >
                  <td class="border border-slate-200 px-2 py-2 text-center">
                    <input
                      v-model="selecionadosMatriz"
                      type="checkbox"
                      :value="row.catalogo_id"
                    >
                  </td>
                  <td class="border border-slate-200 px-3 py-2 font-mono text-xs">{{ row.catalogo_id }}</td>
                  <td
                    class="border border-slate-200 px-3 py-2"
                    :title="row.descricao"
                  >
                    {{ truncarTexto(row.descricao, 72) }}
                  </td>
                  <td class="border border-slate-200 px-3 py-2">
                    <div class="font-medium text-slate-800">{{ formatarMoeda(parseMoney(row.maior_valor)) }}</div>
                    <div class="text-xs text-slate-500">{{ formatarProcessoData(row.maior_ano, row.maior_sequencial, row.maior_data_publicacao) }}</div>
                  </td>
                  <td class="border border-slate-200 px-3 py-2">
                    <div class="font-medium text-slate-800">{{ formatarMoeda(parseMoney(row.menor_valor)) }}</div>
                    <div class="text-xs text-slate-500">{{ formatarProcessoData(row.menor_ano, row.menor_sequencial, row.menor_data_publicacao) }}</div>
                  </td>
                  <td class="border border-slate-200 px-3 py-2">
                    <div class="font-medium text-slate-800">{{ formatarMoeda(parseMoney(row.ultimo_valor)) }}</div>
                    <div class="text-xs text-slate-500">{{ formatarProcessoData(row.ultimo_ano, row.ultimo_sequencial, row.ultimo_data_publicacao) }}</div>
                  </td>
                  <td class="border border-slate-200 px-3 py-2 text-center">
                    <button
                      type="button"
                      class="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1"
                      @click="verEvolucaoMatriz(row)"
                    >
                      Ver evolução
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-semibold text-slate-800">
              Evolução de preço do item da matriz
            </h3>
            <label class="text-xs font-semibold uppercase tracking-wide text-slate-600">
              Modo de análise
              <select
                v-model="modoEvolucaoMatriz"
                class="ml-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 sm:text-sm"
              >
                <option value="semantica">Identificação semântica (consolidado)</option>
                <option value="id_exata">ID exata (uma linha por compra/processo)</option>
              </select>
            </label>
          </div>
          <div
            v-if="!itemMatrizSelecionado"
            class="rounded border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
          >
            Clique em <strong>Ver evolução</strong> em uma linha da matriz.
          </div>
          <div
            v-else-if="carregandoHistoricoItemMatriz"
            class="rounded bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
          >
            Carregando evolução do item...
          </div>
          <div
            v-else-if="historicoItemMatriz.length === 0"
            class="rounded border border-slate-100 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600"
          >
            Nenhum histórico encontrado para este item.
          </div>
          <div v-else>
            <p class="mb-3 text-xs text-slate-500">
              Item {{ itemMatrizSelecionado.catalogo_id }} · {{ truncarTexto(itemMatrizSelecionado.descricao, 120) }}
            </p>
            <div
              v-if="grupoSemanticoMatriz"
              class="mb-4 rounded-md border border-blue-100 bg-blue-50/60 p-3 text-xs text-slate-700"
            >
              <p class="font-semibold text-blue-900">
                Grupo semântico identificado (informativo)
              </p>
              <p class="mt-1 text-slate-600">
                Produto master {{ grupoSemanticoMatriz.catalogoId }} ·
                {{ grupoSemanticoMatriz.totalRegistrosHistorico }} registro(s) no histórico carregado ·
                {{ grupoSemanticoMatriz.totalProcessosRelacionados }} processo(s) relacionado(s).
              </p>
              <div class="mt-2">
                <p class="mb-1 font-semibold text-slate-700">Processos relacionados no histórico</p>
                <ul class="max-h-24 space-y-1 overflow-auto pr-1">
                  <li
                    v-for="proc in grupoSemanticoMatriz.processosRelacionados"
                    :key="`grupo-matriz-proc-${proc.chave}`"
                    class="rounded bg-white/80 px-2 py-1 text-[11px]"
                  >
                    {{ proc.rotulo }}
                  </li>
                  <li
                    v-if="grupoSemanticoMatriz.processosRelacionados.length === 0"
                    class="rounded bg-white/80 px-2 py-1 text-[11px] text-slate-500"
                  >
                    Sem processos correlatos carregados para este grupo.
                  </li>
                </ul>
              </div>
            </div>
            <Apexchart
              type="area"
              height="300"
              :options="optionsEvolucaoItemMatriz"
              :series="seriesEvolucaoItemMatriz"
            />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
