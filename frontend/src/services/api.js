import axios from 'axios'

/**
 * Homologação/produção: SPA e API no mesmo domínio (Apache faz proxy de /api → Gunicorn).
 * Desenvolvimento (Vite): API costuma estar em :8001 no mesmo hostname.
 */
function resolveApiBaseURL() {
  const explicit = import.meta.env.VITE_API_BASE_URL
  if (explicit) {
    return String(explicit).replace(/\/$/, '')
  }
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:8001/api'
  }
  if (import.meta.env.PROD) {
    return `${window.location.origin}/api`
  }
  const host = window.location.hostname
  return `http://${host}:8001/api`
}

const api = axios.create({
  baseURL: resolveApiBaseURL(),
  headers: {
    Accept: 'application/json',
  },
})

/**
 * Lista produtos do catálogo master (GET /catalogo).
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getCatalogo() {
  return api.get('/catalogo')
}

/**
 * Histórico de preços homologados para um produto do catálogo.
 * @param {number|string} catalogoId
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getHistoricoPrecos(catalogoId) {
  return api.get(`/catalogo/${catalogoId}/historico-precos`)
}

/**
 * Lista compras locais por ano (GET /compras/{ano}).
 * @param {number|string} ano
 * @param {number} [pagina=1]
 * @param {number} [tamanhoPagina=200]
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getComprasPorAno(ano, pagina = 1, tamanhoPagina = 200) {
  return api.get(`/compras/${ano}`, {
    params: {
      pagina,
      tamanho_pagina: tamanhoPagina,
    },
  })
}

/**
 * Lista itens de uma compra local (GET /compras/{ano}/{sequencial}/itens).
 * @param {number|string} ano
 * @param {number|string} sequencial
 * @param {number} [pagina=1]
 * @param {number} [tamanhoPagina=500]
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getItensCompra(ano, sequencial, pagina = 1, tamanhoPagina = 500) {
  return api.get(`/compras/${ano}/${sequencial}/itens`, {
    params: {
      pagina,
      tamanho_pagina: tamanhoPagina,
    },
  })
}

/**
 * Matriz consolidada do catálogo com maior/menor/último preço homologado.
 * @param {string} [q='']
 * @param {number} [pagina=1]
 * @param {number} [tamanhoPagina=500]
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getMatrizCatalogo(q = '', pagina = 1, tamanhoPagina = 500) {
  return api.get('/catalogo/matriz', {
    params: {
      q,
      pagina,
      tamanho_pagina: tamanhoPagina,
    },
  })
}
